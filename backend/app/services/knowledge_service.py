"""
知识库业务逻辑层
整合所有RAG模块，提供统一的业务接口

职责：
1. 文档上传、分块、向量化、入库的完整流程
2. 知识库检索（含类别过滤、重排优化）
3. 文档删除、清空
4. 知识库统计

设计模式：Facade模式（对外提供统一入口）
"""

from typing import List, Optional, Dict, Any
import logging
from pathlib import Path
import tempfile
import os

# 导入RAG模块
from rag.embeddings import EmbeddingModel
from rag.vector_store import create_vector_store, BaseVectorStore
from rag.document_loader import DocumentLoader
from rag.text_splitter import TextSplitter
from rag.retriever import Retriever
from rag.vector_store import Document as RAGDocument

# 导入配置
from core.config_api import settings

# 日志记录器
logger = logging.getLogger(__name__)


class KnowledgeService:
    """
    知识库业务逻辑类
    
    设计模式：Facade模式
    对外提供统一入口，内部整合多个RAG模块
    
    初始化流程：
    1. 根据配置创建嵌入模型
    2. 根据配置创建向量库
    3. 创建文档加载器和文本分块器
    4. 创建检索器
    """

    _instance = None

    def __new__(cls):
        """单例模式：确保全局只有一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化知识库服务"""
        if hasattr(self, '_initialized'):
            return

        logger.info("正在初始化知识库服务...")

        # 1. 创建嵌入模型
        self.embedding_model = EmbeddingModel(
            model_name=settings.embedding.model,
            device=settings.embedding.device
        )

        # 2. 创建向量库
        # 根据配置的向量库类型只传递对应实现需要的参数，避免透传不相关参数
        store_kwargs = {}
        if settings.vector_store.type.lower() == "chroma":
            store_kwargs["persist_dir"] = settings.vector_store.chroma.persist_dir
        elif settings.vector_store.type.lower() == "milvus":
            store_kwargs["host"] = settings.vector_store.milvus.host
            store_kwargs["port"] = settings.vector_store.milvus.port
            store_kwargs["collection_name"] = settings.vector_store.milvus.collection_name

        self.vector_store = create_vector_store(
            store_type=settings.vector_store.type,
            embedding_model=self.embedding_model,
            **store_kwargs
        )

        # 3. 创建文档加载器
        self.document_loader = DocumentLoader()

        # 4. 创建文本分块器
        self.text_splitter = TextSplitter(
            chunk_size=500,
            chunk_overlap=50
        )

        # 5. 创建检索器
        self.retriever = Retriever(
            vector_store=self.vector_store,
            embedding=self.embedding_model,
            use_reranker=False,
            top_k=5
        )

        self._initialized = True
        logger.info("知识库服务初始化完成")

    def upload_document(self, file_content: bytes, filename: str, category: str = "营养学") -> Dict[str, Any]:
        """
        上传文档并入库
        
        流程：
        1. 将文件内容保存到临时文件
        2. 加载文档（根据扩展名解析）
        3. 文本分块
        4. 向量化并入库
        
        参数：
            file_content: 文件内容（字节）
            filename: 文件名（含扩展名）
            category: 文档类别
        
        返回：
            上传结果字典
        """
        logger.info(f"开始上传文档: {filename}, category={category}")

        # 创建临时文件
        ext = Path(filename).suffix
        with tempfile.NamedTemporaryFile(mode="wb", suffix=ext, delete=False) as f:
            f.write(file_content)
            temp_path = f.name

        try:
            # 加载文档
            doc = self.document_loader.load(temp_path, category=category)

            # 文本分块
            split_docs = self.text_splitter.split_document(doc)

            # 准备向量化的数据
            texts = [sd.content for sd in split_docs]
            metadatas = [
                {
                    "category": sd.category,
                    "original_id": sd.metadata.get("original_id", ""),
                    "chunk_index": sd.metadata.get("chunk_index", 0),
                    "total_chunks": sd.metadata.get("total_chunks", 1),
                    "file_name": sd.metadata.get("file_name", filename),
                    "source": "upload"
                }
                for sd in split_docs
            ]

            # 向量化并入库
            doc_ids = self.vector_store.add(texts, metadatas)

            logger.info(f"文档上传完成: {filename}, 分块数={len(split_docs)}, 入库ID数={len(doc_ids)}")

            return {
                "success": True,
                "message": f"上传成功，共{len(doc_ids)}个文档块",
                "doc_ids": doc_ids,
                "count": len(doc_ids),
                "original_filename": filename,
                "category": category
            }

        except Exception as e:
            logger.error(f"文档上传失败: {filename}, 错误: {e}")
            return {
                "success": False,
                "message": f"上传失败: {str(e)}",
                "doc_ids": [],
                "count": 0,
                "original_filename": filename,
                "category": category
            }

        finally:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def batch_upload(self, dir_path: str, category: str = None) -> Dict[str, Any]:
        """
        批量上传目录下的文档
        
        参数：
            dir_path: 目录路径
            category: 文档类别（可选）
        
        返回：
            上传结果字典
        """
        logger.info(f"开始批量上传: {dir_path}, category={category}")

        try:
            # 加载目录下所有文档
            docs = self.document_loader.load_directory(dir_path, category=category)

            if not docs:
                return {
                    "success": False,
                    "message": "目录下没有找到支持的文档",
                    "total_count": 0
                }

            # 分块所有文档
            all_split_docs = []
            for doc in docs:
                split_docs = self.text_splitter.split_document(doc)
                all_split_docs.extend(split_docs)

            # 准备向量化的数据
            texts = [sd.content for sd in all_split_docs]
            metadatas = [
                {
                    "category": sd.category,
                    "original_id": sd.metadata.get("original_id", ""),
                    "chunk_index": sd.metadata.get("chunk_index", 0),
                    "total_chunks": sd.metadata.get("total_chunks", 1),
                    "file_name": sd.metadata.get("file_name", ""),
                    "source": "batch_upload"
                }
                for sd in all_split_docs
            ]

            # 向量化并入库
            doc_ids = self.vector_store.add(texts, metadatas)

            logger.info(f"批量上传完成: {len(docs)}个文件, {len(all_split_docs)}个文档块")

            return {
                "success": True,
                "message": f"批量上传成功，共{len(docs)}个文件，{len(doc_ids)}个文档块",
                "doc_ids": doc_ids,
                "file_count": len(docs),
                "chunk_count": len(doc_ids),
                "category": category
            }

        except Exception as e:
            logger.error(f"批量上传失败: {dir_path}, 错误: {e}")
            return {
                "success": False,
                "message": f"批量上传失败: {str(e)}",
                "total_count": 0
            }

    def search(self, query: str, top_k: int = 5, category: str = None) -> Dict[str, Any]:
        """
        知识库检索
        
        参数：
            query: 查询文本
            top_k: 返回数量
            category: 类别过滤（可选）
        
        返回：
            检索结果字典
        """
        logger.info(f"开始检索: query='{query}', top_k={top_k}, category={category}")

        try:
            # 使用检索器进行检索
            results = self.retriever.retrieve(query, top_k=top_k, category=category)

            # 转换为响应格式
            documents = []
            for doc in results:
                documents.append({
                    "id": doc.id,
                    "content": doc.content,
                    "category": doc.category,
                    "score": doc.score,
                    "metadata": doc.metadata
                })

            return {
                "success": True,
                "message": "检索成功",
                "documents": documents,
                "total": len(documents)
            }

        except Exception as e:
            logger.error(f"检索失败: query='{query}', 错误: {e}")
            return {
                "success": False,
                "message": f"检索失败: {str(e)}",
                "documents": [],
                "total": 0
            }

    def delete_documents(self, doc_ids: List[str]) -> Dict[str, Any]:
        """
        删除指定文档
        
        参数：
            doc_ids: 文档ID列表
        
        返回：
            删除结果字典
        """
        logger.info(f"开始删除文档: {len(doc_ids)}个ID")

        try:
            # 删除文档
            self.vector_store.delete(doc_ids)

            return {
                "success": True,
                "message": f"成功删除{len(doc_ids)}个文档",
                "deleted_ids": doc_ids,
                "count": len(doc_ids)
            }

        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            return {
                "success": False,
                "message": f"删除失败: {str(e)}",
                "deleted_ids": [],
                "count": 0
            }

    def clear_knowledge_base(self) -> Dict[str, Any]:
        """
        清空知识库
        
        返回：
            清空结果字典
        """
        logger.info("开始清空知识库")

        try:
            # 获取当前文档数量
            count = self.vector_store.count()

            # 清空向量库
            self.vector_store.clear()

            return {
                "success": True,
                "message": f"知识库已清空，共删除{count}个文档",
                "cleared_count": count
            }

        except Exception as e:
            logger.error(f"清空知识库失败: {e}")
            return {
                "success": False,
                "message": f"清空失败: {str(e)}",
                "cleared_count": 0
            }

    def get_stats(self) -> Dict[str, Any]:
        """
        获取知识库统计信息
        
        返回：
            统计信息字典
        """
        logger.info("获取知识库统计信息")

        try:
            # 获取总文档数
            total_count = self.vector_store.count()

            # 获取类别统计（需要查询向量库中的所有文档）
            # 这里简化处理，返回总文档数
            # 在实际应用中，可以通过查询向量库的metadata来获取类别统计
            category_counts = {}

            return {
                "success": True,
                "message": "获取统计信息成功",
                "total_count": total_count,
                "category_counts": category_counts
            }

        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                "success": False,
                "message": f"获取统计信息失败: {str(e)}",
                "total_count": 0,
                "category_counts": {}
            }


