"""
地域饮食适配工具 - 根据地域特点调整膳食方案

功能：
1. get_region_diet_features: 获取指定地域的饮食特点
2. adapt_diet_to_region: 根据地域特点调整膳食方案

数据来源：内置的中国各地域饮食文化知识库
"""

import logging
from typing import List, Dict, Any, Optional

# 日志记录器
logger = logging.getLogger(__name__)


# ========== 地域饮食知识库 ==========

# 中国主要地域的饮食特点
REGION_DIET_DB = {
    "南方": {
        "description": "南方地区饮食特点",
        "staple_foods": ["米饭", "米粉", "年糕", "肠粉"],
        "cooking_styles": ["清淡", "清蒸", "白灼", "煲汤"],
        "recommended_ingredients": ["水稻", "甘蔗", "竹笋", "山药"],
        "flavor_preferences": ["清淡", "鲜美", "微甜"],
        "avoid": ["过于辛辣", "过于油腻"],
        "sample_dishes": ["白切鸡", "清蒸鲈鱼", "广式早茶", "艇仔粥"]
    },
    "北方": {
        "description": "北方地区饮食特点",
        "staple_foods": ["馒头", "面条", "饺子", "包子", "玉米"],
        "cooking_styles": ["炖煮", "红烧", "酱卤", "油炸"],
        "recommended_ingredients": ["小麦", "玉米", "大豆", "土豆"],
        "flavor_preferences": ["咸鲜", "醇厚", "香辣"],
        "avoid": ["过于清淡", "生冷食物"],
        "sample_dishes": ["红烧肉", "北京烤鸭", "炸酱面", "饺子"]
    },
    "沿海": {
        "description": "沿海地区饮食特点",
        "staple_foods": ["米饭", "海鲜", "贝类"],
        "cooking_styles": ["清蒸", "白灼", "盐焗", "蒜蓉"],
        "recommended_ingredients": ["海鱼", "虾蟹", "贝类", "海藻"],
        "flavor_preferences": ["鲜美", "清淡", "原汁原味"],
        "avoid": ["过多红肉", "辛辣刺激"],
        "sample_dishes": ["清蒸石斑", "白灼基围虾", "蒜蓉粉丝扇贝"]
    },
    "川渝": {
        "description": "川渝地区饮食特点",
        "staple_foods": ["米饭", "面条", "凉粉", "糍粑"],
        "cooking_styles": ["麻辣", "鲜香", "酸辣", "干煸"],
        "recommended_ingredients": ["辣椒", "花椒", "豆瓣", "泡菜"],
        "flavor_preferences": ["麻辣", "鲜香", "酸辣"],
        "avoid": ["过于清淡", "甜味过重"],
        "sample_dishes": ["麻婆豆腐", "水煮鱼", "宫保鸡丁", "重庆小面"]
    },
    "江南": {
        "description": "江南地区饮食特点",
        "staple_foods": ["米饭", "糯米", "面条", "年糕"],
        "cooking_styles": ["红烧", "清蒸", "糖醋", "煲汤"],
        "recommended_ingredients": ["水稻", "莲藕", "茭白", "大闸蟹"],
        "flavor_preferences": ["鲜甜", "咸鲜", "微甜"],
        "avoid": ["过于辛辣", "过于油腻"],
        "sample_dishes": ["松鼠鳜鱼", "东坡肉", "阳澄湖大闸蟹"]
    },
    "东北": {
        "description": "东北地区饮食特点",
        "staple_foods": ["大米", "玉米", "高粱", "饺子"],
        "cooking_styles": ["炖菜", "烧烤", "酱卤", "腌制"],
        "recommended_ingredients": ["大米", "玉米", "大豆", "酸菜"],
        "flavor_preferences": ["咸鲜", "醇厚", "酸辣"],
        "avoid": ["过于清淡", "生冷"],
        "sample_dishes": ["东北乱炖", "酸菜白肉", "锅包肉", "地三鲜"]
    }
}


# 地域关键词映射（用于模糊匹配）
REGION_KEYWORDS = {
    "南方": ["南方", "广东", "广西", "海南", "广州", "深圳"],
    "北方": ["北方", "北京", "天津", "河北", "山东", "山西"],
    "沿海": ["沿海", "上海", "浙江", "福建", "厦门", "青岛", "大连"],
    "川渝": ["四川", "重庆", "成都", "重庆", "西南"],
    "江南": ["江南", "江苏", "南京", "苏州", "无锡", "杭州"],
    "东北": ["东北", "辽宁", "吉林", "黑龙江", "哈尔滨", "沈阳"]
}


# ========== 核心工具函数 ==========

