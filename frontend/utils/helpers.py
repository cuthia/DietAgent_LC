"""
工具函数模块

功能：
1. 时间格式化
2. 数值格式化
3. 安全取值
4. 字符串处理

设计模式：纯函数工具集，无状态依赖
"""

from datetime import datetime
from typing import Dict, Any, Optional


# ======================== 时间格式化 ========================

def format_datetime(ts: float) -> str:
    """
    时间戳转可读时间字符串

    参数：
        ts: Unix 时间戳（秒）

    返回：
        格式化后的时间字符串，如 "2026-07-31 15:30"

    示例：
        >>> format_datetime(1722403800)
        '2024-07-31 15:30'
    """
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return "未知时间"


def format_datetime_full(ts: float) -> str:
    """
    时间戳转完整时间字符串（包含秒）

    参数：
        ts: Unix 时间戳（秒）

    返回：
        格式化后的时间字符串，如 "2026-07-31 15:30:45"
    """
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return "未知时间"


# ======================== 数值格式化 ========================

def format_calories(cal: float) -> str:
    """
    格式化热量显示

    参数：
        cal: 热量值（单位：千卡）

    返回：
        格式化后的热量字符串

    示例：
        >>> format_calories(1450)
        '1450kcal'
        >>> format_calories(1540.5)
        '1.5kcal'  # 超过1000会转换单位
    """
    if cal >= 1000:
        return f"{cal/1000:.1f}kcal"
    return f"{cal:.0f}kcal"


def format_grams(g: float) -> str:
    """
    格式化克数显示

    参数：
        g: 克数

    返回：
        格式化后的克数字符串
    """
    if g >= 1000:
        return f"{g/1000:.1f}kg"
    return f"{g:.0f}g"


def format_percentage(value: float, total: float) -> str:
    """
    计算并格式化百分比

    参数：
        value: 当前值
        total: 总值

    返回：
        百分比字符串，如 "45%"
    """
    if total == 0:
        return "0%"
    return f"{(value / total * 100):.1f}%"


# ======================== 餐次相关 ========================

def get_meal_emoji(meal_type: str) -> str:
    """
    获取餐次对应的 emoji

    参数：
        meal_type: 餐次类型（breakfast/lunch/dinner/snack）

    返回：
        对应的 emoji 字符
    """
    emoji_map = {
        "breakfast": "🌅",
        "lunch": "☀️",
        "dinner": "🌙",
        "snack": "🍎",
    }
    return emoji_map.get(meal_type, "🍽️")


def get_meal_label(meal_type: str) -> str:
    """
    获取餐次中文标签

    参数：
        meal_type: 餐次类型（breakfast/lunch/dinner/snack）

    返回：
        中文餐次名称
    """
    label_map = {
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
        "snack": "加餐",
    }
    return label_map.get(meal_type, meal_type)


# ======================== 安全取值 ========================

def safe_get(d: Dict, *keys, default=None):
    """
    安全获取嵌套字典值

    避免多层嵌套字典取值时的 KeyError 或 TypeError

    参数：
        d: 字典对象
        *keys: 嵌套键路径
        default: 默认值

    返回：
        找到的值或默认值

    示例：
        >>> data = {"user": {"profile": {"name": "Alice"}}}
        >>> safe_get(data, "user", "profile", "name")
        'Alice'
        >>> safe_get(data, "user", "profile", "age", default=25)
        25
    """
    current = d
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
        if current is None:
            return default
    return current


# ======================== 字符串处理 ========================

def truncate_text(text: str, max_length: int = 50) -> str:
    """
    截断长文本

    参数：
        text: 原始文本
        max_length: 最大长度

    返回：
        截断后的文本（超出部分用...替代）
    """
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def format_list_to_string(items: list, separator: str = "、") -> str:
    """
    将列表转换为字符串

    参数：
        items: 列表
        separator: 分隔符

    返回：
        拼接后的字符串
    """
    if not items:
        return ""
    return separator.join(str(item) for item in items)


# ======================== 数据校验 ========================

def is_valid_user_id(user_id: Any) -> bool:
    """
    校验用户ID是否有效

    参数：
        user_id: 用户ID

    返回：
        是否有效
    """
    return isinstance(user_id, int) and user_id > 0


def calculate_bmi(height: float, weight: float) -> float:
    """
    计算 BMI 值

    参数：
        height: 身高（厘米）
        weight: 体重（千克）

    返回：
        BMI 值
    """
    if height <= 0 or weight <= 0:
        return 0.0
    height_m = height / 100
    return round(weight / (height_m * height_m), 1)


def get_bmi_category(bmi: float) -> str:
    """
    根据 BMI 获取分类

    参数：
        bmi: BMI 值

    返回：
        分类字符串
    """
    if bmi < 18.5:
        return "偏瘦"
    elif bmi < 24:
        return "正常"
    elif bmi < 28:
        return "超重"
    else:
        return "肥胖"