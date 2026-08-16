"""
膳食搭配Agent - LCEL链式调用编排

功能：
将各个处理环节通过LangChain的LCEL（LangChain Expression Language）串联起来，
形成完整的膳食搭配Agent处理流程。

执行流程（第一点改进后）：
用户查询 → 信息收集 → LLM 动态规划(Planner) → 按 intent 分支路由：
  - diet_plan       → 知识检索 → 约束构建 → 食谱生成 → 校验 → 输出
  - nutrition_qa    → 条件 RAG 检索 → QA LLM 直接回答
  - health_calc     → 调用计算器工具(bmi/bmr/protein) → LLM 解释结果
  - food_eval       → 条件 RAG 检索 → food_taboo_check_tool → LLM 综合结论
  - profile_update  → user_profile_update_tool 写库 → 确认回复
  - casual_chat     → LLM 直接礼貌回复
  - info_collection → 输出追问消息

特点：
1. LLM Dynamic Planning：替代硬编码 6 步流水线
2. 多意图分支路由：从"只会出食谱"到"膳食健康全科助手"
3. 工具显式调用（@tool）：bind_tools 留给第二点改进
4. 每个环节可独立替换和测试
5. 支持同步和异步两种模式

"""

import logging
from typing import Dict, Any, Optional, List
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from agent.llm_client import LLMClient
from agent.tools.user_tool import get_user_info, format_profile_for_prompt
from agent.tools.rag_tool import search_knowledge, format_knowledge_for_llm
from agent.tools.validate_tool import validate_diet_plan, check_food_taboo
from agent.tools.region_tool import get_region_diet_features, adapt_diet_to_region
# 第四改进点：天气
from agent.tools.weather_tool import weather_tool as weather_tool_impl
# 第一改进点配套 @tool 工具
from agent.tools.health_calc_tool import bmi_calc_tool, bmr_calc_tool, protein_target_tool
from agent.tools.validate_tool import food_taboo_check_tool
from agent.tools.user_tool import user_profile_update_tool
from agent.tools.rag_tool import rag_search_tool
from agent.tools.region_tool import region_adapt_tool
from agent.prompts.diet_prompt import (
    DIET_GENERATE_PROMPT,
    DIET_REVISE_PROMPT,
    build_constraints_text
)
from agent.prompts.system_prompt import (
    INFO_COLLECT_PROMPT,
    get_follow_up_message
)
from agent.prompts.validate_prompt import (
    build_validation_rules,
    format_diet_plan_summary
)
# 第一改进点：Planner
from agent.prompts.planner_prompt import PLANNER_PROMPT, planner_parser, ExecutionPlan

# 日志记录器
logger = logging.getLogger(__name__)


def _normalize_chronic_disease(raw) -> str:
    """
    把 chronic_disease 字段统一解析为干净的疾病名称字符串。

    数据库里该字段可能存为多种格式：
      - None / ""           → 无慢病
      - "[]"                → 空列表的字符串形式（历史 bug 会拼成 "[]饮食"）
      - "['糖尿病']"         → 列表的 repr
      - '["高血压"]'         → JSON 列表字符串
      - "糖尿病"             → 纯字符串
      - ["痛风"]             → 真正的 list

    返回：
      第一个有意义的疾病名称（如 "糖尿病"）；无则返回 ""。
    """
    import json
    import ast

    if not raw:
        return ""

    # 已经是 list/tuple
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if item and str(item).strip():
                return str(item).strip()
        return ""

    # 字符串：尝试解析为 JSON / Python 字面量
    s = str(raw).strip()
    if not s or s in ("[]", "None", "null", "''", '""'):
        return ""

    parsed = None
    # 先试 JSON
    try:
        parsed = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        # 再试 Python literal（如 "['糖尿病']"）
        try:
            parsed = ast.literal_eval(s)
        except (ValueError, SyntaxError):
            parsed = None

    if isinstance(parsed, (list, tuple)):
        for item in parsed:
            if item and str(item).strip():
                return str(item).strip()
        return ""

    # 解析失败或解析出标量：原样返回（去掉首尾空白）
    return s


def _is_async_tool(tool) -> bool:
    """
    判断一个 LangChain @tool 是否是异步工具。

    LangChain 1.x 中 @tool 装饰的 async def 会暴露 .coroutine 属性；
    装饰的同步 def 不会。据此区分以选择 invoke / ainvoke 调用方式。
    """
    # StructuredTool 异步版有 .coroutine
    if hasattr(tool, "coroutine") and tool.coroutine is not None:
        return True
    return False


def _loose_parse_llm_json(raw_text: str) -> Dict[str, Any]:
    """
    宽松解析 LLM 返回的 JSON。

    JsonOutputParser 对 7 天食谱这种超长 JSON 有时会因为：
      - 外面包了 ```json ... ``` 代码块；
      - JSON 结尾后还有自然语言说明；
      - 末尾漏了 ] 或 }（模型生成长文本时不完整）；
      - 转义字符异常（中文引号、多余逗号）
    而抛错或返回 None。这里做兜底：
      1. 从 `` ` `` / `json` / `{}` 里抠第一段匹配的 JSON；
      2. json.JSONDecoder 用 raw_decode，在第一个合法 JSON 结尾处截断；
      3. 都失败返回 {}。
    """
    import re, json as _json
    if not raw_text:
        return {}
    s = str(raw_text).strip()

    # 1. 从 markdown ```json ... ``` 里抠代码块
    md_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s, re.IGNORECASE)
    if md_match:
        candidate = md_match.group(1).strip()
        # 尝试直接解析
        try:
            return _json.loads(candidate)
        except _json.JSONDecodeError:
            pass  # 继续尝试宽松解析
        s = candidate or s

    # 2. 找到第一个 { ... 最外层 JSON 对象（可能不完整），逐字符加宽匹配
    #    用 raw_decode 解析第一个合法 JSON 片段
    try:
        decoder = _json.JSONDecoder()
        # 找到第一个 { 或 [（同时兼容数组，但食谱根是对象）
        start = len(s)
        for ch in ('{', '['):
            pos = s.find(ch)
            if 0 <= pos < start:
                start = pos
        if start >= len(s):
            return {}
        obj, _end = decoder.raw_decode(s[start:])
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            # 少数情况返回 [ {...} ]，包一层结构
            return {"days": obj} if any(isinstance(x, dict) for x in obj) else {}
    except (_json.JSONDecodeError, ValueError):
        pass

    # 3. 最后一搏：补末尾花括号再解析（7天长JSON有时末尾被截断了}）
    brace = s.count('{') - s.count('}')
    bracket = s.count('[') - s.count(']')
    if brace > 0 or bracket > 0:
        fixed = s.rstrip()
        if bracket > 0:
            fixed += "]" * bracket
        if brace > 0:
            fixed += "}" * brace
        try:
            return _json.loads(fixed)
        except _json.JSONDecodeError:
            pass

    return {}


def _sanitize_diet_plan(dp):
    """
    把 LLM 返回的膳食方案做标准化 + 兜底缺省值，保证后续 .get() 不崩。
    输入可以是 dict、None、或其他；输出一定是 dict 且含所有关键 key。
    """
    # 完全不是 dict → 返回一份"空的标准结构"，保证 .get(key) 任何 key 都不是 None
    if not isinstance(dp, dict):
        return {
            "plan_name": "",
            "plan_days": 0,
            "total_calories": 0,
            "avg_daily_calories": 0,
            "weekly_total_calories": 0,
            "health_tips": [],
            "disclaimer": "",
            "breakfast": {"items": [], "total_calories": 0},
            "lunch":     {"items": [], "total_calories": 0},
            "dinner":    {"items": [], "total_calories": 0},
            "snack":     {"items": [], "total_calories": 0},
            "days": [],
        }

    # 顶层缺省值（单日方案兜底）
    dp.setdefault("plan_name", "")
    dp.setdefault("plan_days", 0)
    dp.setdefault("total_calories", 0)
    dp.setdefault("avg_daily_calories", 0)
    dp.setdefault("weekly_total_calories", 0)
    dp.setdefault("health_tips", [])
    dp.setdefault("disclaimer", "")

    # 归一化 total_calories/avg_daily_calories/weekly_total_calories（必须 int）
    for k in ("total_calories", "avg_daily_calories", "weekly_total_calories"):
        v = dp.get(k)
        try:
            dp[k] = int(v) if v not in (None, "") else 0
        except (ValueError, TypeError):
            dp[k] = 0

    # 顶层三餐：如果不是 dict，补空（兼容单日照旧显示）
    for meal in ("breakfast", "lunch", "dinner", "snack"):
        if not isinstance(dp.get(meal), dict):
            dp[meal] = {"items": [], "total_calories": 0}
        else:
            md = dp[meal]
            md.setdefault("items", [])
            md.setdefault("total_calories", 0)
            try:
                md["total_calories"] = int(md["total_calories"] or 0)
            except (ValueError, TypeError):
                md["total_calories"] = 0
            if not isinstance(md["items"], list):
                md["items"] = []

    # 归一化 days[]
    days = dp.get("days")
    if isinstance(days, (list, tuple)):
        cleaned_days = []
        for d in days:
            if not isinstance(d, dict):
                continue
            d.setdefault("day_num", len(cleaned_days) + 1)
            d.setdefault("day_label", f"第{d.get('day_num')}天")
            d.setdefault("day_total_calories", 0)
            try:
                d["day_total_calories"] = int(d["day_total_calories"] or 0)
            except (ValueError, TypeError):
                d["day_total_calories"] = 0
            d.setdefault("day_note", "")
            for meal in ("breakfast", "lunch", "dinner", "snack"):
                if not isinstance(d.get(meal), dict):
                    d[meal] = {"items": [], "total_calories": 0}
                else:
                    md = d[meal]
                    md.setdefault("items", [])
                    md.setdefault("total_calories", 0)
                    try:
                        md["total_calories"] = int(md["total_calories"] or 0)
                    except (ValueError, TypeError):
                        md["total_calories"] = 0
                    if not isinstance(md["items"], list):
                        md["items"] = []
            cleaned_days.append(d)
        dp["days"] = cleaned_days
    else:
        dp["days"] = []

    # 如果 days[] 非空，顺便补平均/合计热量
    if dp["days"]:
        if not dp.get("plan_days"):
            dp["plan_days"] = len(dp["days"])
        if not dp.get("avg_daily_calories"):
            total = sum((d.get("day_total_calories") or 0) for d in dp["days"])
            dp["avg_daily_calories"] = int(total / len(dp["days"])) if dp["days"] else 0
            if not dp.get("weekly_total_calories") and len(dp["days"]) >= 7:
                dp["weekly_total_calories"] = total

    return dp


