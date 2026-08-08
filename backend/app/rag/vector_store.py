"""
向量库统一接口模块
封装向量库操作，支持Chroma和Milvus切换
设计模式：抽象基类 + 工厂模式
上层依赖抽象接口，切换向量库无需修改业务代码
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import logging
import uuid
import os

# ======================== 统一缓存路径配置 ========================
# 将所有第三方库（HuggingFace/Chroma/ONNX）的缓存
# 统一存放到项目的 data/cache 目录，避免占用C盘
_PROJECT_CACHE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "cache")
)
os.makedirs(_PROJECT_CACHE_DIR, exist_ok=True)

# 设置 HuggingFace 生态的缓存路径
os.environ["HF_HOME"] = _PROJECT_CACHE_DIR
os.environ["TRANSFORMERS_CACHE"] = os.path.join(_PROJECT_CACHE_DIR, "transformers")
os.environ["SENTENCE_TRANSFORMERS_HOME"] = os.path.join(_PROJECT_CACHE_DIR, "sentence_transformers")

# 关键：设置 HOME 环境变量以覆盖 Chroma 的默认缓存路径
# Chroma 硬编码使用 Path.home() / ".cache/chroma/onnx_models"
# 通过设置 HOME 指向项目缓存目录，可以把 Chroma 缓存重定向到非 C 盘
os.environ["HOME"] = _PROJECT_CACHE_DIR
# Windows 下同时设置 USERPROFILE 和 HOMEDRIVE/HOMEPATH
os.environ["USERPROFILE"] = _PROJECT_CACHE_DIR
os.environ["HOMEDRIVE"] = os.path.splitdrive(_PROJECT_CACHE_DIR)[0]
os.environ["HOMEPATH"] = _PROJECT_CACHE_DIR.replace(os.path.splitdrive(_PROJECT_CACHE_DIR)[0], "")

# 关闭 Chroma 遥测
os.environ["CHROMA_TELEMETRY_ENABLED"] = "false"

# 日志记录器
logger = logging.getLogger(__name__)


@dataclass
class Document:
    """
    文档数据类
    统一返回格式，包含文档内容和元数据
    """
    id: str
    content: str
    category: str
    score: float = 0.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class _ChromaEmbeddingWrapper:
    """
    Chroma 嵌入函数包装器
    将自定义的 EmbeddingModel（BGE）包装为 Chroma 兼容的接口
    这样 Chroma 就不需要下载默认的 ONNX 模型

    Chroma 的 EmbeddingFunction 接口需要实现：
    - __call__: 获取嵌入向量
    - name: 返回嵌入函数名称
    """

    def __init__(self, embedding_model):
        """
        初始化包装器

        参数：
            embedding_model: 我们的 EmbeddingModel 实例
        """
        self._model = embedding_model

    def __call__(self, input: List[str]) -> List[List[float]]:
        """
        Chroma 调用此方法获取嵌入向量

        参数：
            input: 文本列表

        返回：
            嵌入向量列表
        """
        return self._model.embed(input)

    @staticmethod
    def name() -> str:
        """返回嵌入函数名称"""
        return "bge_embedding_wrapper"


class BaseVectorStore(ABC):
    """
    向量库抽象基类

    定义统一接口，上层依赖抽象而非具体实现
    切换向量库无需修改业务代码

    接口规范：
        add: 添加文档向量
        search: 相似度检索
        delete: 删除文档
        clear: 清空向量库
        count: 文档数量
    """

    @abstractmethod
    def add(self, texts: List[str], metadatas: Optional[List[Dict]] = None) -> List[str]:
        """
        添加文档向量

        参数：
            texts: 文本列表
            metadatas: 元数据列表（可选）

        返回：
            文档ID列表
        """
        ...

    @abstractmethod
    def search(self, query: str, top_k: int = 5, category: str = None) -> List[Document]:
        """
        相似度检索

        参数：
            query: 查询文本
            top_k: 返回数量
            category: 类别过滤（可选）

        返回：
            按相似度排序的文档列表
        """
        ...

    @abstractmethod
    def delete(self, ids: List[str]) -> None:
        """
        删除文档

        参数：
            ids: 文档ID列表
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """清空向量库"""
        ...

    @abstractmethod
    def count(self) -> int:
        """
        获取文档数量

        返回：
            文档总数
        """
        ...

    def list_documents(self, limit: int = 500) -> List[Dict[str, Any]]:
        """
        列出向量库中的文档（按文件聚合）

        参数：
            limit: 最多返回的记录数

        返回：
            文档摘要列表；默认实现返回空列表
        """
        return []


