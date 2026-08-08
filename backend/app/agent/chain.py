"""
膳食搭配Agent - LCEL链式调用编排

功能：
将各个处理环节通过LangChain的LCEL（LangChain Expression Language）串联起来，
形成完整的膳食搭配Agent处理流程。

执行流程：
用户查询 → 信息收集 → 知识检索 → 约束校验 → 食谱生成 → 结果输出

特点：
1. 纯函数式链式调用，无状态副作用
2. 每个环节可独立替换和测试
3. 支持同步和异步两种模式
4. 易于调试和扩展

"""

import logging
from typing import Dict, Any, Optional, List
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from agent.llm_client import LLMClient
from agent.tools.user_tool import get_user_info, format_profile_for_prompt
from agent.tools.rag_tool import search_knowledge, format_knowledge_for_llm
from agent.tools.validate_tool import validate_diet_plan, check_food_taboo
from agent.tools.region_tool import get_region_diet_features, adapt_diet_to_region
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
        
        logger.info("DietAgentChain初始化完成")
    
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
            "region_features": input_data["region_features"]
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
    
    # ========== 主处理流程 ==========
    
    async def process(
        self, 
        user_id: int, 
        user_query: str
    ) -> Dict[str, Any]:
        """
        执行完整的Agent处理流程
        
        流程：信息收集 → 知识检索 → 约束构建 → 食谱生成 → 方案校验 → 结果输出
        
        参数：
            user_id: 用户ID
            user_query: 用户查询内容
        
        返回：
            最终处理结果，包含：
            {
                "success": 是否成功,
                "need_info": 是否需要补充信息,
                "diet_plan": 膳食方案,
                "message": 回复消息,
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
            
            # 执行各环节
            # 环节1：信息收集
            input_data = await self.step_collect_info(input_data)
            
            # 环节2：知识检索
            input_data = await self.step_retrieve_knowledge(input_data)
            
            # 环节3：约束构建
            input_data = await self.step_build_constraints(input_data)
            
            # 环节4：食谱生成
            input_data = await self.step_generate_diet(input_data)
            
            # 环节5：方案校验
            input_data = await self.step_validate_diet(input_data)
            
            # 环节6：结果输出
            result = await self.step_format_output(input_data)
            
            # 添加处理时间
            result["processing_time_ms"] = int((time.time() - start_time) * 1000)
            
            logger.info(
                f"[Agent处理] 完成: user_id={user_id}, "
                f"success={result['success']}, "
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

        用于前端实时显示处理进度 + 打字机效果

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

            # 环节2：知识检索
            yield {"stage": "retrieve_knowledge", "status": "start", "message": "正在检索膳食知识..."}
            input_data = await self.step_retrieve_knowledge(input_data)
            yield {"stage": "retrieve_knowledge", "status": "complete", "message": f"检索到 {len(input_data.get('knowledge_results', []))} 条相关知识"}

            # 环节3：约束构建
            yield {"stage": "build_constraints", "status": "start", "message": "正在构建约束条件..."}
            input_data = await self.step_build_constraints(input_data)
            yield {"stage": "build_constraints", "status": "complete", "message": "约束条件构建完成"}

            # 环节4：食谱生成
            yield {"stage": "generate_diet", "status": "start", "message": "正在为您生成个性化膳食方案..."}
            input_data = await self.step_generate_diet(input_data)
            yield {"stage": "generate_diet", "status": "complete", "message": "膳食方案生成完成"}

            # 环节5：方案校验
            yield {"stage": "validate_diet", "status": "start", "message": "正在校验膳食方案..."}
            input_data = await self.step_validate_diet(input_data)
            yield {"stage": "validate_diet", "status": "complete", "message": "方案校验完成"}

            # 环节6：结果格式化 + 最终答复逐字流
            result = await self.step_format_output(input_data)

            # 只有成功生成了答复，才发 stream 打字效果
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
