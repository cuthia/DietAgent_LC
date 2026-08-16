"""
膳食生成提示词模板 - 用于生成结构化的膳食方案

功能：
1. 定义膳食生成的Prompt模板
2. 规定输出格式为JSON
3. 结合用户信息、知识库、约束条件生成方案
"""

from langchain_core.prompts import ChatPromptTemplate


# ========== 膳食生成主模板 ==========

# JSON 输出格式示例（独立字符串，避免与模板变量语法冲突）
# 结构说明（支持多天/单日）：
# - plan_days: 生成的天数（1=单日, 3=三天, 7=一周 …）
# - days: 长度为 plan_days 的数组，每一天都包含 day_num/day_label/date 与三餐+加餐
# - 当 plan_days == 1 时，为了兼容旧客户端，仍然同时输出顶层的
#   breakfast/lunch/dinner/snack/total_calories 字段，内容与 days[0] 对齐
DIET_JSON_FORMAT = '''```json
{
  "plan_name": "方案名称（如：一周减脂食谱、三天控糖餐单、单日养生搭配）",
  "plan_days": 7,
  "days": [
    {
      "day_num": 1,
      "day_label": "第1天（周一）",
      "date": "建议日期，可为空字符串",
      "breakfast": {
        "items": [
          {"name": "食材名称","amount": "用量（如100g、1个、1碗）","calories": 300,"protein": 15,"tips": "小贴士（可选）"}
        ],
        "total_calories": 500,
        "cooking_method": "蒸、煮",
        "tips": "早餐整体建议"
      },
      "lunch": {
        "items": [
          {"name": "食材名称","amount": "用量","calories": 600,"protein": 30,"tips": ""}
        ],
        "total_calories": 700,
        "cooking_method": "炒、炖",
        "tips": "午餐整体建议"
      },
      "dinner": {
        "items": [
          {"name": "食材名称","amount": "用量","calories": 400,"protein": 20,"tips": ""}
        ],
        "total_calories": 500,
        "cooking_method": "蒸、烤",
        "tips": "晚餐整体建议"
      },
      "snack": {
        "items": [
          {"name": "食材名称","amount": "用量","calories": 100,"protein": 5,"tips": ""}
        ],
        "total_calories": 100,
        "tips": "加餐建议"
      },
      "day_total_calories": 1800,
      "day_note": "当日小提示（如：建议运动30分钟、饮水2000ml）"
    }
  ],
  "avg_daily_calories": 1800,
  "weekly_total_calories": 12600,
  "daily_target_calories": "建议的每日热量摄入",
  "nutrition_balance": {
    "protein": "蛋白质摄入评估",
    "carbs": "碳水化合物摄入评估",
    "fat": "脂肪摄入评估",
    "fiber": "膳食纤维摄入评估",
    "assessment": "整体营养均衡评估"
  },
  "health_tips": ["建议1","建议2","建议3"],
  "disclaimer": "以上建议仅供参考，具体饮食请结合个人情况",

  "breakfast": { "items": [], "total_calories": 0 },
  "lunch":     { "items": [], "total_calories": 0 },
  "dinner":    { "items": [], "total_calories": 0 },
  "snack":     { "items": [], "total_calories": 0 },
  "total_calories": 0
}
```'''

# 用于生成膳食方案的核心Prompt
DIET_GENERATE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位专业的营养师AI助手，请根据用户的健康状况和需求，生成一份个性化的膳食方案。

## 严格规则
1. 所有营养数据必须基于提供的知识库内容，禁止编造任何数据
2. 食材选择必须符合用户的慢性疾病和食物忌口要求
3. 每餐热量分配：早餐30%、午餐40%、晚餐25%、加餐5%（按天计算）
4. 保证营养均衡：蛋白质、碳水化合物、脂肪、维生素、矿物质
5. 食物多样性：
   - 同一天内食材种类不少于10种
   - 相邻2天的主菜/主食至少有60%不重复（多日方案必填）
   - 严禁一周内重复完全一样的一天
6. 烹饪方式健康：优先推荐蒸、煮、炖、烤，少用油炸
7. 气候适配：当"当日天气与气候适配"段提供了 diet_hints 时，必须根据提示调整当日菜品：
   - 天热多用凉拌/冷食/清炒/消暑汤品，减少红烧炖煮火锅；
   - 天冷多用炖煮/煲汤/暖身食材；
   - 高湿度或降雨日，适当加入祛湿食材（薏米、赤小豆、冬瓜、山药等）。
8. 修正模式（重要！）：当"上一版食谱与修改意见"段非空时，必须遵守：
   - **基于上一版做增量修改**，不要重新生成完全无关的方案
   - 用户满意的菜品（未被提及的部分）尽量保留，仅替换用户明确不满的部分
   - 修改后的总热量与营养结构必须保持稳定（波动 ≤ 10%）
   - 输出方案的 plan_name 应体现"v2/修订版"等标识

## 生成天数要求（非常重要！）
请先从"用户需求"中理解用户想要的**天数范围**，按照要求生成对应天数：
- 包含"一周"、"7天"、"七天"、"一礼拜"、"weekly"等字样 → plan_days=7，生成7天完整方案
- 包含"三天"、"3天"、"三日" → plan_days=3
- 包含"两天"、"2天" → plan_days=2
- 包含"五天"、"5天"、"工作日" → plan_days=5
- 没有明确天数、只说"一份/一套/一个食谱/一天/今日/单日" → 默认 plan_days=1

## 输出格式（必须严格遵守！）
请输出以下JSON格式的膳食方案，所有字段严格遵守：

{json_format}

## 重要提醒
- 必须严格检查食材是否符合用户的慢病要求
- 必须避免用户的食物忌口
- 如果知识库中没有的数据，请标注为估算值
- 多日方案请在 days 数组中给出每一天的三餐 + 加餐，并在 day_note 中给出当日提醒；
  单日方案(plan_days=1)除 days[0] 外，请同时把 days[0] 的早/午/晚/加餐复制到
  JSON 顶层的 breakfast/lunch/dinner/snack 字段，并把 day_total_calories 复制到
  顶层 total_calories，以兼容旧客户端展示。"""),

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

## 当日天气与气候适配（请作为食材选择+烹饪方式的重要参考）
{weather_context}

## 上一版食谱与修改意见（仅"修正模式"启用，正常生成时为"无"）
{prev_diet_context}

请根据以上信息，为用户生成一份完整的膳食方案。""")
]).partial(json_format=DIET_JSON_FORMAT)


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