import chromadb
from chromadb.config import Settings

class ChromaVectorStore(BaseVectorStore):
    """
    Chroma向量库实现（开发环境）
    """

    def __init__(self, persist_dir: str = "./data/chroma", embedding_model=None):
        """
        初始化Chroma向量库

        参数：
            persist_dir: 持久化目录
            embedding_model: 外部嵌入模型（可选）
        """

        self.persist_dir = persist_dir
        self.embedding_model = embedding_model

        # 创建Chroma客户端
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(
                anonymized_telemetry=False  # 关闭匿名遥测
            )
        )

        # 创建自定义嵌入函数包装器，避免Chroma下载默认的ONNX模型
        # 如果提供了外部嵌入模型（BGE），使用包装器
        # 否则使用一个简单的伪嵌入函数（避免ONNX下载）
        if embedding_model is not None:
            chroma_embedding_func = _ChromaEmbeddingWrapper(embedding_model)
        else:
            # 如果没有外部模型，使用一个简单的占位符函数
            # 注意：这会导致Chroma无法自动向量化，需要调用方手动传递embeddings
            class _PlaceholderEmbedding:
                def __call__(self, input: List[str]) -> List[List[float]]:
                    # 返回零向量作为占位符
                    return [[0.0] * 512 for _ in input]

                @staticmethod
                def name() -> str:
                    return "placeholder_embedding"
            chroma_embedding_func = _PlaceholderEmbedding()

        # 优先复用已有集合，只有 embedding_function 不兼容时才重建，避免重启清空知识库
        try:
            self.collection = self.client.get_or_create_collection(
                name="diet_knowledge",
                embedding_function=chroma_embedding_func
            )
        except Exception:
            try:
                self.client.delete_collection(name="diet_knowledge")
                self.collection = self.client.get_or_create_collection(
                    name="diet_knowledge",
                    embedding_function=chroma_embedding_func
                )
            except Exception as e:
                logger.error(f"Chroma集合初始化失败: {e}")
                raise

        logger.info(f"Chroma向量库初始化完成: {persist_dir}")

    def add(self, texts: List[str], metadatas: Optional[List[Dict]] = None) -> List[str]:
        """
        添加文档向量到Chroma

        参数：
            texts: 文本列表
            metadatas: 元数据列表

        返回：
            文档ID列表
        """
        # 生成唯一ID
        ids = [str(uuid.uuid4()) for _ in texts]

        # 如果提供了外部嵌入模型，先向量化
        embeddings = None
        if self.embedding_model is not None:
            embeddings = self.embedding_model.embed(texts)

        # 添加到Chroma集合
        self.collection.add(
            documents=texts,
            metadatas=metadatas if metadatas else None,
            ids=ids,
            embeddings=embeddings
        )

        logger.info(f"Chroma添加文档: {len(texts)}条")
        return ids

    def search(self, query: str, top_k: int = 5, category: str = None) -> List[Document]:
        """
        相似度检索

        参数：
            query: 查询文本
            top_k: 返回数量
            category: 类别过滤

        返回：
            文档列表
        """
        # 构建过滤条件
        where = None
        if category:
            where = {"category": category}

        # 如果提供了外部嵌入模型，先向量化查询
        query_embedding = None
        if self.embedding_model is not None:
            query_embedding = self.embedding_model.embed_single(query, is_query=True)

        # 执行检索
        results = self.collection.query(
            query_texts=[query] if query_embedding is None else None,
            query_embeddings=[query_embedding] if query_embedding is not None else None,
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        # 转换为统一的Document格式
        documents = []
        for i in range(len(results["ids"][0])):
            doc_id = results["ids"][0][i]
            content = results["documents"][0][i]

            # 安全获取metadata（可能为None或空列表）
            metadata = {}
            if results["metadatas"] and results["metadatas"][0]:
                meta_item = results["metadatas"][0][i]
                if meta_item is not None:
                    metadata = meta_item

            distance = results["distances"][0][i] if results["distances"] and results["distances"][0] else 1.0

            # Chroma返回的是距离，需要转换为相似度（1 - distance）
            # 余弦距离：相似度 = 1 - 距离
            score = 1.0 - distance

            # 从metadata中提取category
            doc_category = metadata.get("category", "") if metadata else ""

            documents.append(Document(
                id=doc_id,
                content=content,
                category=doc_category,
                score=score,
                metadata=metadata
            ))

        logger.info(f"Chroma检索完成: 查询'{query}', 返回{len(documents)}条结果")
        return documents

    def delete(self, ids: List[str]) -> None:
        """
        删除文档

        参数：
            ids: 文档ID列表
        """
        self.collection.delete(ids=ids)
        logger.info(f"Chroma删除文档: {len(ids)}条")

    def clear(self) -> None:
        """清空向量库"""
        # 删除并重建集合
        self.client.delete_collection(name="diet_knowledge")
        self.collection = self.client.get_or_create_collection(
            name="diet_knowledge",
            embedding_function=None
        )
        logger.info("Chroma向量库已清空")

    def count(self) -> int:
        """
        获取文档数量

        返回：
            文档总数
        """
        return self.collection.count()

    def list_documents(self, limit: int = 500) -> List[Dict[str, Any]]:
        """
        列出知识库文档，按 file_name + category 聚合为一份文档。

        返回：
            [{
                "id": 首个chunk的id,
                "title": 文件名,
                "category": 文档类别,
                "chunk_count": 分块数,
                "doc_ids": 全部chunk id（删除时使用）,
                "preview": 首个chunk内容预览
            }]
        """
        try:
            data = self.collection.get(
                include=["metadatas", "documents"],
                limit=limit
            )
            ids = data.get("ids") or []
            contents = data.get("documents") or []
            metadatas = data.get("metadatas") or []

            groups: Dict[str, Dict[str, Any]] = {}
            for doc_id, content, meta in zip(ids, contents, metadatas):
                meta = meta or {}
                file_name = meta.get("file_name") or meta.get("source") or doc_id
                category = meta.get("category") or "未分类"
                key = f"{file_name}\0{category}"
                group = groups.setdefault(key, {
                    "file_name": file_name,
                    "category": category,
                    "chunk_count": 0,
                    "doc_ids": [],
                    "preview": "",
                })
                group["chunk_count"] += 1
                group["doc_ids"].append(doc_id)
                if not group["preview"] and content:
                    group["preview"] = content[:120]

            documents = []
            for group in groups.values():
                documents.append({
                    "id": group["doc_ids"][0],
                    "title": group["file_name"],
                    "category": group["category"],
                    "chunk_count": group["chunk_count"],
                    "doc_ids": group["doc_ids"],
                    "preview": group["preview"],
                })
            return documents
        except Exception as e:
            logger.error(f"列出知识库文档失败: {e}")
            return []


class MilvusVectorStore(BaseVectorStore):
    """
    Milvus向量库实现（生产环境）

    """

    def __init__(self, host: str = "localhost", port: int = 19530,
                 collection_name: str = "diet_knowledge", embedding_model=None):
        """
        初始化Milvus向量库

        参数：
            host: Milvus服务地址
            port: Milvus服务端口
            collection_name: 集合名称
            embedding_model: 外部嵌入模型
        """
        try:
            from pymilvus import connections, Collection, utility
            from pymilvus import FieldSchema, CollectionSchema, DataType
        except ImportError:
            raise ImportError("需要安装 pymilvus 库: pip install pymilvus")

        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.embedding_model = embedding_model

        # 连接Milvus
        connections.connect(alias="default", host=host, port=port)

        # 获取向量维度
        if embedding_model is not None:
            self.dim = embedding_model.dim
        else:
            self.dim = 512  # 默认维度

        # 定义字段
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.dim)
        ]

        # 创建集合（如果不存在）
        if not utility.has_collection(collection_name):
            schema = CollectionSchema(fields=fields, description="膳食知识库")
            self.collection = Collection(name=collection_name, schema=schema)

            # 创建索引
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 1024}
            }
            self.collection.create_index(field_name="embedding", index_params=index_params)
            logger.info(f"Milvus集合创建完成: {collection_name}")
        else:
            self.collection = Collection(name=collection_name)
            logger.info(f"Milvus集合加载完成: {collection_name}")

        # 加载集合到内存
        self.collection.load()

    def add(self, texts: List[str], metadatas: Optional[List[Dict]] = None) -> List[str]:
        """
        添加文档向量到Milvus

        参数：
            texts: 文本列表
            metadatas: 元数据列表

        返回：
            文档ID列表
        """
        # 生成唯一ID
        ids = [str(uuid.uuid4()) for _ in texts]

        # 向量化
        embeddings = self.embedding_model.embed(texts)

        # 提取category
        categories = []
        if metadatas:
            for meta in metadatas:
                categories.append(meta.get("category", ""))
        else:
            categories = [""] * len(texts)

        # 构建插入数据
        entities = [
            ids,
            texts,
            categories,
            embeddings
        ]

        # 插入数据
        self.collection.insert(entities)
        self.collection.flush()

        logger.info(f"Milvus添加文档: {len(texts)}条")
        return ids

    def search(self, query: str, top_k: int = 5, category: str = None) -> List[Document]:
        """
        相似度检索

        参数：
            query: 查询文本
            top_k: 返回数量
            category: 类别过滤

        返回：
            文档列表
        """
        # 向量化查询
        query_embedding = self.embedding_model.embed_single(query, is_query=True)

        # 构建过滤条件
        expr = None
        if category:
            expr = f'category == "{category}"'

        # 执行检索
        search_params = {
            "metric_type": "COSINE",
            "params": {"nprobe": 10}
        }

        results = self.collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            expr=expr,
            output_fields=["content", "category"]
        )

        # 转换为统一的Document格式
        documents = []
        for hit in results[0]:
            doc_id = hit.id
            content = hit.entity.get("content")
            doc_category = hit.entity.get("category", "")
            score = hit.score  # Milvus返回的是相似度（余弦相似度）

            documents.append(Document(
                id=doc_id,
                content=content,
                category=doc_category,
                score=score,
                metadata={"category": doc_category}
            ))

        logger.info(f"Milvus检索完成: 查询'{query}', 返回{len(documents)}条结果")
        return documents

    def delete(self, ids: List[str]) -> None:
        """
        删除文档

        参数：
            ids: 文档ID列表
        """
        expr = f'id in [{",".join([f"{id_}" for id_ in ids])}]'
        self.collection.delete(expr)
        self.collection.flush()
        logger.info(f"Milvus删除文档: {len(ids)}条")

    def clear(self) -> None:
        """清空向量库"""
        from pymilvus import utility
        self.collection.release()
        utility.drop_collection(self.collection_name)
        logger.info(f"Milvus集合已删除: {self.collection_name}")

    def count(self) -> int:
        """
        获取文档数量

        返回：
            文档总数
        """
        return self.collection.num_entities


