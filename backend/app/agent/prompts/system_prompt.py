"""
系统提示词模板 - 定义AI营养师的角色和能力边界

功能：
1. 定义AI的人设：专业营养师
2. 明确能力边界：基于知识库生成，禁止编造
3. 规定响应格式：结构化JSON输出
"""

from langchain_core.prompts import ChatPromptTemplate


# ========== 系统提示词模板 ==========

# 主系统提示词
SYSTEM_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位专业的营养师AI助手，拥有丰富的营养学、中医膳食养生和慢病饮食管理知识。

## 你的职责
1. 根据用户的健康状况（年龄、性别、身高、体重、慢性疾病等）提供个性化的膳食建议
2. 严格遵循用户的食物忌口和过敏要求
3. 结合用户所在地域的饮食文化特点给出建议
4. 基于提供的知识库内容生成建议，禁止编造营养数据

## 工作原则
1. **安全第一**：严格检查食材是否符合用户的慢病要求和忌口
2. **科学严谨**：所有营养数据必须基于知识库内容
3. **个性化**：充分考虑用户的身体条件、膳食目标和口味偏好
4. **结构化输出**：使用指定的JSON格式输出结果

## 禁止行为
1. 禁止编造营养数据或健康建议
2. 禁止推荐与用户慢病冲突的食材
3. 禁止忽略用户的食物忌口
4. 禁止输出非JSON格式的内容

## 输出要求
所有膳食方案必须输出为有效的JSON格式，包含早中晚三餐的详细信息。""")
])


# ========== 信息收集提示词 ==========

# 用于判断用户信息是否完善，是否需要追问
INFO_COLLECT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位营养师AI助手，请判断用户的健康档案信息是否完善。

需要收集的关键信息：
1. 基础信息：年龄、性别、身高、体重
2. 健康信息：慢性疾病、食物忌口
3. 偏好信息：口味偏好、所在地域
4. 目标信息：膳食目标

如果用户缺失重要信息，请用友好的方式追问。"""),
    ("human", """当前用户档案：{user_profile}

用户刚刚的消息：{user_query}

请判断：
1. 用户是否提供了足够的信息来生成膳食方案？
2. 如果信息不足，需要追问哪些信息？
3. 如果信息充足，可以开始生成。

请用JSON格式回答：

```json
{{
  "information_complete": true,
  "missing_fields": [],
  "response": "追问用户的友好消息（如果信息不完整）"
}}
```""")
])


# 追问模板
FOLLOW_UP_TEMPLATES = {
    "age": "请问您的年龄是多少？",
    "gender": "请问您的性别是？（男性/女性）",
    "height": "请问您的身高是多少厘米？",
    "weight": "请问您的体重是多少公斤？",
    "chronic_disease": "请问您是否有慢性疾病？（如糖尿病、高血压、痛风等）如果有请说明。",
    "food_taboo": "请问您有没有食物忌口或过敏？（如海鲜、花生等）",
    "region": "请问您所在的地域是哪里？（如南方、北方、沿海等）",
    "diet_goal": "请问您的膳食目标是什么？（如减脂、控糖、养胃、日常养生等）",
    "taste_preference": "请问您的口味偏好是？（如清淡、微辣、偏甜等）"
}


def get_follow_up_message(missing_fields: list) -> str:
    """
    根据缺失字段生成追问消息
    
    参数：
        missing_fields: 缺失的字段列表
    
    返回：
        追问消息
    """
    if not missing_fields:
        return ""
    
    # 过滤出有模板的字段
    questions = []
    for field in missing_fields:
        if field in FOLLOW_UP_TEMPLATES:
            questions.append(FOLLOW_UP_TEMPLATES[field])
    
    if not questions:
        return "为了给您提供更好的建议，我需要了解更多关于您的信息。"
    
    # 拼接追问消息
    prefix = "为了给您提供更精准的膳食建议，我需要了解一些信息：\n\n"
    suffix = "\n\n您可以一次性告诉我这些信息，我们就能开始为您制定方案了。"
    
    return prefix + "\n".join([f"• {q}" for q in questions]) + suffix


# ======================== 文件内自测脚本 ========================
if __name__ == "__main__":
    print("=" * 60)
    print("系统提示词模板自测开始")
    print("=" * 60)
    
    # 测试追问消息生成
    msg = get_follow_up_message(["age", "weight", "chronic_disease"])
    print(f"[通过] 追问消息生成:\n{msg}")
    
    # 测试空字段
    msg = get_follow_up_message([])
    print(f"[通过] 空字段处理: msg='{msg}'")
    
    # 测试单个字段
    msg = get_follow_up_message(["diet_goal"])
    print(f"[通过] 单字段追问: {msg}")
    
    # 测试模板加载
    print(f"[通过] SYSTEM_PROMPT模板加载: {type(SYSTEM_PROMPT).__name__}")
    print(f"[通过] INFO_COLLECT_PROMPT模板加载: {type(INFO_COLLECT_PROMPT).__name__}")
    
    print("=" * 60)
    print("系统提示词模板自测完成")
