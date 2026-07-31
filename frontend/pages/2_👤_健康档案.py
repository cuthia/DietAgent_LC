"""
用户健康档案页面

功能：
1. 查看当前健康档案
2. 编辑档案信息
3. 保存更新

设计模式：MVC 中的 View 层
"""

import streamlit as st
from services.api_client import get_api_client
from components.user_form import render_user_form, render_profile_summary, render_bmi_card
from utils.helpers import calculate_bmi, get_bmi_category

# ======================== 页面配置 ========================
st.set_page_config(
    page_title="健康档案",
    page_icon="👤",
    layout="wide"
)

# ======================== 权限检查 ========================
if not st.session_state.user_id:
    st.warning("⚠️ 请先登录后再访问健康档案")
    if st.button("前往登录"):
        st.switch_page("app.py")
    st.stop()

# ======================== 初始化 ========================
api = st.session_state.api_client
user_id = st.session_state.user_id

# ======================== 页面标题 ========================
st.title("👤 健康档案管理")
st.caption("完善您的健康信息，获得更精准的膳食推荐")
st.divider()

# ======================== 获取当前档案 ========================
profile = api.get_profile(user_id)

# ======================== 左右布局 ========================
col1, col2 = st.columns([2, 1])

# ========== 左列：表单 ==========
with col1:
    st.subheader("📝 档案编辑")

    # 渲染表单
    result = render_user_form(profile, editable=True)

    # 处理提交
    if result:
        # 调用API保存
        success = api.update_profile(user_id, result)

        if success:
            st.success("✅ 档案保存成功！")
            st.balloons()
            # 刷新页面
            st.rerun()
        else:
            st.error("❌ 保存失败，请稍后重试")

# ========== 右列：摘要和BMI ==========
with col2:
    if profile:
        # 档案摘要
        render_profile_summary(profile)

        st.divider()

        # BMI 卡片
        height = profile.get("height", 0)
        weight = profile.get("weight", 0)

        if height and weight:
            st.subheader("📊 BMI 分析")
            render_bmi_card(height, weight)

            # BMI 参考标准
            with st.expander("📖 BMI 参考标准"):
                st.markdown("""
                **BMI 分类标准（中国成人）：**

                - 偏瘦：BMI < 18.5
                - 正常：18.5 ≤ BMI < 24
                - 超重：24 ≤ BMI < 28
                - 肥胖：BMI ≥ 28

                💡 **提示**：
                - BMI 仅作为参考指标，不能完全反映健康状况
                - 建议结合体脂率、腰围等指标综合评估
                - 如有疑问，请咨询专业医生或营养师
                """)
    else:
        st.info("📝 暂无档案数据，请填写左侧表单")

# ======================== 底部操作区 ========================
st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("💬 开始对话", use_container_width=True):
        st.switch_page("pages/1_💬_膳食对话.py")

with col2:
    if st.button("📊 历史方案", use_container_width=True):
        st.switch_page("pages/4_📊_历史记录.py")

with col3:
    if st.button("🏠 返回首页", use_container_width=True):
        st.switch_page("app.py")

# ======================== 提示信息 ========================
st.divider()
st.info("""
💡 **完善档案的好处：**

1. **精准推荐**：AI 会根据您的年龄、体重、慢病情况，生成更适合的方案
2. **自动过滤**：系统会自动避开您的忌口食物
3. **地域适配**：根据您所在地域，推荐当地特色食材
4. **目标匹配**：根据您的膳食目标（减脂/增肌/控糖等），优化营养配比
""")