"""
Streamlit 主入口文件

功能：
1. 初始化页面配置和全局状态
2. 实现用户登录/注册界面
3. 展示侧边栏导航
4. 提供欢迎页面

设计模式：MVC 架构中的 View 层
"""

import streamlit as st
from services.api_client import get_api_client
from config import PAGE_CONFIG
from utils.helpers import calculate_bmi, get_bmi_category

# ======================== 页面配置（必须是第一个 Streamlit 命令）========================
st.set_page_config(**PAGE_CONFIG)

# ======================== 初始化会话状态 ========================
"""
Streamlit session_state 说明：
- 每次用户交互时会重新运行整个脚本
- session_state 用于保存跨交互的状态数据
- 类似于前端的 localStorage / sessionStorage
"""

# API 客户端实例（全局单例）
if "api_client" not in st.session_state:
    st.session_state.api_client = get_api_client()

# 用户ID（登录后设置）
if "user_id" not in st.session_state:
    st.session_state.user_id = None

# 会话ID（多轮对话标识）
if "session_id" not in st.session_state:
    st.session_state.session_id = None

# 对话消息列表
if "messages" not in st.session_state:
    st.session_state.messages = []

# 当前膳食方案（用于保存/查看）
if "current_diet_plan" not in st.session_state:
    st.session_state.current_diet_plan = None

# ======================== 侧边栏 ========================
with st.sidebar:
    st.title("🥗 膳食搭配助手")
    st.caption("AI 驱动的个性化营养顾问")

    st.divider()

    # ========== 未登录状态：显示登录/注册 ==========
    if not st.session_state.user_id:
        tab_login, tab_register = st.tabs(["🔑 登录", "📝 注册"])

        # 登录表单
        with tab_login:
            with st.form("login_form"):
                username = st.text_input(
                    "用户名",
                    placeholder="请输入用户名",
                    key="login_username"
                )
                password = st.text_input(
                    "密码",
                    type="password",
                    placeholder="请输入密码",
                    key="login_password"
                )

                submitted = st.form_submit_button("登录", use_container_width=True)

                if submitted:
                    if not username or not password:
                        st.error("请填写用户名和密码")
                    else:
                        api = st.session_state.api_client
                        result = api.login(username, password)

                        if result:
                            st.session_state.user_id = result.get("user_id")
                            st.success("登录成功！")
                            st.rerun()  # 重新运行以更新页面状态
                        else:
                            st.error("用户名或密码错误，请重试")

        # 注册表单
        with tab_register:
            with st.form("register_form"):
                reg_username = st.text_input(
                    "用户名",
                    placeholder="设置用户名",
                    key="reg_username"
                )
                reg_password = st.text_input(
                    "密码",
                    type="password",
                    placeholder="设置密码",
                    key="reg_password"
                )
                reg_password_confirm = st.text_input(
                    "确认密码",
                    type="password",
                    placeholder="再次输入密码",
                    key="reg_password_confirm"
                )

                submitted = st.form_submit_button("注册", use_container_width=True)

                if submitted:
                    if not reg_username or not reg_password:
                        st.error("请填写用户名和密码")
                    elif reg_password != reg_password_confirm:
                        st.error("两次密码输入不一致")
                    else:
                        api = st.session_state.api_client
                        result = api.register(reg_username, reg_password)

                        if result:
                            st.session_state.user_id = result.get("user_id")
                            st.success("注册成功！已自动登录")
                            st.rerun()
                        else:
                            st.error("注册失败，用户名可能已存在")

    # ========== 已登录状态：显示用户信息和快捷操作 ==========
    else:
        api = st.session_state.api_client

        # 尝试获取用户档案
        profile = api.get_profile(st.session_state.user_id)

        st.success(f"👋 欢迎回来！")

        if profile:
            # 计算并显示 BMI
            height = profile.get("height", 0)
            weight = profile.get("weight", 0)

            if height and weight:
                bmi = calculate_bmi(height, weight)
                bmi_category = get_bmi_category(bmi)

                col1, col2 = st.columns(2)
                with col1:
                    st.metric("年龄", f"{profile.get('age', '-')}岁")
                with col2:
                    st.metric("BMI", f"{bmi} ({bmi_category})")
            else:
                st.info("📝 请完善健康档案以获取个性化方案")

        st.divider()

        # 快捷操作按钮
        if st.button("💬 开始对话", use_container_width=True, type="primary"):
            st.switch_page("pages/1_💬_膳食对话.py")

        if st.button("📝 编辑健康档案", use_container_width=True):
            st.switch_page("pages/2_👤_健康档案.py")

        if st.button("📚 管理知识库", use_container_width=True):
            st.switch_page("pages/3_📚_知识库.py")

        if st.button("📊 历史方案", use_container_width=True):
            st.switch_page("pages/4_📊_历史记录.py")

        st.divider()

        # 退出登录
        if st.button("🚪 退出登录", use_container_width=True):
            api.logout()
            st.session_state.user_id = None
            st.session_state.messages = []
            st.session_state.current_diet_plan = None
            st.rerun()

