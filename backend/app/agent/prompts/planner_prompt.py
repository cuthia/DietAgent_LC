"""
Planner 提示词模板 —— LLM 动态规划层（第一点改进）

功能：
1. 在 Agent 主流程开始前，让 LLM 根据用户 Query + 用户档案 + 对话历史
   判断用户真实意图，并输出结构化 ExecutionPlan 决策 JSON
2. 替代"硬编码 6 步流水线"，实现 Dynamic Planning
3. 支持 7 种意图分支路由：diet_plan / nutrition_qa / health_calc /
   food_eval / profile_update / casual_chat / info_collection

设计要点：
- 用 Pydantic BaseModel 描述输出 schema，配合 JsonOutputParser 严格校验
- Prompt 中所有字面量花括号必须用 {{ }} 转义（ChatPromptTemplate 模板语法）
- {json_schema} 是唯一占位符，由 .partial() 注入 ExecutionPlan 的 JSON Schema 字符串
"""

import json
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser


# ========== ExecutionPlan：Planner 输出的结构化决策 Schema ==========

class ExecutionPlan(BaseModel):
    """
    Planner 决策结果 Schema

    LLM 必须输出符合此 schema 的 JSON，主流程据此分支路由
    """
    intent: str = Field(
        description=(
            "意图枚举，必须是以下之一："
            "diet_plan / diet_revise / nutrition_qa / health_calc / food_eval / "
            "profile_update / casual_chat / info_collection"
        )
    )
    plan_days: int = Field(
        default=1,
        description="仅 diet_plan / diet_revise 意图有效：生成食谱的天数（1/2/3/5/7）"
    )
    need_rag: bool = Field(
        default=False,
        description="是否需要检索知识库"
    )
    rag_query_hint: Optional[str] = Field(
        default=None,
        description="RAG 检索关键词建议（need_rag=true 时必填）"
    )
    need_weather: bool = Field(
        default=False,
        description="是否需要结合当地天气决策（生成食谱、消暑/保暖建议时为 true）"
    )
    need_calc_tools: List[str] = Field(
        default_factory=list,
        description=(
            "健康计算器工具名列表，仅 health_calc 意图使用："
            "bmi_calc_tool / bmr_calc_tool / protein_target_tool"
        )
    )
    profile_updates: Optional[dict] = Field(
        default=None,
        description=(
            "profile_update 意图：要更新的字段字典，"
            "key 必须是 age/gender/height/weight/chronic_disease/"
            "food_taboo/region/diet_goal/taste_preference 之一"
        )
    )
    revision_feedback: Optional[str] = Field(
        default=None,
        description=(
            "仅 diet_revise 意图使用：用户对上一版食谱的具体修改意见原文摘要"
            "（如'鸡蛋太多、早餐换燕麦、不要汤'）。非 diet_revise 意图必须为 null"
        )
    )
    tools_to_call: List[str] = Field(
        default_factory=list,
        description="显式声明此轮要调用的工具名列表"
    )
    reasoning: str = Field(
        default="",
        description="决策推理过程：为什么选择这个 intent + 这些工具（中文）"
    )


# ========== JsonOutputParser 实例（可被 chain 复用） ==========

planner_parser = JsonOutputParser(pydantic_object=ExecutionPlan)


# ========== Planner Prompt ==========

# 把 ExecutionPlan schema 序列化成 JSON 字符串注入 Prompt
# 注意：字符串里包含大量花括号，但通过 .partial() 注入不会被 ChatPromptTemplate 二次解析
_EXECUTION_PLAN_SCHEMA_STR = json.dumps(
    ExecutionPlan.model_json_schema(),
    ensure_ascii=False,
    indent=2,
)

PLANNER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是膳食健康助手的 Planner（规划器）。
根据用户 Query + 用户档案 + 对话历史，在执行前先判断用户的真实意图，并决策后续要调用哪些工具与执行链路。

## 意图与决策规则

1. **diet_plan**：用户明确要食谱/餐单/饮食方案（包含"食谱、餐单、吃什么、方案、减脂餐、控糖餐、一周、一天"等关键词）。
   - 天数识别："一周/7天/七天"→7；"三天/3天"→3；"两天/2天"→2；"五天/工作日"→5；只说"一份/今天/一天/今日"→1
   - need_rag=true，rag_query_hint=慢病名+饮食+用户目标
   - need_weather=true（热天自动推荐消暑、冷天推荐暖身）
   - tools_to_call 通常为空（diet_plan 走专用 6 步链路）
   - **判别要点**：用户首次或独立提出要食谱，没有针对上一版的具体修改意见

