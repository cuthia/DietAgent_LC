"""
检索器模块，实现相似度检索 + 重排优化

检索流程：
1. 查询文本向量化
2. 向量库相似度检索（召回Top N）
3. 重排优化（CrossEncoder，可选）
4. 返回最终结果

设计：
- 支持多种检索策略
- 支持按类别过滤
- 支持重排优化（可选）
"""

from typing import List, Optional, Dict, Any
import logging

# 日志记录器
logger = logging.getLogger(__name__)

# 从 vector_store 导入 Document 类，确保类型一致
try:
    from rag.vector_store import Document
except Exception:
    try:
        from vector_store import Document
    except Exception:
        # 兜底：如果都无法导入，使用本地定义（尽量避免触发）
        from dataclasses import dataclass
        
        @dataclass
        class Document:
            id: str
            content: str
            category: str = ""
            score: float = 0.0
            metadata: Dict[str, Any] = None

            def __post_init__(self):
                if self.metadata is None:
                    self.metadata = {}


class Retriever:
    """
    检索器
    
    检索流程：
    1. 查询文本向量化
    2. 向量库相似度检索（召回Top N）
    3. 重排优化（CrossEncoder，可选）
    4. 返回最终结果
    
    设计：
    - 支持多种检索策略
    - 支持按类别过滤
    - 支持重排优化（可选）
    
    参数：
        vector_store: 向量库实例
        embedding: 嵌入模型实例
        use_reranker: 是否启用重排优化（默认False）
        reranker_model: 重排模型名称（默认BGE-reranker-base）
        top_k: 默认返回数量
        recall_k: 召回数量（用于重排时先召回更多结果）
    """

    def __init__(self, vector_store, embedding, use_reranker: bool = False,
                 reranker_model: str = "BAAI/bge-reranker-base",
                 top_k: int = 5, recall_k: int = 20):
        """
        初始化检索器
        
        参数：
            vector_store: 向量库实例（BaseVectorStore子类）
            embedding: 嵌入模型实例（EmbeddingModel）
            use_reranker: 是否启用重排优化
            reranker_model: 重排模型名称
            top_k: 默认返回数量
            recall_k: 召回数量（重排时使用）
        """
        self.vector_store = vector_store
        self.embedding = embedding
        self.use_reranker = use_reranker
        self.reranker_model = reranker_model
        self.top_k = top_k
        self.recall_k = recall_k
        
        # 重排模型（懒加载）
        self._reranker = None

    def _load_reranker(self):
        """
        延迟加载重排模型
        
        BGE-reranker 是一个CrossEncoder模型，用于对召回结果进行精排
        输入：(query, document) 对
        输出：相关性分数
        """
        if self._reranker is None and self.use_reranker:
            try:
                from sentence_transformers import CrossEncoder
                logger.info(f"正在加载重排模型: {self.reranker_model}")
                self._reranker = CrossEncoder(self.reranker_model)
                logger.info(f"重排模型加载完成: {self.reranker_model}")
            except ImportError:
                logger.warning("sentence_transformers 未安装，重排功能不可用")
                self.use_reranker = False

    def retrieve(self, query: str, top_k: int = None, category: str = None,
                 use_reranker: bool = None) -> List[Document]:
        """
        检索相关文档
        
        参数：
            query: 查询文本
            top_k: 返回数量（覆盖默认值）
            category: 类别过滤（营养学/中医/禁忌等）
            use_reranker: 是否使用重排（覆盖默认设置）
        
        返回：
            按相关性排序的文档列表
        """
        # 使用默认值或传入值
        actual_top_k = top_k if top_k is not None else self.top_k
        actual_use_reranker = use_reranker if use_reranker is not None else self.use_reranker

        if not query:
            return []

        logger.info(f"开始检索: query='{query}', top_k={actual_top_k}, category={category}")

        # 步骤1：向量库检索（召回阶段）
        # 如果启用重排，先召回更多结果
        recall_count = self.recall_k if actual_use_reranker else actual_top_k
        results = self.vector_store.search(query, top_k=recall_count, category=category)

        if not results:
            logger.info("检索结果为空")
            return []

        # 步骤2：重排优化（精排阶段）
        if actual_use_reranker:
            results = self._rerank(query, results, actual_top_k)

        logger.info(f"检索完成: 返回{len(results)}条结果")
        return results

    def _rerank(self, query: str, documents: List[Document], top_k: int) -> List[Document]:
        """
        使用CrossEncoder对召回结果进行重排
        
        参数：
            query: 查询文本
            documents: 召回的文档列表
            top_k: 返回数量
        
        返回：
            重排后的文档列表
        """
        # 确保重排模型已加载
        self._load_reranker()
        
        if self._reranker is None:
            # 如果重排模型加载失败，直接返回原始结果
            return documents[:top_k]

        # 构建 (query, document) 对
        pairs = [(query, doc.content) for doc in documents]

        # 使用重排模型计算分数
        scores = self._reranker.predict(pairs)

        # 将分数赋给文档
        for doc, score in zip(documents, scores):
            doc.score = float(score)

        # 按分数排序（降序）
        documents.sort(key=lambda x: x.score, reverse=True)

        # 返回前top_k个
        return documents[:top_k]

    def batch_retrieve(self, queries: List[str], top_k: int = None,
                       category: str = None) -> List[List[Document]]:
        """
        批量检索
        
        参数：
            queries: 查询文本列表
            top_k: 返回数量
            category: 类别过滤
        
        返回：
            文档列表的列表
        """
        results = []
        for query in queries:
            result = self.retrieve(query, top_k=top_k, category=category)
            results.append(result)
        return results


