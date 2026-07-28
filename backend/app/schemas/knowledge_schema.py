"""
知识库相关数据模型
定义请求和响应的数据结构

使用 Pydantic 进行数据校验和序列化
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


# ======================== 请求模型 ========================

class KnowledgeUploadRequest(BaseModel):
    """
    上传文档请求模型
    
    参数：
        file: 上传的文件
        category: 文档类别（营养学/中医/禁忌/食谱等）
    """
    category: str = Field(description="文档类别", default="营养学")


class KnowledgeBatchUploadRequest(BaseModel):
    """
    批量上传文档请求模型
    
    参数：
        dir_path: 目录路径
        category: 文档类别（可选）
    """
    dir_path: str = Field(description="目录路径")
    category: Optional[str] = Field(None, description="文档类别")


class KnowledgeSearchRequest(BaseModel):
    """
    知识库检索请求模型
    
    参数：
        query: 查询文本
        top_k: 返回数量（1-20）
        category: 类别过滤（可选）
    """
    query: str = Field(description="查询文本", min_length=1)
    top_k: int = Field(5, ge=1, le=20, description="返回数量")
    category: Optional[str] = Field(None, description="类别过滤")



# ======================== 响应模型 ========================

class KnowledgeDocumentResponse(BaseModel):
    """
    知识库文档响应模型（单个文档）
    
    参数：
        id: 文档ID
        content: 文档内容
        category: 文档类别
        score: 相似度分数（0-1）
        metadata: 元数据
    """
    id: str = Field(description="文档ID")
    content: str = Field(description="文档内容")
    category: str = Field(description="文档类别")
    score: float = Field(description="相似度分数")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class KnowledgeSearchResponse(BaseModel):
    """
    知识库多文档响应模型
    
    参数：
        documents: 返回的文档响应对象列表
        total: 返回的文档总数
    """
    documents: List[KnowledgeDocumentResponse] = Field(description="文档列表")
    total: int = Field(description="返回文档总数")


class KnowledgeStatsResponse(BaseModel):
    """
    知识库状态统计响应模型
    
    参数：
        total_count: 总文档数
        category_counts: 各类别文档数
    """
    total_count: int = Field(description="总文档数")
    category_counts: Dict[str, int] = Field(description="各类别文档数")


class KnowledgeUploadResponse(BaseModel):
    """
    上传文档响应模型
    
    参数：
        success: 是否成功
        message: 提示信息
        doc_ids: 上传的文档ID列表
        count: 上传数量
    """
    success: bool = Field(description="是否成功")
    message: str = Field(description="提示信息")
    doc_ids: List[str] = Field(description="上传的文档ID列表")
    count: int = Field(description="上传数量")


class KnowledgeDeleteResponse(BaseModel):
    """
    删除文档响应模型
    
    参数：
        success: 是否成功
        message: 提示信息
        deleted_ids: 删除的文档ID列表
        count: 删除数量
    """
    success: bool = Field(description="是否成功")
    message: str = Field(description="提示信息")
    deleted_ids: List[str] = Field(description="删除的文档ID列表")
    count: int = Field(description="删除数量")


class KnowledgeClearResponse(BaseModel):
    """
    清空知识库响应模型
    
    参数：
        success: 是否成功
        message: 提示信息
        cleared_count: 清空的文档数量
    """
    success: bool = Field(description="是否成功")
    message: str = Field(description="提示信息")
    cleared_count: int = Field(description="清空的文档数量")


# ======================== 文件内自测脚本 ========================
# 运行方式：在 backend/app 目录下执行  python -m schemas.knowledge_schema
if __name__ == "__main__":
    print("=" * 60)
    print("知识库数据模型自测开始")
    print("=" * 60)

    # ---------- 测试1：搜索请求模型校验 ----------
    # 用例：正确参数通过校验
    req = KnowledgeSearchRequest(query="糖尿病饮食", top_k=5)
    assert req.query == "糖尿病饮食"
    assert req.top_k == 5
    assert req.category is None
    print("[通过] 测试1 - 搜索请求模型校验")

    # ---------- 测试2：搜索请求模型 - top_k边界值 ----------
    # 用例：top_k在1-20范围内
    req = KnowledgeSearchRequest(query="测试", top_k=1)
    assert req.top_k == 1
    req = KnowledgeSearchRequest(query="测试", top_k=20)
    assert req.top_k == 20
    print("[通过] 测试2 - top_k边界值校验")

    # ---------- 测试3：文档响应模型 ----------
    # 用例：创建文档响应对象
    doc = KnowledgeDocumentResponse(
        id="test123",
        content="苹果富含维生素C",
        category="营养学",
        score=0.95,
        metadata={"source": "test"}
    )
    assert doc.id == "test123"
    assert doc.content == "苹果富含维生素C"
    assert doc.category == "营养学"
    assert doc.score == 0.95
    assert doc.metadata["source"] == "test"
    print("[通过] 测试3 - 文档响应模型")

    # ---------- 测试4：搜索响应模型 ----------
    # 用例：创建搜索响应对象
    docs = [doc]
    search_resp = KnowledgeSearchResponse(documents=docs, total=1)
    assert len(search_resp.documents) == 1
    assert search_resp.total == 1
    print("[通过] 测试4 - 搜索响应模型")

    # ---------- 测试5：统计响应模型 ----------
    # 用例：创建统计响应对象
    stats = KnowledgeStatsResponse(
        total_count=100,
        category_counts={"营养学": 50, "中医": 30, "禁忌": 20}
    )
    assert stats.total_count == 100
    assert stats.category_counts["营养学"] == 50
    assert stats.category_counts["中医"] == 30
    assert stats.category_counts["禁忌"] == 20
    print("[通过] 测试5 - 统计响应模型")

    # ---------- 测试6：上传响应模型 ----------
    # 用例：创建上传响应对象
    upload_resp = KnowledgeUploadResponse(
        success=True,
        message="上传成功",
        doc_ids=["id1", "id2"],
        count=2
    )
    assert upload_resp.success is True
    assert upload_resp.count == 2
    assert len(upload_resp.doc_ids) == 2
    print("[通过] 测试6 - 上传响应模型")

    # ---------- 测试7：模型序列化 ----------
    # 用例：模型转换为字典
    data = doc.model_dump()
    assert isinstance(data, dict)
    assert data["id"] == "test123"
    print("[通过] 测试7 - 模型序列化")

    print("=" * 60)
    print("知识库数据模型自测全部通过（7/7）")
    print("=" * 60)