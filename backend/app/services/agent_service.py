"""
Agent业务服务 - 封装Agent的业务逻辑

功能：
1. AgentService: Agent业务服务类，提供统一的Agent调用接口
2. 处理与API层的交互，调用Agent Chain完成业务流程
3. 管理会话状态和异常处理

设计模式：
- 服务层模式：将业务逻辑与API层解耦
- 策略模式：支持不同的Agent处理策略
"""

import logging
from typing import Dict, Any, Optional, AsyncGenerator

from agent.chain import DietAgentChain
from agent.memory import MemoryManager, save_interaction
from agent.tools.user_tool import get_user_info, update_user_info
from agent.tools.validate_tool import validate_diet_plan

# 日志记录器
logger = logging.getLogger(__name__)


class AgentService:
    """
    Agent业务服务类
    
    提供膳食搭配Agent的统一调用接口，封装：
    1. Agent初始化和配置
    2. 会话管理
    3. 异常处理和日志记录
    4. 对话历史保存
    
    """
    
    def __init__(self):
        """初始化Agent服务"""
        self._agent: Optional[DietAgentChain] = None  # Agent Chain实例
        self._memory: Optional[MemoryManager] = None  # 记忆管理器
        self._initialized = False  # 是否初始化完成
        logger.info("AgentService初始化中...")
    
    async def initialize(self) -> None:
        """
        异步初始化Agent服务
        
        延迟初始化，避免在导入时加载LLM等重型资源
        """
        if self._initialized:
            return
        
        # 初始化Agent Chain
        self._agent = DietAgentChain()
        
        # 初始化记忆管理器
        self._memory = MemoryManager()
        
        self._initialized = True
        logger.info("AgentService初始化完成")
    
    # ========== 核心接口 ==========
    
    async def chat(
        self, 
        user_id: int, 
        message: str,
        session_id: str = "default"
    ) -> Dict[str, Any]:
        """
        处理用户的膳食咨询请求
        
        功能：
        1. 调用Agent处理用户消息
        2. 保存对话历史
        3. 返回处理结果
        
        参数：
            user_id: 用户ID
            message: 用户消息
            session_id: 会话ID
        
        返回：
            {
                "success": 是否成功,
                "need_info": 是否需要补充信息,
                "diet_plan": 膳食方案,
                "message": 回复消息,
                "processing_time_ms": 处理耗时
            }
        
        """
        try:
            # 确保初始化
            if not self._initialized:
                await self.initialize()
            
            # 调用Agent处理
            result = await self._agent.process(
                user_id=user_id,
                user_query=message
            )
            
            # 保存对话历史
            if self._memory:
                self._memory.add_message(
                    user_id=user_id,
                    message={"role": "user", "content": message},
                    session_id=session_id
                )
                if result.get("message"):
                    self._memory.add_message(
                        user_id=user_id,
                        message={"role": "assistant", "content": result["message"]},
                        session_id=session_id
                    )
            
            # 保存生成的膳食方案
            if result.get("diet_plan") and result.get("success"):
                if self._memory:
                    self._memory.save_diet_plan(user_id, result["diet_plan"])
            
            logger.info(f"[AgentService] 处理完成: user_id={user_id}")
            return result
            
        except Exception as e:
            logger.error(f"[AgentService] 处理异常: {e}")
            return {
                "success": False,
                "need_info": False,
                "diet_plan": None,
                "message": f"服务异常，请稍后重试。错误：{str(e)}",
                "processing_time_ms": 0
            }
    
    async def chat_stream(
        self, 
        user_id: int, 
        message: str,
        session_id: str = "default"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式处理用户请求（SSE/WebSocket场景）
        
        逐步返回各环节的处理进度，用于前端实时展示
        
        参数：
            user_id: 用户ID
            message: 用户消息
            session_id: 会话ID
        
        Yields:
            {
                "stage": 处理阶段,
                "status": start/complete/error,
                "message": 状态描述,
                "data": 最终数据（仅在最后一个事件）
            }
        """
        try:
            # 确保初始化
            if not self._initialized:
                await self.initialize()
            
            # 保存用户消息
            if self._memory:
                self._memory.add_message(
                    user_id=user_id,
                    message={"role": "user", "content": message},
                    session_id=session_id
                )
            
            # 流式处理
            result_data = None
            async for event in self._agent.process_stream(
                user_id=user_id,
                user_query=message
            ):
                # 保存最终结果
                if event.get("stage") == "output" and event.get("data"):
                    result_data = event["data"]
                    # 保存AI回复
                    if self._memory and result_data.get("message"):
                        self._memory.add_message(
                            user_id=user_id,
                            message={"role": "assistant", "content": result_data["message"]},
                            session_id=session_id
                        )
                    # 保存方案
                    if result_data.get("diet_plan"):
                        self._memory.save_diet_plan(user_id, result_data["diet_plan"])
                
                yield event
            
        except Exception as e:
            logger.error(f"[AgentService] 流式处理异常: {e}")
            yield {
                "stage": "error",
                "status": "error",
                "message": f"服务异常：{str(e)}"
            }
    
    # ========== 用户管理接口 ==========
    
    async def get_user_profile(self, user_id: int) -> Dict[str, Any]:
        """
        获取用户健康档案
        
        参数：
            user_id: 用户ID
        
        返回：
            用户健康档案
        """
        try:
            profile = await get_user_info(user_id)
            return profile
        except Exception as e:
            logger.error(f"[AgentService] 获取用户档案失败: {e}")
            return {"error": str(e)}
    
    async def update_user_profile(
        self, 
        user_id: int, 
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        更新用户健康档案
        
        参数：
            user_id: 用户ID
            updates: 要更新的字段
        
        返回：
            更新结果
        """
        try:
            result = await update_user_info(user_id, updates)
            if result:
                return {"success": True, "message": "用户档案更新成功", "data": updates}
            return {"success": False, "error": "用户档案更新失败"}
        except Exception as e:
            logger.error(f"[AgentService] 更新用户档案失败: {e}")
            return {"success": False, "error": str(e)}
    
    # ========== 历史查询接口 ==========
    
    async def get_chat_history(
        self, 
        user_id: int, 
        max_messages: int = 20,
        session_id: Optional[str] = None
    ) -> list:
        """
        获取用户的对话历史
        
        参数：
            user_id: 用户ID
            max_messages: 最大消息数
        
        返回：
            对话历史列表
        """
        if not self._memory:
            self._memory = MemoryManager()
        
        return self._memory.get_conversation(
            user_id,
            session_id=session_id,
            max_messages=max_messages
        )

    async def save_diet_plan(
        self,
        user_id: int,
        diet_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        手动保存一份膳食方案到历史
        """
        if not self._memory:
            self._memory = MemoryManager()
        self._memory.save_diet_plan(user_id, diet_plan)
        return {"success": True, "message": "膳食方案已保存"}
    
    async def get_diet_history(
        self, 
        user_id: int, 
        limit: int = 10
    ) -> list:
        """
        获取用户的膳食方案历史
        
        参数：
            user_id: 用户ID
            limit: 返回数量
        
        返回：
            膳食方案历史列表
        """
        if not self._memory:
            self._memory = MemoryManager()
        
        return self._memory.get_diet_history(user_id, limit=limit)
    
    async def clear_history(
        self, 
        user_id: int, 
        session_id: str = "default"
    ) -> Dict[str, Any]:
        """
        清空用户对话历史
        
        参数：
            user_id: 用户ID
            session_id: 会话ID
        
        返回：
            清空结果
        """
        if not self._memory:
            self._memory = MemoryManager()
        
        self._memory.clear_conversation(user_id, session_id)
        return {"success": True, "message": "对话历史已清空"}
    
    # ========== 方案校验接口 ==========
    
    async def validate_plan(
        self, 
        user_id: int, 
        diet_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        校验膳食方案是否符合用户要求
        
        参数：
            user_id: 用户ID
            diet_plan: 膳食方案
        
        返回：
            校验结果
        """
        try:
            profile = await get_user_info(user_id)
            result = validate_diet_plan(diet_plan, profile)
            return result
        except Exception as e:
            logger.error(f"[AgentService] 方案校验失败: {e}")
            return {"passed": False, "error": str(e)}


# ========== 单例模式 ==========

_service_instance: Optional[AgentService] = None


async def get_agent_service() -> AgentService:
    """
    获取Agent服务单例
    
    返回：
        AgentService实例
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = AgentService()
        await _service_instance.initialize()
    return _service_instance


# 同步版本（简化使用）
def get_agent_service_sync() -> AgentService:
    """获取Agent服务（同步，不等待初始化）"""
    global _service_instance
    if _service_instance is None:
        _service_instance = AgentService()
    return _service_instance


# ======================== 文件内自测脚本 ========================
if __name__ == "__main__":
    import asyncio
    
    async def test_service():
        print("=" * 60)
        print("AgentService 自测开始")
        print("=" * 60)
        
        # 创建服务实例
        service = AgentService()
        await service.initialize()
        print("[通过] 服务初始化完成")
        
        # 测试获取用户档案
        print("\n[测试] 获取用户档案...")
        profile = await service.get_user_profile(1)
        print(f"[通过] 用户档案: {profile.get('user_id')}")
        
        # 测试对话历史
        print("\n[测试] 获取对话历史...")
        history = await service.get_chat_history(1)
        print(f"[通过] 对话历史: {len(history)}条")
        
        # 测试膳食历史
        print("\n[测试] 获取膳食历史...")
        diet_history = await service.get_diet_history(1)
        print(f"[通过] 膳食历史: {len(diet_history)}条")
        
        print("\n" + "=" * 60)
        print("AgentService 自测完成")
    
    asyncio.run(test_service())
