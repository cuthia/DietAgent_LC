# 🥗 每日膳食搭配助手 (DietAgent)

> **AI 驱动的个性化营养顾问** - 基于 LangChain + RAG + Streamlit 构建的智能膳食搭配系统

---

## 📖 项目简介

DietAgent 是一款基于大语言模型的智能膳食搭配助手，能够根据用户的健康档案（年龄、体重、慢病、忌口等），结合专业营养学知识库，生成个性化的膳食方案。

### ✨ 核心特性

- 🤖 **AI 智能分析**：基于 LangChain LCEL 链式调用，多步骤处理用户饮食需求
- 📚 **RAG 知识增强**：结合专业营养学知识库，解决 LLM 营养幻觉问题
- 🎯 **多维度约束**：综合考虑慢病禁忌、食物忌口、地域饮食、膳食目标
- 💬 **多轮对话**：支持追问、调整，保持上下文语义
- 📊 **营养可视化**：清晰展示热量、蛋白质、碳水等营养成分配比
- ⚡ **流式响应**：SSE 流式输出，实时展示 AI 处理进度

### 🎯 适用场景

- 减脂塑形、增肌增重
- 慢病饮食管理（糖尿病、高血压、痛风等）
- 地域化膳食搭配（南方/北方/川渝/沿海等）
- 特殊人群营养方案（孕期、老年、儿童等）

---

## 🏗️ 技术架构

### 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 前端 | Streamlit | >= 1.30 |
| 后端 | FastAPI | >= 0.100 |
| Agent | LangChain | >= 0.2 |
| 向量库 | Chroma | >= 0.4 |
| 嵌入模型 | BAAI/bge-small-zh-v1.5 | - |
| 数据库 | SQLite | - |
| 缓存 | Redis (可选) | >= 6.0 |
| LLM | DeepSeek / 通义千问 / GPT-4o | - |

### 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                  Streamlit 前端展示层                        │
│  (对话界面 / 健康档案 / 知识库管理 / 历史记录)                │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP/SSE
┌───────────────────────────▼─────────────────────────────────┐
│                  FastAPI API 网关层                          │
│  (路由分发 / JWT鉴权 / 参数校验 / 异常处理)                   │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                  Agent 核心层 (LangChain LCEL)              │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  6步处理流水线                                        │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌────────┐ │   │
│  │  │信息收集  │→│知识检索  │→│约束构建  │→│食谱生成 │ │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └────────┘ │   │
│  │         ↑                                    │         │   │
│  │         │         ┌─────────┐                │         │   │
│  │         └─────────│校验修正  │←──────────────┘         │   │
│  │                   └─────────┘                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │
│  │ LLM客户端    │  │ 工具集      │  │ 对话记忆(Redis)  │   │
│  └─────────────┘  └─────────────┘  └─────────────────┘   │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                  RAG 知识库层                                │
│  (BGE嵌入 / Chroma向量库 / 文档检索)                         │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                  数据持久层                                  │
│  (SQLite用户数据 / Redis会话缓存 / 本地知识库文档)           │
└─────────────────────────────────────────────────────────────┘
```

### Agent 处理流程

```
用户输入 → 信息收集 → 知识检索 → 约束构建 → 食谱生成 → 校验修正 → 结果输出
            │          │          │          │          │          │
            ▼          ▼          ▼          ▼          ▼          ▼
        查询用户档案  检索相关知识  构建慢病/忌口  LCEL链式调用  检查合规性  流式返回结果
                               地域约束      Prompt+LLM+Parser   生成修正方案