# ======================== 文件内自测脚本 ========================
# 运行方式：在 backend/app 目录下执行  python -m services.knowledge_service
if __name__ == "__main__":
    print("=" * 60)
    print("知识库业务逻辑自测开始")
    print("=" * 60)

    # 创建知识库服务实例
    service = KnowledgeService()

    # ---------- 测试1：上传文档 ----------
    # 用例：上传简单的文本内容
    test_content = "苹果富含维生素C，每天吃一个有益健康。香蕉含有丰富的钾元素，有助于维持心脏健康。"
    result = service.upload_document(test_content.encode("utf-8"), "test.txt", category="营养学")
    
    assert result["success"] is True, f"上传失败: {result['message']}"
    assert result["count"] > 0, "上传数量为0"
    assert len(result["doc_ids"]) == result["count"], "文档ID数量不匹配"
    print(f"[通过] 测试1 - 上传文档: {result['count']}个文档块")

    # ---------- 测试2：检索文档 ----------
    # 用例：检索刚刚上传的文档
    result = service.search("水果营养", top_k=3)
    
    assert result["success"] is True, f"检索失败: {result['message']}"
    assert result["total"] > 0, "检索结果为空"
    assert all("content" in doc for doc in result["documents"]), "文档缺少content字段"
    print(f"[通过] 测试2 - 检索文档: 返回{result['total']}条结果")

    # ---------- 测试3：获取统计信息 ----------
    # 用例：获取知识库统计
    result = service.get_stats()
    
    assert result["success"] is True, f"获取统计失败: {result['message']}"
    assert result["total_count"] > 0, "文档数量为0"
    print(f"[通过] 测试3 - 获取统计信息: 总文档数={result['total_count']}")

    # ---------- 测试4：删除文档 ----------
    # 用例：删除指定文档
    result_search = service.search("水果营养", top_k=1)
    if result_search["total"] > 0:
        doc_id = result_search["documents"][0]["id"]
        result_delete = service.delete_documents([doc_id])
        
        assert result_delete["success"] is True, f"删除失败: {result_delete['message']}"
        assert result_delete["count"] == 1, "删除数量错误"
        print("[通过] 测试4 - 删除文档")
    else:
        print("[跳过] 测试4 - 删除文档（没有可删除的文档）")

    # ---------- 测试5：清空知识库 ----------
    # 用例：清空知识库
    result = service.clear_knowledge_base()
    
    assert result["success"] is True, f"清空失败: {result['message']}"
    print(f"[通过] 测试5 - 清空知识库: 删除{result['cleared_count']}个文档")

    # 验证清空后文档数量为0
    result = service.get_stats()
    assert result["total_count"] == 0, "清空后文档数量不为0"
    print("[通过] 测试6 - 验证清空结果")

    print("=" * 60)
    print("知识库业务逻辑自测完成")
    print("=" * 60)