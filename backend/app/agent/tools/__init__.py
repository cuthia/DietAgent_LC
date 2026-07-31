"""
Agent工具集模块

提供膳食搭配Agent所需的各类工具：
- user_tool: 用户信息查询与更新
- rag_tool: RAG知识库检索
- validate_tool: 忌口与慢病校验
- region_tool: 地域饮食特点适配
"""

from agent.tools.user_tool import get_user_info, update_user_info, format_profile_for_prompt
from agent.tools.rag_tool import search_knowledge, format_knowledge_for_llm
from agent.tools.validate_tool import check_food_taboo, validate_diet_plan, get_recommended_foods
from agent.tools.region_tool import get_region_diet_features, adapt_diet_to_region

__all__ = [
    "get_user_info",
    "update_user_info",
    "format_profile_for_prompt",
    "search_knowledge",
    "format_knowledge_for_llm",
    "check_food_taboo",
    "validate_diet_plan",
    "get_recommended_foods",
    "get_region_diet_features",
    "adapt_diet_to_region",
]
