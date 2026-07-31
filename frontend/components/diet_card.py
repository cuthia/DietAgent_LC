"""
膳食方案卡片组件

功能：
1. 渲染完整的膳食方案展示
2. 营养总览卡片
3. 分餐详情展示
4. 健康建议展示

设计模式：组件化设计，可复用
"""

import streamlit as st
from typing import Dict, Any
from utils.helpers import (
    get_meal_emoji,
    get_meal_label,
    format_calories,
    format_grams
)


def render_diet_plan_card(diet_plan: Dict[str, Any]):
    """
    渲染完整的膳食方案卡片

    布局结构：
    1. 营养总览（总热量、蛋白质、碳水、脂肪）
    2. 分餐详情（早餐、午餐、晚餐、加餐，可折叠）
    3. 健康建议

    参数：
        diet_plan: 膳食方案字典，包含：
            - total_calories: 总热量
            - nutrition_balance: 营养均衡信息
            - breakfast/lunch/dinner/snack: 各餐次详情
            - health_tips: 健康建议列表
            - disclaimer: 免责声明

    使用示例：
        >>> diet_plan = {...}
        >>> render_diet_plan_card(diet_plan)
    """

    # ========== 1. 营养总览 ==========
    st.subheader("📊 营养总览")

    # 创建4个指标卡片
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_cal = diet_plan.get("total_calories", 0)
        target_cal = diet_plan.get("daily_target_calories", 0)
        delta = f"目标 {format_calories(target_cal)}" if target_cal else None

        st.metric(
            "总热量",
            format_calories(total_cal),
            delta=delta
        )

    with col2:
        nutrition = diet_plan.get("nutrition_balance", {})
        st.metric("蛋白质", nutrition.get("protein", "--"))

    with col3:
        st.metric("碳水", nutrition.get("carbs", "--"))

    with col4:
        st.metric("脂肪", nutrition.get("fat", "--"))

    # 营养均衡评估
    assessment = nutrition.get("assessment", "")
    if assessment:
        if "均衡" in assessment or "良好" in assessment:
            st.success(f"✅ {assessment}")
        elif "偏低" in assessment or "不足" in assessment:
            st.warning(f"⚠️ {assessment}")
        elif "偏高" in assessment or "过量" in assessment:
            st.warning(f"⚠️ {assessment}")
        else:
            st.info(f"ℹ️ {assessment}")

    st.divider()

    # ========== 2. 分餐详情 ==========
    st.subheader("🍽️ 分餐详情")

    # 按顺序展示各餐次
    meal_order = ["breakfast", "lunch", "dinner", "snack"]

    for meal_type in meal_order:
        meal_data = diet_plan.get(meal_type)

        if not meal_data:
            continue

        # 获取餐次信息
        emoji = get_meal_emoji(meal_type)
        label = get_meal_label(meal_type)
        total_cal = meal_data.get("total_calories", 0)

        # 创建折叠面板
        with st.expander(
            f"{emoji} {label}  ({format_calories(total_cal)})",
            expanded=(meal_type == "breakfast")  # 默认展开早餐
        ):
            items = meal_data.get("items", [])

            if not items:
                st.info("暂无菜品")
                continue

            # 表格头
            cols = st.columns([3, 1, 1, 2])
            with cols[0]:
                st.markdown("**食材**")
            with cols[1]:
                st.markdown("**用量**")
            with cols[2]:
                st.markdown("**热量**")
            with cols[3]:
                st.markdown("**小贴士**")

            st.divider()

            # 食材列表
            for item in items:
                cols = st.columns([3, 1, 1, 2])

                with cols[0]:
                    # 食材名称
                    st.write(f"**{item.get('name', '')}**")

                with cols[1]:
                    # 用量
                    amount = item.get("amount", "")
                    st.write(amount)

                with cols[2]:
                    # 热量
                    cal = item.get("calories", 0)
                    st.write(format_calories(cal))

                with cols[3]:
                    # 小贴士
                    tips = item.get("tips", "")
                    if tips:
                        st.caption(tips)

            # 本餐建议
            meal_tips = meal_data.get("tips", "")
            if meal_tips:
                st.info(f"💡 {meal_tips}")

    st.divider()

    # ========== 3. 健康建议 ==========
    health_tips = diet_plan.get("health_tips", [])

    if health_tips:
        st.subheader("💡 健康建议")

        for i, tip in enumerate(health_tips, 1):
            st.write(f"{i}. {tip}")

    # 免责声明
    disclaimer = diet_plan.get("disclaimer", "")
    if disclaimer:
        st.caption(f"⚠️ {disclaimer}")


def render_diet_plan_compact(diet_plan: Dict[str, Any]):
    """
    渲染紧凑版膳食方案卡片

    用于历史记录列表展示

    参数：
        diet_plan: 膳食方案字典
    """
    with st.container():
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            total_cal = diet_plan.get("total_calories", 0)
            st.write(f"**总热量**: {format_calories(total_cal)}")

        with col2:
            breakfast_cal = diet_plan.get("breakfast", {}).get("total_calories", 0)
            st.write(f"🌅 {format_calories(breakfast_cal)}")

        with col3:
            lunch_cal = diet_plan.get("lunch", {}).get("total_calories", 0)
            st.write(f"☀️ {format_calories(lunch_cal)}")

        with col4:
            dinner_cal = diet_plan.get("dinner", {}).get("total_calories", 0)
            st.write(f"🌙 {format_calories(dinner_cal)}")


def render_meal_summary(meal_type: str, meal_data: Dict[str, Any]):
    """
    渲染单个餐次摘要

    参数：
        meal_type: 餐次类型
        meal_data: 餐次数据
    """
    emoji = get_meal_emoji(meal_type)
    label = get_meal_label(meal_type)
    total_cal = meal_data.get("total_calories", 0)

    items_count = len(meal_data.get("items", []))

    st.markdown(f"""
    **{emoji} {label}** - {format_calories(total_cal)} - {items_count}道菜品
    """)