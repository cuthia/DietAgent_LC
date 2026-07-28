"""
知识库管理模块路由 - 提供文档上传、检索、删除、统计接口
路由前缀：/api/knowledge

接口列表：
    POST    /api/knowledge/upload      - 上传文档
    POST    /api/knowledge/batch       - 批量上传目录下文档
    GET     /api/knowledge/search      - 知识库检索
    DELETE  /api/knowledge/{doc_id}    - 删除指定文档
    DELETE  /api/knowledge/clear       - 清空知识库
    GET     /api/knowledge/stats       - 获取知识库统计
"""

from fastapi import APIRouter, Depends, File, UploadFile, Query, Path
from typing import Optional, List

# 导入服务层
from services.knowledge_service import KnowledgeService

# 导入数据模型
from schemas.knowledge_schema import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeDocumentResponse,
    KnowledgeStatsResponse,
    KnowledgeUploadResponse,
    KnowledgeDeleteResponse,
    KnowledgeClearResponse
)

# 导入认证依赖
from api.dependencies import get_current_user
from db.models.user import User

# 创建路由实例，设置前缀和标签
router = APIRouter(prefix="/knowledge", tags=["知识库管理"])

# 获取知识库服务实例
knowledge_service = KnowledgeService()


@router.post("/upload", summary="上传文档")
async def upload_document(
    file: UploadFile = File(description="上传的文件"),
    category: str = Query("营养学", description="文档类别"),
    current_user: User = Depends(get_current_user)
):
    """
    上传文档并向量化入库
    
    参数：
        file: 上传的文件（支持 .txt, .md, .pdf, .docx）
        category: 文档类别（营养学/中医/禁忌/食谱等）
    
    返回：
        上传结果
    """
    # 读取文件内容
    content = await file.read()
    
    # 调用服务层上传
    result = knowledge_service.upload_document(content, file.filename, category)
    
    # 返回响应
    return KnowledgeUploadResponse(
        success=result["success"],
        message=result["message"],
        doc_ids=result["doc_ids"],
        count=result["count"]
    )


@router.post("/batch", summary="批量上传")
async def batch_upload(
    dir_path: str = Query(description="目录路径"),
    category: Optional[str] = Query(None, description="文档类别"),
    current_user: User = Depends(get_current_user)
):
    """
    批量上传目录下的文档
    
    参数：
        dir_path: 目录路径
        category: 文档类别（可选）
    
    返回：
        上传结果
    """
    # 调用服务层批量上传
    result = knowledge_service.batch_upload(dir_path, category)
    
    # 返回响应
    return KnowledgeUploadResponse(
        success=result["success"],
        message=result["message"],
        doc_ids=result.get("doc_ids", []),
        count=result.get("chunk_count", 0)
    )


@router.get("/search", summary="知识库检索")
async def search_knowledge(
    query: str = Query(description="查询文本"),
    top_k: int = Query(5, ge=1, le=20, description="返回数量"),
    category: Optional[str] = Query(None, description="类别过滤"),
    current_user: User = Depends(get_current_user)
):
    """
    知识库检索 - 根据查询文本检索相关文档
    
    参数：
        query: 查询文本
        top_k: 返回数量（1-20）
        category: 类别过滤（可选）
    
    返回：
        检索结果列表
    """
    # 调用服务层检索
    result = knowledge_service.search(query, top_k=top_k, category=category)
    
    # 转换为响应格式
    documents = []
    for doc in result["documents"]:
        documents.append(KnowledgeDocumentResponse(
            id=doc["id"],
            content=doc["content"],
            category=doc["category"],
            score=doc["score"],
            metadata=doc["metadata"]
        ))
    
    # 返回响应
    return KnowledgeSearchResponse(
        documents=documents,
        total=result["total"]
    )


@router.delete("/{doc_id}", summary="删除文档")
async def delete_document(
    doc_id: str = Path(description="文档ID"),
    current_user: User = Depends(get_current_user)
):
    """
    删除指定文档
    
    参数：
        doc_id: 文档ID
    
    返回：
        删除结果
    """
    # 调用服务层删除
    result = knowledge_service.delete_documents([doc_id])
    
    # 返回响应
    return KnowledgeDeleteResponse(
        success=result["success"],
        message=result["message"],
        deleted_ids=result["deleted_ids"],
        count=result["count"]
    )


@router.delete("/clear", summary="清空知识库")
async def clear_knowledge_base(
    current_user: User = Depends(get_current_user)
):
    """
    清空知识库中的所有文档
    
    返回：
        清空结果
    """
    # 调用服务层清空
    result = knowledge_service.clear_knowledge_base()
    
    # 返回响应
    return KnowledgeClearResponse(
        success=result["success"],
        message=result["message"],
        cleared_count=result["cleared_count"]
    )


@router.get("/stats", summary="知识库统计")
async def get_knowledge_stats(
    current_user: User = Depends(get_current_user)
):
    """
    获取知识库统计信息
    
    返回：
        统计信息（总文档数、各类别文档数）
    """
    # 调用服务层获取统计
    result = knowledge_service.get_stats()
    
    # 返回响应
    return KnowledgeStatsResponse(
        total_count=result["total_count"],
        category_counts=result["category_counts"]
    )


# ======================== 文件内自测脚本 ========================
# 运行方式：在 backend/app 目录下执行  python -m api.routers.knowledge
if __name__ == "__main__":
    print("=" * 60)
    print("知识库路由自测开始")
    print("=" * 60)

    # ---------- 测试1：API路由定义 ----------
    # 用例：验证路由基本结构
    assert router.prefix == "/knowledge", f"路由前缀错误: {router.prefix}"
    assert len(router.routes) == 6, f"路由数量错误: 期望6, 实际{len(router.routes)}"
    print("[通过] 测试1 - API路由定义")

    # ---------- 测试2：知识服务实例创建 ----------
    # 用例：验证服务实例能正常创建
    assert knowledge_service is not None, "知识库服务实例为None"
    print("[通过] 测试2 - 知识库服务实例创建")

    # ---------- 测试3：文档响应模型 ----------
    # 用例：创建文档响应对象
    doc = KnowledgeDocumentResponse(
        id="test123",
        content="测试内容",
        category="营养学",
        score=0.95,
        metadata={"source": "test"}
    )
    assert doc.id == "test123"
    assert doc.score == 0.95
    print("[通过] 测试3 - 文档响应模型")

    # ---------- 测试4：搜索响应模型 ----------
    # 用例：创建搜索响应对象
    docs = [doc]
    search_resp = KnowledgeSearchResponse(documents=docs, total=1)
    assert len(search_resp.documents) == 1
    assert search_resp.total == 1
    print("[通过] 测试4 - 搜索响应模型")

    print("=" * 60)
    print("知识库路由自测全部通过（4/4）")
    print("=" * 60)