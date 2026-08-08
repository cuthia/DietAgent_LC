"""
对话记忆管理模块 - 管理用户与Agent的对话历史

功能：
1. RedisMemory: 基于Redis的对话记忆（生产环境）
2. InMemoryStore: 基于内存的对话记忆（开发/测试环境）
3. MemoryManager: 记忆管理器，根据配置选择存储方式

记忆类型：
- 短期记忆：当前会话的对话历史（用于上下文理解）
- 长期记忆：用户偏好、历史方案等（用于个性化服务）
"""

import json
import time
from typing import List, Dict, Any, Optional

from langchain_classic.memory import ConversationBufferMemory
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# 日志记录器（使用项目统一的 loguru logger，避免标准 logging -> loguru 脱节导致日志丢失）
try:
    from core.logger import logger
except (ImportError, Exception):
    try:
        from loguru import logger  # noqa: F811
    except ImportError:
        import logging
        logger = logging.getLogger(__name__)


# ========== 消息序列化工具 ==========

def serialize_message(message) -> Dict[str, Any]:
    """
    序列化LangChain消息为字典
    
    参数：
        message: LangChain消息对象
    
    返回：
        序列化后的字典
    """
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": message.content}
    elif isinstance(message, AIMessage):
        return {"role": "assistant", "content": message.content}
    elif isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}
    else:
        return {"role": "unknown", "content": str(message)}


def deserialize_message(data: Dict[str, Any]):
    """
    反序列化为LangChain消息对象
    
    参数：
        data: 序列化的字典
    
    返回：
        LangChain消息对象
    """
    role = data.get("role", "")
    content = data.get("content", "")
    
    if role == "user":
        return HumanMessage(content=content)
    elif role == "assistant":
        return AIMessage(content=content)
    elif role == "system":
        return SystemMessage(content=content)
    else:
        return HumanMessage(content=content)


# ========== 内存存储实现（开发环境） ==========

