"""
知识库管理页面

功能：
1. 知识库文档上传
2. 知识库检索
3. 统计信息展示

设计模式：MVC 中的 View 层
"""

import streamlit as st
from services.api_client import get_api_client

# ======================== 页面配置 ========================
st.set_page_config(
    page_title="知识库管理",
    page_icon="📚",
    layout="wide"
)

# ======================== 权限检查 ========================
if not st.session_state.user_id:
    st.warning("⚠️ 请先登录后再访问知识库")
    if st.button("前往登录"):
        st.switch_page("app.py")
    st.stop()

# ======================== 初始化 ========================
api = st.session_state.api_client

# ======================== 页面标题 ========================
st.title("📚 知识库管理")
st.caption("上传和管理膳食营养知识库文档")
st.divider()

# ======================== 统计卡片 ========================
stats = api.get_knowledge_stats()

if stats:
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("📄 文档总数", stats.get("total_documents", 0))

    with col2:
        st.metric("📝 总字符数", f"{stats.get('total_chars', 0):,}")

    with col3:
        st.metric("📦 分块数量", stats.get("total_chunks", 0))

    with col4:
        categories = stats.get("categories", [])
        st.metric("🏷️ 分类数", len(categories) if categories else 0)

    st.divider()

# ======================== 文档上传 ========================
st.subheader("📤 上传文档")

uploaded_file = st.file_uploader(
    "选择膳食营养相关文档",
    type=["txt", "md", "pdf", "docx"],
    help="支持格式：.txt / .md / .pdf / .docx"
)

if uploaded_file:
    # 预览文件内容
    try:
        content = uploaded_file.read().decode("utf-8", errors="ignore")
        uploaded_file.seek(0)  # 重置文件指针

        with st.expander("📄 预览文档", expanded=False):
            preview_text = content[:1000] + "..." if len(content) > 1000 else content
            st.text(preview_text)
    except Exception as e:
        st.error(f"文件读取失败：{e}")

    # 文档分类选择
    col1, col2 = st.columns([2, 1])

    with col1:
        category = st.selectbox(
            "文档分类",
            [
                "chronic_disease",  # 慢病饮食
                "basic_nutrition",  # 基础营养
                "regional",         # 地域饮食
                "taboo",            # 食物忌口
                "recipe"            # 食谱菜谱
            ],
            format_func=lambda x: {
                "chronic_disease": "慢病饮食",
                "basic_nutrition": "基础营养",
                "regional": "地域饮食",
                "taboo": "食物忌口",
                "recipe": "食谱菜谱"
            }.get(x, x)
        )

    with col2:
        if st.button("🚀 上传并向量化", type="primary", use_container_width=True):
            with st.spinner("正在处理文档..."):
                result = api.upload_knowledge(uploaded_file, category)

                if result:
                    chunks = result.get("chunks_created", 0)
                    st.success(f"✅ 上传成功！创建 {chunks} 个知识分块")
                    st.balloons()
                else:
                    st.error("❌ 上传失败，请检查文件格式")

st.divider()

# ======================== 知识库检索 ========================
st.subheader("🔍 知识库检索")

search_query = st.text_input(
    "输入检索关键词",
    placeholder="如：糖尿病饮食、痛风忌口、减脂食谱...",
    key="knowledge_search_input"
)

if search_query:
    with st.spinner("检索中..."):
        results = api.search_knowledge(search_query, top_k=5)

        if results:
            st.success(f"找到 {len(results)} 条相关知识")

            for i, doc in enumerate(results, 1):
                score = doc.get("score", 0)
                content = doc.get("content", "")
                category = doc.get("category", "未知")

                with st.expander(
                    f"📄 结果 {i} (相关度: {score:.2f})",
                    expanded=(i == 1)
                ):
                    st.markdown(f"**分类**：`{category}`")
                    st.divider()
                    st.write(content[:500] + "..." if len(content) > 500 else content)
        else:
            st.info("未找到相关文档，请尝试其他关键词或先上传知识库文档")

st.divider()

# ======================== 使用指南 ========================
st.subheader("📖 使用指南")

st.markdown("""
**知识库的作用：**

知识库是 AI 膳食顾问的"大脑"，存储了专业的营养学知识。

当您提问时，AI 会：
1. 根据您的问题检索相关知识库文档
2. 结合检索到的知识生成答案
3. 确保建议科学可靠

**建议上传的内容：**

- 📚 **慢病饮食指南**：糖尿病、高血压、痛风等疾病饮食注意事项
- 🥗 **基础营养知识**：蛋白质、碳水、脂肪等营养素作用
- 🍜 **地域饮食特色**：南北方、川渝、沿海等地饮食偏好
- 🚫 **食物忌口知识**：过敏源、不宜同食的食物等
- 📖 **健康食谱**：适合不同人群的食谱菜谱

**上传提示：**

- 文档内容越专业，AI 回答越准确
- 建议上传结构化、条理清晰的文档
- 支持多个文档，覆盖不同维度的知识
""")

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