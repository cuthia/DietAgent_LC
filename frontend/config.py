"""
前端配置模块

功能：
1. 定义后端API地址和路径
2. 页面配置参数
3. 环境相关配置

设计模式：配置集中管理，便于环境切换
"""

import os

# ======================== 后端API配置 ========================

# 后端 API 地址（可通过环境变量覆盖）
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# API 路径映射（统一管理所有后端接口路径）
API_PATHS = {
    # 用户认证相关
    "login": "/api/user/login",
    "register": "/api/user/register",
    "profile": "/api/agent/user/{user_id}/profile",

    # Agent 对话相关
    "chat": "/api/agent/chat",
    "chat_stream": "/api/agent/chat/stream",
    "chat_history": "/api/agent/user/{user_id}/history",
    "diet_history": "/api/agent/user/{user_id}/diet-history",
    "clear_history": "/api/agent/user/{user_id}/history",

    # 知识库管理相关
    "knowledge_upload": "/api/knowledge/upload",
    "knowledge_search": "/api/knowledge/search",
    "knowledge_delete": "/api/knowledge/{doc_id}",
    "knowledge_stats": "/api/knowledge/stats",

    # 膳食方案校验
    "validate": "/api/agent/validate",
}

# ======================== 页面配置 ========================

# Streamlit 页面配置
PAGE_CONFIG = {
    "page_title": "每日膳食搭配助手",
    "page_icon": "🥗",
    "layout": "wide",  # 宽屏布局，更好展示膳食方案卡片
    "initial_sidebar_state": "expanded",
}

# 对话历史配置
CHAT_CONFIG = {
    "max_history_messages": 50,  # 最多显示50条历史消息
    "max_diet_history": 20,      # 最多显示20份历史膳食方案
}

# 营养目标范围配置（用于校验）
NUTRITION_TARGETS = {
    "calories_min": 1200,  # 每日最低热量
    "calories_max": 3500,  # 每日最高热量
    "protein_ratio_min": 0.15,  # 蛋白质占比最低15%
    "carbs_ratio_min": 0.45,    # 碳水占比最低45%
    "fat_ratio_max": 0.30,      # 脂肪占比最高30%
}

# 餐次配置
MEAL_CONFIG = {
    "breakfast": {"name": "早餐", "emoji": "🌅", "calorie_ratio": 0.30},
    "lunch": {"name": "午餐", "emoji": "☀️", "calorie_ratio": 0.40},
    "dinner": {"name": "晚餐", "emoji": "🌙", "calorie_ratio": 0.25},
    "snack": {"name": "加餐", "emoji": "🍎", "calorie_ratio": 0.05},
}