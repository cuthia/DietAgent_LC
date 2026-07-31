"""
Agent API路由 - 膳食搭配Agent的RESTful接口

路由列表：
- POST /agent/chat: 处理膳食咨询（同步）
- POST /agent/chat/stream: 处理膳食咨询（SSE流式）
- GET /agent/user/{user_id}/profile: 获取用户档案
- PUT /agent/user/{user_id}/profile: 更新用户档案
- GET /agent/user/{user_id}/history: 获取对话历史
- GET /agent/user/{user_id}/diet-history: 获取膳食方案历史
- DELETE /agent/user/{user_id}/history: 清空对话历史
- POST /agent/validate: 校验膳食方案


"""

import asyncio
import json
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from schemas.agent_schema import (
    ChatRequest,
    ChatResponse,
    UserProfileUpdate,
    UserProfileResponse,
    ChatHistoryResponse,
    DietHistoryResponse,
    ValidatePlanRequest,
    ValidationResult,
    BaseResponse,
    ErrorResponse,
    chat_response_from_result
)
from services.agent_service import AgentService, get_agent_service

# 日志记录器
logger = logging.getLogger(__name__)

# 创建路由
router = APIRouter(prefix="/agent", tags=["Agent"])


# ========== 辅助函数 ==========

async def _get_service() -> AgentService:
    """获取Agent服务实例"""
    return await get_agent_service()


# ========== 路由实现 ==========

@router.post(
    "/chat", 
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorResponse, "description": "请求参数错误"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"}
    },
    summary="处理膳食咨询（同步）",
    description="""
    用户向Agent发送膳食咨询请求，Agent处理后返回完整响应。
    
    处理流程：
    1. 收集用户健康信息
    2. 检索相关膳食知识
    3. 构建约束条件
    4. 生成膳食方案
    5. 校验方案合规性
    6. 返回结果
    
    如果用户信息不完善，会返回need_info=true，并给出追问消息。
    """
)
async def chat(request: ChatRequest):
    """
    处理膳食咨询（同步接口）
    
    传入ChatRequest对象，其中包含：
    - user_id: 用户ID
    - message: 用户消息（支持中英文）
    - session_id: 会话ID（可选）
    
    返回完整的膳食方案或追问消息
    """
    try:
        service = await _get_service()
        
        result = await service.chat(
            user_id=request.user_id,
            message=request.message,
            session_id=request.session_id
        )
        
        response = chat_response_from_result(result)
        
        if not response.success:
            logger.warning(f"Agent处理失败: {response.message}")
            raise HTTPException(
                status_code=500,
                detail=ErrorResponse(
                    success=False,
                    message=response.message,
                    error_code="AGENT_PROCESSING_ERROR"
                ).model_dump()
            )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat接口异常: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                success=False,
                message=f"服务器内部错误: {str(e)}",
                error_code="INTERNAL_ERROR"
            ).model_dump()
        )


@router.post(
    "/chat/stream",
    response_class=StreamingResponse,
    summary="处理膳食咨询（SSE流式）",
    description="""
    用户向Agent发送膳食咨询请求，Agent以SSE（Server-Sent Events）格式
    逐步返回处理进度和结果。
    
    前端可以实时展示处理进度，提升用户体验。
    
    SSE事件格式：
    ```
    data: {"stage": "collect_info", "status": "start", "message": "正在收集信息..."}
    
    data: {"stage": "output", "status": "complete", "message": "处理完成", "data": {...}}
    ```
    """
)
async def chat_stream(request: ChatRequest):
    """
    处理膳食咨询（SSE流式接口）
    
    逐步返回各环节的处理进度
    """
    async def event_generator():
        try:
            service = await _get_service()
            
            async for event in service.chat_stream(
                user_id=request.user_id,
                message=request.message,
                session_id=request.session_id
            ):
                # 转换为SSE格式
                if event.get("data"):
                    # 最后一个事件包含完整数据
                    data = chat_response_from_result(event["data"]).model_dump()
                    event["data"] = data
                
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            
            # 发送完成事件
            yield f"data: {json.dumps({'done': True})}\n\n"
            
        except Exception as e:
            logger.error(f"流式处理异常: {e}")
            error_event = {
                "stage": "error",
                "status": "error",
                "message": f"服务异常: {str(e)}"
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get(
    "/user/{user_id}/profile",
    response_model=UserProfileResponse,
    summary="获取用户健康档案",
    description="获取指定用户的完整健康档案信息"
)
async def get_user_profile(user_id: int):
    """
    获取用户健康档案
    """
    try:
        service = await _get_service()
        profile = await service.get_user_profile(user_id)
        
        if "error" in profile:
            raise HTTPException(
                status_code=500,
                detail=ErrorResponse(
                    success=False,
                    message=profile["error"]
                ).model_dump()
            )
        
        return profile
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取用户档案异常: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(success=False, message=str(e)).model_dump()
        )


