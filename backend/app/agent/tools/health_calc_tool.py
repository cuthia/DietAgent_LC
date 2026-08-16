"""
健康计算工具 —— BMI / BMR / 蛋白质目标（第一点改进配套工具）

设计原则：
1. 纯数学/确定性逻辑必须工具化（LLM 算 BMI 会算错数、代不出公式）
2. 工具不依赖 LLM、不依赖外部 API，100% 可重现
3. 用 LangChain @tool 装饰，可被 chain 直接显式调用，也可在第二点改进中被 bind_tools 注册

公式来源：
- BMI：国际标准 body mass index = weight_kg / (height_m)^2
- BMR：Mifflin-St Jeor 公式（1990 年代推荐，比 Harris-Benedict 更准）
  - 男性: BMR = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
  - 女性: BMR = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
- 蛋白质目标：根据膳食目标取每公斤体重的蛋白质克数
  - 普通：0.8~1.0 g/kg
  - 减脂：1.6~2.0 g/kg
  - 增肌：1.6~2.2 g/kg
"""

import logging
from typing import Dict
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# ========== BMI 计算 ==========

@tool
def bmi_calc_tool(height_cm: float, weight_kg: float) -> Dict:
    """
    计算 BMI（身体质量指数）并返回分类与解读。

    参数：
        height_cm: 身高（厘米），如 175.0
        weight_kg: 体重（公斤），如 70.0

    返回：
        {
            "bmi": 22.9,
            "category": "正常",
            "category_en": "normal",
            "interpretation": "您的 BMI 为 22.9，属于正常范围（18.5~24）...",
            "healthy_weight_range_kg": [56.7, 73.5]
        }
    """
    if height_cm <= 0 or weight_kg <= 0:
        return {
            "error": "身高/体重必须为正数",
            "bmi": None,
            "category": "无法计算",
        }

    height_m = height_cm / 100.0
    bmi = round(weight_kg / (height_m * height_m), 1)

    # 中国成人 BMI 分类标准（WS/T 428-2013）
    if bmi < 18.5:
        category, category_en = "偏瘦", "underweight"
        advice = "建议适当增加营养摄入，保证蛋白质和健康脂肪"
    elif 18.5 <= bmi < 24:
        category, category_en = "正常", "normal"
        advice = "体重在健康范围，建议继续保持均衡饮食和规律运动"
    elif 24 <= bmi < 28:
        category, category_en = "超重", "overweight"
        advice = "建议控制总热量摄入，增加有氧运动，目标 BMI < 24"
    else:
        category, category_en = "肥胖", "obese"
        advice = "建议在医生/营养师指导下系统减重，避免高糖高脂饮食"

    # 健康体重范围（BMI 18.5~24 对应的体重区间）
    healthy_low = round(18.5 * height_m * height_m, 1)
    healthy_high = round(24 * height_m * height_m, 1)

    interpretation = (
        f"您的 BMI 为 {bmi}，属于「{category}」范围。{advice}。"
        f"身高 {height_cm}cm 的健康体重范围为 {healthy_low}~{healthy_high}kg。"
    )

    return {
        "bmi": bmi,
        "category": category,
        "category_en": category_en,
        "interpretation": interpretation,
        "healthy_weight_range_kg": [healthy_low, healthy_high],
    }


# ========== BMR 计算（基础代谢率）==========

