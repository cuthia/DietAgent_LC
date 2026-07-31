"""
膳食对话主页面

功能：
1. AI 膳食对话界面
2. 流式输出处理进度
3. 膳食方案可视化展示
4. 多轮对话支持

设计模式：MVC 中的 View 层
"""

import streamlit as st
import time
from services.api_client import get_api_client
from components.chat_display import render_chat_message, render_progress_update
from components.diet_card import render_diet_plan_card
from utils.helpers import format_datetime

# ======================== 页面配置 ========================
st.set_page_config(
    page_title="膳食对话",
    page_icon="💬",
    layout="wide"
)

# ======================== 状态初始化 ========================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "processing" not in st.session_state:
    st.session_state.processing = False
if "current_plan" not in st.session_state:
    st.session_state.current_plan = None

api = st.session_state.api_client

# ======================== 权限检查 ========================
if not st.session_state.user_id:
    st.warning("⚠️ 请先登录后再使用对话功能")
    if st.button("前往登录"):
        st.switch_page("app.py")
    st.stop()

# ======================== 页面标题 ========================
st.title("💬 AI 膳食顾问")
st.caption("基于您的健康档案，为您定制个性化膳食方案")
st.divider()

# ======================== 聊天消息展示区 ========================
# 使用高度固定的容器，避免滚动时跳动
chat_container = st.container(height=500)

with chat_container:
    # 欢迎消息
    if not st.session_state.messages:
        with st.chat_message("assistant", avatar="🥗"):
            st.write("""
            你好！我是 **AI 膳食顾问** 🥗

            我可以根据您的健康状况（年龄、体重、慢病、忌口等）为您制定个性化膳食方案。

            **试试这样问我：**
            - "给我设计一份减脂餐"
            - "糖尿病患者早餐吃什么好？"
            - "我是北方人，痛风该怎么吃？"
            - "最近健身，帮我设计增肌食谱"

            💡 **提示**：完善健康档案可以获得更精准的推荐！
            """)

    # 历史消息
    for msg in st.session_state.messages:
        render_chat_message(msg)

# ======================== 用户输入区 ========================
# 禁用输入框当正在处理时
if st.session_state.processing:
    prompt = st.chat_input(
        "AI 正在处理中...",
        disabled=True
    )
else:
    prompt = st.chat_input(
        "描述您的饮食需求...（如：给我设计一份减脂餐）"
    )

# ======================== 处理用户输入 ========================
if prompt and not st.session_state.processing:
    # 添加用户消息
    st.session_state.messages.append({
        "role": "user",
        "content": prompt,
        "timestamp": time.time()
    })

    # 重新渲染显示
    with chat_container:
        render_chat_message({
            "role": "user",
            "content": prompt,
            "timestamp": time.time()
        })

    # 调用 Agent（流式）
    st.session_state.processing = True

    with chat_container:
        with st.chat_message("assistant", avatar="🥗"):
            # 进度显示区
            progress_placeholder = st.empty()
            plan_placeholder = st.empty()
            text_placeholder = st.empty()

            # 进度消息列表
            progress_messages = []

            # 最终响应数据
            final_response = {
                "message": "",
                "diet_plan": None,
                "session_id": None
            }

            try:
                # 调用流式接口
                for event in api.chat_stream(
                    message=prompt,
                    session_id=st.session_state.session_id
                ):
                    # 错误处理
                    if event.get("stage") == "error":
                        text_placeholder.error(f"❌ 处理失败：{event.get('message', '未知错误')}")
                        break

                    # 进度更新
                    status = event.get("status", "")
                    message = event.get("message", "")

                    if status == "start":
                        progress_messages.append(f"⏳ {message}")
                    elif status == "complete":
                        progress_messages.append(f"✅ {message}")

                    # 更新进度显示
                    with progress_placeholder.container():
                        for msg in progress_messages:
                            st.write(msg)

                    # 处理最终输出
                    if event.get("stage") == "output" and event.get("data"):
                        data = event["data"]

                        # 保存 session_id
                        if data.get("session_id"):
                            st.session_state.session_id = data["session_id"]
                            final_response["session_id"] = data["session_id"]

                        # 显示文本回复
                        if data.get("message"):
                            final_response["message"] = data["message"]
                            text_placeholder.write(data["message"])

                        # 渲染膳食方案
                        if data.get("diet_plan"):
                            final_response["diet_plan"] = data["diet_plan"]
                            st.session_state.current_plan = data["diet_plan"]

                            with plan_placeholder.container():
                                render_diet_plan_card(data["diet_plan"])

                # 清空进度显示
                progress_placeholder.empty()

                # 保存到历史
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": final_response["message"],
                    "diet_plan": final_response["diet_plan"],
                    "timestamp": time.time()
                })

            except Exception as e:
                text_placeholder.error(f"❌ 对话异常：{str(e)}")
                st.error("请稍后重试或联系管理员")

    st.session_state.processing = False
    st.rerun()

# ======================== 侧边栏：快捷操作 ========================
with st.sidebar:
    st.divider()

    # 当前会话信息
    if st.session_state.session_id:
        st.caption(f"📝 会话ID: `{st.session_state.session_id[:8]}...`")

    st.divider()

    # 快捷操作
    st.subheader("⚡ 快捷操作")

    if st.button("🔄 新建对话", use_container_width=True):
        st.session_state.messages = []
        st.session_state.current_plan = None
        st.session_state.session_id = None
        st.rerun()

    if st.button("📝 编辑健康档案", use_container_width=True):
        st.switch_page("pages/2_👤_健康档案.py")

    if st.button("📊 查看历史方案", use_container_width=True):
        st.switch_page("pages/4_📊_历史记录.py")

    st.divider()

    # 当前方案
    if st.session_state.current_plan:
        st.subheader("📋 当前方案")

        total_cal = st.session_state.current_plan.get("total_calories", 0)
        st.write(f"总热量：{total_cal} kcal")

        if st.button("💾 保存方案", use_container_width=True):
            # TODO: 调用保存接口
            st.success("✅ 方案已保存！")

    # 示例问题
    st.divider()
    st.subheader("💡 示例问题")
    st.caption("点击可快速输入")

    examples = [
        "给我设计一份减脂餐",
        "糖尿病患者早餐吃什么？",
        "我是北方人，痛风该怎么吃？",
        "最近健身，帮我设计增肌食谱"
    ]

    for example in examples:
        if st.button(example, key=f"example_{example}", use_container_width=True):
            # 模拟输入
            st.session_state.example_input = example
            st.rerun()

# ======================== 处理示例输入 ========================
if "example_input" in st.session_state:
    example = st.session_state.example_input
    del st.session_state.example_input
    # 通过 JavaScript 填充输入框（Streamlit 限制，需要用户确认）
    st.info(f"💡 您想问：\"{example}\"，请在下方输入框确认或修改后发送")