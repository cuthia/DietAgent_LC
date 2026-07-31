"""
路由聚合模块 - 统一注册所有API路由
创建总路由 APIRouter,统一路径,并聚合所有子路由

路由结构：
    /api/user/*        - 用户模块接口
    /api/chat/*        - 对话Agent模块接口
    /api/knowledge/*   - 知识库管理接口
    /api/agent/*       - 膳食搭配Agent接口（第三阶段新增）
"""

from fastapi import APIRouter

# 导入各模块路由
from .user import router as user_router
from .chat import router as chat_router
from .knowledge import router as knowledge_router
from .agent import router as agent_router

# 创建总路由，设置统一路径 /api
api_router = APIRouter(prefix="/api")

# 注册子路由到总路由
api_router.include_router(user_router)
api_router.include_router(chat_router)
api_router.include_router(knowledge_router)
api_router.include_router(agent_router)
