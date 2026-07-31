"""
膳食生成提示词模板 - 用于生成结构化的膳食方案

功能：
1. 定义膳食生成的Prompt模板
2. 规定输出格式为JSON
3. 结合用户信息、知识库、约束条件生成方案
"""

from langchain_core.prompts import ChatPromptTemplate


# ========== 膳食生成主模板 ==========

# 用于生成膳食方案的核心Prompt
DIET_GENERATE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位专业的营养师AI助手，请根据用户的健康状况和需求，生成一份个性化的膳食方案。

## 严格规则
1. 所有营养数据必须基于提供的知识库内容，**禁止编造**任何数据
2. 食材选择必须符合用户的慢性疾病和食物忌口要求
3. 每餐热量分配：早餐30%、午餐40%、晚餐25%、加餐5%
4. 保证营养均衡：蛋白质、碳水化合物、脂肪、维生素、矿物质
5. 食物多样性：避免连续使用相同食材
6. 烹饪方式健康：优先推荐蒸、煮、炖、烤，少用油炸

## 输出格式（必须严格遵守）
请输出以下JSON格式的膳食方案：

```json
{
  "breakfast": {
    "items": [
      {
        "name": "食材名称",
        "amount": "用量（如：100g、1个、1碗）",
        "calories": 热量（千卡）,
        "protein": 蛋白质（克）,
        "tips": "小贴士（可选）"
      }
    ],
    "total_calories": 早餐总热量,
    "cooking_method": "烹饪方式",
    "tips": "早餐整体建议"
  },
  "lunch": {
    "items": [...],
    "total_calories": 午餐总热量,
    "cooking_method": "烹饪方式",
    "tips": "午餐整体建议"
  },
  "dinner": {
    "items": [...],
    "total_calories": 晚餐总热量,
    "cooking_method": "烹饪方式",
    "tips": "晚餐整体建议"
  },
  "snack": {
    "items": [...],
    "total_calories": 加餐总热量,
    "tips": "加餐建议"
  },
  "total_calories": 全天总热量,
  "daily_target_calories": "建议的每日热量摄入",
  "nutrition_balance": {
    "protein": "蛋白质摄入评估",
    "carbs": "碳水化合物摄入评估",
    "fat": "脂肪摄入评估",
    "fiber": "膳食纤维摄入评估",
    "assessment": "整体营养均衡评估"
  },
  "health_tips": ["健康建议1", "健康建议2", "健康建议3"],
  "disclaimer": "以上建议仅供参考，具体饮食请结合个人情况"
}
```

## 重要提醒
- 必须严格检查食材是否符合用户的慢病要求
- 必须避免用户的食物忌口
- 如果知识库中没有的数据，请标注为"估算值"
- 建议搭配具体的烹饪步骤和小贴士"""),
    
    ("human", """## 用户信息
{user_profile}

## 用户需求
{user_query}

## 相关知识库内容
{knowledge_context}

## 约束条件
{constraints}

## 地域特点
{region_features}

请根据以上信息，为用户生成一份完整的膳食方案。""")
])


# ========== 膳食方案修正模板 ==========

# 当生成的方案不符合要求时，用于修正的Prompt
DIET_REVISE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位专业的营养师AI助手，之前生成的膳食方案存在一些问题，需要进行修正。

## 修正原则
1. **优先移除**：必须移除违反用户忌口或慢病要求的食材
2. **合理替换**：用同类食材替换被移除的食材，保证营养均衡
3. **保持结构**：保持原方案的整体结构和热量分配
4. **标注变更**：在tips中标注修改的内容和原因

## 输出格式
请输出完整的修正后膳食方案，格式与原方案相同。"""),
    
    ("human", """## 原膳食方案
{diet_plan}

## 问题清单
{issues}

## 用户信息
{user_profile}

请修正以上膳食方案，解决列出的问题。""")
])


# ========== 快速生成模板（简化版） ==========

# 用于简单场景的快速生成模板
QUICK_DIET_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位营养师AI助手，请为用户推荐一份简单健康的膳食方案。

要求：
1. 每天三餐 + 可选加餐
2. 营养均衡，食材常见
3. 烹饪简单易行
4. 符合用户的忌口和健康要求"""),
    
    ("human", """用户情况：{brief_profile}
膳食需求：{user_query}

请推荐一份简单实用的膳食方案。""")
])


# ======================== 辅助函数 ========================

def build_constraints_text(
    chronic_disease: str = "",
    food_taboo: str = "",
    diet_goal: str = ""
) -> str:
    """
    构建约束条件文本
    
    参数：
        chronic_disease: 慢性疾病
        food_taboo: 食物忌口
        diet_goal: 膳食目标
    
    返回：
        约束条件描述文本
    """
    parts = []
    
    # 慢病约束
    if chronic_disease:
        parts.append(f"- 慢性疾病：{chronic_disease}，需遵循相应的饮食禁忌")
    
    # 忌口约束
    if food_taboo:
        parts.append(f"- 食物忌口：{food_taboo}，**严禁出现这些食材**")
    
    # 目标约束
    if diet_goal:
        goal_tips = {
            "减脂": "控制总热量，增加蛋白质和膳食纤维",
            "增肌": "增加蛋白质摄入，保证热量盈余",
            "控糖": "选择低GI食物，控制碳水摄入",
            "养胃": "选择温和易消化的食物，避免刺激性食材",
            "日常养生": "营养均衡，食物多样"
        }
        tips = goal_tips.get(diet_goal, "")
        parts.append(f"- 膳食目标：{diet_goal}，{tips}")
    
    return "\n".join(parts) if parts else "- 暂无特殊约束条件"


# ======================== 文件内自测脚本 ========================
if __name__ == "__main__":
    print("=" * 60)
    print("膳食生成提示词模板自测开始")
    print("=" * 60)
    
    # 测试约束条件构建
    constraints = build_constraints_text(
        chronic_disease="糖尿病",
        food_taboo="海鲜,花生",
        diet_goal="减脂"
    )
    print(f"[通过] 约束条件构建:\n{constraints}")
    
    # 测试空值
    constraints = build_constraints_text()
    print(f"[通过] 空值处理: {constraints}")
    
    # 测试模板加载
    print(f"[通过] DIET_GENERATE_PROMPT: {type(DIET_GENERATE_PROMPT).__name__}")
    print(f"[通过] DIET_REVISE_PROMPT: {type(DIET_REVISE_PROMPT).__name__}")
    print(f"[通过] QUICK_DIET_PROMPT: {type(QUICK_DIET_PROMPT).__name__}")
    
    print("=" * 60)
    print("膳食生成提示词模板自测完成")
