"""
LLM客户端封装模块

功能：
1. 封装大模型统一调用接口，兼容多厂商LLM
2. 支持同步和流式两种调用模式
3. 提供LangChain兼容的LLM实例

支持的LLM提供商：
- DeepSeek: 高性价比，中文效果好
- 通义千问: 阿里出品，中文优化
- OpenAI: GPT-4o，通用能力强

设计模式：策略模式 + 工厂模式
"""

import logging
from typing import List, Dict, Any, Iterator, Optional
from core.config_handler import LLMConfig

# 日志记录器
logger = logging.getLogger(__name__)


class LLMClient:
    """
    大模型统一封装
    
    核心方法：
    - chat(): 单轮同步对话
    - stream_chat(): 流式对话（用于SSE推送）
    - get_llm(): 获取LangChain兼容的LLM实例
    
    使用示例：
    from core.config_handler import get_settings
    llm_client = LLMClient(get_settings().llm)
    
    # 同步调用
    response = llm_client.chat([
        {"role": "system", "content": "你是一位营养师"},
        {"role": "user", "content": "给我一份减脂餐"}
    ])
    
    # 流式调用
    for chunk in llm_client.stream_chat(messages):
        print(chunk, end="")
    """
    
    def __init__(self, llm_config: LLMConfig):
        """
        初始化LLM客户端
        
        参数：
            llm_config: LLM配置对象，包含type/api_key/base_url/model等
        """
        self.config = llm_config
        self._llm = None  # 懒加载的LLM实例
        self._create_llm()
    
    def _create_llm(self):
        """
        根据配置创建对应的LLM实例
        
        支持的type值：
        - deepseek: 使用ChatDeepSeek
        - qwen: 使用ChatDashScope
        - openai: 使用ChatOpenAI
        """
        try:
            llm_type = self.config.type
            
            if llm_type == "deepseek":
                from langchain_community.chat_models import ChatDeepSeek
                self._llm = ChatDeepSeek(
                    model=self.config.model,
                    api_key=self.config.api_key,
                    base_url=self.config.base_url,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens
                )
                logger.info(f"LLM初始化成功: DeepSeek ({self.config.model})")
                
            elif llm_type == "qwen":
                from langchain_community.chat_models import ChatDashScope
                self._llm = ChatDashScope(
                    model=self.config.model,
                    dashscope_api_key=self.config.api_key,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens
                )
                logger.info(f"LLM初始化成功: 通义千问 ({self.config.model})")
                
            elif llm_type == "openai":
                from langchain_community.chat_models import ChatOpenAI
                self._llm = ChatOpenAI(
                    model=self.config.model,
                    api_key=self.config.api_key,
                    base_url=self.config.base_url,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens
                )
                logger.info(f"LLM初始化成功: OpenAI ({self.config.model})")
                
            else:
                # 默认使用DeepSeek
                logger.warning(f"未知的LLM类型: {llm_type}，默认使用DeepSeek")
                from langchain_community.chat_models import ChatDeepSeek
                self._llm = ChatDeepSeek(
                    model=self.config.model,
                    api_key=self.config.api_key,
                    base_url=self.config.base_url,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens
                )
                
        except ImportError as e:
            logger.error(f"LLM导入失败: {e}")
            self._llm = None
        except Exception as e:
            logger.error(f"LLM初始化失败: {e}")
            self._llm = None

    def _convert_messages(self, messages: List[Dict[str, str]]):
        """
        转换消息格式为LangChain兼容格式
        
        输入格式：[{"role": "user", "content": "..."}, ...]
        输出格式：[HumanMessage(content="..."), SystemMessage(content="..."), ...]
        
        支持的角色：
        - system: 系统提示
        - user: 用户消息
        - assistant: AI回复
        """
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
        
        role_map = {
            "user": HumanMessage,
            "assistant": AIMessage,
            "system": SystemMessage
        }
        
        langchain_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # 获取对应的消息类
            message_class = role_map.get(role, HumanMessage)
            langchain_messages.append(message_class(content=content))
        
        return langchain_messages


    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        同步单轮对话
        
        参数：
            messages: 消息列表 [{"role": "user", "content": "..."}, ...]
            **kwargs: 额外参数（如temperature、max_tokens等）
        
        返回：
            LLM回复文本
        
        """
        if not self._llm:
            raise RuntimeError("LLM未初始化")
        
        try:
            # 转换消息格式为LangChain兼容格式
            langchain_messages = self._convert_messages(messages)
            
            # 调用LLM
            response = self._llm.invoke(langchain_messages, **kwargs)
            
            # 返回文本内容
            return response.content if hasattr(response, 'content') else str(response)
            
        except Exception as e:
            logger.error(f"LLM对话失败: {e}")
            raise
    
    def stream_chat(self, messages: List[Dict[str, str]], **kwargs) -> Iterator[str]:
        """
        流式对话（用于SSE推送）
        
        参数：
            messages: 消息列表
            **kwargs: 额外参数
        
        Yields：
            逐字yield文本片段
        
        使用示例：
        ```python
        for chunk in llm_client.stream_chat(messages):
            print(chunk, end="")
        ```
        """
        if not self._llm:
            raise RuntimeError("LLM未初始化")
        
        try:
            # 转换消息格式
            langchain_messages = self._convert_messages(messages)
            
            # 流式调用
            for chunk in self._llm.stream(langchain_messages, **kwargs):
                # 处理不同的chunk格式
                if hasattr(chunk, 'content'):
                    yield chunk.content or ""
                elif isinstance(chunk, str):
                    yield chunk
                else:
                    yield str(chunk)
                    
        except Exception as e:
            logger.error(f"LLM流式对话失败: {e}")
            yield f"生成失败: {str(e)}"
    
    def get_llm(self):
        """
        获取LangChain兼容的LLM实例
        
        用于LCEL链式调用中的 | 操作符
        
        返回：
            LangChain BaseChatModel实例
        """
        if not self._llm:
            raise RuntimeError("LLM未初始化")
        return self._llm
    

    
    @property
    def is_available(self) -> bool:
        """检查LLM是否可用"""
        return self._llm is not None
    
    @classmethod
    def from_config(cls) -> "LLMClient":
        """
        从全局配置创建LLMClient实例
        
        便捷方法，自动从settings获取LLM配置
        
        返回：
            LLMClient实例
        
        使用示例：
        ```python
        client = LLMClient.from_config()
        ```
        """
        from core.config_handler import get_settings
        settings = get_settings()
        return cls(settings.llm)


# ======================== 文件内自测脚本 ========================
# 运行方式：在 backend/app 目录下执行  python -m agent.llm_client
if __name__ == "__main__":
    import os
    os.environ["ENV"] = "dev"
    
    print("=" * 60)
    print("LLM客户端自测开始")
    print("=" * 60)
    
    from core.config_handler import get_settings
    
    # 获取配置
    settings = get_settings()
    print(f"LLM配置: type={settings.llm.type}, model={settings.llm.model}")
    
    # 创建LLM客户端
    llm_client = LLMClient(settings.llm)
    print(f"LLM可用: {llm_client.is_available}")
    
    if llm_client.is_available:
        # 测试同步对话
        try:
            response = llm_client.chat([
                {"role": "system", "content": "你是一位专业的营养师AI助手。请用简洁的语言回答。"},
                {"role": "user", "content": "简单介绍一下减脂餐的基本原则"}
            ])
            print(f"\n[通过] 同步对话测试: {response[:100]}...")
        except Exception as e:
            print(f"[跳过] 同步对话测试: {e}")
        
        # 测试获取LLM实例
        try:
            llm = llm_client.get_llm()
            print(f"[通过] LLM实例获取: {type(llm).__name__}")
        except Exception as e:
            print(f"[跳过] LLM实例获取: {e}")
    else:
        print("[提示] LLM未初始化（可能未配置API Key），跳过对话测试")
    
    print("=" * 60)
    print("LLM客户端自测完成")