```

---

## 📁 项目结构

```
DietAgent_LC/
├── backend/                              # 后端服务
│   └── app/
│       ├── main.py                       # FastAPI 入口
│       ├── core/                         # 核心基础组件
│       │   ├── config/                   # YAML配置文件
│       │   │   ├── config.yaml           # 基础配置
│       │   │   ├── config.dev.yaml       # 开发环境配置
│       │   │   └── config.prod.yaml      # 生产环境配置
│       │   ├── config_handler.py         # 配置加载器
│       │   ├── security.py               # JWT鉴权
│       │   ├── logger.py                 # 日志配置
│       │   └── exception.py             # 异常处理
│       ├── api/                          # API路由层
│       │   ├── dependencies.py           # 依赖注入
│       │   └── routers/
│       │       ├── user.py               # 用户接口
│       │       ├── agent.py              # Agent对话接口
│       │       └── knowledge.py         # 知识库管理接口
│       ├── agent/                        # Agent核心层
│       │   ├── chain.py                  # LCEL链式调用编排
│       │   ├── llm_client.py             # LLM统一封装
│       │   ├── memory.py                 # 对话记忆管理
│       │   ├── tools/                    # Agent工具集
│       │   │   ├── user_tool.py          # 用户信息查询
│       │   │   ├── rag_tool.py           # RAG检索工具
│       │   │   ├── validate_tool.py      # 忌口/慢病校验
│       │   │   └── region_tool.py        # 地域适配工具
│       │   └── prompts/                  # Prompt模板
│       │       ├── system_prompt.py      # 系统提示词
│       │       └── diet_prompt.py        # 膳食生成提示词
│       ├── rag/                          # RAG知识库层
│       │   ├── embeddings.py             # BGE向量嵌入
│       │   ├── vector_store.py           # Chroma向量库
│       │   ├── retriever.py              # 检索器
│       │   ├── document_loader.py        # 文档加载
│       │   └── text_splitter.py          # 文本分块
│       ├── db/                           # 数据持久层
│       │   ├── models/user.py            # 用户模型
│       │   └── crud/user_crud.py         # 用户CRUD
│       ├── schemas/                      # Pydantic数据模型
│       ├── services/                     # 业务逻辑层
│       │   ├── agent_service.py          # Agent业务编排
│       │   └── knowledge_service.py      # 知识库服务
│       └── working_docs/                 # 开发文档
│
├── frontend/                             # 前端服务
│   ├── app.py                            # Streamlit应用入口
│   ├── config.py                         # 前端配置
│   ├── requirements.txt                  # 前端依赖
│   ├── pages/                            # 多页面
│   │   ├── 1_💬_膳食对话.py              # AI对话页面
│   │   ├── 2_👤_健康档案.py              # 用户档案页面
│   │   ├── 3_📚_知识库.py                # 知识库管理页面
│   │   └── 4_📊_历史记录.py              # 历史膳食记录
│   ├── components/                       # UI组件库
│   │   ├── chat_display.py               # 对话展示组件
│   │   ├── diet_card.py                  # 膳食方案卡片
│   │   ├── user_form.py                  # 用户档案表单
│   │   └── nutrition_chart.py            # 营养图表组件
│   ├── services/                         # 前端服务层
│   │   └── api_client.py                 # 后端API客户端
│   └── utils/                            # 工具函数
│       └── helpers.py                    # 格式化辅助
│
├── data/                                 # 数据目录
│   ├── chroma/                           # Chroma向量库存储
│   └── models/                           # 本地模型
│       └── bge-small-zh-v1.5/            # BGE嵌入模型
│
├── docs/                                 # 项目文档
│   ├── 项目架构方案2.0.md
│   └── API文档.md
│
├── requirements.txt                      # 后端依赖
└── README.md                             # 项目说明
```

---

## 🚀 快速开始

### 环境要求

- Python 3.11+
- pip 包管理器
- （可选）Redis 6.0+（用于会话缓存，未安装则自动降级为内存存储）

### 1. 克隆项目

```bash
git clone <repository-url>
cd DietAgent_LC
```

### 2. 安装依赖

```bash
# 安装后端依赖
pip install -r requirements.txt

# 安装前端依赖
cd frontend
pip install -r requirements.txt
cd ..
```

### 3. 配置环境

#### 3.1 配置 LLM API Key

编辑 `backend/app/core/config/config.yaml`：

```yaml
llm:
  type: deepseek                    # 支持: deepseek / qwen / openai
  api_key: "your-api-key"           # 或使用环境变量: ${LLM_API_KEY}
  base_url: "https://api.deepseek.com"
  model: "deepseek-chat"
  temperature: 0.7
  max_tokens: 4096
```

**支持的 LLM 提供商**：

| 类型 | 说明 | base_url |
|------|------|----------|
| `deepseek` | 深度求索（推荐） | https://api.deepseek.com |
| `qwen` | 通义千问 | https://dashscope.aliyuncs.com |
| `openai` | GPT-4o | https://api.openai.com |

**使用环境变量**（推荐）：

```bash
# Windows PowerShell
$env:LLM_API_KEY = "your-api-key"

# Linux/Mac
export LLM_API_KEY="your-api-key"
```

#### 3.2 配置 Redis（可选）

如果需要 Redis 会话缓存，编辑 `config.yaml`：

```yaml
redis:
  host: localhost
  port: 6379
  db: 0
  password: ""
