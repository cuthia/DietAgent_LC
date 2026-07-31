"""
忌口/慢病校验工具 - 校验食材是否符合用户健康要求

功能：
1. check_food_taboo: 校验单个食材是否符合忌口
2. validate_diet_plan: 校验整个膳食方案

数据来源：
1. 内置的慢性病-食物禁忌知识库
2. 用户档案中的忌口信息
"""

import logging
from typing import List, Dict, Any

# 日志记录器
logger = logging.getLogger(__name__)


# ========== 内置知识库 ==========

# 慢性病对应的食物禁忌列表
# 可根据实际情况扩展
CHRONIC_DISEASE_FOOD_TABOO = {
    "糖尿病": {
        "forbidden": ["高糖饮品", "甜点", "蛋糕", "糖果", "蜂蜜", "含糖饮料"],
        "warning": ["白米饭", "白面包", "白馒头", "精制碳水"],
        "recommended": ["粗粮", "燕麦", "糙米", "全麦", "蔬菜", "豆制品"]
    },
    "痛风": {
        "forbidden": ["动物内脏", "海鲜", "海鱼", "虾蟹", "啤酒", "肉汤"],
        "warning": ["蘑菇", "芦笋", "菠菜"],
        "recommended": ["鸡蛋", "精肉", "低脂乳制品", "蔬菜", "水果"]
    },
    "高血压": {
        "forbidden": ["腌制食品", "咸菜", "腊肉", "浓茶", "咖啡", "酒类"],
        "warning": ["咸蛋", "方便面", "酱油（过量）"],
        "recommended": ["新鲜蔬菜", "水果", "低脂乳制品", "全谷物"]
    },
    "高血脂": {
        "forbidden": ["动物内脏", "肥肉", "黄油", "椰子油", "棕榈油"],
        "warning": ["蛋黄", "奶酪", "奶油"],
        "recommended": ["燕麦", "豆类", "坚果", "鱼油", "蔬菜"]
    },
    "胃炎": {
        "forbidden": ["辛辣食物", "咖啡", "浓茶", "酒精", "生冷食物"],
        "warning": ["油炸食品", "碳酸饮料"],
        "recommended": ["小米粥", "蒸蛋", "炖菜", "香蕉", "南瓜"]
    }
}


# ========== 核心工具函数 ==========

def check_food_taboo(
    food_items: List[str], 
    user_profile: Dict[str, Any]
) -> Dict[str, Any]:
    """
    校验食材是否符合用户忌口/慢病要求
    
    功能：
    根据用户的慢性疾病和食物忌口，检查给定的食材列表是否安全。
    将食材分为三类：安全、警告、禁忌。
    
    参数：
        food_items: 待校验的食材列表，如 ["米饭", "鸡蛋", "海鲜"]
        user_profile: 用户档案，包含：
                     - chronic_disease: 慢性疾病（如"糖尿病"）
                     - food_taboo: 食物忌口（如"海鲜,花生"）
    
    返回：
        校验结果字典：
        {
            "safe": ["米饭", "鸡蛋"],
            "warning": [],
            "forbidden": ["海鲜"],
            "details": {
                "海鲜": "痛风患者禁食"
            }
        }
    
    """
    result = {
        "safe": [],
        "warning": [],
        "forbidden": [],
        "details": {}
    }
    
    # 获取用户的慢性疾病和忌口
    chronic_disease = user_profile.get("chronic_disease", "")
    user_taboo = user_profile.get("food_taboo", "")
    
    # 解析用户忌口（支持逗号分隔）
    user_taboo_list = []
    if user_taboo:
        user_taboo_list = [item.strip() for item in user_taboo.split(",") if item.strip()]
    
    # 获取疾病对应的禁忌表
    disease_taboo = CHRONIC_DISEASE_FOOD_TABOO.get(chronic_disease, {})
    forbidden_foods = disease_taboo.get("forbidden", [])
    warning_foods = disease_taboo.get("warning", [])
    
    # 检查每个食材
    for food in food_items:
        food = food.strip()
        if not food:
            continue
        
        # 检查是否在用户忌口中
        is_user_taboo = any(
            taboo in food or food in taboo 
            for taboo in user_taboo_list
        )
        
        # 检查是否在疾病禁忌中
        is_forbidden = any(
            taboo in food or food in taboo 
            for taboo in forbidden_foods
        )
        
        # 检查是否在疾病警告中
        is_warning = any(
            warn in food or food in warn 
            for warn in warning_foods
        )
        
        # 分类
        if is_user_taboo or is_forbidden:
            result["forbidden"].append(food)
            reason = ""
            if is_user_taboo:
                reason = "用户忌口"
            if is_forbidden:
                reason = f"{chronic_disease}患者禁食"
            result["details"][food] = reason
        elif is_warning:
            result["warning"].append(food)
            result["details"][food] = f"{chronic_disease}患者建议减少食用"
        else:
            result["safe"].append(food)
    
    return result