class DietAgentChain:
    """
    膳食搭配Agent - LCEL链式调用
    
    将Agent的各个处理环节封装为可组合的函数。
    通过LangChain的LCEL运算符（|）将各环节串联成完整的处理链。

    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        初始化Agent链式调用

        参数：
            llm_client: LLM客户端实例，为None时自动从配置创建
        """
        # 初始化LLM客户端
        self.llm_client = llm_client or LLMClient.from_config()
        self.llm = self.llm_client.get_llm()

        # 输出解析器
        self.json_parser = JsonOutputParser()

        # ========== 第一改进点：LLM Planner 链 ==========
        # LCEL 链：PLANNER_PROMPT | LLM | JsonOutputParser
        # 用于在主流程开始时动态决策意图与工具调用
        self.planner_chain = PLANNER_PROMPT | self.llm | planner_parser

        # ========== 第一改进点配套 @tool 工具注册表 ==========
        # 显式调用模式：chain 根据 Planner 决策直接 await tool.ainvoke(...)
        self.tool_map = {
            "bmi_calc_tool": bmi_calc_tool,
            "bmr_calc_tool": bmr_calc_tool,
            "protein_target_tool": protein_target_tool,
            "food_taboo_check_tool": food_taboo_check_tool,
            "user_profile_update_tool": user_profile_update_tool,
            "rag_search_tool": rag_search_tool,
            "region_adapt_tool": region_adapt_tool,
            "weather_tool": weather_tool_impl,
        }

        # ========== 第二改进点：bind_tools Function Calling ==========
        # 把全部 @tool 注册给 LLM，让 LLM 自主决定调哪些工具 + 填什么参数
        # 形成 标准 ReAct 闭环：LLM 决策 → 工具执行(Observation) → LLM 基于观察生成结论
        self.llm_with_tools = self.llm.bind_tools(list(self.tool_map.values()))

        # ========== 第三改进点：混合 LCEL 编排 ==========
        # 把每个 step 包成 RunnableLambda 实例属性，线性段用 | 串成 sub-chain
        # 消除 RunnableLambda / RunnablePassthrough import 但不用的尴尬
        # 对外暴露 as_runnable() 统一 Runnable 接口（支持 ainvoke / abatch / callbacks）
        self.r_collect_info      = RunnableLambda(self.step_collect_info)
        self.r_plan_execution    = RunnableLambda(self.step_plan_execution)
        self.r_retrieve          = RunnableLambda(self.step_retrieve_knowledge)
        self.r_retrieve_cond     = RunnableLambda(self.step_retrieve_knowledge_conditional)
        self.r_build_constraints = RunnableLambda(self.step_build_constraints)
        self.r_fetch_weather     = RunnableLambda(self.step_fetch_weather)
        self.r_fetch_prev_plan   = RunnableLambda(self.step_fetch_prev_plan)
        self.r_generate_diet     = RunnableLambda(self.step_generate_diet)
        self.r_validate_diet     = RunnableLambda(self.step_validate_diet)
        self.r_format_output     = RunnableLambda(self.step_format_output)

        # diet_plan 意图的线性 5 连段（检索→约束→天气→生成→校验），用 | 串成真正的 LCEL 链
        self.diet_linear_chain = (
            self.r_retrieve
            | self.r_build_constraints
            | self.r_fetch_weather
            | self.r_generate_diet
            | self.r_validate_diet
        )

        # diet_revise 意图：在 diet_plan 链基础上多插一个"取上一版食谱"环节
        # （step_fetch_prev_plan 内部会判断 intent，非 diet_revise 时直接透传，所以可以安全插入）
        self.diet_revise_chain = (
            self.r_retrieve
            | self.r_build_constraints
            | self.r_fetch_weather
            | self.r_fetch_prev_plan
            | self.r_generate_diet
            | self.r_validate_diet
        )

        logger.info("DietAgentChain初始化完成（含 Planner 链 + 8 意图 + 8 个 @tool + bind_tools + LCEL sub-chain + 修正闭环）")
    
    # ========== 环节1：信息收集 ==========
    
    async def step_collect_info(
        self, 
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        环节1：收集并验证用户信息
        
        功能：
        1. 查询用户完整健康档案
        2. 检查信息是否完善（必要字段：年龄、性别、身高、体重）
        3. 如果信息不足，生成追问
        
        参数：
            input_data: 输入数据，包含 user_id 和 user_query
        
        返回：
            {
                "user_id": 用户ID,
                "user_query": 用户原始查询,
                "user_profile": 用户健康档案,
                "profile_text": 格式化后的档案文本（供LLM使用）,
                "information_complete": 信息是否完善,
                "follow_up": 追问消息（如信息不完善）
            }
        """
        user_id = input_data["user_id"]
        user_query = input_data["user_query"]
        
        # 查询用户档案
        user_profile = await get_user_info(user_id)
        
        # 格式化档案为文本
        profile_text = format_profile_for_prompt(user_profile)
        
        # 检查信息是否完善
        key_fields = ["age", "gender", "height", "weight"]
        missing_fields = []
        for field in key_fields:
            if not user_profile.get(field):
                missing_fields.append(field)
        
        # 检查其他可选但重要的字段
        for field in ["chronic_disease", "food_taboo", "region", "diet_goal"]:
            if not user_profile.get(field):
                missing_fields.append(field)
        
        # 判断信息是否完善
        # 核心字段缺失时需要追问，其他字段可以后续补充
        core_missing = [f for f in missing_fields if f in key_fields]
        information_complete = len(core_missing) == 0
        
        # 生成追问消息
        follow_up = ""
        if not information_complete:
            follow_up = get_follow_up_message(core_missing)
        
        result = {
            "user_id": user_id,
            "user_query": user_query,
            "user_profile": user_profile,
            "profile_text": profile_text,
            "information_complete": information_complete,
            "follow_up": follow_up
        }
        
        logger.info(f"[环节1] 信息收集完成: user_id={user_id}, complete={information_complete}")
        return result

    # ========== 环节 0：LLM 动态规划（第一改进点核心） ==========

    async def step_plan_execution(
        self,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        环节 0：LLM 动态规划（Dynamic Planning）

        在信息收集之后、知识检索之前运行。
        调用 planner_chain（PLANNER_PROMPT | LLM | JsonOutputParser）让 LLM 根据
        用户 Query + 用户档案 + 对话历史 输出结构化 ExecutionPlan，包含：
        - intent：意图枚举（7 选 1）
        - plan_days / need_rag / rag_query_hint / need_weather
        - need_calc_tools / profile_updates / tools_to_call / reasoning

        写入 input_data["plan"]，主流程据此分支路由。

        异常兜底：Planner 失败时降级为 diet_plan 意图（保持原 6 步流程不破坏）
        """
        user_query = input_data["user_query"]
        user_profile = input_data.get("user_profile", {})

        # 用户档案快照（空字段也会显示，便于 LLM 判断是否触发 info_collection）
        profile_snapshot = {
            "age": user_profile.get("age"),
            "gender": user_profile.get("gender", ""),
            "height": user_profile.get("height"),
            "weight": user_profile.get("weight"),
            "chronic_disease": user_profile.get("chronic_disease", ""),
            "food_taboo": user_profile.get("food_taboo", ""),
            "region": user_profile.get("region", ""),
            "diet_goal": user_profile.get("diet_goal", ""),
            "taste_preference": user_profile.get("taste_preference", ""),
        }

        # 从 memory 取最近 6 轮对话历史（如可用）
        recent_history_str = "[]"
        try:
            from agent.memory import MemoryManager
            mem = MemoryManager()
            history = mem.get_conversation(
                input_data["user_id"],
                max_messages=12,  # 6 轮 = 12 条消息
            )
            if history:
                # 精简：只保留 role + content 前 80 字
                slim = []
                for msg in history[-12:]:
                    role = msg.get("role", "user")
                    content = (msg.get("content") or "")[:80]
                    slim.append({"role": role, "content": content})
                import json as _json
                recent_history_str = _json.dumps(slim, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"[环节0] 取对话历史失败（忽略）: {e}")

        try:
            plan = await self.planner_chain.ainvoke({
                "user_query": user_query,
                "recent_history": recent_history_str,
                "user_profile_snapshot": str(profile_snapshot),
            })

            # 兜底校验：plan 必须是 dict 且含 intent 字段
            if not isinstance(plan, dict) or "intent" not in plan:
                raise ValueError(f"Planner 输出格式异常: {plan}")

            # intent 合法性校验
            valid_intents = {
                "diet_plan", "diet_revise", "nutrition_qa", "health_calc", "food_eval",
                "profile_update", "casual_chat", "info_collection",
            }
            if plan["intent"] not in valid_intents:
                logger.warning(f"[环节0] Planner 输出未知 intent: {plan['intent']}，降级 diet_plan")
                plan["intent"] = "diet_plan"

            # 兜底默认值（防止 LLM 漏字段）
            plan.setdefault("plan_days", 1)
            plan.setdefault("need_rag", False)
            plan.setdefault("rag_query_hint", None)
            plan.setdefault("need_weather", False)
            plan.setdefault("need_calc_tools", [])
            plan.setdefault("revision_feedback", None)
            plan.setdefault("profile_updates", None)
            plan.setdefault("tools_to_call", [])
            plan.setdefault("reasoning", "")

            # 档案缺失强保护：核心字段缺失 + 需个人数据的意图 → 强制 info_collection
            core_missing = []
            for f in ("age", "gender", "height", "weight"):
                if not user_profile.get(f):
                    core_missing.append(f)
            needs_profile_intents = {"diet_plan", "diet_revise", "health_calc", "food_eval"}
            if core_missing and plan["intent"] in needs_profile_intents:
                logger.info(f"[环节0] 档案缺失({core_missing}) + intent={plan['intent']} → 降级 info_collection")
                plan["intent"] = "info_collection"
                plan["reasoning"] = (
                    f"档案核心字段缺失({core_missing})，"
                    f"原意图 {plan.get('reasoning', '')}".strip()
                )

            input_data["plan"] = plan
            logger.info(
                f"[环节0] Planner 完成: intent={plan['intent']}, "
                f"need_rag={plan['need_rag']}, tools={plan['tools_to_call']}, "
                f"reasoning={plan['reasoning'][:80]}"
            )
        except Exception as e:
            logger.exception(f"[环节0] Planner 异常，降级 diet_plan: {e}")
            input_data["plan"] = {
                "intent": "diet_plan",
                "plan_days": 1,
                "need_rag": True,
                "rag_query_hint": user_query,
                "need_weather": False,
                "need_calc_tools": [],
                "profile_updates": None,
                "tools_to_call": [],
                "reasoning": f"Planner 异常降级: {e}",
            }

        return input_data

    # ========== 第二改进点：_execute_tool_calls + step_react_with_tools ==========

    async def _execute_tool_calls(self, ai_msg) -> List:
        """
        统一工具执行器：处理 LLM 返回的 tool_calls，并发执行工具，返回 ToolMessage 列表。

        输入：上一轮 LLM 返回的 AIMessage（可能含 .tool_calls）
        输出：ToolMessage[]（每个工具的真实结果），喂回 LLM 形成 ReAct 闭环

        特性：
        1. 支持并发工具调用（多个 tool_calls 用 asyncio.gather 并发）
        2. 同步工具用 invoke，异步工具用 ainvoke（自动识别）
        3. 工具异常不抛出，包装为 error 字符串返回（防止单个工具失败打断整条链）
        """
        import asyncio
        from langchain_core.messages import ToolMessage

        if not hasattr(ai_msg, "tool_calls") or not ai_msg.tool_calls:
            return []

        async def _run_one(tc):
            tool_name = tc.get("name", "")
            args = tc.get("args") or {}
            t = self.tool_map.get(tool_name)
            if t is None:
                obs = f"错误：未找到工具 {tool_name}"
            else:
                try:
                    if _is_async_tool(t):
                        obs = await t.ainvoke(args)
                    else:
                        obs = t.invoke(args)
                except Exception as e:
                    logger.error(f"[tool_exec] {tool_name} 异常: {e}")
                    obs = {"error": f"工具执行异常: {e}"}
            # 统一转字符串（ToolMessage.content 必须是 str）
            if not isinstance(obs, str):
                import json as _json
                try:
                    obs = _json.dumps(obs, ensure_ascii=False, default=str)
                except Exception:
                    obs = str(obs)
            return ToolMessage(content=obs, tool_call_id=tc.get("id", ""), name=tool_name)

        # 并发执行所有 tool_calls
        results = await asyncio.gather(*[_run_one(tc) for tc in ai_msg.tool_calls])
        logger.info(f"[tool_exec] 执行 {len(results)} 个工具: {[r.name for r in results]}")
        return list(results)

    async def step_react_with_tools(
        self,
        input_data: Dict[str, Any],
        system_prompt: str,
        max_iterations: int = 2,
    ) -> str:
        """
        通用 ReAct 工具调用步骤（第二改进点核心）。

        流程：
          1. 构造初始 messages（system + human），system 里注入用户档案 + RAG 上下文
          2. LLM_WITH_TOOLS 第一轮：决定调哪些工具 + 填参数
          3. _execute_tool_calls 并发执行 → ToolMessage 追加回 messages
          4. LLM 第二轮：基于 Observation 生成最终结论
          5. max_iterations 控制最大轮次（防止死循环，默认 2 轮足够）

        参数：
            input_data: 含 user_query / user_profile / knowledge_context 等
            system_prompt: 该意图专属的 system 指令文本
            max_iterations: 最大 LLM 轮次（每轮可能含一次工具调用）

        返回：
            最终 AIMessage 的文本内容（Markdown）
        """
        from langchain_core.messages import SystemMessage, HumanMessage

        # 构造 system prompt：注入用户档案 + RAG 上下文
        profile = input_data.get("user_profile", {})
        profile_text = format_profile_for_prompt(profile) if profile else "（用户档案暂无）"
        knowledge = input_data.get("knowledge_context", "") or "（无相关知识库内容）"

        full_system = f"""{system_prompt}

## 用户档案
{profile_text}

## 参考知识（RAG 检索结果，若为空请诚实说明）
{knowledge}

## 工具使用说明
你可以调用以下工具来获取准确信息。工具调用规则：
1. 只在需要时调用工具（如计算 BMI、校验食材禁忌、检索知识）
2. 工具参数从用户档案中提取（如身高/体重/年龄等）
3. 拿到工具结果后，用清晰中文给出最终回答（Markdown 格式）
4. 禁止编造数据，必须基于工具结果或参考知识回答"""

        messages = [
            SystemMessage(content=full_system),
            HumanMessage(content=input_data["user_query"]),
        ]

        for i in range(max_iterations):
            ai_msg = await self.llm_with_tools.ainvoke(messages)
            messages.append(ai_msg)

            # 如果 LLM 没有调工具，直接返回最终回答
            if not getattr(ai_msg, "tool_calls", None):
                logger.info(f"[react] 第 {i+1} 轮：LLM 未调工具，直接返回")
                return ai_msg.content if hasattr(ai_msg, "content") else str(ai_msg)

            # 执行工具调用 → ToolMessage 追加
            tool_msgs = await self._execute_tool_calls(ai_msg)
            messages.extend(tool_msgs)
            logger.info(f"[react] 第 {i+1} 轮：执行 {len(tool_msgs)} 个工具，进入下一轮")

        # 达到 max_iterations，再调一次 LLM（不带 tools）生成最终回答
        final = await self.llm.ainvoke(messages)
        return final.content if hasattr(final, "content") else str(final)

    # ========== 通用：条件 RAG 检索（按 Planner 决策决定是否检索） ==========

    async def step_retrieve_knowledge_conditional(
        self,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        条件 RAG 检索：根据 Planner 的 need_rag 与 rag_query_hint 决定是否检索。

        - need_rag=False：跳过检索，knowledge_context=""
        - need_rag=True：用 rag_query_hint（优先）或 user_query 检索 top 5 条
        """
        plan = input_data.get("plan", {})
        if not plan.get("need_rag", False):
            input_data["knowledge_context"] = ""
            input_data["knowledge_results"] = []
            logger.info("[条件RAG] Planner 指示跳过检索")
            return input_data

        query = plan.get("rag_query_hint") or input_data["user_query"]
        try:
            docs = await rag_search_tool.ainvoke({
                "query": query,
                "category": "",
                "top_k": 5,
            })
        except Exception as e:
            logger.warning(f"[条件RAG] 检索失败: {e}")
            docs = []

        input_data["knowledge_results"] = docs
        input_data["knowledge_context"] = format_knowledge_for_llm(docs)
        logger.info(f"[条件RAG] 检索完成: query='{query}', 返回 {len(docs)} 条")
        return input_data

    # ========== 分支 1：casual_chat 闲聊 ==========

    async def step_casual_reply(
        self,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """casual_chat 意图：用最小 Prompt 礼貌回复，不调工具"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", "你是膳食健康助手。用户在闲聊/问候/致谢，请用 1~2 句简洁友好的中文回复，可顺带引导用户提出膳食问题。"),
            ("human", "{user_query}"),
        ])
        chain = prompt | self.llm
        try:
            resp = await chain.ainvoke({"user_query": input_data["user_query"]})
            text = resp.content if hasattr(resp, "content") else str(resp)
        except Exception as e:
            logger.error(f"[casual_chat] LLM 调用失败: {e}")
            text = "你好，我是您的膳食健康助手，有什么可以帮您的吗？"

        return {
            "success": True,
            "need_info": False,
            "diet_plan": None,
            "message": text,
            "plan": input_data.get("plan"),
        }

    # ========== 分支 2：nutrition_qa 营养问答 ==========

    async def step_nutrition_qa_answer(
        self,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        nutrition_qa 意图：基于 RAG 上下文用 LLM 回答（第二改进点：ReAct 模式）。

        覆盖所有膳食/营养/饮食健康相关知识类问题：
        - 营养成分/热量/GI
        - 食物相克/搭配禁忌
        - 慢病饮食原则/禁忌清单
        - 特殊人群饮食
        - 食材功效/选购/储存/烹饪营养保留
        - 饮食习惯/方法（轻断食/生酮等）

        LLM 可自主决定是否调用 rag_search_tool 补充检索（支持多角度检索）。
        流程：system_prompt + RAG 上下文 → LLM_WITH_TOOLS → 可能调工具 → 最终回答
        """
        system_prompt = """你是专业营养师AI助手。请回答用户关于膳食/营养/饮食健康的知识性问题。

## 回答范围（nutrition_qa 意图覆盖）
- 营养成分/热量/升糖指数/GI
- 食物相克/搭配禁忌（如"番茄不能和什么一起吃"）
- 慢病饮食原则/禁忌清单（如"糖尿病不可以吃什么"）
- 特殊人群饮食（孕妇/老人/儿童）
- 食材功效/选购/储存
- 烹饪与营养保留
- 饮食习惯/方法（轻断食/生酮/低碳水等）

## 回答要求
1. **必须基于参考知识或 rag_search_tool 检索结果**，禁止编造数据
2. 用清晰中文回答，可使用 Markdown（标题/列表/加粗/表格）
3. **多角度检索策略**（重要！）：若初次检索结果不充分，可调用 rag_search_tool 用不同关键词补查：
   - 食物相克类：先查"X 食物相克"，再查"X 搭配禁忌"
   - 慢病禁忌类：先查"X 病 饮食禁忌"，再查"X 病 不能吃什么"
   - 营养成分类：先查"X 营养"，再查"X 热量/维生素/矿物质"
4. 回答结构建议：
   - 先给结论（一句话直答）
   - 再展开细节（分点说明）
   - 最后给实用建议（如有）
5. 涉及"能不能/可不可以"的问题，给出明确判断 + 理由 + 替代方案
6. 涉及清单类问题（"XX 不能吃什么"），用表格或列表清晰呈现
7. **不要输出完整食谱 JSON**（这是 nutrition_qa 而非 diet_plan）
8. **不要调用 food_taboo_check_tool**（那是 food_eval 意图针对个人档案的校验工具，本意图是通用知识问答）"""

        try:
            text = await self.step_react_with_tools(input_data, system_prompt, max_iterations=3)
        except Exception as e:
            logger.error(f"[nutrition_qa] ReAct 调用失败: {e}")
            text = f"抱歉，回答生成失败：{e}"

        return {
            "success": True,
            "need_info": False,
            "diet_plan": None,
            "message": text,
            "plan": input_data.get("plan"),
        }

    # ========== 分支 3：health_calc 健康计算（第二改进点：ReAct 模式） ==========

    async def step_health_calc(
        self,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        health_calc 意图：LLM 自主调用 bmi/bmr/protein 工具并解读结果。

        第二改进点改造：从"chain 硬编码组装参数调用工具"升级为
        "LLM 从用户档案自主提取参数 + 自主决定调哪些计算器"。
        step_health_calc_explain 不再单独需要，合并到 ReAct 流程内。
        """
        system_prompt = """你是营养师AI助手。用户想计算健康指标（BMI/BMR/蛋白质目标）。

请根据用户档案中的身高/体重/年龄/性别/膳食目标，自主调用合适的计算器工具：
- bmi_calc_tool：计算 BMI（需要 height_cm, weight_kg）
- bmr_calc_tool：计算基础代谢率（需要 age, gender, height_cm, weight_kg）
- protein_target_tool：计算每日蛋白质目标（需要 weight_kg, diet_goal）

调用工具后，基于结果用清晰中文解读，包含：
1. 各指标数值与分类
2. 综合解读与膳食建议
回答使用 Markdown 格式。"""

        try:
            text = await self.step_react_with_tools(input_data, system_prompt, max_iterations=2)
        except Exception as e:
            logger.error(f"[health_calc] ReAct 调用失败: {e}")
            text = f"健康指标计算失败：{e}"

        return {
            "success": True,
            "need_info": False,
            "diet_plan": None,
            "message": text,
            "plan": input_data.get("plan"),
        }

    async def step_health_calc_explain(
        self,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        health_calc 意图：第二改进点后此方法不再单独使用（已合并到 step_health_calc 的 ReAct 流程）。
        保留方法签名是为了向后兼容 process() 调用链不报错——直接透传 input_data 的 message。
        """
        # ReAct 模式下 step_health_calc 已直接输出最终回复，这里不再二次调用 LLM
        # 如果 step_health_calc 没有产出 message（异常情况），返回兜底
        msg = input_data.get("message") or "健康指标计算完成。"
        return {
            "success": True,
            "need_info": False,
            "diet_plan": None,
            "message": msg,
            "plan": input_data.get("plan"),
        }

    # ========== 分支 4：food_eval 食材评估（第二改进点：ReAct 模式） ==========

    async def step_food_taboo_check(
        self,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        food_eval 意图：第二改进点后此方法不再单独使用（已合并到 step_food_eval_reply 的 ReAct 流程）。
        保留方法签名是为了向后兼容 process() 调用链不报错——直接透传 input_data。
        """
        return input_data

    async def step_food_eval_reply(
        self,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        food_eval 意图：LLM 自主调用 food_taboo_check_tool + rag_search_tool 综合判断。

        第二改进点改造：从"chain 硬编码提取食材名 + 调工具 + 拼 Prompt"升级为
        "LLM 自主识别食材 + 自主调禁忌校验工具 + 自主调 RAG 补充 + 综合结论"。
        """
        system_prompt = """你是营养师AI助手。用户询问某种食材对自己（有特定慢病/忌口）是否可以食用。

请自主决定调用哪些工具：
1. food_taboo_check_tool：校验食材是否违反用户慢病禁忌或忌口（需要 food_name, chronic_disease, food_taboo）
2. rag_search_tool：检索该食材的营养/慢病相关知识（需要 query）

从用户档案中提取 chronic_disease 和 food_taboo，从用户问题中识别 food_name。

输出格式（Markdown）：
1. 一句话结论：能吃 / 慎吃 / 禁食
2. 理由（结合用户慢病与忌口 + 工具结果 + 参考知识）
3. 如有推荐替代食材，列出
4. 摄入量建议"""

        try:
            text = await self.step_react_with_tools(input_data, system_prompt, max_iterations=2)
        except Exception as e:
            logger.error(f"[food_eval_reply] ReAct 调用失败: {e}")
            text = f"食材评估失败：{e}"

        return {
            "success": True,
            "need_info": False,
            "diet_plan": None,
            "message": text,
            "plan": input_data.get("plan"),
        }

    # ========== 分支 5：profile_update 档案修正 ==========

    async def step_apply_profile_update(
        self,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """profile_update 意图：调用 user_profile_update_tool 写库"""
        plan = input_data.get("plan", {})
        updates = plan.get("profile_updates") or {}
        user_id = input_data["user_id"]

        if not updates:
            input_data["profile_update_result"] = {
                "success": False,
                "message": "Planner 未识别到要更新的字段",
            }
            return input_data

        try:
            result = await user_profile_update_tool.ainvoke({
                "user_id": user_id,
                "updates": updates,
            })
        except Exception as e:
            logger.error(f"[profile_update] 工具调用异常: {e}")
            result = {"success": False, "message": str(e)}

        input_data["profile_update_result"] = result
        logger.info(f"[profile_update] user_id={user_id}, result={result}")
        return input_data

    async def step_profile_ack_reply(
        self,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """profile_update 意图：根据更新结果生成确认回复"""
        result = input_data.get("profile_update_result", {})
        plan = input_data.get("plan", {})

        if result.get("success"):
            updated = result.get("updated_fields", [])
            rejected = result.get("rejected_fields", [])
            msg = f"已为您更新档案字段：{', '.join(updated)}。"
            if rejected:
                msg += f"\n\n⚠️ 以下字段不在允许范围，已被拒绝：{', '.join(rejected)}。"
            msg += "\n\n如有其他需要调整的，请继续告诉我。"
        else:
            msg = f"档案更新失败：{result.get('message', '未知原因')}。" \
                  f"\n\n您可以重新表述要修改的内容（如：我海鲜过敏、我是糖尿病）。"

        # 让 LLM 润色一下确认语（可选，失败就用上面的兜底）
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", "你是膳食健康助手。用户刚刚更新了健康档案，请基于更新结果用 1~2 句中文确认并引导用户继续。"),
                ("human", "更新结果：{update_result}"),
            ])
            chain = prompt | self.llm
            import json as _json
            resp = await chain.ainvoke({
                "update_result": _json.dumps(result, ensure_ascii=False)
            })
            llm_text = resp.content if hasattr(resp, "content") else str(resp)
            if llm_text and len(llm_text) > 5:
                msg = llm_text
        except Exception as e:
            logger.debug(f"[profile_ack] LLM 润色失败，用兜底文案: {e}")

        return {
            "success": True,
            "need_info": False,
            "diet_plan": None,
            "message": msg,
            "plan": plan,
        }

    # ========== 环节2：知识检索 ==========
    
    async def step_retrieve_knowledge(
        self, 
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        环节2：从RAG知识库检索相关膳食知识
        
        功能：
        1. 根据用户查询和健康状况构建检索查询
        2. 从向量知识库检索相关内容
        3. 格式化检索结果供LLM使用
        
        参数：
            input_data: 包含用户信息的中间结果
        
        返回：
            在input_data基础上增加：
            {
                "knowledge_context": 格式化的知识文本,
                "knowledge_results": 原始检索结果
            }
        """
        if not input_data.get("information_complete", False):
            # 信息不完善时跳过检索
            input_data["knowledge_context"] = ""
            input_data["knowledge_results"] = []
            return input_data
        
        user_query = input_data["user_query"]
        user_profile = input_data["user_profile"]

        # 构建检索查询（结合用户健康状况）
        # chronic_disease 可能存为：None / "" / "[]" / "['糖尿病']" / "糖尿病" 等格式
        # 需要统一解析为有意义的疾病名称字符串，避免把字面量 "[]" 拼进检索 query
        raw_chronic = user_profile.get("chronic_disease", "")
        chronic = _normalize_chronic_disease(raw_chronic)  # 返回干净的疾病名（如"糖尿病"），无则 ""

        search_query = user_query
        if chronic:
            search_query = f"{chronic}饮食 {user_query}"

        # 从知识库检索
        category = None
        if chronic:
            category_map = {
                "糖尿病": "chronic_disease",
                "高血压": "chronic_disease",
                "痛风": "chronic_disease",
                "高血脂": "chronic_disease",
                "胃炎": "chronic_disease"
            }
            category = category_map.get(chronic)
        
        knowledge_results = await search_knowledge(
            query=search_query,
            category=category,
            top_k=5
        )
        
        # 格式化知识文本
        knowledge_context = format_knowledge_for_llm(knowledge_results)
        
        input_data["knowledge_context"] = knowledge_context
        input_data["knowledge_results"] = knowledge_results
        
        logger.info(f"[环节2] 知识检索完成: results={len(knowledge_results)}条")
        return input_data
    
    # ========== 环节3：约束构建 ==========
    
    async def step_build_constraints(
        self, 
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        环节3：构建膳食方案的约束条件
        
        功能：
        1. 整合慢性疾病、食物忌口、膳食目标等约束
        2. 获取地域饮食特点
        3. 生成约束条件文本
        
        参数：
            input_data: 包含用户信息和知识的中间结果
        
        返回：
            在input_data基础上增加：
            {
                "constraints": 约束条件文本,
                "region_features": 地域特点文本
            }
        """
        if not input_data.get("information_complete", False):
            input_data["constraints"] = ""
            input_data["region_features"] = ""
            return input_data
        
        user_profile = input_data["user_profile"]
        
        # 构建约束条件
        constraints = build_constraints_text(
            chronic_disease=user_profile.get("chronic_disease", ""),
            food_taboo=user_profile.get("food_taboo", ""),
            diet_goal=user_profile.get("diet_goal", "")
        )
        
        # 获取地域特点
        region = user_profile.get("region", "")
        region_features = ""
        if region:
            region_info = get_region_diet_features(region)
            region_features = f"""## 地域特点（{region_info['region']}）
- 主食推荐：{'、'.join(region_info['staple_foods'][:3])}
- 烹饪风格：{'、'.join(region_info['cooking_styles'][:2])}
- 口味偏好：{'、'.join(region_info['flavor_preferences'][:2])}
- 特色食材：{'、'.join(region_info['recommended_ingredients'][:3])}"""
        
        input_data["constraints"] = constraints
        input_data["region_features"] = region_features
        
        logger.info(f"[环节3] 约束构建完成")
        return input_data

    # ========== 环节 3.5：天气获取与上下文构建（第四改进点） ==========

    async def step_fetch_weather(
        self,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        根据用户档案地区 + Planner 的 need_weather 决策，获取天气数据并构造 Prompt 上下文。

        - Planner need_weather=false 或天气获取失败 → weather_context="（天气功能未启用或不可用）"
        - 成功 → 拼接温度/天气/湿度 + diet_hints 注入 weather_context
        """
        plan = input_data.get("plan", {})
        profile = input_data.get("user_profile", {})

        # 如果 Planner 明确说不需要天气，跳过
        if plan and not plan.get("need_weather", True):
            input_data["weather_data"] = {"ok": False, "fallback_reason": "Planner 指示跳过天气"}
            input_data["weather_context"] = "（Planner 指示本轮不需要天气适配）"
            logger.info("[天气] Planner 指示跳过")
            return input_data

        try:
            result = await weather_tool_impl.ainvoke({
                "region_name": profile.get("region") or None,
                "user_id": input_data["user_id"],
            })
        except Exception as e:
            logger.warning(f"[天气] 调用异常: {e}")
            result = {"ok": False, "fallback_reason": str(e)}

        input_data["weather_data"] = result

        if result.get("ok"):
            hints = result.get("diet_hints", [])
            temp = result.get("temperature")
            weather_desc = result.get("weather", "")
            humidity = result.get("humidity", "")
            region = result.get("region", "")
            hint_text = "\n".join(f"  - {h}" for h in hints) if hints else "  （无特殊气候提示）"
            input_data["weather_context"] = (
                f"**地区**：{region} | **温度**：{temp}℃ | **天气**：{weather_desc} | **湿度**：{humidity}%\n"
                f"**气候适配建议**：\n{hint_text}"
            )
            logger.info(f"[天气] {region} {temp}℃ {weather_desc}，{len(hints)} 条适配建议")
        else:
            input_data["weather_context"] = f"（天气信息不可用：{result.get('fallback_reason', '未知原因')}）"
            logger.info(f"[天气] 降级: {result.get('fallback_reason')}")

        return input_data

    # ========== 环节 3.6：上一版食谱获取（diet_revise 专用） ==========

    async def step_fetch_prev_plan(
        self,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        仅 diet_revise 意图调用：从 MemoryManager 取上一版保存的食谱，
        拼成 prev_diet_context 字符串，注入 step_generate_diet 的 prompt_input。

        - 没有历史食谱 → 自动降级为 diet_plan（不走修正模式）
        - prev_diet_context 默认 "无"，不破坏 diet_plan 链路
        """
        # 默认值：diet_plan 链路无需关心
        input_data.setdefault("prev_diet_context", "无")

        plan = input_data.get("plan", {})
        if plan.get("intent") != "diet_revise":
            return input_data

        try:
            from agent.memory import MemoryManager
            mem = MemoryManager()
            history = mem.get_diet_history(input_data["user_id"], limit=1)
            if not history:
                logger.warning("[diet_revise] 无历史食谱，自动降级 diet_plan")
                plan["intent"] = "diet_plan"
                plan["revision_feedback"] = None
                input_data["plan"] = plan
                return input_data

            prev = history[-1].get("plan") or {}
            if not prev or not (prev.get("days") or prev.get("breakfast") or prev.get("plan_name")):
                logger.warning("[diet_revise] 历史食谱结构无效，降级 diet_plan")
                plan["intent"] = "diet_plan"
                plan["revision_feedback"] = None
                input_data["plan"] = plan
                return input_data

            # 精简上一版食谱，避免 prompt 过长（只保留 plan_name/总热量/每日餐次摘要）
            summary = self._summarize_prev_plan(prev)
            feedback = plan.get("revision_feedback") or "（Planner 未提取到具体意见，请整体微调）"

            input_data["prev_diet_context"] = (
                f"**上一版食谱摘要**：\n{summary}\n\n"
                f"**用户修改意见**：{feedback}\n"
                f"**要求**：基于上一版做增量修改，保留用户满意的部分，仅调整被意见指出的部分。"
            )
            input_data["prev_diet_plan"] = prev
            logger.info(f"[diet_revise] 取到上一版食谱，注入修正上下文（feedback={feedback[:40]}...）")
        except Exception as e:
            logger.warning(f"[diet_revise] 取历史食谱异常，降级 diet_plan: {e}")
            plan = input_data.get("plan", {})
            plan["intent"] = "diet_plan"
            plan["revision_feedback"] = None
            input_data["plan"] = plan

        return input_data

    @staticmethod
    def _summarize_prev_plan(prev: Dict[str, Any]) -> str:
        """把上一版食谱精简成短文本，避免 prompt 爆炸"""
        lines = []
        name = prev.get("plan_name") or "未命名方案"
        total = prev.get("total_calories") or prev.get("avg_daily_calories") or "—"
        lines.append(f"- 方案名：{name}")
        lines.append(f"- 总热量：{total} kcal")

        days = prev.get("days") or []
        if days:
            lines.append(f"- 天数：{len(days)} 天")
            for i, d in enumerate(days[:3]):  # 最多展示前 3 天摘要
                date = d.get("date") or f"第{i+1}天"
                meals = []
                for key, label in [("breakfast","早"),("lunch","午"),("dinner","晚"),("snack","加")]:
                    m = d.get(key) or {}
                    items = m.get("items") or []
                    if items:
                        names = "、".join(it.get("name","") for it in items[:3])
                        meals.append(f"{label}:{names}")
                if meals:
                    lines.append(f"  · {date} → {' | '.join(meals)}")
        else:
            # 单日方案
            for key, label in [("breakfast","早餐"),("lunch","午餐"),("dinner","晚餐"),("snack","加餐")]:
                m = prev.get(key) or {}
                items = m.get("items") or []
                if items:
                    names = "、".join(it.get("name","") for it in items[:4])
                    lines.append(f"- {label}：{names}")
        return "\n".join(lines)

    # ========== 环节4：食谱生成 ==========
    
    async def step_generate_diet(
        self, 
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        环节4：调用LLM生成膳食方案
        
        功能：
        1. 将用户信息、知识库、约束条件等组装成Prompt
        2. 调用LLM生成膳食方案
        3. 解析LLM返回的JSON结果
        
        参数：
            input_data: 包含所有必要信息的中间结果
        
        返回：
            在input_data基础上增加：
            {
                "diet_plan": 生成的膳食方案（字典格式）,
                "raw_response": LLM原始响应文本
            }
        """
        if not input_data.get("information_complete", False):
            input_data["diet_plan"] = None
            input_data["raw_response"] = ""
            return input_data
        
        # 准备Prompt输入
        prompt_input = {
            "user_profile": input_data["profile_text"],
            "user_query": input_data["user_query"],
            "knowledge_context": input_data["knowledge_context"],
            "constraints": input_data["constraints"],
            "region_features": input_data["region_features"],
            "weather_context": input_data.get("weather_context", "（天气信息不可用）"),
            "prev_diet_context": input_data.get("prev_diet_context", "无"),
        }
        
        try:
            # 先跑 Prompt → LLM，拿到 AIMessage 原文（保留非 JSON 尾部/代码块信息）
            # 再用两层 JSON 解析：优先 JsonOutputParser，失败就宽松正则兜底
            llm_chain = DIET_GENERATE_PROMPT | self.llm
            llm_resp = await llm_chain.ainvoke(prompt_input)

            # 兼容 LangChain 不同返回类型：AIMessage / str
            if hasattr(llm_resp, "content") and llm_resp.content:
                raw_text = str(llm_resp.content)
            else:
                raw_text = str(llm_resp)

            input_data["raw_response"] = raw_text

            diet_plan: Dict[str, Any] = {}
            parse_error = None

            # 1) 优先用标准 JsonOutputParser
            try:
                diet_plan = self.json_parser.parse(raw_text)
            except Exception as pe:
                parse_error = f"JsonOutputParser 解析失败，进入兜底: {pe}"

            # 2) 若解析结果为空/None 或报错，尝试宽松提取
            if not isinstance(diet_plan, dict) or len(diet_plan) == 0 or not (
                diet_plan.get("days") or diet_plan.get("breakfast") or diet_plan.get("plan_name")
            ):
                loose = _loose_parse_llm_json(raw_text)
                if loose:
                    if parse_error:
                        logger.warning(f"[环节4] {parse_error}，宽松解析成功（keys={list(loose.keys())[:8]}）")
                    diet_plan = loose
                elif parse_error:
                    logger.error(f"[环节4] {parse_error}，宽松解析也为空")

            # 3) 标准化 + 兜底缺省值（保证后续所有 .get() 不会 NoneType）
            diet_plan = _sanitize_diet_plan(diet_plan)

            if not diet_plan:
                # 最终还是解析不到结构化数据 → 标记失败
                raise ValueError(
                    "LLM返回内容未能解析为膳食方案JSON，"
                    "请稍后重试或在提示中明确要求仅输出JSON。"
                )

            input_data["diet_plan"] = diet_plan

            # 7天/多天显示 day_count+avg，单日显示 total_cal
            days = diet_plan.get("days") or []
            if days:
                avg = diet_plan.get("avg_daily_calories") or 0
                weekly = diet_plan.get("weekly_total_calories") or 0
                cal_info = f"days={len(days)}, avg≈{avg}kcal, weekly≈{weekly}kcal"
            else:
                cal_info = f"total_cal={diet_plan.get('total_calories', 0)}千卡"
            logger.info(f"[环节4] 食谱生成完成: {cal_info}")
        except Exception as e:
            logger.exception(f"[环节4] 食谱生成失败: {e}")  # exception 带堆栈，方便定位
            # 失败时返回错误信息（仍用 dict 含 error 字段，让后续步骤统一判断）
            input_data["diet_plan"] = {
                "error": True,
                "message": f"膳食方案生成失败，请稍后重试。错误：{str(e)}"
            }
            input_data.setdefault("raw_response", str(e))
        
        return input_data
    
    # ========== 环节5：方案校验 ==========
    
    async def step_validate_diet(
        self, 
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        环节5：校验生成的膳食方案
        
        功能：
        1. 检查方案中是否包含用户忌口食材
        2. 检查方案是否符合慢病饮食要求
        3. 如果有问题，尝试修正方案
        
        参数：
            input_data: 包含生成方案的中间结果
        
        返回：
            在input_data基础上增加：
            {
                "validation_result": 校验结果,
                "final_diet_plan": 最终膳食方案（可能已修正）
            }
        """
        if not input_data.get("diet_plan") or input_data["diet_plan"].get("error"):
            input_data["validation_result"] = {"passed": False, "issues": []}
            input_data["final_diet_plan"] = input_data.get("diet_plan")
            return input_data
        
        diet_plan = input_data["diet_plan"]
        user_profile = input_data["user_profile"]
        
        # 使用工具进行快速校验
        validation_result = validate_diet_plan(diet_plan, user_profile)
        
        # 如果校验通过，直接使用
        if validation_result["passed"]:
            input_data["validation_result"] = validation_result
            input_data["final_diet_plan"] = diet_plan
            logger.info(f"[环节5] 方案校验通过")
            return input_data
        
        # 如果校验不通过，尝试修正
        logger.warning(f"[环节5] 方案校验未通过，开始修正: forbidden={validation_result['forbidden_items']}")
        
        try:
            # 使用LLM修正方案
            issues_text = "\n".join([
                f"- {item}" for item in validation_result["forbidden_items"]
            ])
            if validation_result["suggestions"]:
                issues_text += "\n修正建议：\n" + "\n".join([
                    f"- {s}" for s in validation_result["suggestions"]
                ])

            revise_input = {
                "diet_plan": str(diet_plan),
                "issues": issues_text,
                "user_profile": input_data["profile_text"]
            }

            # 修正同样两层解析：先拿 LLM 原文，再 JsonOutputParser + 宽松兜底
            revise_chain = DIET_REVISE_PROMPT | self.llm
            revised_resp = await revise_chain.ainvoke(revise_input)
            revised_raw = (
                str(revised_resp.content)
                if hasattr(revised_resp, "content") and revised_resp.content
                else str(revised_resp)
            )
            revised_plan: Dict[str, Any] = {}
            try:
                revised_plan = self.json_parser.parse(revised_raw)
            except Exception:
                pass
            if not isinstance(revised_plan, dict) or not (
                revised_plan.get("days") or revised_plan.get("breakfast")
            ):
                loose = _loose_parse_llm_json(revised_raw)
                if loose:
                    revised_plan = loose
            revised_plan = _sanitize_diet_plan(revised_plan)

            # 再次校验修正后的方案
            revised_validation = validate_diet_plan(revised_plan, user_profile) if revised_plan else {
                "passed": False, "forbidden_items": [], "issues": [], "suggestions": []
            }
            
            if revised_validation["passed"]:
                input_data["final_diet_plan"] = revised_plan
                input_data["validation_result"] = revised_validation
                logger.info(f"[环节5] 方案修正成功并通过校验")
            else:
                # 修正后仍有问题，保留原方案但标注警告
                input_data["final_diet_plan"] = diet_plan
                input_data["validation_result"] = validation_result
                input_data["validation_result"]["warning"] = "部分食材可能不符合要求，建议人工审查"
                logger.warning(f"[环节5] 方案修正后仍有问题")
                
        except Exception as e:
            logger.error(f"[环节5] 方案修正失败: {e}")
            input_data["final_diet_plan"] = diet_plan
            input_data["validation_result"] = validation_result
            input_data["validation_result"]["warning"] = "自动修正失败，建议人工审查"
        
        return input_data
    
    # ========== 环节6：结果输出 ==========
    
    async def step_format_output(
        self, 
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        环节6：格式化最终输出结果
        
        功能：
        1. 根据处理结果生成用户友好的输出
        2. 处理信息不完善的情况（返回追问）
        3. 处理错误情况
        
        参数：
            input_data: 完成所有处理环节的结果
        
        返回：
            最终输出：
            {
                "success": 是否成功,
                "need_info": 是否需要补充信息,
                "diet_plan": 膳食方案（如果有）,
                "follow_up": 追问消息（如果需要）,
                "message": 友好的回复消息
            }
        """
        # 情况1：信息不完善，需要追问
        if not input_data.get("information_complete", False):
            return {
                "success": True,
                "need_info": True,
                "diet_plan": None,
                "follow_up": input_data.get("follow_up", ""),
                "message": input_data.get("follow_up", "")
            }
        
        # 情况2：方案生成失败
        diet_plan = input_data.get("final_diet_plan")
        if not diet_plan or diet_plan.get("error"):
            return {
                "success": False,
                "need_info": False,
                "diet_plan": None,
                "follow_up": "",
                "message": "抱歉，膳食方案生成失败，请稍后重试。"
            }
        
        # 情况3：成功生成方案
        # 生成方案摘要
        summary = format_diet_plan_summary(diet_plan)
        
        # 添加校验警告（如果有）
        validation = input_data.get("validation_result", {})
        warning = validation.get("warning", "")
        if warning:
            summary += f"\n\n⚠️ **注意**：{warning}"
        
        return {
            "success": True,
            "need_info": False,
            "diet_plan": diet_plan,
            "follow_up": "",
            "message": summary
        }
    
    # ========== 第三改进点：对外暴露标准 Runnable 接口 ==========

    def as_runnable(self) -> RunnableLambda:
        """
        把 DietAgentChain 对外暴露成一个标准的 LangChain Runnable。

        - 输入：{ "user_id": int, "user_query": str }
        - 输出：process() 返回的标准 result dict
        - 支持的标准接口：ainvoke / astream / abatch / with_fallbacks / with_config(callbacks=[LangSmithTracer])

        用途：
        1. 接入 LangSmith 全链路追踪：as_runnable().with_config(callbacks=[tracer])
        2. 批量处理：as_runnable().abatch([{...}, {...}, {...}])
        3. 降级兜底：as_runnable().with_fallbacks([fallback_runnable])
        """
        async def _run(input_dict: Dict[str, Any]) -> Dict[str, Any]:
            return await self.process(
                user_id=input_dict["user_id"],
                user_query=input_dict["user_query"],
            )
        return RunnableLambda(_run).with_config(
            run_name="DietAgentChain",
            tags=["DietAgent", "Production"],
        )

    # ========== 主处理流程（第一改进点：基于 Planner 的动态分支路由） ==========

    async def process(
        self,
        user_id: int,
        user_query: str
    ) -> Dict[str, Any]:
        """
        执行完整的 Agent 处理流程（第一改进点：基于 LLM Planner 的动态分支路由）

        流程：
          信息收集 → LLM Planner 决策 → 按 intent 分支路由：
            - diet_plan       → 知识检索 → 约束构建 → 食谱生成 → 校验 → 输出（原 6 步）
            - nutrition_qa    → 条件 RAG → QA LLM 直接答
            - health_calc     → bmi/bmr/protein 工具 → LLM 解释
            - food_eval       → 条件 RAG → food_taboo_check_tool → LLM 综合结论
            - profile_update  → user_profile_update_tool 写库 → 确认回复
            - casual_chat     → LLM 直接礼貌回复
            - info_collection → step_format_output 输出追问

        参数：
            user_id: 用户ID
            user_query: 用户查询内容

        返回：
            最终处理结果，包含：
            {
                "success": 是否成功,
                "need_info": 是否需要补充信息,
                "diet_plan": 膳食方案（仅 diet_plan 意图非空）,
                "message": 回复消息,
                "plan": Planner 决策（含 intent/reasoning）,
                "processing_time_ms": 处理耗时
            }
        """
        import time
        start_time = time.time()

        try:
            # 初始化输入
            input_data = {
                "user_id": user_id,
                "user_query": user_query
            }

            # 环节 1：信息收集（识别档案缺失）
            input_data = await self.step_collect_info(input_data)

            # 环节 0：LLM 动态规划（Planner）
            input_data = await self.step_plan_execution(input_data)

            # 按 intent 分支路由
            intent = input_data["plan"]["intent"]
            logger.info(f"[Agent处理] 路由分支: intent={intent}")

            if intent == "casual_chat":
                result = await self.step_casual_reply(input_data)

            elif intent == "nutrition_qa":
                input_data = await self.step_retrieve_knowledge_conditional(input_data)
                result = await self.step_nutrition_qa_answer(input_data)

            elif intent == "health_calc":
                # 第二改进点：ReAct 模式，step_health_calc 直接返回最终 result
                result = await self.step_health_calc(input_data)

            elif intent == "food_eval":
                input_data = await self.step_retrieve_knowledge_conditional(input_data)
                input_data = await self.step_food_taboo_check(input_data)
                result = await self.step_food_eval_reply(input_data)

            elif intent == "profile_update":
                input_data = await self.step_apply_profile_update(input_data)
                result = await self.step_profile_ack_reply(input_data)

            elif intent == "info_collection":
                # 复用原有的 step_format_output，它会基于 information_complete=False 输出追问
                result = await self.step_format_output(input_data)

            elif intent == "diet_plan":
                # 第三改进点：diet_plan 线性段用 LCEL sub-chain（| 串联）
                # 原 4 行 await 改为 1 行 ainvoke，消除 RunnableLambda import 不用
                input_data = await self.diet_linear_chain.ainvoke(input_data)
                result = await self.step_format_output(input_data)

            elif intent == "diet_revise":
                # 食谱修正闭环：diet_revise_chain = retrieve → constraints → weather
                # → fetch_prev_plan → generate_diet → validate_diet
                # step_fetch_prev_plan 内部若无历史食谱会自动降级为 diet_plan
                input_data = await self.diet_revise_chain.ainvoke(input_data)
                # 降级后 intent 可能已被改为 diet_plan，同步更新本地变量
                intent = input_data.get("plan", {}).get("intent", intent)
                result = await self.step_format_output(input_data)

            else:
                # 兜底（不应该走到这里，Planner 已做合法性校验）
                logger.error(f"[Agent处理] 未知 intent: {intent}，降级 diet_plan")
                input_data = await self.step_retrieve_knowledge(input_data)
                input_data = await self.step_build_constraints(input_data)
                input_data = await self.step_generate_diet(input_data)
                input_data = await self.step_validate_diet(input_data)
                result = await self.step_format_output(input_data)

            # 添加处理时间与意图标记
            result["processing_time_ms"] = int((time.time() - start_time) * 1000)
            result["intent"] = intent

            logger.info(
                f"[Agent处理] 完成: user_id={user_id}, intent={intent}, "
                f"success={result.get('success')}, "
                f"time={result['processing_time_ms']}ms"
            )

            return result

        except Exception as e:
            elapsed = int((time.time() - start_time) * 1000)
            logger.error(f"[Agent处理] 异常: {e}, time={elapsed}ms")

            return {
                "success": False,
                "need_info": False,
                "diet_plan": None,
                "message": f"系统处理异常，请稍后重试。错误：{str(e)}",
                "processing_time_ms": elapsed
            }
    
    # ========== 流式处理 ==========

    async def _stream_text_chunks(self, text: str, chunk_size_min: int = 2, chunk_size_max: int = 5):
        """
        把最终答复文本切成小 chunk 逐段 yield，
        形成"逐字流式输出"的用户体验。
        不增加额外 LLM 调用，内容与同步版完全一致。
        """
        import asyncio
        import random
        if not text:
            return
        i = 0
        n = len(text)
        # 如果文本较短就逐字；较长就 2-5 字/块，总体打字速度适中
        if n < 60:
            chunk_size_min, chunk_size_max = 1, 2
        rng = random.Random(hash(text) & 0xFFFFFFFF)
        while i < n:
            sz = rng.randint(chunk_size_min, chunk_size_max)
            chunk = text[i:i + sz]
            i += sz
            yield chunk
            await asyncio.sleep(0.01 + rng.random() * 0.02)

    async def process_stream(
        self,
        user_id: int,
        user_query: str
    ):
        """
        流式处理（返回各环节进度事件 + 最终答复逐字流）

        第一改进点：同步加入 Planner 环节，支持 7 意图分支流式输出。

        事件类型：
        1. 阶段事件：{"stage":"xxx", "status":"start/complete", "message":"..."}
        2. 最终答复流：{"stage":"finalize", "status":"stream", "chunk":"逐字"}
        3. 完成事件：{"stage":"output", "status":"complete", "message":"处理完成", "data": result}
        """
        try:
            input_data = {
                "user_id": user_id,
                "user_query": user_query
            }

            # 环节1：信息收集
            yield {"stage": "collect_info", "status": "start", "message": "正在收集您的健康信息..."}
            input_data = await self.step_collect_info(input_data)
            yield {"stage": "collect_info", "status": "complete", "message": "健康信息收集完成"}

            # 环节0：LLM 动态规划（Planner）
            yield {"stage": "plan_execution", "status": "start", "message": "正在分析您的需求..."}
            input_data = await self.step_plan_execution(input_data)
            intent = input_data["plan"]["intent"]
            reasoning = input_data["plan"].get("reasoning", "")
            yield {
                "stage": "plan_execution", "status": "complete",
                "message": f"识别意图：{self._intent_label(intent)}",
                "intent": intent,
                "reasoning": reasoning,
            }

            # 按意图分支路由（与 process() 一致，但每个分支内发流式事件）
            if intent == "casual_chat":
                yield {"stage": "casual_reply", "status": "start", "message": "正在回复..."}
                result = await self.step_casual_reply(input_data)
                yield {"stage": "casual_reply", "status": "complete", "message": "回复完成"}

            elif intent == "nutrition_qa":
                yield {"stage": "retrieve_knowledge", "status": "start", "message": "正在检索膳食知识..."}
                input_data = await self.step_retrieve_knowledge_conditional(input_data)
                n_docs = len(input_data.get("knowledge_results", []))
                yield {"stage": "retrieve_knowledge", "status": "complete", "message": f"检索到 {n_docs} 条相关知识"}

                yield {"stage": "qa_answer", "status": "start", "message": "正在生成回答..."}
                result = await self.step_nutrition_qa_answer(input_data)
                yield {"stage": "qa_answer", "status": "complete", "message": "回答生成完成"}

            elif intent == "health_calc":
                # 第二改进点：ReAct 模式，合并计算+解读为一步
                yield {"stage": "health_calc", "status": "start", "message": "正在计算并解读健康指标..."}
                result = await self.step_health_calc(input_data)
                yield {"stage": "health_calc", "status": "complete", "message": "健康指标计算与解读完成"}

            elif intent == "food_eval":
                yield {"stage": "retrieve_knowledge", "status": "start", "message": "正在检索相关知识..."}
                input_data = await self.step_retrieve_knowledge_conditional(input_data)
                yield {"stage": "retrieve_knowledge", "status": "complete", "message": "知识检索完成"}

                yield {"stage": "food_taboo_check", "status": "start", "message": "正在校验食材禁忌..."}
                input_data = await self.step_food_taboo_check(input_data)
                verdict = input_data.get("food_eval_result", {}).get("verdict", "")
                yield {"stage": "food_taboo_check", "status": "complete", "message": f"校验完成：{self._verdict_label(verdict)}"}

                yield {"stage": "food_eval_reply", "status": "start", "message": "正在生成结论..."}
                result = await self.step_food_eval_reply(input_data)
                yield {"stage": "food_eval_reply", "status": "complete", "message": "结论生成完成"}

            elif intent == "profile_update":
                yield {"stage": "profile_update", "status": "start", "message": "正在更新您的档案..."}
                input_data = await self.step_apply_profile_update(input_data)
                yield {"stage": "profile_update", "status": "complete", "message": "档案更新完成"}

                yield {"stage": "profile_ack", "status": "start", "message": "正在确认..."}
                result = await self.step_profile_ack_reply(input_data)
                yield {"stage": "profile_ack", "status": "complete", "message": "确认完成"}

            elif intent == "info_collection":
                # 复用 step_format_output 输出追问
                result = await self.step_format_output(input_data)

            elif intent == "diet_plan":
                # 第三改进点：diet_plan 线性段用 LCEL sub-chain
                # 流式事件用粗粒度（start/complete 包整条 sub-chain），保持前端进度可见
                yield {"stage": "diet_linear_chain", "status": "start", "message": "正在生成个性化膳食方案（检索→约束→生成→校验）..."}
                input_data = await self.diet_linear_chain.ainvoke(input_data)
                yield {"stage": "diet_linear_chain", "status": "complete", "message": "膳食方案生成与校验完成"}

                result = await self.step_format_output(input_data)

            elif intent == "diet_revise":
                # 食谱修正闭环流式：先取上一版食谱 → 复用 diet_plan 5 连段生成修订版
                yield {"stage": "diet_revise", "status": "start", "message": "正在取出上一版食谱并应用您的修改意见..."}
                input_data = await self.diet_revise_chain.ainvoke(input_data)
                # step_fetch_prev_plan 内部可能降级为 diet_plan，同步 intent
                new_intent = input_data.get("plan", {}).get("intent", intent)
                if new_intent != intent:
                    logger.info(f"[Agent流式] diet_revise 降级为 {new_intent}")
                    intent = new_intent
                yield {"stage": "diet_revise", "status": "complete", "message": "修订版食谱生成完成"}

                result = await self.step_format_output(input_data)

            else:
                # 兜底走 diet_plan 流程
                logger.error(f"[Agent流式] 未知 intent: {intent}，降级 diet_plan")
                input_data = await self.step_retrieve_knowledge(input_data)
                input_data = await self.step_build_constraints(input_data)
                input_data = await self.step_generate_diet(input_data)
                input_data = await self.step_validate_diet(input_data)
                result = await self.step_format_output(input_data)

            # 标注意图
            result["intent"] = intent

            # 最终答复逐字流
            final_message = result.get("message", "") or ""
            if final_message and result.get("success"):
                yield {"stage": "finalize", "status": "start", "message": "正在整理最终答复..."}
                async for chunk in self._stream_text_chunks(final_message):
                    yield {"stage": "finalize", "status": "stream", "chunk": chunk}
                yield {"stage": "finalize", "status": "complete", "message": "答复生成完成"}

            yield {"stage": "output", "status": "complete", "message": "处理完成", "data": result}

        except Exception as e:
            logger.exception("[Agent流式处理] 异常: {}", str(e))
            yield {
                "stage": "error",
                "status": "error",
                "message": f"处理异常：{str(e)}"
            }

    @staticmethod
    def _intent_label(intent: str) -> str:
        """把 intent 枚举翻译成中文标签（流式事件用）"""
        return {
            "diet_plan": "生成膳食方案",
            "diet_revise": "修订食谱",
            "nutrition_qa": "营养问答",
            "health_calc": "健康指标计算",
            "food_eval": "食材评估",
            "profile_update": "档案更新",
            "casual_chat": "闲聊",
            "info_collection": "信息收集",
        }.get(intent, intent)

    @staticmethod
    def _verdict_label(verdict: str) -> str:
        """把 food_eval 的 verdict 翻译成中文（流式事件用）"""
        return {
            "safe": "可以食用",
            "warning": "建议慎吃",
            "forbidden": "建议禁食",
            "unknown": "无法判断",
        }.get(verdict, verdict)


# ======================== 文件内自测脚本 ========================
if __name__ == "__main__":
    import asyncio
    
    async def test_chain():
        print("=" * 60)
        print("DietAgentChain 自测开始")
        print("=" * 60)
        
        # 创建Agent实例
        print("\n[初始化] 创建DietAgentChain...")
        agent = DietAgentChain()
        print("[通过] Agent初始化完成")
        
        # 测试处理流程
        print("\n[测试] 调用process方法...")
        try:
            result = await agent.process(
                user_id=1,
                user_query="我想制定一份减脂食谱"
            )
            
            print(f"[结果] success={result['success']}")
            print(f"[结果] need_info={result['need_info']}")
            print(f"[结果] processing_time={result.get('processing_time_ms', 0)}ms")
            
            if result.get("message"):
                print(f"\n[回复消息]:\n{result['message'][:200]}...")
            
        except Exception as e:
            print(f"[失败] 测试异常: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 60)
        print("DietAgentChain 自测完成")
    
    # 运行测试
    asyncio.run(test_chain())
