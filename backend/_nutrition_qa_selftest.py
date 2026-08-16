"""nutrition_qa 路由细化 - 静态自测（绕过 langchain_core）"""
import sys, os
BASE = os.path.join(os.path.dirname(__file__), "app", "agent")
results = []

def check(name, cond, detail=""):
    results.append((name, cond, detail))
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))

# 1) planner_prompt.py - nutrition_qa 规则扩充
with open(os.path.join(BASE, "prompts", "planner_prompt.py"), encoding="utf-8") as f:
    pp = f.read()
check("planner: nutrition_qa 覆盖食物相克",
      "食物相克/搭配禁忌" in pp and "番茄不能和什么一起吃" in pp)
check("planner: nutrition_qa 覆盖慢病禁忌清单",
      "慢病饮食原则/禁忌清单" in pp and "糖尿病不可以吃什么" in pp)
check("planner: nutrition_qa 覆盖特殊人群饮食",
      "特殊人群饮食" in pp)
check("planner: nutrition_qa 覆盖食材功效/烹饪/饮食习惯",
      "食材功效" in pp and "烹饪与营养保留" in pp and "饮食习惯/方法" in pp)
check("planner: nutrition_qa 判别要点已写明",
      "通用知识查询" in pp)
check("planner: food_eval 边界收窄为个人合规校验",
      "针对**用户个人慢病+忌口**做合规校验" in pp)
check("planner: food_eval 触发句式明确",
      "我能吃 X 吗" in pp)
check("planner: food_eval 与 nutrition_qa 区别用例已写",
      "番茄不能和什么一起吃" in pp and "我痛风，能吃番茄吗" in pp)
check("planner: health_calc 规则保留未误删",
      "**health_calc**" in pp and "bmr_calc_tool" in pp)

# 2) chain.py - nutrition_qa system prompt 升级
with open(os.path.join(BASE, "chain.py"), encoding="utf-8") as f:
    cp = f.read()
check("chain: nutrition_qa system_prompt 含回答范围",
      "回答范围（nutrition_qa 意图覆盖）" in cp)
check("chain: nutrition_qa 多角度检索策略",
      "多角度检索策略" in cp and "食物相克类" in cp and "慢病禁忌类" in cp)
check("chain: nutrition_qa 回答结构建议",
      "回答结构建议" in cp)
check("chain: nutrition_qa 禁止调 food_taboo_check_tool",
      "不要调用 food_taboo_check_tool" in cp)
check("chain: nutrition_qa max_iterations 提到 3",
      "step_react_with_tools(input_data, system_prompt, max_iterations=3)" in cp)
check("chain: nutrition_qa 文档字符串已扩充",
      "覆盖所有膳食/营养/饮食健康相关知识类问题" in cp)

print("\n=== 测试结果汇总 ===")
passed = sum(1 for _, c, _ in results if c)
total = len(results)
print(f"通过 {passed}/{total}")
if passed < total:
    print("\n失败项:")
    for n, c, d in results:
        if not c:
            print(f"  - {n}")
    sys.exit(1)
else:
    print("\n=== nutrition_qa 路由细化静态自测全部通过 ===")