def get_region_diet_features(region: str) -> Dict[str, Any]:
    """
    获取指定地域的饮食特点
    
    功能：
    根据地域名称返回该地区的饮食文化特点，
    包括主食、烹饪方式、推荐食材、口味偏好等。
    
    参数：
        region: 地域名称，支持：
                - 直接匹配：南方、北方、沿海、川渝、江南、东北
                - 模糊匹配：广东、北京、上海等具体城市
    
    返回：
        地域饮食特点字典：
        {
            "region": "南方",
            "description": "南方地区饮食特点",
            "staple_foods": ["米饭", "米粉", "年糕"],
            "cooking_styles": ["清淡", "清蒸"],
            "recommended_ingredients": ["水稻", "竹笋"],
            "flavor_preferences": ["清淡", "鲜美"],
            "avoid": ["过于辛辣"],
            "sample_dishes": ["白切鸡", "清蒸鲈鱼"]
        }
    
    使用示例：
    ```python
    features = get_region_diet_features("广东")
    # 返回南方地区的饮食特点
    ```
    """
    # 直接匹配
    if region in REGION_DIET_DB:
        result = {"region": region}
        result.update(REGION_DIET_DB[region])
        return result
    
    # 模糊匹配
    for standard_region, keywords in REGION_KEYWORDS.items():
        if region in keywords or any(kw in region for kw in keywords):
            result = {"region": standard_region}
            result.update(REGION_DIET_DB[standard_region])
            return result
    
    # 返回默认值
    logger.warning(f"未知地域: {region}，使用通用建议")
    return {
        "region": region,
        "description": "通用饮食建议",
        "staple_foods": ["米饭", "面条"],
        "cooking_styles": ["蒸煮", "炖煮"],
        "recommended_ingredients": ["蔬菜", "水果", "全谷物"],
        "flavor_preferences": ["根据个人口味"],
        "avoid": ["过于辛辣", "过于油腻"],
        "sample_dishes": []
    }


def adapt_diet_to_region(
    diet_plan: Dict[str, Any], 
    region: str
) -> Dict[str, Any]:
    """
    根据地域特点调整膳食方案
    
    功能：
    根据用户所在地域的饮食文化特点，调整膳食方案：
    1. 推荐使用地域特色食材
    2. 采用地域常见的烹饪方式
    3. 调整口味偏好
    
    参数：
        diet_plan: 膳食方案字典
        region: 地域名称
    
    返回：
        调整后的膳食方案（增加地域特色标记）
    
    使用示例：
    ```python
    plan = {
        "breakfast": {"items": [{"name": "面包"}]},
        "lunch": {"items": [{"name": "米饭"}, {"name": "炒菜"}]}
    }
    
    adapted = adapt_diet_to_region(plan, "川渝")
    # 会增加麻辣风味的建议
    ```
    """
    # 获取地域特点
    features = get_region_diet_features(region)
    
    # 构建调整建议
    adaptations = {
        "region": region,
        "region_features": features,
        "suggestions": []
    }
    
    # 添加主食建议
    if features["staple_foods"]:
        adaptations["suggestions"].append(
            f"推荐主食：{'、'.join(features['staple_foods'][:3])}"
        )
    
    # 添加烹饪方式建议
    if features["cooking_styles"]:
        adaptations["suggestions"].append(
            f"推荐烹饪方式：{'、'.join(features['cooking_styles'][:2])}"
        )
    
    # 添加口味建议
    if features["flavor_preferences"]:
        adaptations["suggestions"].append(
            f"口味偏好：{'、'.join(features['flavor_preferences'][:2])}"
        )
    
    # 添加特色菜品参考
    if features["sample_dishes"]:
        adaptations["suggestions"].append(
            f"当地特色：{'、'.join(features['sample_dishes'][:3])}"
        )
    
    # 添加应避免的食物
    if features["avoid"]:
        adaptations["suggestions"].append(
            f"建议避免：{'、'.join(features['avoid'][:2])}"
        )
    
    return adaptations


# ========== LangChain @tool 包装（第一点改进配套） ==========

from langchain_core.tools import tool as _lc_tool


@_lc_tool
def region_adapt_tool(region: str) -> Dict[str, Any]:
    """
    获取指定地域的饮食文化特点（主食/烹饪方式/口味/特色菜/避免项）。

    适用于 diet_plan 意图：根据用户所在地域推荐符合当地饮食文化的食材与做法。

    参数：
        region: 地域名称，支持直接匹配（南方/北方/沿海/川渝/江南/东北）
                和模糊匹配（广东→南方、北京→北方、上海→沿海 等）

    返回：
        {
            "region": "南方",
            "staple_foods": ["米饭", "米粉", "年糕"],
            "cooking_styles": ["清淡", "清蒸", "白灼", "煲汤"],
            "recommended_ingredients": ["水稻", "甘蔗", "竹笋"],
            "flavor_preferences": ["清淡", "鲜美", "微甜"],
            "avoid": ["过于辛辣", "过于油腻"],
            "sample_dishes": ["白切鸡", "清蒸鲈鱼", "广式早茶"]
        }
    """
    return get_region_diet_features(region)


# ======================== 文件内自测脚本 ========================
# 运行方式：在 backend/app 目录下执行  python -m agent.tools.region_tool
if __name__ == "__main__":
    print("=" * 60)
    print("地域适配工具自测开始")
    print("=" * 60)
    
    # 测试1：直接匹配
    features = get_region_diet_features("南方")
    print(f"[通过] 测试1-直接匹配: region={features['region']}, staple={features['staple_foods'][:2]}")
    
    # 测试2：模糊匹配（广东→南方）
    features = get_region_diet_features("广东")
    print(f"[通过] 测试2-模糊匹配: 广东→{features['region']}")
    
    # 测试3：川渝地区
    features = get_region_diet_features("川渝")
    print(f"[通过] 测试3-川渝: cooking={features['cooking_styles'][:2]}")
    
    # 测试4：未知地域
    features = get_region_diet_features("火星")
    print(f"[通过] 测试4-未知地域: 使用默认建议")
    
    # 测试5：适配膳食方案
    plan = {
        "breakfast": {"items": [{"name": "面包"}]},
        "lunch": {"items": [{"name": "米饭"}]}
    }
    adapted = adapt_diet_to_region(plan, "川渝")
    print(f"[通过] 测试5-方案适配: suggestions={adapted['suggestions'][:2]}")
    
    print("=" * 60)
    print("地域适配工具自测完成")
