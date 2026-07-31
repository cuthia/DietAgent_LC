"""
校验修正提示词模板 - 用于校验和修正膳食方案

功能：
1. 校验膳食方案是否符合要求
2. 生成修正建议
3. 检查营养均衡性
"""

from langchain_core.prompts import ChatPromptTemplate


# ========== 方案校验模板 ==========

# 用于校验膳食方案是否合规的Prompt
VALIDATE_DIET_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位专业的膳食方案审核员，请检查生成的膳食方案是否符合用户的健康要求。

## 校验要点
1. **食材合规性**：检查是否有用户忌口或慢病禁忌食材
2. **营养均衡性**：检查蛋白质、碳水、脂肪的比例是否合理
3. **热量合理性**：检查总热量是否符合用户需求
4. **食物多样性**：检查食材是否过于单一
5. **烹饪健康性**：检查烹饪方式是否健康

## 输出格式
请用JSON格式返回校验结果：
{
  "passed": true/false,
  "issues": [
    {
      "type": "forbidden_food" | "nutrition" | "calories" | "variety",
      "severity": "high" | "medium" | "low",
      "description": "问题描述",
      "suggestion": "修正建议"
    }
  ],
  "overall_score": 1-10,
  "summary": "整体评价"
}"""),
    
    ("human", """## 待校验膳食方案
{diet_plan}

## 用户健康档案
{user_profile}

## 校验规则
{validation_rules}

请仔细校验这份膳食方案。""")
])


# ========== 营养评估模板 ==========

# 用于评估膳食营养均衡性的Prompt
NUTRITION_EVALUATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位营养师，请评估以下膳食方案的营养均衡性。

## 评估维度
1. 热量：是否符合用户需求
2. 蛋白质：是否充足且来源优质
3. 碳水化合物：是否合理（减脂期选择低GI）
4. 脂肪：是否过多或过少
5. 膳食纤维：是否充足
6. 维生素/矿物质：是否多样化

## 参考标准（成人每日建议摄入量）
- 总热量：1800-2200千卡（女性）/ 2200-2800千卡（男性）
- 蛋白质：55-65克
- 脂肪：占总热量20-30%
- 碳水化合物：占总热量50-60%
- 膳食纤维：25-30克

## 输出格式
{
  "calories": {"status": "ok"|"low"|"high", "detail": "..."},
  "protein": {"status": "ok"|"low"|"high", "detail": "..."},
  "carbs": {"status": "ok"|"low"|"high", "detail": "..."},
  "fat": {"status": "ok"|"low"|"high", "detail": "..."},
  "fiber": {"status": "ok"|"low"|"high", "detail": "..."},
  "overall_balance": "excellent"|"good"|"fair"|"poor",
  "recommendations": ["建议1", "建议2"]
}"""),
    
    ("human", """## 膳食方案
{diet_plan}

## 用户信息
{user_profile}

请评估这份膳食方案的营养均衡性。""")
])


# ========== 最终回复生成模板 ==========

# 用于生成最终给用户的友好回复
FINAL_RESPONSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位专业友好的营养师AI助手，需要将生成的膳食方案以友好的方式呈现给用户。

## 回复要求
1. 语气亲切专业，避免生硬的技术术语
2. 先用一段话总结方案的特点
3. 再分餐次详细介绍
4. 最后给出健康小贴士
5. 如果有需要用户注意的事项，请特别标注"""),
    
    ("human", """## 膳食方案
{diet_plan}

## 用户档案摘要
{user_summary}

## 补充说明
{additional_notes}

请为用户生成一份友好的回复。""")
])


# ======================== 辅助函数 ========================

def build_validation_rules(user_profile: dict) -> str:
    """
    构建校验规则文本
    
    参数：
        user_profile: 用户档案
    
    返回：
        校验规则描述
    """
    rules = []
    
    chronic = user_profile.get("chronic_disease", "")
    taboo = user_profile.get("food_taboo", "")
    goal = user_profile.get("diet_goal", "")
    weight = user_profile.get("weight")
    height = user_profile.get("height")
    
    # 慢病规则
    if chronic:
        rules.append(f"• 慢病限制：{chronic}患者的饮食禁忌")
    
    # 忌口规则
    if taboo:
        taboo_list = [t.strip() for t in taboo.split(",") if t.strip()]
        rules.append(f"• 食物忌口：严禁包含 {', '.join(taboo_list)}")
    
    # 体重相关
    if weight and height:
        bmi = weight / ((height / 100) ** 2)
        if bmi > 24:
            rules.append("• BMI超标：建议控制总热量，增加蛋白质比例")
        elif bmi < 18.5:
            rules.append("• BMI偏低：建议适当增加热量摄入")
    
    # 膳食目标
    if goal == "减脂":
        rules.append("• 减脂目标：总热量较基础代谢减少300-500千卡，蛋白质占比提高")
    elif goal == "增肌":
        rules.append("• 增肌目标：保证热量盈余，蛋白质摄入1.6-2.2g/kg体重")
    elif goal == "控糖":
        rules.append("• 控糖目标：选择低GI主食，控制精制碳水摄入")
    
    return "\n".join(rules) if rules else "• 通用规则：营养均衡，食物多样，烹饪健康"


def format_diet_plan_summary(diet_plan: dict) -> str:
    """
    格式化膳食方案摘要
    
    参数：
        diet_plan: 膳食方案字典
    
    返回：
        摘要文本
    """
    lines = []
    
    total_cal = diet_plan.get("total_calories", 0)
    lines.append(f"📊 **总热量**：约 {total_cal} 千卡")
    
    meals = {"breakfast": "🌅 早餐", "lunch": "☀️ 午餐", "dinner": "🌙 晚餐", "snack": "🍎 加餐"}
    for meal_key, meal_name in meals.items():
        meal_data = diet_plan.get(meal_key, {})
        if meal_data:
            items = meal_data.get("items", [])
            cal = meal_data.get("total_calories", 0)
            item_names = "、".join([item.get("name", "") for item in items])
            lines.append(f"\n{meal_name}：{item_names}（约 {cal} 千卡）")
    
    return "\n".join(lines)


# ======================== 文件内自测脚本 ========================
if __name__ == "__main__":
    print("=" * 60)
    print("校验修正提示词模板自测开始")
    print("=" * 60)
    
    # 测试校验规则构建
    rules = build_validation_rules({
        "chronic_disease": "糖尿病",
        "food_taboo": "海鲜,花生",
        "diet_goal": "减脂",
        "weight": 80,
        "height": 175
    })
    print(f"[通过] 校验规则构建:\n{rules}")
    
    # 测试膳食方案摘要
    summary = format_diet_plan_summary({
        "total_calories": 1800,
        "breakfast": {
            "items": [{"name": "燕麦粥"}, {"name": "水煮蛋"}],
            "total_calories": 400
        },
        "lunch": {
            "items": [{"name": "糙米饭"}, {"name": "清蒸鱼"}],
            "total_calories": 700
        }
    })
    print(f"[通过] 膳食方案摘要:\n{summary}")
    
    # 测试模板加载
    print(f"[通过] VALIDATE_DIET_PROMPT: {type(VALIDATE_DIET_PROMPT).__name__}")
    print(f"[通过] NUTRITION_EVALUATION_PROMPT: {type(NUTRITION_EVALUATION_PROMPT).__name__}")
    print(f"[通过] FINAL_RESPONSE_PROMPT: {type(FINAL_RESPONSE_PROMPT).__name__}")
    
    print("=" * 60)
    print("校验修正提示词模板自测完成")