@tool
def bmr_calc_tool(age: int, gender: str, height_cm: float, weight_kg: float) -> Dict:
    """
    计算基础代谢率 BMR（Basal Metabolic Rate），即静息状态下维持生命所需的最低热量。

    使用 Mifflin-St Jeor 公式（比 Harris-Benedict 更准）。
    参数：
        age: 年龄（岁），如 30
        gender: 性别，"male" 或 "female"
        height_cm: 身高（厘米）
        weight_kg: 体重（公斤）

    返回：
        {
            "bmr_kcal": 1650.0,
            "formula": "Mifflin-St Jeor",
            "interpretation": "您的基础代谢率约为 1650 千卡/天...",
            "daily_calorie_advice": {
                "sedentary": 1980, "light": 2269, "moderate": 2558,
                "active": 2846, "very_active": 3135
            }
        }
    """
    if age <= 0 or height_cm <= 0 or weight_kg <= 0:
        return {"error": "参数必须为正数", "bmr_kcal": None}

    gender_lower = (gender or "").lower().strip()
    # Mifflin-St Jeor 公式
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    if gender_lower == "male":
        bmr = base + 5
    elif gender_lower == "female":
        bmr = base - 161
    else:
        # 未知性别：取男女均值，并标注
        bmr_male = base + 5
        bmr_female = base - 161
        bmr = (bmr_male + bmr_female) / 2
        logger.warning(f"bmr_calc_tool: 未知性别 '{gender}'，取男女均值")

    bmr = round(bmr, 1)

    # 不同活动水平下的每日推荐热量（BMR × 活动系数）
    activity_multipliers = {
        "sedentary": 1.2,      # 久坐
        "light": 1.375,        # 轻度活动（每周 1~3 天）
        "moderate": 1.55,      # 中度活动（每周 3~5 天）
        "active": 1.725,       # 高度活动（每周 6~7 天）
        "very_active": 1.9,    # 极高强度（体力劳动者/运动员）
    }
    daily_advice = {k: round(bmr * v) for k, v in activity_multipliers.items()}

    interpretation = (
        f"您的基础代谢率（BMR）约为 {bmr} 千卡/天，"
        f"即完全静息状态下身体维持生命所需的最低热量。"
        f"根据活动水平，每日推荐摄入热量范围："
        f"久坐 {daily_advice['sedentary']} ~ 高度活动 {daily_advice['active']} 千卡。"
        f"减脂建议在 TDEE 基础上减少 300~500 千卡/天。"
    )

    return {
        "bmr_kcal": bmr,
        "formula": "Mifflin-St Jeor",
        "interpretation": interpretation,
        "daily_calorie_advice": daily_advice,
    }


# ========== 蛋白质摄入目标计算 ==========

@tool
def protein_target_tool(weight_kg: float, diet_goal: str = "") -> Dict:
    """
    根据体重和膳食目标计算每日蛋白质摄入建议。

    参数：
        weight_kg: 体重（公斤），如 70.0
        diet_goal: 膳食目标关键词，如 "减脂"、"增肌"、"控糖"、"日常养生"
                   支持模糊匹配（包含关键词即可）

    返回：
        {
            "target_g_per_day": [112, 140],
            "per_kg_range": [1.6, 2.0],
            "interpretation": "您的每日蛋白质摄入建议为 112~140g..."
        }
    """
    if weight_kg <= 0:
        return {"error": "体重必须为正数", "target_g_per_day": None}

    goal = (diet_goal or "").strip()

    # 根据目标匹配每公斤体重的蛋白质克数
    if any(kw in goal for kw in ("减脂", "减重", "瘦身", "控糖")):
        per_kg_range = (1.6, 2.0)
        category = "减脂/控糖"
        note = "减脂期间高蛋白饮食有助于保持肌肉量、增加饱腹感"
    elif any(kw in goal for kw in ("增肌", "增重", "健身", "力量")):
        per_kg_range = (1.6, 2.2)
        category = "增肌"
        note = "增肌期需配合力量训练，蛋白质分餐摄入更利于吸收"
    elif any(kw in goal for kw in ("养胃", "养生", "日常", "保健")):
        per_kg_range = (0.8, 1.0)
        category = "日常养生"
        note = "日常养生保持基础蛋白质摄入即可，避免过量加重肝肾负担"
    else:
        per_kg_range = (0.8, 1.2)
        category = "普通成人"
        note = "未明确目标，按普通成人推荐；如有特殊需求请说明"

    target_low = round(per_kg_range[0] * weight_kg, 1)
    target_high = round(per_kg_range[1] * weight_kg, 1)

    interpretation = (
        f"体重 {weight_kg}kg，目标「{category}」："
        f"每日蛋白质摄入建议为 {target_low}~{target_high}g"
        f"（每公斤体重 {per_kg_range[0]}~{per_kg_range[1]}g）。{note}。"
    )

    return {
        "target_g_per_day": [target_low, target_high],
        "per_kg_range": list(per_kg_range),
        "category": category,
        "interpretation": interpretation,
    }