def create_vector_store(store_type: str, embedding_model=None, **kwargs) -> BaseVectorStore:
    """
    工厂函数：根据配置创建向量库实例

    参数：
        store_type: 向量库类型（chroma/milvus）
        embedding_model: 嵌入模型（可选）
        **kwargs: 向量库初始化参数

    返回：
        向量库实例

    使用示例：
        # 创建Chroma向量库
        chroma_store = create_vector_store("chroma", persist_dir="./data/chroma")

        # 创建Milvus向量库
        milvus_store = create_vector_store("milvus", host="localhost", port=19530)
    """
    if store_type.lower() == "chroma":
        return ChromaVectorStore(embedding_model=embedding_model, **kwargs)
    elif store_type.lower() == "milvus":
        return MilvusVectorStore(embedding_model=embedding_model, **kwargs)
    else:
        raise ValueError(f"不支持的向量库类型: {store_type}, 支持类型: chroma/milvus")


# ======================== 文件内自测脚本 ========================
# 运行方式：在 backend/app 目录下执行  python -m rag.vector_store
if __name__ == "__main__":
    print("=" * 60)
    print("向量库统一接口自测开始")
    print("=" * 60)

    # ---------- 测试1：Chroma向量库基本操作 ----------
    print("\n--- 测试Chroma向量库 ---")
    
    # 创建Chroma向量库实例
    chroma_store = create_vector_store("chroma", persist_dir="./data/chroma_test")

    # 测试清空
    chroma_store.clear()
    assert chroma_store.count() == 0, "清空后文档数量不为0"
    print("[通过] 测试1.1 - 清空向量库: count=0")

    # 测试添加文档
    test_texts = ["苹果富含维生素C，每天吃一个有益健康", "香蕉含有丰富的钾元素，有助于维持心脏健康"]
    test_metadatas = [{"category": "营养学"}, {"category": "营养学"}]
    doc_ids = chroma_store.add(test_texts, test_metadatas)
    assert len(doc_ids) == 2, f"添加文档数量错误: 期望2, 实际{len(doc_ids)}"
    assert chroma_store.count() == 2, f"添加后文档数量错误: 期望2, 实际{chroma_store.count()}"
    print(f"[通过] 测试1.2 - 添加文档: {len(doc_ids)}条, count={chroma_store.count()}")

    # 测试检索
    results = chroma_store.search("水果营养", top_k=2)
    assert len(results) == 2, f"检索结果数量错误: 期望2, 实际{len(results)}"
    assert all(isinstance(r, Document) for r in results), "检索结果类型错误"
    assert results[0].score >= results[1].score, "检索结果未按相似度排序"
    print(f"[通过] 测试1.3 - 相似度检索: 返回{len(results)}条, 最高分={results[0].score:.4f}")

    # 测试类别过滤检索
    results_filtered = chroma_store.search("水果", top_k=2, category="营养学")
    assert len(results_filtered) > 0, "类别过滤检索未返回结果"
    assert all(r.category == "营养学" for r in results_filtered), "类别过滤未生效"
    print(f"[通过] 测试1.4 - 类别过滤检索: 返回{len(results_filtered)}条")

    # 测试删除文档
    chroma_store.delete(doc_ids[:1])
    assert chroma_store.count() == 1, f"删除后文档数量错误: 期望1, 实际{chroma_store.count()}"
    print(f"[通过] 测试1.5 - 删除文档: count={chroma_store.count()}")

    # 清理测试数据
    chroma_store.clear()

    # ---------- 测试2：工厂函数创建向量库 ----------
    print("\n--- 测试工厂函数 ---")
    store = create_vector_store("chroma", persist_dir="./data/chroma_factory")
    assert isinstance(store, BaseVectorStore), "工厂函数未返回BaseVectorStore子类"
    assert isinstance(store, ChromaVectorStore), "工厂函数返回类型错误"
    print("[通过] 测试2 - 工厂函数创建Chroma向量库")

    # ---------- 测试3：Document数据类 ----------
    print("\n--- 测试Document数据类 ---")
    doc = Document(id="test123", content="测试内容", category="测试")
    assert doc.id == "test123"
    assert doc.content == "测试内容"
    assert doc.category == "测试"
    assert doc.score == 0.0
    assert doc.metadata == {}
    print("[通过] 测试3 - Document数据类")

    print("\n" + "=" * 60)
    print("向量库统一接口自测全部通过（3/3）")
    print("=" * 60)
