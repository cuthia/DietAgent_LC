"""
后端 API 统一客户端

功能：
1. 封装所有后端接口调用
2. 处理 JWT 认证
3. 处理 SSE 流式响应
4. 统一异常处理

设计模式：单例模式 + 外观模式
"""

import requests
import json
import logging
from typing import Optional, Dict, Any, Generator
from config import BACKEND_URL, API_PATHS

# 日志记录器
logger = logging.getLogger(__name__)


class APIClient:
    """
    后端 API 统一客户端

    职责：
    - 封装所有后端接口调用
    - 管理 JWT token 和用户会话
    - 处理流式响应（SSE）
    - 统一异常处理和日志记录

    使用示例：
        api = APIClient()
        api.login("username", "password")
        result = api.chat("给我设计减脂餐")
    """

    def __init__(self):
        """初始化客户端"""
        self.base_url = BACKEND_URL
        self.token: Optional[str] = None
        self.user_id: Optional[int] = None
        self.session_id: Optional[str] = None

    # ======================== 内部方法 ========================

    def _get_headers(self, include_auth: bool = True) -> Dict[str, str]:
        """
        获取请求头

        参数：
            include_auth: 是否包含认证头

        返回：
            请求头字典
        """
        headers = {"Content-Type": "application/json"}
        if include_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, **kwargs) -> Optional[Dict]:
        """
        统一请求方法（内部使用）

        参数：
            method: HTTP 方法（GET/POST/PUT/DELETE）
            path: API 路径
            **kwargs: requests 参数

        返回：
            响应数据字典，失败返回 None
        """
        url = f"{self.base_url}{path}"

        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()

            data = response.json()

            # 检查业务状态码
            if data.get("code") == 200:
                return data.get("data")
            else:
                logger.error(f"API业务错误: {data.get('message', '未知错误')}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败 [{method} {path}]: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return None

    # ======================== 用户认证 ========================

    def login(self, username: str, password: str) -> Optional[Dict]:
        """
        用户登录

        参数：
            username: 用户名
            password: 密码

        返回：
            登录成功返回用户信息字典，失败返回 None

        示例：
            >>> result = api.login("alice", "password123")
            >>> if result:
            ...     print(f"登录成功，用户ID: {result['user_id']}")
        """
        try:
            response = requests.post(
                f"{self.base_url}{API_PATHS['login']}",
                json={"username": username, "password": password}
            )
            data = response.json()

            if data.get("code") == 200:
                login_data = data.get("data", {})
                self.token = login_data.get("token")
                self.user_id = login_data.get("user_id")
                logger.info(f"登录成功: user_id={self.user_id}")
                return login_data
            else:
                logger.warning(f"登录失败: {data.get('message', '未知错误')}")
                return None

        except Exception as e:
            logger.error(f"登录异常: {e}")
            return None

    def register(self, username: str, password: str, **kwargs) -> Optional[Dict]:
        """
        用户注册

        参数：
            username: 用户名
            password: 密码
            **kwargs: 其他用户信息

        返回：
            注册成功返回用户信息，失败返回 None
        """
        payload = {"username": username, "password": password}
        payload.update(kwargs)

        try:
            response = requests.post(
                f"{self.base_url}{API_PATHS['register']}",
                json=payload
            )
            data = response.json()

            if data.get("code") == 200:
                register_data = data.get("data", {})
                self.token = register_data.get("token")
                self.user_id = register_data.get("user_id")
                logger.info(f"注册成功: user_id={self.user_id}")
                return register_data
            else:
                logger.warning(f"注册失败: {data.get('message', '未知错误')}")
                return None

        except Exception as e:
            logger.error(f"注册异常: {e}")
            return None

    def logout(self):
        """
        退出登录（清除本地会话）
        """
        self.token = None
        self.user_id = None
        self.session_id = None
        logger.info("已退出登录")

    # ======================== 用户档案 ========================

    def get_profile(self, user_id: int) -> Optional[Dict]:
        """
        获取用户健康档案

        参数：
            user_id: 用户ID

        返回：
            用户档案字典
        """
        path = API_PATHS['profile'].format(user_id=user_id)
        return self._request("GET", path, headers=self._get_headers())

    def update_profile(self, user_id: int, updates: Dict) -> Optional[Dict]:
        """
        更新用户健康档案

        参数：
            user_id: 用户ID
            updates: 更新字段字典

        返回：
            更新后的档案
        """
        path = API_PATHS['profile'].format(user_id=user_id)
        return self._request("PUT", path, headers=self._get_headers(), json=updates)

    # ======================== Agent 对话 ========================

    def chat(self, message: str, session_id: str = None) -> Optional[Dict]:
        """
        同步对话（一次性返回完整结果）

        参数：
            message: 用户消息
            session_id: 会话ID（可选，用于多轮对话）

        返回：
            对话结果字典
        """
        payload = {
            "user_id": self.user_id,
            "message": message,
        }
        if session_id:
            payload["session_id"] = session_id

        return self._request(
            "POST",
            API_PATHS['chat'],
            headers=self._get_headers(),
            json=payload
        )

    def chat_stream(self, message: str, session_id: str = None) -> Generator[Dict, None, None]:
        """
        流式对话（SSE）

        通过 Server-Sent Events 实时推送处理进度和结果

        参数：
            message: 用户消息
            session_id: 会话ID（可选）

        Yields：
            每个事件的字典，包含以下字段：
            - stage: 当前阶段（collect_info/retrieve_knowledge/generate_diet/output）
            - status: 状态（start/complete）
            - message: 进度消息
            - data: 最终数据（仅output阶段）

        使用示例：
            >>> for event in api.chat_stream("减脂餐"):
            ...     if event.get("stage") == "output":
            ...         print(event["data"]["diet_plan"])
        """
        url = f"{self.base_url}{API_PATHS['chat_stream']}"
        payload = {"user_id": self.user_id, "message": message}
        if session_id:
            payload["session_id"] = session_id

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                stream=True  # 启用流式读取
            )
            response.raise_for_status()

            # 解析 SSE 事件流
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue

                # SSE 格式：data: {...}
                if line.startswith("data: "):
                    data_str = line[6:]  # 去掉 "data: " 前缀

                    if data_str == "[DONE]":
                        break

                    try:
                        event = json.loads(data_str)
                        yield event
                    except json.JSONDecodeError:
                        logger.warning(f"SSE事件解析失败: {data_str}")
                        continue

        except requests.exceptions.RequestException as e:
            logger.error(f"流式对话请求失败: {e}")
            yield {"stage": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"流式对话异常: {e}")
            yield {"stage": "error", "message": str(e)}

    def get_chat_history(self, user_id: int, max_messages: int = 20) -> list:
        """
        获取对话历史

        参数：
            user_id: 用户ID
            max_messages: 最大消息数

        返回：
            消息列表
        """
        path = API_PATHS['chat_history'].format(user_id=user_id)
        result = self._request(
            "GET",
            path,
            headers=self._get_headers(),
            params={"max_messages": max_messages}
        )
        return result if result else []

    def clear_history(self, user_id: int, session_id: str = "default") -> bool:
        """
        清空对话历史

        参数：
            user_id: 用户ID
            session_id: 会话ID

        返回：
            是否成功
        """
        path = API_PATHS['clear_history'].format(user_id=user_id)
        result = self._request(
            "DELETE",
            path,
            headers=self._get_headers(),
            params={"session_id": session_id}
        )
        return result is not None

    def get_diet_history(self, user_id: int, limit: int = 10) -> list:
        """
        获取膳食方案历史

        参数：
            user_id: 用户ID
            limit: 最大记录数

        返回：
            膳食方案列表
        """
        path = API_PATHS['diet_history'].format(user_id=user_id)
        result = self._request(
            "GET",
            path,
            headers=self._get_headers(),
            params={"limit": limit}
        )
        return result if result else []

    # ======================== 知识库管理 ========================

    def upload_knowledge(self, file, category: str = None) -> Optional[Dict]:
        """
        上传知识库文档

        参数：
            file: 文件对象（Streamlit UploadedFile）
            category: 文档分类

        返回：
            上传结果
        """
        url = f"{self.base_url}{API_PATHS['knowledge_upload']}"

        try:
            files = {"file": (file.name, file.getvalue(), file.type)}
            data = {}
            if category:
                data["category"] = category

            response = requests.post(
                url,
                files=files,
                data=data,
                headers={"Authorization": f"Bearer {self.token}"} if self.token else {}
            )

            result = response.json()
            if result.get("code") == 200:
                return result.get("data")
            else:
                logger.error(f"上传失败: {result.get('message')}")
                return None

        except Exception as e:
            logger.error(f"上传异常: {e}")
            return None

    def search_knowledge(self, query: str, top_k: int = 5) -> list:
        """
        检索知识库

        参数：
            query: 检索关键词
            top_k: 返回数量

        返回：
            检索结果列表
        """
        result = self._request(
            "POST",
            API_PATHS['knowledge_search'],
            headers=self._get_headers(),
            json={"query": query, "top_k": top_k}
        )
        return result if result else []

    def get_knowledge_stats(self) -> Optional[Dict]:
        """
        获取知识库统计信息

        返回：
            统计信息字典
        """
        return self._request(
            "GET",
            API_PATHS['knowledge_stats'],
            headers=self._get_headers()
        )

    # ======================== 膳食方案校验 ========================

    def validate_plan(self, user_id: int, diet_plan: Dict) -> Optional[Dict]:
        """
        校验膳食方案

        参数：
            user_id: 用户ID
            diet_plan: 膳食方案字典

        返回：
            校验结果
        """
        return self._request(
            "POST",
            API_PATHS['validate'],
            headers=self._get_headers(),
            json={"user_id": user_id, "diet_plan": diet_plan}
        )


# ======================== 全局单例 ========================

_api_client: Optional[APIClient] = None


def get_api_client() -> APIClient:
    """
    获取全局 API 客户端实例（单例模式）

    返回：
        APIClient 实例

    使用示例：
        >>> api = get_api_client()
        >>> api.login("username", "password")
    """
    global _api_client
    if _api_client is None:
        _api_client = APIClient()
    return _api_client