```

**安装 Redis**（Windows）：

```bash
# 方式1: Docker
docker run -d --name redis -p 6379:6379 redis:7

# 方式2: 下载 Windows 版 Redis
# 访问 https://github.com/tporadowski/redis/releases
```

**注意**：如果不安装 Redis，系统会自动降级为内存存储，功能不受影响（重启后会话丢失）。

#### 3.3 配置 JWT Secret

```yaml
jwt:
  secret_key: "your-secret-key"     # 建议使用随机字符串
  algorithm: "HS256"
  expire_minutes: 1440              # Token有效期（24小时）
```

**生成 Secret Key**：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

#### 3.4 配置向量嵌入模型

默认使用本地 BGE 模型，路径：`data/models/bge-small-zh-v1.5/`

如果需要下载：

```bash
# 使用 huggingface-cli 下载
huggingface-cli download BAAI/bge-small-zh-v1.5 --local-dir data/models/bge-small-zh-v1.5

# 或使用 modelscope
python -c "from modelscope import snapshot_download; snapshot_download('BAAI/bge-small-zh-v1.5', cache_dir='data/models')"
```

#### 3.5 配置数据库（SQLite 开箱即用）

默认使用 SQLite，无需额外配置。数据库文件位于 `backend/app/data/` 目录。

生产环境可切换为 PostgreSQL，编辑 `config.yaml`：

```yaml
database:
  type: postgresql
  postgresql:
    host: localhost
    port: 5432
    database: diet_agent
    user: postgres
    password: your-password
```

### 4. 启动服务

#### 方式一：命令行启动（推荐开发使用）

**启动后端服务**：

```bash
cd backend/app
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**启动前端服务**（另开终端）：

```bash
cd frontend
streamlit run app.py --server.port 8501
```

**访问地址**：

| 服务 | 地址 | 说明 |
|------|------|------|
| API 文档 | http://localhost:8000/docs | Swagger UI，可测试所有接口 |
| Streamlit 前端 | http://localhost:8501 | AI 对话界面 |
| 健康检查 | http://localhost:8000/agent/health | 服务状态检查 |

#### 方式二：Docker 启动（预留）

> ⚠️ Docker 配置即将提供，敬请期待

```bash
# 构建镜像
docker build -t dietagent-backend ./backend
docker build -t dietagent-frontend ./frontend

# 启动容器
docker compose up -d
```

---

## 📚 API 接口文档

### 通用响应格式

```json
{
  "success": true,
  "message": "操作成功",
  "data": {}
}
```

### 用户认证

#### 用户注册

```
POST /api/user/register
```

```json
// 请求
{
  "username": "string",
  "password": "string"
}

// 响应
{
  "success": true,
  "data": {
    "user_id": 1,
    "token": "jwt-token"
  }
}
```

#### 用户登录

```
POST /api/user/login
```

```json
// 请求
{
  "username": "string",
  "password": "string"
}

// 响应
{
  "success": true,
  "data": {
    "user_id": 1,
    "token": "jwt-token"
  }
}
```

### Agent 对话

#### 同步对话

```
POST /api/agent/chat
```

```json
// 请求
{
  "user_id": 1,
  "message": "给我设计一份减脂餐",
  "session_id": "optional-session-id"
}

// 响应
{
  "success": true,
  "data": {
    "message": "为您定制减脂餐方案...",
    "diet_plan": { ... },
    "session_id": "session-id",
    "needs_info": false
  }
}
```

#### 流式对话（SSE）

```
POST /api/agent/chat/stream
```

**SSE 事件格式**：

```
data: {"stage": "collect_info", "status": "start", "message": "正在收集用户信息..."}
data: {"stage": "collect_info", "status": "complete", "message": "用户信息收集完成"}
data: {"stage": "retrieve_knowledge", "status": "start", "message": "正在检索知识库..."}
data: {"stage": "generate_diet", "status": "start", "message": "正在生成膳食方案..."}
data: {"stage": "output", "status": "complete", "message": "处理完成", "data": {...}}
data: {"done": true}
```

#### 获取用户档案

```
GET /api/agent/user/{user_id}/profile
```

#### 更新用户档案

```
PUT /api/agent/user/{user_id}/profile
```

```json
// 请求
{
  "age": 25,
  "gender": "male",
  "height": 170,
  "weight": 65,
  "chronic_disease": "糖尿病",
  "food_taboo": "海鲜,花生",
  "region": "北方",
  "diet_goal": "减脂塑形"
}
```

