"""
对话消息展示组件

功能：
1. 渲染对话消息气泡
2. 区分用户/助手消息样式
3. 支持展示膳食方案

设计模式：组件化设计
"""

import streamlit as st
from typing import Dict, Any
from utils.helpers import format_datetime
from components.diet_card import render_diet_plan_card


def render_chat_message(message: Dict[str, Any]):
    """
    渲染单条对话消息

    参数：
        message: 消息字典，包含：
            - role: 角色（user/assistant）
            - content: 消息内容
            - timestamp: 时间戳（可选）
            - diet_plan: 膳食方案（可选，仅助手消息）

    使用示例：
        >>> msg = {"role": "user", "content": "给我设计减脂餐"}
        >>> render_chat_message(msg)
    """

    role = message.get("role", "user")
    content = message.get("content", "")
    timestamp = message.get("timestamp")
    diet_plan = message.get("diet_plan")

    # 设置头像
    if role == "user":
        avatar = "👤"
    else:
        avatar = "🥗"

    # 创建消息气泡
    with st.chat_message(role, avatar=avatar):
        # 显示消息内容
        if content:
            st.write(content)

        # 如果包含膳食方案，渲染方案卡片
        if diet_plan:
            st.divider()
            render_diet_plan_card(diet_plan)

        # 显示时间戳
        if timestamp:
            st.caption(f"🕐 {format_datetime(timestamp)}")


def render_typing_indicator():
    """
    渲染"正在输入"指示器

    用于流式对话时显示处理状态
    """
    with st.chat_message("assistant", avatar="🥗"):
        st.write("⏳ 正在思考...")


def render_progress_update(stage: str, message: str, status: str = "progress"):
    """
    渲染进度更新消息

    参数：
        stage: 阶段名称
        message: 进度消息
        status: 状态（progress/success/error）
    """
    if status == "success":
        st.success(f"✅ {message}")
    elif status == "error":
        st.error(f"❌ {message}")
    else:
        st.info(f"⏳ {message}")