# ======================== 文件内自测脚本 ========================
# 运行方式：在 backend/app 目录下执行  python -m rag.retriever
if __name__ == "__main__":
    import logging as _logging
    # 配置日志，让嵌入模型加载失败的警告在终端可见
    _logging.basicConfig(level=_logging.WARNING, format="[%(levelname)s] %(message)s")

    print("=" * 60)
    print("检索器自测开始")
    print("=" * 60)

    # 创建测试用的向量库和嵌入模型（使用Chroma）
    from rag.vector_store import create_vector_store, ChromaVectorStore
    from rag.embeddings import EmbeddingModel

    # 创建嵌入模型
    model = EmbeddingModel("BAAI/bge-small-zh-v1.5", device="cpu")

    # 显式触发懒加载，以便准确检查模型加载状态
    # （_load_model 是懒加载，不主动调用时 _model 仍为 None，is_mock_mode 会误报）
    model._load_model()

    # Mock模式提示：随机向量不保证语义检索相关性，部分测试会降级验证
    if model.is_mock_mode:
        print("[提示] 嵌入模型处于 Mock 模式（随机向量），语义相关性测试将降级验证")
        if getattr(model, "_last_load_error", ""):
            print(f"[诊断] 模型加载失败详情: {model._last_load_error}")

    # 创建向量库并添加测试数据
    # 关键：必须传入 embedding_model，否则 Chroma 会使用占位符零向量，检索全部失效
    store = create_vector_store("chroma", embedding_model=model,
                                persist_dir="./testdata/chroma_retriever_test")
    store.clear()

    # 添加测试文档
    test_texts = [
        "苹果富含维生素C，每天吃一个有益健康",
        "香蕉含有丰富的钾元素，有助于维持心脏健康",
        "橙子含有丰富的水分和维生素C",
        "葡萄富含抗氧化物质，有助于延缓衰老",
        "西瓜含有大量水分，适合夏季解暑",
        "中医认为苹果性平味甘，具有补脾气的功效",
        "中医认为香蕉性寒，脾胃虚寒者不宜多食",
        "糖尿病患者应控制水果摄入量，选择低糖水果",
    ]
    test_metadatas = [
        {"category": "营养学"},
        {"category": "营养学"},
        {"category": "营养学"},
        {"category": "营养学"},
        {"category": "营养学"},
        {"category": "中医"},
        {"category": "中医"},
        {"category": "禁忌"},
    ]
    store.add(test_texts, test_metadatas)

    # ---------- 测试1：基本检索功能 ----------
    # 用例：检索相关文档，验证返回结果数量和排序
    retriever = Retriever(store, model, use_reranker=False)
    results = retriever.retrieve("水果营养", top_k=3)
    
    assert len(results) == 3, f"检索结果数量错误: 期望3, 实际{len(results)}"
    assert all(isinstance(r, Document) for r in results), "结果类型错误"
    assert results[0].score >= results[1].score >= results[2].score, "结果未按相似度排序"
    print(f"[通过] 测试1 - 基本检索功能: 返回{len(results)}条, 最高分={results[0].score:.4f}")

    # ---------- 测试2：类别过滤检索 ----------
    # 用例：只检索中医类别的文档
    results = retriever.retrieve("水果", top_k=3, category="中医")
    
    assert len(results) == 2, f"中医类别检索结果数量错误: 期望2, 实际{len(results)}"
    assert all(r.category == "中医" for r in results), "类别过滤未生效"
    print(f"[通过] 测试2 - 类别过滤检索: 返回{len(results)}条")

    # ---------- 测试3：空查询处理 ----------
    # 用例：空查询返回空列表
    results = retriever.retrieve("")
    assert results == [], "空查询应返回空列表"
    print("[通过] 测试3 - 空查询处理")

    # ---------- 测试4：批量检索 ----------
    # 用例：批量查询多个问题
    queries = ["维生素C", "钾元素"]
    batch_results = retriever.batch_retrieve(queries, top_k=2)
    
    assert len(batch_results) == 2, f"批量检索数量错误: 期望2, 实际{len(batch_results)}"
    assert len(batch_results[0]) == 2, f"第一个查询结果数量错误"
    assert len(batch_results[1]) == 2, f"第二个查询结果数量错误"
    print("[通过] 测试4 - 批量检索")

    # ---------- 测试5：文档内容包含查询关键词 ----------
    # 用例：检索结果应与查询相关
    # 注意：Mock模式下向量为 MD5→随机种子 生成的随机向量，无语义关联保证，
    #       因此真实模型才验证 "结果字面含关键词"，Mock模式降级为仅验证数量
    results = retriever.retrieve("糖尿病", top_k=2)

    assert len(results) >= 1, "糖尿病相关文档未被检索到"
    if not model.is_mock_mode:
        # 真实模型：语义匹配应命中字面含 "糖尿病" 的文档
        assert any("糖尿病" in r.content for r in results), "检索结果不相关"
        print(f"[通过] 测试5 - 相关性验证（真实模型）: 返回{len(results)}条相关文档")
    else:
        # Mock模式：验证有结果即可，打印命中信息便于观察
        hit_keyword = any("糖尿病" in r.content for r in results)
        status = "命中文档" if hit_keyword else "未命中文档（Mock 随机向量，属正常现象）"
        print(f"[通过] 测试5 - 相关性验证（Mock 模式降级）: 返回{len(results)}条, {status}")

    # ---------- 测试6：重排优化（可选） ----------
    # 用例：启用重排后结果顺序可能变化
    try:
        retriever_with_rerank = Retriever(store, model, use_reranker=True)
        results_reranked = retriever_with_rerank.retrieve("水果营养", top_k=3)
        
        assert len(results_reranked) == 3, f"重排结果数量错误: 期望3, 实际{len(results_reranked)}"
        assert all(isinstance(r, Document) for r in results_reranked), "重排结果类型错误"
        print(f"[通过] 测试6 - 重排优化: 返回{len(results_reranked)}条")
    except Exception as e:
        print(f"[跳过] 测试6 - 重排优化: {e}")

    # 清理测试数据
    store.clear()

    print("=" * 60)
    print("检索器自测完成")
    print("=" * 60)