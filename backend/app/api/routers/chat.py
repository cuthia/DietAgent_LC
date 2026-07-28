"""
对话Agent模块路由 - 提供与膳食助手的对话接口

路由前缀：/api/v1/chat

当前阶段：第一阶段开发，模拟返回，后续替换为真实LangGraph Agent逻辑
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from schemas.common_schema import ApiResponse
from api.dependencies import get_current_user
from db.models.user import User


# 创建路由实例，设置前缀和标签
router = APIRouter(prefix="/chat", tags=["对话Agent模块"])


class ChatRequest(BaseModel):
    """
    对话请求模型

    message: 用户发送的消息内容
    session_id: 会话ID（可选，用于多轮对话上下文管理）
    """
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    """
    对话响应模型
    
    reply: Agent返回的回复内容  
    session_id: 当前会话ID
    """
    reply: str
    session_id: str


@router.post("/send", response_model=ApiResponse[ChatResponse])
def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    """
    发送消息给膳食Agent
    
    message: 用户消息
    session_id: 会话ID（可选）
    
    依赖：get_current_user: 自动验证登录状态
    """
    # TODO: 后续替换为真实的LangGraph Agent调用逻辑
    # 当前为第一阶段模拟返回，验证接口通路
    mock_reply = f"收到你的消息：{req.message}，我是膳食助手，正在为你生成专属食谱~（接口已通，Agent逻辑开发中）"
    
    # 返回模拟响应
    return ApiResponse[ChatResponse](data=ChatResponse(
        reply=mock_reply,
        session_id=req.session_id or "test_session_001"
    ))