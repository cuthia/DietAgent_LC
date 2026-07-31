"""
用户健康档案表单组件

功能：
1. 渲染健康档案录入表单
2. 数据校验
3. BMI 计算

设计模式：组件化设计，可复用
"""

import streamlit as st
from typing import Dict, Any, Optional
from utils.helpers import calculate_bmi, get_bmi_category


def render_user_form(profile: Optional[Dict] = None, editable: bool = True) -> Dict[str, Any]:
    """
    渲染用户健康档案表单

    参数：
        profile: 当前档案数据（编辑模式）
        editable: 是否可编辑

    返回：
        表单数据字典（提交时）或空字典

    使用示例：
        >>> profile = {"age": 25, "height": 170, ...}
        >>> result = render_user_form(profile)
        >>> if result:
        ...     # 保存档案
        ...     api.update_profile(user_id, result)
    """

    st.subheader("👤 健康档案")

    if not profile:
        st.info("📝 请填写您的健康信息，以便 AI 为您制定个性化方案")
        profile = {}

    with st.form("user_profile_form", clear_on_submit=False):
        # 左右两列布局
        col1, col2 = st.columns(2)

        # ========== 左列：基础信息 ==========
        with col1:
            st.markdown("**基础信息**")

            # 年龄
            age = st.number_input(
                "年龄（岁）",
                min_value=1,
                max_value=120,
                value=profile.get("age", 25) or 25,
                disabled=not editable
            )

            # 性别
            gender_options = ["male", "female"]
            gender_labels = ["男", "女"]
            default_gender = profile.get("gender", "male") or "male"
            gender_index = gender_options.index(default_gender) if default_gender in gender_options else 0

            gender = st.selectbox(
                "性别",
                gender_options,
                index=gender_index,
                format_func=lambda x: gender_labels[gender_options.index(x)],
                disabled=not editable
            )

            # 身高
            height = st.number_input(
                "身高（cm）",
                min_value=50,
                max_value=250,
                value=profile.get("height", 170) or 170,
                disabled=not editable
            )

            # 体重
            weight = st.number_input(
                "体重（kg）",
                min_value=20,
                max_value=300,
                value=profile.get("weight", 65) or 65,
                disabled=not editable
            )

        # ========== 右列：健康信息 ==========
        with col2:
            st.markdown("**健康信息**")

            # 慢性疾病
            chronic_options = [
                "无",
                "糖尿病",
                "高血压",
                "痛风",
                "高血脂",
                "胃炎",
                "胃溃疡",
                "肾病",
                "心脏病",
                "其他"
            ]
            default_chronic = profile.get("chronic_disease", "无") or "无"
            chronic_index = chronic_options.index(default_chronic) if default_chronic in chronic_options else 0

            chronic_disease = st.selectbox(
                "慢性疾病",
                chronic_options,
                index=chronic_index,
                disabled=not editable
            )

            # 食物忌口
            food_taboo = st.text_input(
                "食物忌口",
                value=profile.get("food_taboo", ""),
                placeholder="多个用逗号分隔，如：海鲜, 花生, 辣椒",
                disabled=not editable,
                help="请填写您不能吃或不爱吃的食物"
            )

            # 地域
            region_options = [
                "未设置",
                "北方",
                "南方",
                "沿海",
                "川渝",
                "江南",
                "东北",
                "西北",
                "其他"
            ]
            default_region = profile.get("region", "未设置") or "未设置"
            region_index = region_options.index(default_region) if default_region in region_options else 0

            region = st.selectbox(
                "所在地域",
                region_options,
                index=region_index,
                disabled=not editable,
                help="地域会影响饮食偏好和食材选择"
            )

            # 膳食目标
            goal_options = [
                "日常养生",
                "减脂塑形",
                "增肌增重",
                "控糖管理",
                "降压调理",
                "养胃护胃",
                "其他"
            ]
            default_goal = profile.get("diet_goal", "日常养生") or "日常养生"
            goal_index = goal_options.index(default_goal) if default_goal in goal_options else 0

            diet_goal = st.selectbox(
                "膳食目标",
                goal_options,
                index=goal_index,
                disabled=not editable
            )

        # ========== 提交按钮 ==========
        submitted = st.form_submit_button(
            "💾 保存档案",
            disabled=not editable,
            use_container_width=True
        )

        if submitted:
            return {
                "age": age,
                "gender": gender,
                "height": height,
                "weight": weight,
                "chronic_disease": chronic_disease if chronic_disease != "无" else "",
                "food_taboo": food_taboo.strip(),
                "region": region if region != "未设置" else "",
                "diet_goal": diet_goal,
            }

    return {}


def render_bmi_card(height: float, weight: float):
    """
    渲染 BMI 信息卡片

    参数：
        height: 身高（cm）
        weight: 体重（kg）
    """
    if height <= 0 or weight <= 0:
        return

    bmi = calculate_bmi(height, weight)
    category = get_bmi_category(bmi)

    # 根据BMI分类设置颜色
    if category == "正常":
        color = "green"
    elif category == "偏瘦":
        color = "blue"
    else:
        color = "orange"

    st.markdown(f"""
    <div style="padding: 10px; border-radius: 5px; background-color: #f0f2f6; margin: 10px 0;">
        <p style="margin: 0; font-size: 16px;"><strong>BMI 指数</strong></p>
        <p style="margin: 5px 0; font-size: 24px; color: {color};"><strong>{bmi}</strong> ({category})</p>
    </div>
    """, unsafe_allow_html=True)


def render_profile_summary(profile: Dict[str, Any]):
    """
    渲染档案摘要卡片

    参数：
        profile: 档案数据字典
    """
    st.subheader("📋 档案摘要")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("年龄", f"{profile.get('age', '-')}岁")

    with col2:
        st.metric("身高", f"{profile.get('height', '-')}cm")

    with col3:
        st.metric("体重", f"{profile.get('weight', '-')}kg")

    # BMI
    height = profile.get("height", 0)
    weight = profile.get("weight", 0)

    if height and weight:
        bmi = calculate_bmi(height, weight)
        category = get_bmi_category(bmi)
        st.metric("BMI", f"{bmi} ({category})")

    # 健康信息
    st.divider()

    chronic = profile.get("chronic_disease", "")
    goal = profile.get("diet_goal", "")
    region = profile.get("region", "")
    taboo = profile.get("food_taboo", "")

    if chronic:
        st.write(f"📋 **慢病情况**：{chronic}")

    if goal:
        st.write(f"🎯 **膳食目标**：{goal}")

    if region:
        st.write(f"📍 **所在地域**：{region}")

    if taboo:
        st.write(f"🚫 **食物忌口**：{taboo}")