# ======================== 文件内自测脚本 ========================
# 运行方式：在 backend/app 目录下执行  python -m agent.tools.health_calc_tool
if __name__ == "__main__":
    print("=" * 60)
    print("健康计算工具自测开始")
    print("=" * 60)

    # 测试1：BMI 正常
    r = bmi_calc_tool.invoke({"height_cm": 175.0, "weight_kg": 70.0})
    assert 22 < r["bmi"] < 24, f"BMI 计算错误: {r['bmi']}"
    assert r["category"] == "正常"
    print(f"[通过] 测试1 - BMI 正常: {r['bmi']} ({r['category']})")

    # 测试2：BMI 偏瘦
    r = bmi_calc_tool.invoke({"height_cm": 175.0, "weight_kg": 50.0})
    assert r["category"] == "偏瘦"
    print(f"[通过] 测试2 - BMI 偏瘦: {r['bmi']} ({r['category']})")

    # 测试3：BMI 肥胖
    r = bmi_calc_tool.invoke({"height_cm": 170.0, "weight_kg": 90.0})
    assert r["category"] == "肥胖"
    print(f"[通过] 测试3 - BMI 肥胖: {r['bmi']} ({r['category']})")

    # 测试4：BMR 男性
    r = bmr_calc_tool.invoke({
        "age": 30, "gender": "male", "height_cm": 175.0, "weight_kg": 70.0
    })
    assert 1600 < r["bmr_kcal"] < 1800, f"BMR 男性计算错误: {r['bmr_kcal']}"
    print(f"[通过] 测试4 - BMR 男: {r['bmr_kcal']} kcal/天")

    # 测试5：BMR 女性
    r = bmr_calc_tool.invoke({
        "age": 25, "gender": "female", "height_cm": 162.0, "weight_kg": 52.0
    })
    assert 1100 < r["bmr_kcal"] < 1400, f"BMR 女性计算错误: {r['bmr_kcal']}"
    print(f"[通过] 测试5 - BMR 女: {r['bmr_kcal']} kcal/天")

    # 测试6：BMR 未知性别
    r = bmr_calc_tool.invoke({
        "age": 30, "gender": "", "height_cm": 175.0, "weight_kg": 70.0
    })
    assert "bmr_kcal" in r and r["bmr_kcal"] > 0
    print(f"[通过] 测试6 - BMR 未知性别（取均值）: {r['bmr_kcal']} kcal/天")

    # 测试7：蛋白质目标 - 减脂
    r = protein_target_tool.invoke({"weight_kg": 70.0, "diet_goal": "减脂"})
    assert r["target_g_per_day"][0] == 112.0
    assert r["target_g_per_day"][1] == 140.0
    print(f"[通过] 测试7 - 蛋白质(减脂): {r['target_g_per_day']} g/天")

    # 测试8：蛋白质目标 - 增肌
    r = protein_target_tool.invoke({"weight_kg": 70.0, "diet_goal": "增肌"})
    assert r["target_g_per_day"][0] == 112.0
    assert r["target_g_per_day"][1] == 154.0
    print(f"[通过] 测试8 - 蛋白质(增肌): {r['target_g_per_day']} g/天")

    # 测试9：蛋白质目标 - 日常
    r = protein_target_tool.invoke({"weight_kg": 70.0, "diet_goal": "日常养生"})
    assert r["target_g_per_day"][0] == 56.0
    print(f"[通过] 测试9 - 蛋白质(日常): {r['target_g_per_day']} g/天")

    # 测试10：非法参数
    r = bmi_calc_tool.invoke({"height_cm": 0, "weight_kg": 70.0})
    assert "error" in r
    print(f"[通过] 测试10 - 非法参数: {r['error']}")

    print("=" * 60)
    print("健康计算工具自测完成（10/10）")