class InMemoryStore:
    """
    内存存储 - 用于开发和测试环境
    
    特点：
    1. 简单可靠，无需外部依赖
    2. 数据在内存中，重启后丢失
    3. 适合开发和测试使用
    """
    
    def __init__(self):
        """初始化内存存储"""
        self._conversations: Dict[str, List[Dict[str, Any]]] = {}
        self._user_preferences: Dict[int, Dict[str, Any]] = {}
        self._user_diet_history: Dict[int, List[Dict[str, Any]]] = {}
        logger.info("InMemoryStore初始化完成")
    
    # ========== 对话历史操作 ==========
    
    def get_conversation(
        self, 
        user_id: int, 
        session_id: Optional[str] = None,
        max_messages: int = 20
    ) -> List[Dict[str, Any]]:
        """
        获取用户会话的对话历史
        
        参数：
            user_id: 用户ID
            session_id: 会话ID；为 None 时返回该用户全部会话
            max_messages: 最大消息数量（最近N条）
        
        返回：
            对话历史列表
        """
        if session_id:
            key = f"{user_id}:{session_id}"
            messages = self._conversations.get(key, [])
            return [self._with_session(m, session_id) for m in messages[-max_messages:]]

        # 返回全部会话并按时间合并
        prefix = f"{user_id}:"
        all_messages = []
        for key, messages in self._conversations.items():
            if key.startswith(prefix):
                sid = key[len(prefix):]
                all_messages.extend(self._with_session(m, sid) for m in messages)
        all_messages.sort(key=lambda m: m.get("timestamp") or 0)
        return all_messages[-max_messages:]

    @staticmethod
    def _with_session(message: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """返回带 session_id 的消息副本，避免污染存储中的原始消息。"""
        item = dict(message)
        item["session_id"] = session_id
        return item
    
    def add_message(
        self, 
        user_id: int, 
        message: Dict[str, Any],
        session_id: str = "default"
    ) -> None:
        """
        添加一条消息到对话历史
        
        参数：
            user_id: 用户ID
            message: 消息字典 {"role": "user"|"assistant", "content": "..."}
            session_id: 会话ID
        """
        key = f"{user_id}:{session_id}"
        message["timestamp"] = time.time()
        
        if key not in self._conversations:
            self._conversations[key] = []
        
        self._conversations[key].append(message)
    
    def clear_conversation(
        self, 
        user_id: int, 
        session_id: str = "default"
    ) -> None:
        """
        清空用户会话的对话历史
        
        参数：
            user_id: 用户ID
            session_id: 会话ID
        """
        key = f"{user_id}:{session_id}"
        if key in self._conversations:
            del self._conversations[key]
    
    # ========== 用户偏好操作 ==========
    
    def get_user_preferences(self, user_id: int) -> Dict[str, Any]:
        """
        获取用户的长期偏好设置
        
        参数：
            user_id: 用户ID
        
        返回：
            用户偏好字典
        """
        return self._user_preferences.get(user_id, {})
    
    def update_user_preferences(
        self, 
        user_id: int, 
        preferences: Dict[str, Any]
    ) -> None:
        """
        更新用户的长期偏好设置
        
        参数：
            user_id: 用户ID
            preferences: 偏好字典
        """
        if user_id not in self._user_preferences:
            self._user_preferences[user_id] = {}
        
        # 合并新偏好
        self._user_preferences[user_id].update(preferences)
    
    # ========== 膳食历史操作 ==========
    
    def get_diet_history(
        self, 
        user_id: int, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取用户的历史膳食方案
        
        参数：
            user_id: 用户ID
            limit: 返回数量
        
        返回：
            膳食方案历史列表
        """
        history = self._user_diet_history.get(user_id, [])
        return history[-limit:]
    
    def save_diet_plan(
        self, 
        user_id: int, 
        diet_plan: Dict[str, Any]
    ) -> None:
        """
        保存用户的膳食方案到历史
        
        参数：
            user_id: 用户ID
            diet_plan: 膳食方案
        """
        if user_id not in self._user_diet_history:
            self._user_diet_history[user_id] = []
        
        # 添加时间戳
        plan_with_time = {
            "plan": diet_plan,
            "saved_at": time.time()
        }
        
        self._user_diet_history[user_id].append(plan_with_time)
        
        # 最多保存30条历史
        if len(self._user_diet_history[user_id]) > 30:
            self._user_diet_history[user_id] = self._user_diet_history[user_id][-30:]


# ========== Redis存储实现（生产环境） ==========

class RedisMemory:
    """
    Redis存储 - 用于生产环境
    
    特点：
    1. 支持多实例部署
    2. 数据持久化
    3. 高性能读写
    
    注意：
    实际Redis集成需要安装redis库，这里预留接口
    """
    
    def __init__(
        self, 
        host: str = "localhost", 
        port: int = 6379, 
        db: int = 0,
        password: str = ""
    ):
        """
        初始化Redis连接（预留实现）
        
        参数：
            host: Redis主机
            port: Redis端口
            db: Redis数据库编号
            password: Redis密码（空字符串表示无密码）
        """
        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._client = None
        auth_info = "有密码" if password else "无密码"
        logger.info(f"RedisMemory初始化: host={host}, port={port}, db={db}, {auth_info}")
    
    def _get_client(self):
        """获取Redis客户端（延迟初始化）；首次连接时输出详细诊断日志"""
        if self._client is None:
            try:
                import redis
                # 连接参数（无密码时不传 password，避免部分老 Redis 报 AUTH 错误）
                conn_kwargs = dict(
                    host=self._host,
                    port=self._port,
                    db=self._db,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                    protocol=2
                )
                if self._password:
                    conn_kwargs["password"] = self._password
                self._client = redis.Redis(**conn_kwargs)
                # PING 校验连通性
                pong = self._client.ping()
                # 尝试获取 Redis 服务端信息（版本等），失败不影响主流程
                server_info = {}
                try:
                    server_info = self._client.info("server") or {}
                except Exception:
                    server_info = {}
                redis_version = server_info.get("redis_version", "unknown")
                redis_mode = server_info.get("redis_mode", "unknown")
                os_info = server_info.get("os", "unknown")
                logger.info(
                    "Redis连接成功: PING={} | {}:{}/{} | version={} | mode={} | os={}".format(
                        pong, self._host, self._port, self._db,
                        redis_version, redis_mode, os_info
                    )
                )
            except ImportError as e:
                logger.warning("redis库未安装(ImportError: {})，回退到内存存储".format(e))
                self._fallback = InMemoryStore()
                self._client = None
                return None
            except Exception as e:
                logger.warning("Redis连接失败: {}:{} ({})，回退到内存存储. 异常: {}".format(
                    self._host, self._port, type(e).__name__, e
                ))
                self._fallback = InMemoryStore()
                self._client = None
                return None
        return self._client

    def is_available(self) -> bool:
        """检查Redis是否可用"""
        client = self._get_client()
        return client is not None
    
    def get_conversation(
        self, 
        user_id: int, 
        session_id: Optional[str] = None,
        max_messages: int = 20
    ) -> List[Dict[str, Any]]:
        """获取对话历史"""
        client = self._get_client()
        if client is None:
            return self._fallback.get_conversation(user_id, session_id, max_messages)
        
        try:
            if session_id:
                key = f"conversation:{user_id}:{session_id}"
                raw_messages = client.lrange(key, -max_messages, -1)
                messages = [json.loads(msg) for msg in raw_messages]
                for msg in messages:
                    msg["session_id"] = session_id
                return messages

            all_messages = []
            pattern = f"conversation:{user_id}:*"
            for key in client.keys(pattern):
                sid = key.rsplit(":", 1)[-1]
                raw_messages = client.lrange(key, -max_messages, -1)
                for raw in raw_messages:
                    msg = json.loads(raw)
                    msg["session_id"] = sid
                    all_messages.append(msg)
            all_messages.sort(key=lambda m: m.get("timestamp") or 0)
            return all_messages[-max_messages:]
        except Exception as e:
            logger.error(f"Redis读取对话历史失败: {e}")
            return []
    
    def add_message(
        self, 
        user_id: int, 
        message: Dict[str, Any],
        session_id: str = "default"
    ) -> None:
        """添加消息"""
        client = self._get_client()
        if client is None:
            self._fallback.add_message(user_id, message, session_id)
            return
        
        key = f"conversation:{user_id}:{session_id}"
        try:
            message["timestamp"] = time.time()
            client.rpush(key, json.dumps(message))
            # 设置过期时间（7天）
            client.expire(key, 7 * 24 * 3600)
        except Exception as e:
            logger.error(f"Redis写入消息失败: {e}")
    
    def clear_conversation(
        self, 
        user_id: int, 
        session_id: str = "default"
    ) -> None:
        """清空对话"""
        client = self._get_client()
        if client is None:
            self._fallback.clear_conversation(user_id, session_id)
            return
        
        key = f"conversation:{user_id}:{session_id}"
        try:
            client.delete(key)
        except Exception as e:
            logger.error(f"Redis清空对话失败: {e}")
    
    def get_user_preferences(self, user_id: int) -> Dict[str, Any]:
        """获取用户偏好"""
        client = self._get_client()
        if client is None:
            return self._fallback.get_user_preferences(user_id)
        
        key = f"user_prefs:{user_id}"
        try:
            raw = client.get(key)
            return json.loads(raw) if raw else {}
        except Exception as e:
            logger.error(f"Redis读取用户偏好失败: {e}")
            return {}
    
    def update_user_preferences(
        self, 
        user_id: int, 
        preferences: Dict[str, Any]
    ) -> None:
        """更新用户偏好"""
        client = self._get_client()
        if client is None:
            self._fallback.update_user_preferences(user_id, preferences)
            return
        
        key = f"user_prefs:{user_id}"
        try:
            # 获取现有偏好并合并
            existing = self.get_user_preferences(user_id)
            existing.update(preferences)
            client.set(key, json.dumps(existing))
        except Exception as e:
            logger.error(f"Redis更新用户偏好失败: {e}")
    
    def get_diet_history(
        self, 
        user_id: int, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取膳食历史"""
        client = self._get_client()
        if client is None:
            return self._fallback.get_diet_history(user_id, limit)
        
        key = f"diet_history:{user_id}"
        try:
            raw = client.lrange(key, -limit, -1)
            return [json.loads(item) for item in raw]
        except Exception as e:
            logger.error(f"Redis读取膳食历史失败: {e}")
            return []
    
    def save_diet_plan(
        self, 
        user_id: int, 
        diet_plan: Dict[str, Any]
    ) -> None:
        """保存膳食方案"""
        client = self._get_client()
        if client is None:
            self._fallback.save_diet_plan(user_id, diet_plan)
            return
        
        key = f"diet_history:{user_id}"
        try:
            plan_with_time = {
                "plan": diet_plan,
                "saved_at": time.time()
            }
            client.rpush(key, json.dumps(plan_with_time))
            # 保留最近30条
            client.ltrim(key, -30, -1)
        except Exception as e:
            logger.error(f"Redis保存膳食方案失败: {e}")


# ========== 记忆管理器（统一接口） ==========

class MemoryManager:
    """
    记忆管理器 - 提供统一的记忆操作接口
    
    根据配置自动选择存储方式：
    - 开发环境：使用内存存储（InMemoryStore）
    - 生产环境：使用Redis存储（RedisMemory）
    
    使用示例：
    ```python
    memory = MemoryManager()
    
    # 添加消息
    memory.add_message(user_id=1, message={"role": "user", "content": "你好"})
    
    # 获取历史
    history = memory.get_conversation(user_id=1)
    
    # 保存方案
    memory.save_diet_plan(user_id=1, diet_plan={...})
    ```
    """
    
    _instance: Optional['MemoryManager'] = None
    _initialized = False
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化（只执行一次）"""
        if self._initialized:
            return
        
        # 根据配置选择存储方式
        try:
            from core.config_handler import get_settings
            settings = get_settings()
            
            redis_config = getattr(settings, 'redis', None)
            if redis_config:
                logger.info(
                    "MemoryManager: 检测到Redis配置 -> host={}, port={}, db={}".format(
                        getattr(redis_config, 'host', 'localhost'),
                        getattr(redis_config, 'port', 6379),
                        getattr(redis_config, 'db', 0)
                    )
                )
                redis_store = RedisMemory(
                    host=getattr(redis_config, 'host', 'localhost'),
                    port=getattr(redis_config, 'port', 6379),
                    db=getattr(redis_config, 'db', 0),
                    password=getattr(redis_config, 'password', '') or ''
                )
                if redis_store.is_available():
                    self._store = redis_store
                    logger.info(
                        "MemoryManager: [OK] 使用Redis存储 {}:{}".format(
                            getattr(redis_config, 'host', 'localhost'),
                            getattr(redis_config, 'port', 6379)
                        )
                    )
                else:
                    self._store = InMemoryStore()
                    logger.warning("MemoryManager: [FALLBACK] Redis不可用，回退到内存存储（对话历史/膳食方案不会跨进程持久化）")
            else:
                self._store = InMemoryStore()
                logger.info("MemoryManager: 未配置Redis，使用内存存储")
        except Exception as e:
            logger.warning("MemoryManager: Redis初始化异常({})，回退到内存存储".format(e))
            self._store = InMemoryStore()
        
        self._initialized = True
    
    # ========== 对话历史接口 ==========
    
    def get_conversation(
        self, 
        user_id: int, 
        session_id: Optional[str] = None,
        max_messages: int = 20
    ) -> List[Dict[str, Any]]:
        """获取用户会话的对话历史；session_id 为 None 时返回全部会话"""
        return self._store.get_conversation(user_id, session_id, max_messages)
    
    def add_message(
        self, 
        user_id: int, 
        message: Dict[str, Any],
        session_id: str = "default"
    ) -> None:
        """添加消息到对话历史"""
        self._store.add_message(user_id, message, session_id)
    
    def clear_conversation(
        self, 
        user_id: int, 
        session_id: str = "default"
    ) -> None:
        """清空对话历史"""
        self._store.clear_conversation(user_id, session_id)
    
    # ========== LangChain兼容接口 ==========
    
    def get_langchain_messages(
        self, 
        user_id: int, 
        session_id: str = "default",
        max_messages: int = 20
    ) -> List:
        """
        获取LangChain格式的消息列表
        
        用于直接传给LangChain的对话链
        
        参数：
            user_id: 用户ID
            session_id: 会话ID
            max_messages: 最大消息数
        
        返回：
            LangChain消息对象列表
        """
        conversation = self.get_conversation(user_id, session_id, max_messages)
        return [deserialize_message(msg) for msg in conversation]
    
    def get_langchain_memory(
        self, 
        user_id: int, 
        session_id: str = "default",
        max_messages: int = 20
    ) -> ConversationBufferMemory:
        """
        获取LangChain的ConversationBufferMemory对象
        
        用于需要LangChain Memory对象的场景
        
        参数：
            user_id: 用户ID
            session_id: 会话ID
            max_messages: 最大消息数
        
        返回：
            ConversationBufferMemory对象
        """
        memory = ConversationBufferMemory(
            memory_key=f"history:{user_id}:{session_id}",
            max_history_length=max_messages
        )
        
        # 加载历史消息
        messages = self.get_langchain_messages(user_id, session_id, max_messages)
        for msg in messages:
            if isinstance(msg, HumanMessage):
                memory.chat_memory.add_user_message(msg.content)
            elif isinstance(msg, AIMessage):
                memory.chat_memory.add_ai_message(msg.content)
        
        return memory
    
    # ========== 用户偏好接口 ==========
    
    def get_user_preferences(self, user_id: int) -> Dict[str, Any]:
        """获取用户偏好"""
        return self._store.get_user_preferences(user_id)
    
    def update_user_preferences(
        self, 
        user_id: int, 
        preferences: Dict[str, Any]
    ) -> None:
        """更新用户偏好"""
        self._store.update_user_preferences(user_id, preferences)
    
    # ========== 膳食历史接口 ==========
    
    def get_diet_history(
        self, 
        user_id: int, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取膳食方案历史"""
        return self._store.get_diet_history(user_id, limit)
    
    def save_diet_plan(
        self, 
        user_id: int, 
        diet_plan: Dict[str, Any]
    ) -> None:
        """保存膳食方案"""
        self._store.save_diet_plan(user_id, diet_plan)


# ========== 便捷函数 ==========

def get_memory() -> MemoryManager:
    """
    获取记忆管理器单例
    
    返回：
        MemoryManager实例
    """
    return MemoryManager()


def get_conversation_history(
    user_id: int, 
    max_messages: int = 20
) -> List[Dict[str, Any]]:
    """
    便捷函数：获取对话历史
    
    参数：
        user_id: 用户ID
        max_messages: 最大消息数
    
    返回：
        对话历史列表
    """
    return get_memory().get_conversation(user_id, max_messages=max_messages)


def save_interaction(
    user_id: int, 
    user_message: str, 
    assistant_message: str
) -> None:
    """
    便捷函数：保存一次完整的交互（用户消息+AI回复）
    
    参数：
        user_id: 用户ID
        user_message: 用户消息
        assistant_message: AI回复
    """
    memory = get_memory()
    memory.add_message(user_id, {"role": "user", "content": user_message})
    memory.add_message(user_id, {"role": "assistant", "content": assistant_message})


# ======================== 文件内自测脚本 ========================
if __name__ == "__main__":
    print("=" * 60)
    print("MemoryManager 自测开始")
    print("=" * 60)
    
    # 测试1：初始化
    print("\n[测试1] 初始化MemoryManager...")
    memory = MemoryManager()
    print(f"[通过] 存储类型: {type(memory._store).__name__}")
    
    # 测试2：对话历史
    print("\n[测试2] 对话历史操作...")
    memory.add_message(1, {"role": "user", "content": "你好"})
    memory.add_message(1, {"role": "assistant", "content": "您好！有什么可以帮助您的？"})
    
    history = memory.get_conversation(1)
    print(f"[通过] 对话历史: {len(history)}条消息")
    for msg in history:
        print(f"  - [{msg['role']}]: {msg['content']}")
    
    # 测试3：LangChain消息格式
    print("\n[测试3] LangChain消息格式...")
    lc_messages = memory.get_langchain_messages(1)
    print(f"[通过] LangChain消息: {len(lc_messages)}条")
    for msg in lc_messages:
        print(f"  - {type(msg).__name__}: {msg.content}")
    
    # 测试4：用户偏好
    print("\n[测试4] 用户偏好操作...")
    memory.update_user_preferences(1, {"favorite": "减脂", "avoid": "辛辣"})
    prefs = memory.get_user_preferences(1)
    print(f"[通过] 用户偏好: {prefs}")
    
    # 测试5：膳食历史
    print("\n[测试5] 膳食历史操作...")
    plan = {"breakfast": {"items": [{"name": "燕麦粥"}]}}
    memory.save_diet_plan(1, plan)
    history = memory.get_diet_history(1)
    print(f"[通过] 膳食历史: {len(history)}条方案")
    
    # 测试6：清空对话
    print("\n[测试6] 清空对话...")
    memory.clear_conversation(1)
    history = memory.get_conversation(1)
    print(f"[通过] 清空后历史: {len(history)}条消息")
    
    # 测试7：便捷函数
    print("\n[测试7] 便捷函数...")
    save_interaction(1, "测试消息", "测试回复")
    history = get_conversation_history(1)
    print(f"[通过] 保存后历史: {len(history)}条消息")
    
    print("\n" + "=" * 60)
    print("MemoryManager 自测完成")