#### 获取对话历史

```
GET /api/agent/user/{user_id}/history?max_messages=20
```

#### 获取膳食方案历史

```
GET /api/agent/user/{user_id}/diet-history?limit=10
```

#### 清空对话历史

```
DELETE /api/agent/user/{user_id}/history?session_id=default
```

### 知识库管理

#### 上传文档

```
POST /api/knowledge/upload
Content-Type: multipart/form-data
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | 支持 TXT/MD/PDF/DOCX 格式 |
| category | String | 否 | 文档分类 |

#### 检索文档

```
POST /api/knowledge/search
```

```json
// 请求
{
  "query": "糖尿病饮食",
  "top_k": 5
}
```

#### 删除文档

```
DELETE /api/knowledge/{doc_id}
```

#### 获取统计信息

```
GET /api/knowledge/stats
```

---

## 🔧 配置详解

### 完整配置文件示例

`backend/app/core/config/config.yaml`：

```yaml
# ======================== 服务配置 ========================
server:
  host: "0.0.0.0"
  port: 8000
  env: dev  # dev / prod

# ======================== LLM配置 ========================
llm:
  type: deepseek                    # deepseek / qwen / openai
  api_key: ${LLM_API_KEY}            # 支持环境变量
  base_url: "https://api.deepseek.com"
  model: "deepseek-chat"
  temperature: 0.7                   # 生成温度，0-1，越高越随机
  max_tokens: 4096                  # 最大生成token数

# ======================== Redis配置 ========================
redis:
  host: localhost
  port: 6379
  db: 0
  password: ""

# ======================== 向量库配置 ========================
vector_store:
  type: chroma                      # chroma / milvus
  chroma:
    persist_dir: "./data/chroma"
  milvus:                           # 生产环境预留
    host: localhost
    port: 19530
    collection_name: diet_knowledge

# ======================== 嵌入模型配置 ========================
embedding:
  model: "BAAI/bge-small-zh-v1.5"
  device: "cpu"                     # cpu / cuda
  local_path: "./data/models/bge-small-zh-v1.5"
  hf_endpoint: "https://hf-mirror.com"
  offline: false

# ======================== 数据库配置 ========================
database:
  type: sqlite                      # sqlite / postgresql
  sqlite:
    path: "./data/diet_agent.db"
  postgresql:                       # 生产环境预留
    host: localhost
    port: 5432
    database: diet_agent
    user: postgres
    password: ""

# ======================== JWT配置 ========================
jwt:
  secret_key: ${JWT_SECRET_KEY}
  algorithm: "HS256"
  expire_minutes: 1440

# ======================== 日志配置 ========================
logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

### 环境变量占位符

配置文件支持 `${ENV_VAR:default_value}` 格式：

```yaml
llm:
  api_key: ${LLM_API_KEY}           # 必须设置
jwt:
  secret_key: ${JWT_SECRET_KEY}     # 必须设置
redis:
  password: ${REDIS_PASSWORD:}     # 可选，默认空
```

### 开发/生产环境切换

```yaml
# config.yaml (基础配置)
llm:
  type: deepseek
  temperature: 0.7

# config.dev.yaml (开发环境覆盖)
server:
  port: 8000
llm:
  temperature: 0.8                   # 开发环境更有创造性

# config.prod.yaml (生产环境覆盖)
server:
  port: 8001
llm:
  temperature: 0.3                   # 生产环境更稳定
```

设置环境变量切换：

```bash
# 开发环境（默认）
$env:ENV = "dev"

# 生产环境
$env:ENV = "prod"
```

---

## 📦 依赖清单

### 后端依赖 (requirements.txt)

```
fastapi>=0.100
uvicorn[standard]>=0.20
sqlalchemy>=2.0
pydantic>=2.0
python-jose[cryptography]>=3.3
passlib[bcrypt]>=1.7
langchain>=0.2
langchain-community>=0.0.10
chromadb>=0.4
sentence-transformers>=2.2
PyYAML>=6.0
redis>=5.0
python-multipart>=0.0.5
python-docx>=1.0
PyPDF2>=3.0
```

### 前端依赖 (frontend/requirements.txt)

```
streamlit>=1.30
plotly>=5.18
pandas>=2.0
requests>=2.31
```

---

## 🛠️ 常见问题

### 1. 启动时提示 "LLM 未初始化"

**原因**：LLM API Key 未配置或无效

