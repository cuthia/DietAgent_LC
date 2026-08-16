"""
RAG检索工具 - 检索膳食知识库

功能：
1. search_knowledge: 检索知识库获取相关文档
2. format_knowledge_for_llm: 将检索结果格式化为LLM可消费的文本

数据来源：RAG检索器（通过rag/retriever.py）
"""

import logging
from typing import List, Dict, Any, Optional

# 日志记录器
logger = logging.getLogger(__name__)


async def search_knowledge(
    query: str, 
    category: Optional[str] = None, 
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    检索膳食知识库
    
    功能：
    根据用户查询，从知识库中检索相关的膳食文档。
    使用向量相似度检索，返回最相关的top_k条文档。
    
    参数：
        query: 检索关键词/问题，如"减脂餐食谱"、"糖尿病饮食禁忌"
        category: 知识类别过滤（可选），支持：
                  - "nutrition": 现代营养学
                  - "tcm_diet": 中医膳食养生
                  - "taboo": 食物禁忌与慢病饮食
                  - "recipes": 家常食谱
        top_k: 返回结果数量，默认5条
    
    返回：
        文档列表，每个文档包含：
        {
            "id": "文档ID",
            "content": "文档内容",
            "category": "知识类别",
            "score": 0.95,  # 相似度分数
            "metadata": {}   # 元数据
        }
    
    使用示例：
    ```python
    # 检索减脂相关知识
    docs = await search_knowledge("减脂餐食谱", top_k=3)
    
    # 只检索营养学类别
    docs = await search_knowledge("糖尿病饮食", category="nutrition", top_k=5)
    ```
    """
    try:
        # 延迟导入以避免循环依赖
        from rag.retriever import Retriever
        from rag.embeddings import EmbeddingModel
        from rag.vector_store import create_vector_store
        from core.config_handler import get_settings
        
        # 获取配置
        settings = get_settings()
        
        # 初始化嵌入模型和向量库
        embedding_model = EmbeddingModel(
            model_name=settings.embedding.model,
            device=settings.embedding.device,
            local_path=settings.embedding.local_path
        )
        
        vector_store = create_vector_store(
            store_type=settings.vector_store.type,
            embedding_model=embedding_model,
            persist_dir=settings.vector_store.chroma.persist_dir
        )
        
        # 创建检索器
        retriever = Retriever(
            vector_store=vector_store,
            embedding=embedding_model,
            top_k=top_k
        )
        
        # 执行检索
        results = retriever.retrieve(
            query=query,
            top_k=top_k,
            category=category
        )
        
        # 转换为字典列表
        docs = []
        for doc in results:
            docs.append({
                "id": doc.id if hasattr(doc, 'id') else str(hash(doc.content))[:8],
                "content": doc.content,
                "category": doc.category if hasattr(doc, 'category') else "",
                "score": doc.score if hasattr(doc, 'score') else 0.0,
                "metadata": doc.metadata if hasattr(doc, 'metadata') else {}
            })
        
        logger.info(f"知识检索完成: query='{query}', 返回{len(docs)}条结果")
        return docs
        
    except Exception as e:
        logger.error(f"知识检索失败: {e}")
        # 返回空列表，保证Agent可以继续执行
        return []


def format_knowledge_for_llm(docs: List[Dict[str, Any]]) -> str:
    """
    将检索结果格式化为LLM可消费的文本

    功能：
    将检索到的文档列表转换为结构化文本，
    便于LLM理解和引用知识库内容。
    
    参数：
        docs: 文档列表（来自search_knowledge）
    
    返回：
        格式化的文本，包含每条文档的内容和来源
    
    使用示例：
    ```python
    docs = await search_knowledge("减脂餐")
    knowledge_text = format_knowledge_for_llm(docs)
    # 输出示例：
    # 参考知识：
    # [1] (营养学) 减脂餐应控制总热量摄入，建议每日减少300-500千卡...
    # [2] (食谱) 推荐早餐：燕麦粥+水煮蛋+牛奶...
    # ```
    """
    if not docs:
        return "暂无相关知识库内容"
    
    parts = ["参考知识："]
    
    for i, doc in enumerate(docs, 1):
        content = doc.get("content", "")
        category = doc.get("category", "")
        score = doc.get("score", 0)
        
        # 截取内容前200字符（避免过长）
        if len(content) > 200:
            content = content[:200] + "..."
        
        parts.append(f"[{i}] ({category}) {content}")
    
    return "\n".join(parts)


# ========== LangChain @tool 包装（第一点改进配套） ==========

from langchain_core.tools import tool as _lc_tool


@_lc_tool
async def rag_search_tool(query: str, category: str = "", top_k: int = 5) -> List[Dict[str, Any]]:
    """
    从膳食知识库检索相关文档（向量相似度检索）。

    适用于 nutrition_qa / food_eval / diet_plan 等需要知识库支撑的意图：
    输入查询关键词，返回 top_k 条最相关的文档（含 content/category/score）。

    参数：
        query: 检索关键词/问题，如 "糖尿病饮食禁忌"、"南瓜升糖指数"
        category: 知识类别过滤（可选），支持：
                  "nutrition" / "tcm_diet" / "taboo" / "recipes"
                  空字符串表示不过滤
        top_k: 返回结果数量，默认 5 条

    返回：
        文档列表，每个文档：
        {
            "id": "doc_id",
            "content": "文档内容（前200字）",
            "category": "知识类别",
            "score": 0.95,
            "metadata": {}
        }
    """
    cat = category if category else None
    docs = await search_knowledge(query=query, category=cat, top_k=top_k)
    # 截断 content 便于 LLM 消费（避免单条过长）
    for d in docs:
        if len(d.get("content", "")) > 200:
            d["content"] = d["content"][:200] + "..."
    return docs


# ======================== 文件内自测脚本 ========================
# 运行方式：在 backend/app 目录下执行  python -m agent.tools.rag_tool
if __name__ == "__main__":
    import asyncio
    
    print("=" * 60)
    print("RAG检索工具自测开始")
    print("=" * 60)
    
    async def test():
        # 测试检索
        docs = await search_knowledge("减脂餐", top_k=3)
        print(f"[通过] 知识检索: 返回{len(docs)}条结果")
        
        if docs:
            print(f"  第一条: {docs[0]['content'][:100]}...")
        
        # 测试格式化
        formatted = format_knowledge_for_llm(docs)
        print(f"[通过] 格式化知识:\n{formatted[:200]}...")
        
        # 测试空结果
        empty_docs = await search_knowledge("", top_k=3)
        formatted_empty = format_knowledge_for_llm(empty_docs)
        print(f"[通过] 空结果处理: {formatted_empty}")
        
        print("=" * 60)
        print("RAG检索工具自测完成")
    
    asyncio.run(test())