@router.put(
    "/user/{user_id}/profile",
    response_model=BaseResponse,
    summary="更新用户健康档案",
    description="""
    更新指定用户的健康档案信息。
    
    支持更新的字段：
    - age: 年龄
    - gender: 性别
    - height: 身高(cm)
    - weight: 体重(kg)
    - chronic_disease: 慢性疾病
    - food_taboo: 食物忌口
    - taste_preference: 口味偏好
    - region: 所在地域
    - diet_goal: 膳食目标
    """
)
async def update_user_profile(user_id: int, updates: UserProfileUpdate):
    """
    更新用户健康档案
    """
    try:
        service = await _get_service()
        
        # 提取要更新的字段
        update_data = updates.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    success=False,
                    message="没有提供要更新的字段"
                ).model_dump()
            )
        
        # 确保user_id一致
        update_data["user_id"] = user_id
        
        result = await service.update_user_profile(user_id, update_data)
        
        if not result.get("success", True):
            raise HTTPException(
                status_code=500,
                detail=ErrorResponse(
                    success=False,
                    message=result.get("error", "更新失败")
                ).model_dump()
            )
        
        return BaseResponse(
            success=True,
            message="用户档案更新成功",
            data=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新用户档案异常: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(success=False, message=str(e)).model_dump()
        )


@router.get(
    "/user/{user_id}/history",
    response_model=ChatHistoryResponse,
    summary="获取对话历史",
    description="获取指定用户的历史对话记录"
)
async def get_chat_history(
    user_id: int, 
    max_messages: int = 20
):
    """
    获取对话历史
    
    - max_messages: 最大返回消息数（默认20条）
    """
    try:
        service = await _get_service()
        history = await service.get_chat_history(user_id, max_messages)
        
        messages = [
            {
                "role": msg.get("role", ""),
                "content": msg.get("content", ""),
                "timestamp": msg.get("timestamp")
            }
            for msg in history
        ]
        
        return ChatHistoryResponse(
            messages=messages,
            total=len(messages)
        )
        
    except Exception as e:
        logger.error(f"获取对话历史异常: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(success=False, message=str(e)).model_dump()
        )


@router.get(
    "/user/{user_id}/diet-history",
    response_model=DietHistoryResponse,
    summary="获取膳食方案历史",
    description="获取指定用户的历史膳食方案记录"
)
async def get_diet_history(
    user_id: int, 
    limit: int = 10
):
    """
    获取膳食方案历史
    
    - limit: 返回数量（默认10条）
    """
    try:
        service = await _get_service()
        history = await service.get_diet_history(user_id, limit)
        
        return DietHistoryResponse(
            plans=history,
            total=len(history)
        )
        
    except Exception as e:
        logger.error(f"获取膳食历史异常: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(success=False, message=str(e)).model_dump()
        )


@router.delete(
    "/user/{user_id}/history",
    response_model=BaseResponse,
    summary="清空对话历史",
    description="清空指定用户的所有对话历史记录"
)
async def clear_chat_history(
    user_id: int, 
    session_id: str = "default"
):
    """
    清空对话历史
    """
    try:
        service = await _get_service()
        result = await service.clear_history(user_id, session_id)
        
        return BaseResponse(
            success=True,
            message=result.get("message", "对话历史已清空")
        )
        
    except Exception as e:
        logger.error(f"清空对话历史异常: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(success=False, message=str(e)).model_dump()
        )


@router.post(
    "/validate",
    response_model=ValidationResult,
    summary="校验膳食方案",
    description="""
    校验膳食方案是否符合用户的健康要求。
    
    检查内容：
    1. 是否包含用户忌口食材
    2. 是否包含慢病禁忌食材
    3. 营养是否均衡
    
    返回校验结果和修正建议
    """
)
async def validate_plan(request: ValidatePlanRequest):
    """
    校验膳食方案
    """
    try:
        service = await _get_service()
        result = await service.validate_plan(
            request.user_id,
            request.diet_plan
        )
        
        if result.get("error"):
            raise HTTPException(
                status_code=500,
                detail=ErrorResponse(
                    success=False,
                    message=result["error"]
                ).model_dump()
            )
        
        return ValidationResult(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"校验膳食方案异常: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(success=False, message=str(e)).model_dump()
        )


@router.get(
    "/health",
    response_model=BaseResponse,
    summary="健康检查",
    description="检查Agent服务是否正常运行"
)
async def health_check():
    """
    健康检查接口
    """
    try:
        service = await _get_service()
        return BaseResponse(
            success=True,
            message="Agent服务运行正常",
            data={
                "service": "DietAgent",
                "status": "healthy",
                "initialized": service._initialized if hasattr(service, '_initialized') else True
            }
        )
    except Exception as e:
        return BaseResponse(
            success=False,
            message=f"服务异常: {str(e)}"
        )
