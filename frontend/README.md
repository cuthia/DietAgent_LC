# 第四阶段任务实现说明

> **阶段目标**：完成 Streamlit 前端开发，实现可交互的膳食搭配助手 Demo
>
> **开发时间**：2026-07-31
>
> **技术栈**：Streamlit + Plotly + Requests

---

## 一、完成情况总览

| 任务 | 文件 | 状态 |
|------|------|------|
| 4.1 前端工程初始化 | `config.py`, `api_client.py`, `helpers.py` | ✅ |
| 4.2 主入口与全局状态 | `app.py` | ✅ |
| 4.3 对话主页面 | `pages/1_💬_膳食对话.py`, `components/diet_card.py` | ✅ |
| 4.4 用户档案页面 | `pages/2_👤_健康档案.py`, `components/user_form.py` | ✅ |
| 4.5 知识库管理页面 | `pages/3_📚_知识库.py` | ✅ |
| 4.6 历史记录页面 | `pages/4_📊_历史记录.py` | ✅ |
| 4.7 营养图表组件 | `components/nutrition_chart.py` | ✅ |

---

## 二、目录结构

```
frontend/
├── app.py                          # 主入口（登录/注册/欢迎页）
├── config.py                       # 前端配置
├── requirements.txt                # 依赖包
├── README.md                       # 说明文档
│
├── pages/                          # 多页面目录
│   ├── 1_💬_膳食对话.py             # AI 对话主页面（核心）
│   ├── 2_👤_健康档案.py             # 档案编辑页面
│   ├── 3_📚_知识库.py               # 知识库管理页面
│   └── 4_📊_历史记录.py             # 历史记录页面
│
├── components/                     # UI 组件库
│   ├── __init__.py
│   ├── chat_display.py             # 对话消息展示组件
│   ├── diet_card.py                # 膳食方案卡片（核心）
│   ├── user_form.py                # 档案表单组件
│   └── nutrition_chart.py          # 营养图表组件（可选）
│
├── services/                       # 前端服务层
│   ├── __init__.py
│   └── api_client.py               # 后端 API 统一封装
│
└── utils/                          # 工具函数
    ├── __init__.py
    └── helpers.py                  # 格式化/时间处理等
```

---

## 三、核心功能实现

### 3.1 API 客户端封装（[services/api_client.py](file:///e:/Programs/Python%20Programs/DietAgent_LC/frontend/services/api_client.py)）

**职责**：统一封装所有后端 API 调用

**核心功能**：
- ✅ 用户认证（登录/注册/登出）
- ✅ 用户档案管理
- ✅ Agent 对话（同步/流式）
- ✅ 知识库管理（上传/检索/统计）
- ✅ 对话历史管理
- ✅ SSE 流式响应解析

**关键代码**：
```python
class APIClient:
    def chat_stream(self, message: str) -> Generator[Dict, None, None]:
        """流式对话（SSE）"""
        for line in response.iter_lines(decode_unicode=True):
            if line.startswith("data: "):
                event = json.loads(line[6:])
                yield event
```

### 3.2 膳食方案卡片（[components/diet_card.py](file:///e:/Programs/Python%20Programs/DietAgent_LC/frontend/components/diet_card.py)）

**职责**：渲染完整的膳食方案展示

**布局结构**：
1. **营养总览**：总热量、蛋白质、碳水、脂肪（4个指标卡片）
2. **分餐详情**：早餐/午餐/晚餐/加餐（可折叠面板）
3. **健康建议**：营养师建议列表

**关键函数**：
- `render_diet_plan_card()`：完整方案渲染
- `render_diet_plan_compact()`：紧凑版（历史列表用）

### 3.3 对话主页面（[pages/1_💬_膳食对话.py](file:///e:/Programs/Python%20Programs/DietAgent_LC/frontend/pages/1_💬_膳食对话.py)）

**职责**：AI 膳食对话界面

**核心流程**：
1. 用户输入 → 添加到 `st.session_state.messages`
2. 调用 `api.chat_stream()` → 实时展示进度事件
3. 接收最终数据 → 渲染膳食方案卡片
4. 保存到历史 → 持久化对话记录

**状态管理**：
```python
st.session_state.messages = []           # 对话消息列表
st.session_state.processing = False      # 处理状态锁
st.session_state.current_plan = None     # 当前膳食方案
st.session_state.session_id = None       # 会话ID
```

### 3.4 用户档案表单（[components/user_form.py](file:///e:/Programs/Python%20Programs/DietAgent_LC/frontend/components/user_form.py)）

**职责**：健康档案录入界面

**表单字段**：
- **基础信息**：年龄、性别、身高、体重
- **健康信息**：慢性疾病、食物忌口、所在地域、膳食目标

**数据校验**：
- 年龄：1-120岁
- 身高：50-250cm
- 体重：20-300kg
- BMI 自动计算

---

