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
from langchain.memory import ConversationBufferMemory

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
        search_query = user_query
        chronic = user_profile.get("chronic_disease", "")
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
            # 使用LCEL链：Prompt → LLM → Parser
            chain = DIET_GENERATE_PROMPT | self.llm | self.json_parser
            diet_plan = await chain.ainvoke(prompt_input)
            
            input_data["diet_plan"] = diet_plan
            input_data["raw_response"] = str(diet_plan)
            
            logger.info(f"[环节4] 食谱生成完成: total_cal={diet_plan.get('total_calories', 0)}千卡")
        except Exception as e:
            logger.error(f"[环节4] 食谱生成失败: {e}")
            # 失败时返回错误信息
            input_data["diet_plan"] = {
                "error": True,
                "message": f"膳食方案生成失败，请稍后重试。错误：{str(e)}"
            }
            input_data["raw_response"] = str(e)
        
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
            
            revise_chain = DIET_REVISE_PROMPT | self.llm | self.json_parser
            revised_plan = await revise_chain.ainvoke(revise_input)
            
            # 再次校验修正后的方案
            revised_validation = validate_diet_plan(revised_plan, user_profile)
            
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
    
    async def process_stream(
        self, 
        user_id: int, 
        user_query: str
    ):
        """
        流式处理（返回各环节进度事件）
        
        用于前端实时显示处理进度
        
        参数：
            user_id: 用户ID
            user_query: 用户查询
        
        Yields:
            每个处理阶段的状态事件：
            {
                "stage": "collect_info" | "retrieve_knowledge" | ...,
                "status": "start" | "complete",
                "message": 状态描述
            }
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
            
            # 环节6：结果输出
            result = await self.step_format_output(input_data)
            yield {"stage": "output", "status": "complete", "message": "处理完成", "data": result}
            
        except Exception as e:
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