**解决**：
```bash
# 设置环境变量
$env:LLM_API_KEY = "your-api-key"

# 或编辑 config.yaml
llm:
  api_key: "your-api-key"
```

### 2. 启动时提示 "Redis 连接失败"

**原因**：Redis 未启动

**解决**：
```bash
# 方式1: 启动 Redis
redis-server

# 方式2: 使用 Docker
docker start redis

# 方式3: 忽略（自动降级为内存存储）
# 系统会自动降级，功能不受影响
```

### 3. 向量库报错 "模型文件不存在"

**原因**：BGE 嵌入模型未下载

**解决**：
```bash
# 下载模型
huggingface-cli download BAAI/bge-small-zh-v1.5 --local-dir data/models/bge-small-zh-v1.5
```

### 4. 前端访问接口报 404

**原因**：后端服务未启动或端口不对

**解决**：
```bash
# 确认后端已启动
curl http://localhost:8000/agent/health

# 检查前端配置
# frontend/config.py
BACKEND_URL = "http://localhost:8000"
```

### 5. SSE 流式输出无响应

**原因**：网络超时或 LLM API 响应慢

**解决**：
- 检查网络连接
- 降低 `max_tokens` 配置
- 增加超时时间

### 6. 如何更换 LLM 提供商

**解决**：编辑 `config.yaml`

```yaml
# 切换到通义千问
llm:
  type: qwen
  api_key: "your-qwen-api-key"
  model: "qwen-plus"

# 切换到 GPT-4o
llm:
  type: openai
  api_key: "your-openai-api-key"
  model: "gpt-4o"
```

### 7. 如何导入自定义知识库

**解决**：
1. 访问前端知识库页面：http://localhost:8501
2. 上传 TXT/MD/PDF/DOCX 文件
3. 选择文档分类
4. 点击"上传并向量化"

### 8. 数据存在哪里

| 数据类型 | 存储位置 | 说明 |
|---------|---------|------|
| 用户数据 | `backend/app/data/diet_agent.db` | SQLite 数据库 |
| 向量库 | `backend/app/data/chroma/` | Chroma 向量库 |
| 对话缓存 | Redis 或内存 | 会话历史 |
| 上传文档 | 前端上传，向量化后存入 Chroma | 原始文档不保留 |

---

## 📝 开发指南

### 项目路线图

| 阶段 | 内容 | 状态 |
|------|------|------|
| 第一阶段 | 项目骨架、用户认证、数据库 | ✅ 已完成 |
| 第二阶段 | RAG知识库、向量嵌入、检索器 | ✅ 已完成 |
| 第三阶段 | LangChain Agent核心开发 | ✅ 已完成 |
| 第四阶段 | Streamlit前端开发 | ✅ 已完成 |
| 第五阶段 | 联调测试、文档完善 | 🚧 进行中 |
| 第六阶段 | 优化与简历包装 | ⏳ 待开发 |

### 文档索引

- [项目架构方案 2.0](docs/项目架构方案2.0.md)
- [API 接口文档](docs/API文档.md)
- [第三阶段任务规划](backend/app/working_docs/第三阶段任务规划.md)
- [第三阶段实现说明](backend/app/working_docs/第三阶段任务实现说明.md)
- [第四阶段任务规划](backend/app/working_docs/第四阶段任务规划.md)
- [第四阶段实现说明](backend/app/working_docs/第四阶段任务实现说明.md)

---

## 🎯 面试亮点

1. **LangChain LCEL 链式调用**：展示多步骤 Agent 编排能力，区别于简单的单轮问答
2. **RAG + Agent 融合**：结合知识库检索与 Agent 自主决策，解决 LLM 营养幻觉问题
3. **SSE 流式响应**：前端实时展示 Agent 处理进度，区别于普通聊天窗口
4. **Streamlit 快速原型**：展示全栈快速落地能力，5 天从后端到前端一站式实现
5. **Redis 会话记忆**：实现多轮对话上下文管理，支持用户长期偏好存储
6. **工程化设计**：配置分离、接口抽象、环境隔离，符合工业级开发标准

### 技术关键词

```
LangChain | LCEL | RAG | BGE嵌入 | Chroma向量库 | Redis会话记忆 
| FastAPI | Streamlit | SSE流式 | Pydantic | SQLAlchemy | JWT鉴权
```

---

## 📄 License

本项目仅供学习和面试使用。

---

## 🤝 贡献

欢迎提交 Issue 和 PR！

---

**Made with ❤️ by DietAgent Team**