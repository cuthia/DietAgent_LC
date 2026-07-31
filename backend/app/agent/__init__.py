"""
Agent模块 - 膳食搭配智能Agent

模块结构：
- llm_client.py: LLM客户端封装
- chain.py: LCEL链式调用编排
- memory.py: 对话记忆管理
- tools/: 工具集
  - user_tool.py: 用户信息查询
  - rag_tool.py: RAG知识检索
  - validate_tool.py: 忌口/慢病校验
  - region_tool.py: 地域饮食适配
- prompts/: Prompt模板
  - system_prompt.py: 系统提示词
  - diet_prompt.py: 膳食生成提示词
  - validate_prompt.py: 校验修正提示词

使用示例：
```python
from agent import DietAgentChain, MemoryManager

# 创建Agent
agent = DietAgentChain()

# 处理请求
result = await agent.process(user_id=1, user_query="减脂食谱")

# 使用记忆
memory = MemoryManager()
history = memory.get_conversation(user_id=1)
```
"""

from agent.chain import DietAgentChain
from agent.memory import MemoryManager, get_memory, save_interaction

# 导出常用类和函数
__all__ = [
    "DietAgentChain",
    "MemoryManager",
    "get_memory",
    "save_interaction",
]