2. **diet_revise**：用户已收到过食谱，对上一版食谱提出修改/重做/调整意见。
   - 触发关键词：换一个/重新生成/重新做/重做/改一下/调整/不要/太多/太少/不喜欢/换成/去掉/增加/减少/太油腻/太清淡/不饱/不够 等
   - **必须同时满足**：(a) 对话历史里最近一条 assistant 消息含完整食谱；(b) 用户当前 Query 在对那份食谱提具体意见
   - 把用户意见原文压缩成 1~3 条要点填入 revision_feedback（中文，分号分隔）
   - plan_days 沿用上一版天数（如无明确变更）
   - need_rag=true，need_weather=true（保持与 diet_plan 一致的链路）
   - tools_to_call 通常为空
   - **与 diet_plan 区别**：diet_revise 必须基于上一版做增量修改，不重新生成全新方案
   - **与 casual_chat 区别**：用户说"谢谢这个食谱不错"是 casual_chat；"鸡蛋太多了换一下"才是 diet_revise

3. **nutrition_qa**：用户询问任何**膳食/营养/饮食健康相关知识**的泛化问题（不针对具体个人档案做合规校验）。
   覆盖范围包括但不限于：
   - 营养成分/热量/升糖指数/GI（"番茄有多少卡路里"、"南瓜 GI 高吗"）
   - **食物相克/搭配禁忌**（"番茄不能和什么一起吃"、"虾和维生素 C 能同吃吗"）
   - **慢病饮食原则/禁忌清单**（"糖尿病不可以吃什么"、"高血压怎么吃"）
   - **特殊人群饮食**（"孕妇不能吃什么"、"老人补钙吃什么"）
   - 食材功效/选购/储存（"山药有什么营养"、"怎么挑新鲜鱼"）
   - 烹饪与营养保留（"蔬菜怎么煮不流失维生素"）
   - 饮食习惯/方法（"轻断食怎么吃"、"生酮饮食适合谁"）
   - need_rag=true，rag_query_hint=问题关键词+食材名/慢病名
   - tools_to_call 通常为空（由 LLM 在 ReAct 中自主决定是否补查 rag_search_tool）
   - **判别要点**：问题是"通用知识查询"，不依赖用户个人档案即可回答

4. **health_calc**：明确请求计算 BMI / BMR（基础代谢）/ 每日蛋白质目标 / 每日热量目标。
   - need_rag=false
   - need_calc_tools 填工具名列表：["bmi_calc_tool"] / ["bmr_calc_tool"] / ["protein_target_tool"]，可多选
   - 如果缺少身高/体重/年龄/性别 → 强制改 intent=info_collection，优先追问完善档案

5. **food_eval**：用户给出**具体食材**，要求针对**用户个人慢病+忌口**做合规校验。
   - 触发句式："我能吃 X 吗"、"X 适合我吗"、"我痛风/糖尿病，X 能吃吗"
   - 必须同时满足：(a) 有明确的具体食材名；(b) 隐含或明示"针对我个人"
   - need_rag=true（拿通用知识做对照），rag_query_hint=食材+慢病
   - tools_to_call=["food_taboo_check_tool"]（用个人档案做正向校验）
   - **与 nutrition_qa 的关键区别**：
     · "番茄不能和什么一起吃" → nutrition_qa（通用搭配禁忌知识）
     · "我痛风，能吃番茄吗" → food_eval（个人慢病合规校验）
     · "糖尿病不可以吃什么" → nutrition_qa（通用禁忌清单，不针对个人）
     · "我有糖尿病，豆腐能吃吗" → food_eval（针对个人慢病+具体食材）

6. **profile_update**：用户在对话中补充/修正档案（"哦我海鲜过敏"、"我是糖尿病"、"我 175cm/70kg"）。
   - 识别字段 → 填入 profile_updates dict
   - 字段名必须严格使用：age/gender/height/weight/chronic_disease/food_taboo/region/diet_goal/taste_preference
   - gender 只能是 "male" 或 "female"
   - tools_to_call=["user_profile_update_tool"]