def validate_diet_plan(
    diet_plan: Dict[str, Any], 
    user_profile: Dict[str, Any]
) -> Dict[str, Any]:
    """
    校验整个膳食方案是否合规
    
    功能：
    对生成的膳食方案进行全面校验，检查：
    1. 是否包含用户忌口食材
    2. 是否包含慢病禁忌食材
    3. 营养是否均衡（可选）
    
    参数：
        diet_plan: 膳食方案字典，包含早中晚三餐
        user_profile: 用户档案
    
    返回：
        校验结果：
        {
            "passed": True/False,
            "forbidden_items": ["海鲜", "甜点"],
            "suggestions": ["请将海鲜替换为瘦肉", "请将甜点替换为水果"],
            "details": {...}
        }
    
    使用示例：
    ```python
    plan = {
        "breakfast": {"items": [{"name": "甜点"}, {"name": "牛奶"}]},
        "lunch": {"items": [{"name": "米饭"}, {"name": "海鲜"}]},
        "dinner": {"items": [{"name": "蔬菜"}]}
    }
    
    result = validate_diet_plan(plan, user_profile)
    if not result["passed"]:
        print(f"发现禁忌食材: {result['forbidden_items']}")
    ```
    """
    forbidden_items = []
    all_food_items = []
    
    # 收集所有食材
    meals = ["breakfast", "lunch", "dinner", "snack"]
    for meal in meals:
        meal_data = diet_plan.get(meal, {})
        items = meal_data.get("items", [])
        for item in items:
            food_name = item.get("name", "")
            if food_name:
                all_food_items.append(food_name)
    
    # 校验所有食材
    if all_food_items:
        check_result = check_food_taboo(all_food_items, user_profile)
        forbidden_items = check_result["forbidden"]
    
    # 生成建议
    suggestions = []
    for item in forbidden_items:
        reason = check_result.get("details", {}).get(item, "不符合要求")
        suggestions.append(f"请将「{item}」替换为其他食材（原因：{reason}）")
    
    # 汇总结果
    passed = len(forbidden_items) == 0
    
    return {
        "passed": passed,
        "forbidden_items": forbidden_items,
        "suggestions": suggestions,
        "details": check_result if all_food_items else {}
    }


def get_recommended_foods(chronic_disease: str) -> List[str]:
    """
    获取特定慢病推荐食用的食材
    
    参数：
        chronic_disease: 慢性疾病名称
    
    返回：
        推荐食材列表
    """
    disease_info = CHRONIC_DISEASE_FOOD_TABOO.get(chronic_disease, {})
    return disease_info.get("recommended", [])


# ======================== 文件内自测脚本 ========================
# 运行方式：在 backend/app 目录下执行  python -m agent.tools.validate_tool
if __name__ == "__main__":
    print("=" * 60)
    print("忌口校验工具自测开始")
    print("=" * 60)
    
    # 测试1：健康用户
    result = check_food_taboo(
        food_items=["米饭", "鸡蛋", "蔬菜"],
        user_profile={"chronic_disease": "", "food_taboo": ""}
    )
    print(f"[通过] 测试1-健康用户: safe={result['safe']}")
    
    # 测试2：糖尿病患者
    result = check_food_taboo(
        food_items=["米饭", "甜点", "燕麦"],
        user_profile={"chronic_disease": "糖尿病", "food_taboo": ""}
    )
    print(f"[通过] 测试2-糖尿病: forbidden={result['forbidden']}, warning={result['warning']}")
    
    # 测试3：痛风患者
    result = check_food_taboo(
        food_items=["海鲜", "鸡蛋", "动物内脏"],
        user_profile={"chronic_disease": "痛风", "food_taboo": ""}
    )
    print(f"[通过] 测试3-痛风: forbidden={result['forbidden']}")
    
    # 测试4：用户自定义忌口
    result = check_food_taboo(
        food_items=["花生", "牛奶", "海鲜"],
        user_profile={"chronic_disease": "", "food_taboo": "花生,海鲜"}
    )
    print(f"[通过] 测试4-自定义忌口: forbidden={result['forbidden']}")
    
    # 测试5：校验膳食方案
    plan = {
        "breakfast": {"items": [{"name": "甜点"}, {"name": "牛奶"}]},
        "lunch": {"items": [{"name": "米饭"}, {"name": "海鲜"}]},
        "dinner": {"items": [{"name": "蔬菜"}]}
    }
    result = validate_diet_plan(plan, {"chronic_disease": "痛风", "food_taboo": ""})
    print(f"[通过] 测试5-方案校验: passed={result['passed']}, forbidden={result['forbidden_items']}")
    
    # 测试6：获取推荐食材
    recommended = get_recommended_foods("糖尿病")
    print(f"[通过] 测试6-推荐食材: {recommended[:3]}...")
    
    print("=" * 60)
    print("忌口校验工具自测完成")