# ======================== 主内容区 ========================
st.title("🥗 每日膳食搭配助手")
st.markdown("---")

# 未登录：展示欢迎信息
if not st.session_state.user_id:
    # 左侧：功能介绍
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("""
        ## 🌟 AI 驱动的个性化营养顾问

        基于 LangChain + RAG 技术的智能膳食搭配系统，为您提供科学的饮食建议。

        ### ✨ 核心功能

        - 🤖 **AI 智能分析**：基于您的健康档案（年龄、体重、慢病等），提供个性化膳食建议
        - 📚 **RAG 知识增强**：结合专业营养学知识库，方案更科学可靠
        - 🎯 **多维度约束**：综合考虑慢病禁忌、食物忌口、地域饮食、膳食目标
        - 📊 **营养可视化**：清晰展示热量、蛋白质、碳水等营养成分配比
        - 💬 **多轮对话**：支持追问、调整，让方案更贴合您的口味偏好
        - 🔄 **流式输出**：实时展示处理进度，了解 AI 如何为您定制方案

        ### 🎯 适用场景

        - 减脂塑形、增肌增重
        - 慢病饮食管理（糖尿病、高血压、痛风等）
        - 地域化膳食搭配（南方/北方/川渝/沿海等）
        - 特殊人群营养方案（孕期、老年、儿童等）

        ---

        👈 **请在左侧登录或注册**，开始您的健康饮食之旅！
        """)

    with col2:
        st.markdown("""
        ### 📌 使用流程

        1. **注册/登录** 账号
        2. **完善健康档案**（年龄、身高、体重、慢病等）
        3. **开始对话**，描述您的饮食需求
        4. **查看方案**，营养搭配一目了然
        5. **追问调整**，让方案更贴合您的口味

        ---

        ### 💬 对话示例

        - "给我设计一份减脂餐"
        - "糖尿病患者早餐吃什么好？"
        - "我是北方人，痛风该怎么吃？"
        - "最近健身，帮我设计增肌食谱"
        """)

# 已登录：引导进入对话页
else:
    st.markdown("""
    ### 👋 欢迎使用膳食搭配助手！

    您已登录，可以开始使用 AI 膳食顾问为您定制个性化方案。

    👉 **点击左侧 [💬 开始对话] 按钮**，或在下方直接进入：

    """)

    if st.button("🚀 立即开始对话", type="primary", use_container_width=True):
        st.switch_page("pages/1_💬_膳食对话.py")

    st.markdown("---")

    # 如果有健康档案，显示简要信息
    api = st.session_state.api_client
    profile = api.get_profile(st.session_state.user_id)

    if profile and profile.get("height") and profile.get("weight"):
        st.markdown("### 📊 您的健康档案概览")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("年龄", f"{profile.get('age', '-')}岁")

        with col2:
            st.metric("身高", f"{profile.get('height', '-')}cm")

        with col3:
            st.metric("体重", f"{profile.get('weight', '-')}kg")

        with col4:
            bmi = calculate_bmi(profile.get("height", 0), profile.get("weight", 0))
            st.metric("BMI", f"{bmi}")

        # 显示慢病和目标
        chronic = profile.get("chronic_disease", "")
        goal = profile.get("diet_goal", "日常养生")

        if chronic:
            st.info(f"📋 慢病情况：{chronic}  |  🎯 膳食目标：{goal}")
        else:
            st.info(f"🎯 膳食目标：{goal}")

    else:
        st.info("📝 建议先完善健康档案，以便获得更精准的膳食建议")

# ======================== 页脚 ========================
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #888; font-size: 12px;">
    基于 LangChain + Streamlit 构建 | 数据来源：专业营养学知识库
</div>
""", unsafe_allow_html=True)