7. **casual_chat**：问候/致谢/闲聊（"你好"、"谢谢"、"再见"）。
   - need_rag=false，need_weather=false，need_calc_tools=[]，tools_to_call=[]，profile_updates=null

8. **info_collection**：当用户 age/gender/height/weight 任一核心字段缺失，且用户意图是 diet_plan / diet_revise / health_calc / food_eval（需要个人数据的意图）时，强制把 intent 改回 info_collection，优先追问完善档案。
   - 注：nutrition_qa / casual_chat / profile_update 不强制补档案（用户只想问南瓜的 GI 或修正档案，不应被强制问身高）

## 输出格式（严格 JSON，禁止额外文字）

必须输出符合以下 JSON Schema 的对象，且所有字段齐全（无默认值的也要显式给）：

{json_schema}

## 重要提醒
- **同一个 Query 通常只匹配一个 intent**，禁止多意图混合
- 决策时必须同时考虑"用户档案是否足够支撑该意图的执行"，不够就降级 info_collection
- reasoning 字段必须写中文推理过程，便于日志排查与前端"规划思路"展示
- profile_updates 必须为 null（非 profile_update 意图）或 dict（profile_update 意图）
- revision_feedback 必须为 null（非 diet_revise 意图）或非空字符串（diet_revise 意图）
- 输出禁止包含任何注释、markdown 代码块标记、自然语言解释，必须是纯 JSON"""),

    ("human", """## 用户 Query
{user_query}

## 已有对话历史（最近 6 轮，用于识别上下文指代，如用户说"我是 175/70"实际是 profile_update）
{recent_history}

## 用户当前档案（空字段 = 缺失，需要留意是否触发 info_collection）
{user_profile_snapshot}

请输出规划 JSON。""")
]).partial(json_schema=_EXECUTION_PLAN_SCHEMA_STR)


# ======================== 文件内自测脚本 ========================
# 运行方式：在 backend/app 目录下执行  python -m agent.prompts.planner_prompt
if __name__ == "__main__":
    print("=" * 60)
    print("Planner Prompt 自测开始")
    print("=" * 60)

    # 测试1：模板加载
    print(f"[通过] 测试1 - PLANNER_PROMPT 加载: {type(PLANNER_PROMPT).__name__}")

    # 测试2：ExecutionPlan schema 序列化
    schema = ExecutionPlan.model_json_schema()
    assert "intent" in schema["properties"], "schema 缺少 intent 字段"
    assert "reasoning" in schema["properties"], "schema 缺少 reasoning 字段"
    print(f"[通过] 测试2 - ExecutionPlan schema: 含 {len(schema['properties'])} 个字段")

    # 测试3：parser 实例化
    print(f"[通过] 测试3 - planner_parser: {type(planner_parser).__name__}")

    # 测试4：模板渲染（检查占位符替换不报错）
    rendered = PLANNER_PROMPT.format_messages(
        user_query="一周减脂食谱",
        recent_history="[]",
        user_profile_snapshot='{"age": 25, "gender": "male", "height": 175, "weight": 70}',
    )
    assert len(rendered) == 2, "模板渲染后应返回 system + human 两条消息"
    assert "一周减脂食谱" in rendered[1].content, "user_query 未正确注入"
    assert "intent" in rendered[0].content, "json_schema 未正确注入到 system 段"
    print(f"[通过] 测试4 - 模板渲染: system 段 {len(rendered[0].content)} 字符, human 段 {len(rendered[1].content)} 字符")

    # 测试5：parser 解析合法 JSON
    sample_json = """
    {
      "intent": "diet_plan",
      "plan_days": 7,
      "need_rag": true,
      "rag_query_hint": "减脂饮食",
      "need_weather": true,
      "need_calc_tools": [],
      "profile_updates": null,
      "tools_to_call": [],
      "reasoning": "用户要一周减脂食谱，档案完整"
    }
    """
    parsed = planner_parser.parse(sample_json)
    assert parsed["intent"] == "diet_plan"
    assert parsed["plan_days"] == 7
    assert parsed["need_rag"] is True
    print(f"[通过] 测试5 - parser 解析: intent={parsed['intent']}, days={parsed['plan_days']}")

    print("=" * 60)
    print("Planner Prompt 自测完成（5/5）")