## 四、技术亮点

### 4.1 SSE 流式响应解析

**挑战**：Streamlit 的 `st.rerun()` 机制与流式输出冲突

**解决方案**：
```python
# 在流式回调中使用 placeholder 动态更新
with st.chat_message("assistant"):
    progress_placeholder = st.empty()
    plan_placeholder = st.empty()
    text_placeholder = st.empty()

    for event in api.chat_stream(message):
        # 更新进度
        progress_placeholder.write(event["message"])
        # 渲染方案
        if event.get("diet_plan"):
            plan_placeholder.render_diet_plan_card(event["diet_plan"])
```

### 4.2 会话状态管理

**挑战**：Streamlit 每次交互都重新运行整个脚本

**解决方案**：
- 使用 `st.session_state` 持久化关键状态
- API 客户端单例模式（避免重复创建）
- 分离 UI 组件和业务逻辑

### 4.3 组件化设计

**优势**：
- `diet_card.py` 可在对话页、历史页复用
- `user_form.py` 支持编辑/查看两种模式
- `nutrition_chart.py` 可选依赖（未安装时降级）

---

## 五、启动方式

### 5.1 安装依赖

```bash
cd frontend
pip install -r requirements.txt
```

### 5.2 启动后端

```bash
cd backend/app
python -m uvicorn main:app --reload --port 8000
```

### 5.3 启动前端

```bash
cd frontend
streamlit run app.py
```

**默认访问地址**：http://localhost:8501

---

## 六、测试验证

### 6.1 功能测试清单

| 测试项 | 测试场景 | 预期结果 |
|--------|---------|---------|
| 登录流程 | 正确/错误密码 | 登录成功/错误提示 |
| 流式对话 | 发送"减脂餐" | 实时显示进度+方案卡片 |
| 档案编辑 | 更新年龄/体重 | 保存成功并更新显示 |
| 知识库上传 | 上传 .txt 文件 | 分块成功+列表显示 |
| 历史查看 | 查看对话/方案历史 | 正确分组展示 |
| 多轮对话 | 追问"换面食" | 保持上下文生成新方案 |

### 6.2 边界测试

- ✅ 未登录访问对话页 → 自动跳转登录
- ✅ API 请求失败 → 显示错误提示
- ✅ 膳食方案数据缺失 → 显示默认值
- ✅ 文件上传失败 → 显示错误信息

---

## 七、后续优化建议

### 7.1 性能优化

- [ ] 使用 `st.cache_data` 缓存 API 响应
- [ ] 对话历史分页加载（避免一次加载过多）
- [ ] 图片懒加载（知识库文档预览）

### 7.2 功能增强

- [ ] 膳食方案导出 PDF
- [ ] 对话历史搜索
- [ ] 营养趋势图表（多日对比）
- [ ] 移动端适配（响应式布局）

### 7.3 用户体验

- [ ] 添加加载骨架屏
- [ ] 优化错误提示（更友好的文案）
- [ ] 增加快捷键支持（Enter 发送）
- [ ] 暗黑模式支持

---

## 八、与后端接口对接

### 8.1 已对接接口

| 前端功能 | 后端接口 | 方法 |
|---------|---------|------|
| 登录 | `/api/user/login` | POST |
| 注册 | `/api/user/register` | POST |
| 获取档案 | `/api/agent/user/{user_id}/profile` | GET |
| 更新档案 | `/api/agent/user/{user_id}/profile` | PUT |
| 流式对话 | `/api/agent/chat/stream` | POST |
| 对话历史 | `/api/agent/user/{user_id}/history` | GET |
| 知识库上传 | `/api/knowledge/upload` | POST |
| 知识库检索 | `/api/knowledge/search` | POST |

### 8.2 数据格式示例

**流式对话响应**：
```json
{
  "stage": "output",
  "status": "complete",
  "data": {
    "session_id": "abc123",
    "message": "为您定制减脂餐方案...",
    "diet_plan": {
      "total_calories": 1450,
      "nutrition_balance": {"protein": "85g", ...},
      "breakfast": {"total_calories": 400, "items": [...]},
      ...
    }
  }
}
```

---

## 九、简历亮点总结

1. **Streamlit 零代码前端**：5 天从后端到前端一站式落地，展示快速原型开发能力
2. **SSE 流式响应**：前端实时展示 Agent 6 步处理进度，区别于普通聊天窗口
3. **膳食方案可视化**：营养总览卡片 + 分餐详情 + 雷达图，数据展示清晰直观
4. **多页面应用**：对话/档案/知识库/历史 4 个页面，功能完整
5. **前后端解耦**：API 客户端封装 + 组件化 UI，结构清晰
6. **会话状态管理**：Streamlit session_state + 后端 Redis 会话，多轮对话上下文保持

---

**完成标志**：前端核心功能已全部实现，可直接启动 Streamlit 展示完整 Demo。