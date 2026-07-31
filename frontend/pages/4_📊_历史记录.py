"""
历史记录页面

功能：
1. 查看对话历史
2. 查看膳食方案历史
3. 清空历史记录

设计模式：MVC 中的 View 层
"""

import streamlit as st
from services.api_client import get_api_client
from components.diet_card import render_diet_plan_card, render_diet_plan_compact
from components.chat_display import render_chat_message
from utils.helpers import format_datetime

# ======================== 页面配置 ========================
st.set_page_config(
    page_title="历史记录",
    page_icon="📊",
    layout="wide"
)

# ======================== 权限检查 ========================
if not st.session_state.user_id:
    st.warning("⚠️ 请先登录后再访问历史记录")
    if st.button("前往登录"):
        st.switch_page("app.py")
    st.stop()

# ======================== 初始化 ========================
api = st.session_state.api_client
user_id = st.session_state.user_id

# ======================== 页面标题 ========================
st.title("📊 历史记录")
st.caption("查看您的对话历史和膳食方案")
st.divider()

# ======================== 标签页 ========================
tab1, tab2 = st.tabs(["💬 对话历史", "📋 膳食方案历史"])

# ========== 标签页1：对话历史 ==========
with tab1:
    st.subheader("对话历史")

    # 获取对话历史
    history = api.get_chat_history(user_id, max_messages=50)

    if history:
        # 按会话分组
        sessions = {}

        for msg in history:
            sid = msg.get("session_id", "default")
            if sid not in sessions:
                sessions[sid] = []
            sessions[sid].append(msg)

        # 展示每个会话
        for sid, messages in sessions.items():
            # 显示会话ID和时间范围
            first_msg = messages[0] if messages else {}
            last_msg = messages[-1] if messages else {}

            first_time = format_datetime(first_msg.get("timestamp", 0))
            last_time = format_datetime(last_msg.get("timestamp", 0))

            with st.expander(
                f"🗨️ 会话 ({len(messages)} 条消息) - {first_time}",
                expanded=False
            ):
                # 显示每条消息
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    timestamp = msg.get("timestamp", 0)

                    # 创建消息气泡
                    with st.chat_message(role, avatar="👤" if role == "user" else "🥗"):
                        st.write(content)
                        if timestamp:
                            st.caption(f"🕐 {format_datetime(timestamp)}")

        # 清空历史按钮
        st.divider()

        col1, col2, col3 = st.columns([1, 1, 2])

        with col1:
            if st.button("🗑️ 清空对话历史", type="secondary"):
                # 显示确认对话框
                st.session_state.show_clear_confirm = True

        # 确认对话框
        if st.session_state.get("show_clear_confirm", False):
            st.warning("⚠️ 确定要清空所有对话历史吗？此操作不可恢复！")

            col_confirm, col_cancel = st.columns(2)

            with col_confirm:
                if st.button("✅ 确认清空"):
                    success = api.clear_history(user_id)

                    if success:
                        st.success("✅ 对话历史已清空")
                        st.session_state.show_clear_confirm = False
                        st.rerun()
                    else:
                        st.error("❌ 清空失败，请稍后重试")

            with col_cancel:
                if st.button("❌ 取消"):
                    st.session_state.show_clear_confirm = False
                    st.rerun()

    else:
        st.info("""
        📭 暂无对话历史

        💬 **开始对话**，AI 会为您记录每一次交流
        """)

        if st.button("前往对话", use_container_width=True):
            st.switch_page("pages/1_💬_膳食对话.py")

# ========== 标签页2：膳食方案历史 ==========
with tab2:
    st.subheader("膳食方案历史")

    # 获取膳食方案历史
    diet_history = api.get_diet_history(user_id, limit=20)

    if diet_history:
        st.info(f"共 {len(diet_history)} 份历史膳食方案")

        # 展示每份方案
        for i, record in enumerate(reversed(diet_history), 1):
            plan = record.get("plan", {})
            saved_at = record.get("saved_at", 0)

            # 方案摘要
            total_cal = plan.get("total_calories", 0)
            time_str = format_datetime(saved_at)

            with st.expander(
                f"📋 方案 #{i} - {time_str} - 总热量: {total_cal} kcal",
                expanded=(i == 1)  # 默认展开最新的方案
            ):
                # 渲染方案详情
                render_diet_plan_card(plan)

    else:
        st.info("""
        📭 暂无历史膳食方案

        💬 **开始对话**，AI 会为您生成并保存膳食方案
        """)

        if st.button("前往对话", use_container_width=True):
            st.switch_page("pages/1_💬_膳食对话.py")

# ======================== 底部操作区 ========================
st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("💬 开始对话", use_container_width=True):
        st.switch_page("pages/1_💬_膳食对话.py")

with col2:
    if st.button("📝 编辑档案", use_container_width=True):
        st.switch_page("pages/2_👤_健康档案.py")

with col3:
    if st.button("🏠 返回首页", use_container_width=True):
        st.switch_page("app.py")

# ======================== 提示信息 ========================
st.divider()
st.caption("""
💡 **提示**：
- 对话历史按会话分组，便于追溯上下文
- 膳食方案会自动保存，方便随时查看
- 可随时清空对话历史，保护隐私
""")