# 🥗 DietAgent · 每日膳食搭配助手

> **AI 驱动的个性化营养顾问** —— 基于 LangChain LCEL + RAG + FastAPI 构建的大模型个性化膳食搭配系统，综合用户慢病、忌口、地域、目标等约束生成单日 / 一周膳食方案。

---

## 📖 项目简介

DietAgent 是一款基于大语言模型的智能膳食搭配助手。它能够根据用户的健康档案（年龄、身高体重、慢病、食物忌口、地域、膳食目标等），结合本地专业营养学知识库（RAG），通过 6 步 Agent 流水线生成结构化、可校验、多日可扩展的膳食方案，并以 SSE 流式 + 打字机效果实时回传前端。

### ✨ 核心特性

- 🤖 **LangChain LCEL 链式编排**：信息收集 → 知识检索 → 约束构建 → 食谱生成 → 合规校验 → 结果输出，6 步流水线
- 📚 **RAG 知识增强**：BGE 中文嵌入 + Chroma 向量库，支持 PDF/TXT/MD/DOCX 入库与 Top-K 语义检索，缓解 LLM 营养幻觉
- 🎯 **多维度约束**：慢病禁忌、食物忌口/过敏、地域饮食偏好、膳食目标，结构化注入 Prompt
- 📅 **多日方案**：支持单日 / 三天 / 五天 / 一周（7 天）食谱，JSON `days[]` 结构，含日均与周合计热量
- 🛡️ **生成-校验-修正闭环**：方案生成后自动校验忌口/慢病食材，不合规自动二次修正；并对超长 JSON 做"宽松解析 + 结构兜底"，杜绝 `NoneType` 崩溃
- 💬 **多轮对话记忆**：基于 Redis（或内存降级）的会话上下文，支持追问与方案调整
- ⚡ **SSE 流式响应**：6 阶段进度事件 + 最终答复逐字打字机输出，实时反馈
- 🖥️ **豆包风格前端**：纯 HTML + Tailwind v3 + 原生 JS，零构建依赖，Node 静态服务器即可启动

### 🎯 适用场景

- 减脂塑形、增肌增重
- 慢病饮食管理（糖尿病、高血压、痛风、高血脂、胃炎等）
- 地域化膳食搭配（南方 / 北方 / 川渝 / 沿海等）
- 一周备餐方案生成

---

## 🏗️ 技术架构

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | HTML + Tailwind CSS v3 + 原生 ES Modules | 豆包风格对话 UI，marked.js 渲染 Markdown，highlight.js 代码高亮 |
| 前端服务 | Node.js 内置 http 模块 | 零依赖静态服务器（`server.js`，端口 8501） |
| 后端框架 | FastAPI + Uvicorn | 异步 API，工厂模式应用，lifespan 启动初始化 |
| Agent 编排 | LangChain LCEL | `Prompt \| LLM \| Parser` 链式调用，6 步流水线 |
| LLM | DeepSeek-Chat（默认） | 兼容通义千问 / OpenAI，统一 `ChatOpenAI` 封装，YAML 切换 |
| RAG 嵌入 | BAAI/bge-small-zh-v1.5 | 本地 SentenceTransformer，512 维，单例缓存 |
| 向量库 | Chroma | 本地持久化（`./data/chroma`） |
| 数据库 | MySQL（aiomysql 异步） | SQLAlchemy 2.0 async，表自动创建 |
| 会话记忆 | Redis（可选）/ 内存降级 | `MemoryManager` 自动选择存储后端 |
| 鉴权 | JWT + bcrypt | `python-jose` + `passlib` |
| 日志 | loguru + InterceptHandler | 桥接标准库 `logging`，统一彩色控制台输出 |

