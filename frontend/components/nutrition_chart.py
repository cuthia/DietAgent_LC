"""
营养图表组件

功能：
1. 营养均衡雷达图
2. 各餐次热量分布饼图
3. 营养成分柱状图

依赖：plotly

设计模式：组件化设计
"""

import streamlit as st
from typing import Dict, Any

# 尝试导入 plotly，如果失败则降级
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    st.warning("⚠️ plotly 未安装，营养图表功能不可用。请运行：`pip install plotly`")


def render_nutrition_radar(nutrition: Dict[str, Any]):
    """
    渲染营养均衡雷达图

    展示蛋白质、碳水、脂肪、膳食纤维、维生素等营养素的均衡程度

    参数：
        nutrition: 营养数据字典，包含各营养素得分

    使用示例：
        >>> nutrition = {"protein_score": 70, "carbs_score": 65, ...}
        >>> render_nutrition_radar(nutrition)
    """

    if not PLOTLY_AVAILABLE:
        st.info("📊 营养雷达图需要安装 plotly")
        return

    # 默认值（如果数据缺失）
    categories = ["蛋白质", "碳水", "脂肪", "膳食纤维", "维生素"]
    values = [
        float(nutrition.get("protein_score", 70)),
        float(nutrition.get("carbs_score", 65)),
        float(nutrition.get("fat_score", 60)),
        float(nutrition.get("fiber_score", 55)),
        float(nutrition.get("vitamin_score", 50)),
    ]

    # 创建雷达图
    fig = go.Figure(data=go.Scatterpolar(
        r=values + [values[0]],  # 闭合图形
        theta=categories + [categories[0]],
        fill="toself",
        name="营养均衡",
        line_color="#2ecc71",
        fillcolor="rgba(46, 204, 113, 0.3)",  # 半透明绿色
    ))

    # 更新布局
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100]
            )
        ),
        showlegend=False,
        height=350,
        margin=dict(l=20, r=20, t=20, b=20),
    )

    # 渲染图表
    st.plotly_chart(fig, use_container_width=True)


def render_meal_calorie_breakdown(diet_plan: Dict[str, Any]):
    """
    渲染各餐次热量分布饼图

    展示早餐、午餐、晚餐、加餐的热量占比

    参数：
        diet_plan: 膳食方案字典

    使用示例：
        >>> diet_plan = {"breakfast": {"total_calories": 400}, ...}
        >>> render_meal_calorie_breakdown(diet_plan)
    """

    if not PLOTLY_AVAILABLE:
        st.info("📊 热量分布图需要安装 plotly")
        return

    # 收集各餐次热量
    meals = []
    calories = []
    colors = []

    meal_order = [
        ("breakfast", "🌅 早餐", "#f39c12"),
        ("lunch", "☀️ 午餐", "#e74c3c"),
        ("dinner", "🌙 晚餐", "#3498db"),
        ("snack", "🍎 加餐", "#2ecc71"),
    ]

    for key, label, color in meal_order:
        meal = diet_plan.get(key, {})
        cal = meal.get("total_calories", 0)

        if cal > 0:
            meals.append(label)
            calories.append(cal)
            colors.append(color)

    # 如果没有数据，不渲染
    if not meals:
        return

    # 创建饼图
    fig = go.Figure(data=[go.Pie(
        labels=meals,
        values=calories,
        marker_colors=colors,
        hole=0.4,  # 环形图效果
        textinfo="label+percent",
        textposition="inside",
    )])

    # 更新布局
    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=20, b=20),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.1,
            xanchor="center",
            x=0.5
        )
    )

    # 渲染图表
    st.plotly_chart(fig, use_container_width=True)


def render_nutrition_bar_chart(nutrition: Dict[str, Any]):
    """
    渲染营养成分柱状图

    展示各营养素的具体数值（蛋白质、碳水、脂肪等）

    参数：
        nutrition: 营养数据字典
    """

    if not PLOTLY_AVAILABLE:
        st.info("📊 营养柱状图需要安装 plotly")
        return

    # 准备数据
    categories = ["蛋白质", "碳水", "脂肪"]
    values = []

    # 提取数值（去除单位）
    protein = nutrition.get("protein", "0g")
    carbs = nutrition.get("carbs", "0g")
    fat = nutrition.get("fat", "0g")

    # 转换为数值
    def extract_number(value):
        try:
            return float(str(value).replace("g", "").replace("G", "").strip())
        except:
            return 0

    values = [
        extract_number(protein),
        extract_number(carbs),
        extract_number(fat)
    ]

    # 创建柱状图
    fig = go.Figure(data=[
        go.Bar(
            x=categories,
            y=values,
            marker_color=["#3498db", "#e74c3c", "#f39c12"],
            text=[f"{v}g" for v in values],
            textposition="outside",
        )
    ])

    # 更新布局
    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
        xaxis_title="营养素",
        yaxis_title="含量 (g)",
        showlegend=False,
    )

    # 渲染图表
    st.plotly_chart(fig, use_container_width=True)


def render_calorie_comparison_chart(current: float, target: float):
    """
    渲染热量对比柱状图

    展示当前热量与目标热量的对比

    参数：
        current: 当前热量
        target: 目标热量
    """

    if not PLOTLY_AVAILABLE:
        st.info("📊 热量对比图需要安装 plotly")
        return

    fig = go.Figure(data=[
        go.Bar(
            name="当前热量",
            x=["热量"],
            y=[current],
            marker_color="#3498db",
            text=f"{current:.0f} kcal",
            textposition="outside",
        ),
        go.Bar(
            name="目标热量",
            x=["热量"],
            y=[target],
            marker_color="#e74c3c",
            text=f"{target:.0f} kcal",
            textposition="outside",
        )
    ])

    fig.update_layout(
        height=250,
        margin=dict(l=20, r=20, t=20, b=20),
        barmode="group",
        showlegend=True,
        yaxis_title="kcal",
    )

    st.plotly_chart(fig, use_container_width=True)