### 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│        前端展示层 (HTML + Tailwind + 原生 JS)                │
│  对话界面 / 健康档案 / 知识库管理 / 历史方案 / Markdown渲染    │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP / SSE (fetch + ReadableStream)
┌───────────────────────────▼─────────────────────────────────┐
│              FastAPI API 网关层 (/api/*)                     │
│  user / chat / knowledge / agent 路由 · JWT依赖注入 · CORS   │
│  全局异常处理 · /health 探活 · SSE StreamingResponse         │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│           Agent 核心层 (LangChain LCEL · DietAgentChain)     │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │
│  │信息收集 │→│知识检索 │→│约束构建 │→│食谱生成 │→│方案校验 │    │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────┬───┘    │
│       ↑   多轮记忆(user_id+session_id)      ↓ 修正 │        │
│       └────────────── 结果输出(环节6) ←──────────┘        │
│  LLMClient · JsonOutputParser+宽松解析 · _sanitize_diet_plan│
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│              RAG 知识库层 (KnowledgeService · Facade)        │
│  DocumentLoader → TextSplitter → EmbeddingModel → Chroma     │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                   数据持久层                                 │
│  MySQL(user/user_profile) · Redis(会话/方案) · Chroma(向量)  │
└─────────────────────────────────────────────────────────────┘
```

### Agent 6 步处理流程

```
用户输入
  │
  ▼
①信息收集  —— 查询用户档案，判断信息是否完整；不完整则生成追问
  │
  ▼
②知识检索  —— 结合慢病拼检索 query，从 Chroma 召回 Top-K 营养学片段
  │
  ▼
③约束构建  —— 汇总慢病禁忌、食物忌口、地域特点、膳食目标成结构化约束
  │
  ▼
④食谱生成  —— LCEL 链(Prompt|LLM)生成 JSON 方案；宽松解析+结构兜底；支持单日/多日
  │
  ▼
⑤方案校验  —— validate_tool 检查忌口/慢病食材；不合规则 LLM revise 二次修正
  │
  ▼
⑥结果输出  —— format_diet_plan_summary 渲染分天卡片；SSE 流式打字机回传
```

---

## 📁 项目结构

```
DietAgent_LC/
├── backend/
│   ├── app/
│   │   ├── main.py                       # FastAPI 入口(工厂+lifespan+/health/CORS/异常)
│   │   ├── core/                         # 核心基础
│   │   │   ├── config/config.yaml        # 主配置(embedding/vector_store/llm/redis)
│   │   │   ├── config_handler.py         # Pydantic 配置模型
│   │   │   ├── config_api.py             # 全局 settings 实例
│   │   │   ├── logger.py                 # loguru + InterceptHandler 日志桥接
│   │   │   ├── security.py               # JWT 创建/校验 + bcrypt 密码
│   │   │   └── exception.py              # 业务异常 + 全局异常处理器
│   │   ├── api/
│   │   │   ├── dependencies.py           # get_current_user 依赖注入
│   │   │   └── routers/
│   │   │       ├── __init__.py           # api_router 聚合(prefix=/api)
│   │   │       ├── user.py               # 注册/登录/档案
│   │   │       ├── chat.py               # 对话(第一阶段 mock)
│   │   │       ├── knowledge.py          # 知识库上传/检索/删除/统计
│   │   │       └── agent.py              # Agent 对话(同步+SSE流式)/档案/历史/校验
│   │   ├── agent/                        # Agent 核心
│   │   │   ├── chain.py                  # DietAgentChain 6步流水线 + process_stream
│   │   │   ├── llm_client.py             # LLMClient 统一封装(DeepSeek/Qwen/OpenAI)
│   │   │   ├── memory.py                 # MemoryManager(Redis/InMemory)
│   │   │   ├── prompts/                  # system/diet/validate 提示词模板
│   │   │   └── tools/                    # user_tool/rag_tool/validate_tool/region_tool
│   │   ├── rag/                          # RAG 知识库
│   │   │   ├── embeddings.py             # EmbeddingModel 单例(BGE)
│   │   │   ├── vector_store.py           # Chroma 向量库封装
│   │   │   ├── retriever.py              # 检索器
│   │   │   ├── document_loader.py        # txt/md/pdf/docx 加载
│   │   │   └── text_splitter.py          # 递归文本切分
│   │   ├── services/
│   │   │   ├── agent_service.py          # AgentService 业务编排
│   │   │   └── knowledge_service.py      # KnowledgeService Facade(入库全流程)
│   │   ├── db/
│   │   │   ├── session.py                # MySQL 异步引擎+会话工厂+init_db
│   │   │   ├── base.py                   # SQLAlchemy Base
│   │   │   ├── models/user.py            # User / UserProfile 表
│   │   │   └── crud/user_crud.py         # 用户 CRUD
│   │   ├── schemas/                      # Pydantic 请求/响应模型
│   │   ├── utils/ · tasks/
│   │   └── working_docs/                 # 各阶段任务规划与实现说明
│   └── data/
│       ├── chroma/                       # Chroma 向量库持久化
│       └── models/bge-small-zh-v1.5/     # 本地 BGE 嵌入模型
│
├── frontend/                             # 纯静态前端(无构建)
│   ├── index.html                        # 豆包风格 UI + Tailwind CDN + 内联样式
│   ├── app.js                            # 对话/SSE/档案/知识库交互逻辑
│   ├── server.js                         # 零依赖 Node 静态服务器(端口8501)
│   └── package.json
│
├── docs/                                 # 架构方案 / API 文档
├── requirements.txt                      # Python 依赖(conda 环境导出)
└── README.md
```

---

## 🚀 快速开始

### 环境要求

- Python 3.11+
- Node.js 16+（仅用于前端静态服务器，亦可改用 `python -m http.server`）
- MySQL 5.7+ / 8.0（必须，存储用户与档案）
- Redis 6.0+（可选，未安装自动降级为内存存储）

### 1. 安装依赖

```bash
# 后端依赖（根目录 requirements.txt 为 conda 环境导出，核心依赖如下）
pip install fastapi uvicorn[standard] langchain langchain-core langchain-openai \
            langchain-chroma langchain-classic chromadb sentence-transformers \
            sqlalchemy[asyncio] aiomysql pydantic pydantic-settings \
            redis python-jose[cryptography] passlib[bcrypt] python-multipart \
            pypdf docx2txt jieba rank-bm25 loguru pyyaml
```

### 2. 配置

#### 2.1 LLM 配置（`backend/app/core/config/config.yaml`）

```yaml
llm:
  type: deepseek              # deepseek / qwen / openai
  api_key: "your-api-key"     # DeepSeek API Key
  base_url: "https://api.deepseek.com"
  model: "deepseek-chat"
  temperature: 0.7
  max_tokens: 8192            # 7天食谱JSON较长，4096易截断
  timeout: 180                # 生成长JSON需60~120s
```

| 类型 | base_url | model 示例 |
|------|----------|-----------|
| `deepseek` | https://api.deepseek.com | deepseek-chat |
| `qwen` | https://dashscope.aliyuncs.com/compatible-mode/v1 | qwen-plus |
| `openai` | https://api.openai.com | gpt-4o |

#### 2.2 嵌入模型与向量库

默认使用本地 BGE 模型，路径 `backend/data/models/bge-small-zh-v1.5/`。如需下载：

```bash
# HuggingFace 镜像
huggingface-cli download BAAI/bge-small-zh-v1.5 \
  --local-dir backend/data/models/bge-small-zh-v1.5
# 或 ModelScope
python -c "from modelscope import snapshot_download; \
  snapshot_download('BAAI/bge-small-zh-v1.5', cache_dir='backend/data/models')"
```

向量库默认 Chroma，持久化目录 `./data/chroma`（见 `config.yaml` 的 `vector_store.chroma.persist_dir`）。

#### 2.3 数据库（MySQL）

`backend/app/db/session.py` 中配置连接串：

```python
ASYNC_DATABASE_URL = "mysql+aiomysql://root:你的密码@localhost:3306/dietapp?charset=utf8"
```

首次启动前创建数据库：

```sql
CREATE DATABASE IF NOT EXISTS dietapp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

数据表（`user`、`user_profile`）由 `init_db()` 在后端启动时通过 `Base.metadata.create_all` 自动创建，无需手动建表。

#### 2.4 Redis（可选）

```yaml
redis:
  host: localhost
  port: 6379
  db: 0
  password: ""
```

未安装 Redis 时，`MemoryManager` 自动降级为内存存储（`InMemoryStore`），功能不受影响，重启后会话丢失。

#### 2.5 JWT Secret

在 `backend/app/core/config_handler.py` / `core/security.py` 中配置 JWT 密钥。生成随机密钥：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. 启动服务

#### 3.1 启动后端（端口 8000）

```bash
cd backend/app
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# 或直接：python main.py
```

启动成功后控制台显示 `服务启动成功，环境：dev，端口：8000`，并完成数据库建表与 `MemoryManager` 预热。

#### 3.2 启动前端（端口 8501，另开终端）

```bash
cd frontend
node server.js          # 或 npm run dev
```

浏览器打开 http://localhost:8501/ 。

> 前端默认连 `http://localhost:8000`，启动后会自动 `GET /health` 探活，顶部徽标显示"已连接后端"（绿色）或"mock 演示"（琥珀色，后端不通时自动用本地 mock 流式回复，便于离线演示）。

#### 3.3 访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 UI | http://localhost:8501 | 豆包风格 AI 对话界面 |
| 后端 Swagger | http://localhost:8000/docs | API 文档（dev 环境） |
| 健康检查 | http://localhost:8000/health | 服务 + Redis 状态 |
| Agent 健康 | http://localhost:8000/api/agent/health | Agent 服务状态 |

---

## 📚 API 接口文档

所有接口统一前缀 `/api`，分为 user / chat / knowledge / agent 四组。

### 用户模块 `/api/user`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/user/register` | 注册（username/password） |
| POST | `/api/user/login` | 登录，返回 JWT |
| GET | `/api/user/profile` | 获取当前用户档案（需 JWT） |
| PUT | `/api/user/profile` | 更新档案（age/gender/height/weight/chronic_disease/food_taboo/region/diet_goal 等） |

### Agent 模块 `/api/agent`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agent/chat` | 同步膳食咨询 |
| POST | `/api/agent/chat/stream` | SSE 流式膳食咨询（6 阶段进度 + 打字机） |
| GET/PUT | `/api/agent/user/{user_id}/profile` | 获取/更新用户档案 |
| GET | `/api/agent/user/{user_id}/history` | 对话历史（max_messages / session_id） |
| POST | `/api/agent/user/{user_id}/diet-history` | 保存膳食方案 |
| GET | `/api/agent/user/{user_id}/diet-history` | 膳食方案历史（limit） |
| DELETE | `/api/agent/user/{user_id}/history` | 清空对话历史 |
| POST | `/api/agent/validate` | 校验膳食方案合规性 |
| GET | `/api/agent/health` | Agent 健康检查 |

**SSE 事件格式**（`/api/agent/chat/stream`）：

```
data: {"stage":"collect_info","status":"start","message":"正在收集用户信息..."}
data: {"stage":"retrieve_knowledge","status":"complete","message":"知识检索完成","results":5}
data: {"stage":"finalize","status":"stream","chunk":"为您定制..."}
data: {"stage":"output","status":"complete","data":{...完整方案...}}
data: {"done": true}
```

### 知识库模块 `/api/knowledge`（均需 JWT）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/knowledge/upload` | 上传文档（file + category，支持 txt/md/pdf/docx） |
| POST | `/api/knowledge/batch` | 批量上传目录（dir_path + category） |
| GET | `/api/knowledge/search` | 语义检索（query + top_k + category） |
| GET | `/api/knowledge/list` | 文档列表（按文件聚合） |
| DELETE | `/api/knowledge/{doc_id}` | 删除指定文档 |
| DELETE | `/api/knowledge/clear` | 清空知识库 |
| GET | `/api/knowledge/stats` | 统计信息（总数 + 分类计数） |

### 对话模块 `/api/chat`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/send` | 第一阶段 mock 对话（验证接口通路） |

---

## 🔄 知识库入库流程

`KnowledgeService`（Facade 模式）统一编排入库全流程，详见 [knowledge_service.py](backend/app/services/knowledge_service.py)：

```
上传文件 → DocumentLoader 解析(txt/md/pdf/docx)
         → TextSplitter 递归切分(按 chunk_size/overlap)
         → EmbeddingModel.embed() 批量向量化(BGE 512维)
         → ChromaVectorStore.add_documents() 入库(含元数据:source/category)
         → 控制台输出分批入库日志(批大小/耗时/总数)
```

检索时 `Retriever` 基于 `EmbeddingModel.embed_single(query)` 生成查询向量，在 Chroma 中做 Top-K 相似度检索，可选 category 过滤。

---

## 🧠 Agent 健壮性设计

针对大模型生成长 JSON 时的常见问题，[chain.py](backend/app/agent/chain.py) 做了多层防护：

1. **两层 JSON 解析**：先 `JsonOutputParser.parse()`，失败则 `_loose_parse_llm_json()` 三层兜底（剥离 ```` ```json ```` 代码块 → `raw_decode` 截断自然语言尾巴 → 统计括号差自动补 `]}`）。
2. **结构兜底** `_sanitize_diet_plan()`：无论输入是 `None`/`list`/残缺 dict，输出必定是含全部关键 key 的标准 dict，杜绝后续 `.get()` 的 `NoneType` 崩溃。
3. **多日方案**：`days[]` 数组结构，支持单日 / 三天 / 五天 / 一周；`format_diet_plan_summary` 按天渲染分天卡片（日均 + 周合计热量）。
4. **生成-校验-修正闭环**：`validate_tool` 检查忌口/慢病食材，不合规自动 `revise` prompt 二次生成。
5. **超时与重试**：LLM `timeout=180s`、`max_tokens=8192`，覆盖 7 天长 JSON 生成耗时。

---

## 🛠️ 常见问题

### 1. 启动提示 "LLM 未初始化"
LLM API Key 未配置或无效。检查 `config.yaml` 的 `llm.api_key`，或确认网络可访问 `api.deepseek.com`。

### 2. MySQL 连接失败 / 登录接口 500
确认 MySQL 已启动、`dietapp` 库已创建、`db/session.py` 连接串账号密码正确。表会在后端首次启动时自动建。

### 3. "模型文件不存在" / 嵌入加载失败
BGE 模型未下载到 `backend/data/models/bge-small-zh-v1.5/`，按上文"嵌入模型"小节下载。

### 4. `EmbeddingModel ... unexpected keyword argument`
早期版本调用 `EmbeddingModel(model=...)` 报错，现已兼容 `model` / `model_name` 两种参数名，并忽略多余关键字参数。

### 5. "一周减脂食谱"生成失败 / 超时
长 JSON 生成需 60~120s。确认 `config.yaml` 中 `llm.timeout: 180`、`max_tokens: 8192`；并确认已部署最新的宽松解析 + 兜底逻辑。

### 6. 控制台看不到业务调试日志
项目用 loguru 输出日志，并通过 `InterceptHandler` 桥接标准库 `logging`。若某模块日志丢失，确认其使用 `logging.getLogger(__name__)` 且 `setup_logger()` 已在启动时调用。

### 7. 前端 SSE 无响应 / CORS 报错
确认后端已启动且 `main.py` 的 CORSMiddleware `allow_origins` 包含前端地址（默认 `["*"]`）。前端默认连 `http://localhost:8000`。

### 8. 数据存储位置

| 数据类型 | 位置 |
|---------|------|
| 用户与档案 | MySQL `dietapp` 库（user / user_profile 表） |
| 向量库 | `backend/data/chroma/` |
| 会话/方案缓存 | Redis（或内存降级） |
| 本地嵌入模型 | `backend/data/models/bge-small-zh-v1.5/` |

---

## 📄 License

本项目仅供学习和面试使用。
