# DietAgent · 每日膳食搭配助手

> 基于 LangChain LCEL + LLM Planner + @tool + RAG + FastAPI 的大模型个性化膳食助手。
> 支持 8 类意图动态路由、8 个 Agent 工具、多轮会话记忆、SSE 流式输出、本地知识库管理与 Docker 一键部署。

---

## 快速开始（部署 · 安装 · 配置 · 启动）

### 方式一：Docker Compose（推荐，当前已部署）

这是项目当前使用的正式运行方式：4 个容器组成完整系统，本地开发与演示共用同一套服务。

#### 1. 环境要求

- Docker Desktop（Windows/Mac）或 Docker Engine + Docker Compose。
- 至少 2 GB 可用内存（BGE 嵌入模型 + Chroma + Python 服务）。
- 可访问 Docker Hub / PyPI 的网络（国内网络通常需要代理或镜像加速）。

#### 2. 准备配置

复制 `.env.example` 为 `.env` 并填写真实值：

```powershell
Copy-Item .env.example .env
```

`.env` 中需要确认的字段：

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key，必填 |
| `MYSQL_ROOT_PASSWORD` | MySQL root 密码，首次部署建议修改 |
| `JWT_SECRET_KEY` | JWT 签名密钥，建议用随机 64 位 hex |
| `AMAP_WEATHER_KEY` | 高德天气 Key，可选，不填时天气功能自动降级 |

`.env` 已被 `.gitignore` 忽略，不要提交到 Git。

#### 3. 构建并启动

```powershell
docker compose up -d --build
```

首次构建会安装 Python/Node 依赖并打包本地 BGE 模型，耗时较长；之后启动使用缓存。

#### 4. 访问

| 服务 | 地址 |
|------|------|
| 前端 UI | http://127.0.0.1:8501 |
| 后端 API | http://127.0.0.1:8000 |
| 健康检查 | http://127.0.0.1:8000/health |
| API 文档 | http://127.0.0.1:8000/docs（`ENV=dev` 时开放） |

> 注意：本机浏览器请使用 `127.0.0.1`，不要用 `localhost`。当前机器上 `localhost` 会优先解析到 IPv6 `::1`，可能被其他进程占用导致无法访问。

#### 5. 验证部署

- 打开 `http://127.0.0.1:8501`，注册账号并登录。
- 进入「档案」完善健康信息，进入「知识库」上传营养学文档。
- 发起聊天，确认 SSE 流式打字机效果正常。
- 访问 `http://127.0.0.1:8000/health`，应返回 `{"status":"ok",...}`。

#### 6. 常用命令

```powershell
docker compose up -d                  # 启动
docker compose logs -f backend        # 查看后端日志
docker compose logs -f frontend       # 查看前端日志
docker compose ps                     # 查看容器状态
docker compose down                   # 停止，保留数据卷
docker compose down -v                # 停止并清空 MySQL/Redis/Chroma 数据，慎用
docker compose up -d --build frontend # 仅重建前端
```

#### 7. 数据持久化

| 数据 | 存储位置 |
|------|---------|
| MySQL 用户/档案 | named volume `mysql_data` |
| Redis 会话/方案历史 | named volume `redis_data` |
| Chroma 知识库向量 | named volume `chroma_data` |
| BGE 本地模型 | 已打进 backend 镜像，不依赖外部下载 |

---

### 方式二：本地 conda + Node（开发调试）

适用于不启动 Docker、直接在 `ragent` conda 环境中调试。

#### 1. 环境要求

- Python 3.11（推荐使用 conda 环境 `ragent`）
- Node.js 16+
- MySQL 5.7+ / 8.0（必须）
- Redis 6.0+（可选，未连接时自动降级为内存记忆）

#### 2. 创建数据库

```sql
CREATE DATABASE IF NOT EXISTS dietapp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

数据表由后端启动时自动创建。

#### 3. 安装依赖

```powershell
conda activate ragent
pip install -r backend/requirements-docker.txt
pip install PyPDF2==3.0.1
```

说明：根目录 `requirements.txt` 是 conda 导出文件，Linux 容器无法直接使用；Docker 构建使用 `backend/requirements-docker.txt`，本地调试也可直接用它安装。

#### 4. 配置

核心配置位于 `backend/app/core/config/`：

- `config.yaml`：embedding / vector_store / llm / redis 基础配置。
- `config.dev.yaml`：开发环境覆盖（LLM Key、天气 Key）。
- `config.prod.yaml`：生产环境覆盖，敏感信息统一使用 `${ENV_VAR}` 占位符。

需要检查：

- `backend/app/db/session.py` 中的 `DATABASE_URL`，或通过环境变量 `DATABASE_URL` 注入。
- LLM Key：DeepSeek 默认，也可切换 Qwen / OpenAI。
- BGE 模型目录：默认 `backend/data/models/bge-small-zh-v1.5`。
- JWT Secret：通过 `JWT_SECRET_KEY` 环境变量注入。

#### 5. 启动后端（8000）

```powershell
conda activate ragent
cd backend/app
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

启动成功后日志会显示数据库初始化完成、MemoryManager 预热完成。

#### 6. 启动前端（8501，另开终端）

```powershell
cd frontend
node server.js
```

浏览器打开 `http://127.0.0.1:8501`。

---

## 项目概述

### 项目简介

DietAgent 是一款大模型驱动的个性化营养膳食助手。用户填写健康档案（年龄、身高体重、慢病、忌口、口味、地域、膳食目标）后，Agent 会结合本地营养学知识库 RAG 检索，动态判断用户意图并调用合适的工具，生成可校验、可多日扩展的膳食方案，并通过 SSE 流式实时回传。

### 核心特性

- **LLM Planner 动态意图规划**：不再是硬编码单条流水线，而是先由 LLM 输出结构化执行计划，支持 8 类意图：生成食谱、修订食谱、营养问答、健康指标计算、食材评估、档案更新、闲聊、信息收集。
- **@tool 工具化 + bind_tools ReAct**：注册 8 个 LangChain 工具，支持 LLM 自主决策调用，形成「决策 → 执行 → 观察 → 结论」闭环。
- **LCEL 子链编排**：食谱生成链路使用 LCEL `|` 串联，并暴露标准 `Runnable` 接口，支持 `ainvoke` / `abatch` / callbacks。
- **本地 RAG 知识增强**：BGE 中文嵌入 + Chroma 向量库，支持 PDF/TXT/MD/DOCX 入库、分类管理、Top-K 语义检索。
- **确定性健康计算工具**：BMI / BMR / 蛋白质目标使用公式工具计算，不依赖 LLM 做算术。
- **生成-校验-修正闭环**：方案生成后自动检查忌口与慢病禁忌，不合规触发二次修订。
- **结构化 JSON 健壮性**：对超长 JSON 做「宽松解析 + 结构兜底」，杜绝 `NoneType` 崩溃。
- **多轮会话记忆**：Redis 存储，无 Redis 自动降级为进程内内存。
- **SSE 流式输出**：阶段进度事件 + 最终答复逐字打字机效果。
- **天气膳食适配**：接入高德天气，按地区温度/天气生成饮食提示，带 TTL 缓存与优雅降级。
- **完整前端**：登录注册、对话、健康档案、知识库管理、会话历史、天气 chip，零构建依赖。
- **Docker 一键部署**：Compose 编排 4 个服务，镜像内离线模型，数据卷持久化。

---

## 系统架构

```text
浏览器（HTML + Tailwind + 原生 JS）
  │ HTTP / SSE（fetch + ReadableStream）
  ▼
FastAPI 层（/api/*）
  ├─ user：注册 / 登录 / 档案
  ├─ agent：同步对话 / SSE 流式 / 档案 / 历史 / 校验 / 天气
  ├─ knowledge：上传 / 检索 / 删除 / 统计
  └─ chat：mock 对话（接口验证）
  ▼
Agent 服务层（AgentService 单例）
  ▼
DietAgentChain（LangChain）
  ├─ LLM Planner：8 意图动态路由
  ├─ 8 个 @tool：BMI/BMR/蛋白质 / 忌口校验 / 档案更新 / RAG 检索 / 地域适配 / 天气
  ├─ bind_tools ReAct（LLM 自主调用工具）
  └─ LCEL 子链：diet_linear_chain / diet_revise_chain
  ▼
RAG 知识层（KnowledgeService）
  ├─ DocumentLoader（txt/md/pdf/docx）
  ├─ TextSplitter（递归切分）
  ├─ EmbeddingModel（BGE 512 维，单例）
  └─ ChromaVectorStore（持久化 + 相似度检索）
  ▼
数据层
  ├─ MySQL：user / user_profile
  ├─ Redis：会话记忆 / 膳食方案历史
  └─ Chroma：知识库向量
外部依赖
  ├─ LLM：DeepSeek / Qwen / OpenAI（统一 ChatOpenAI 封装）
  └─ 高德天气 API
```

### Agent 处理流程

```text
用户输入
  ▼
① 信息收集：读取用户档案，检查信息完整性，缺失则追问
  ▼
② LLM Planner：输出结构化 ExecutionPlan（intent / plan_days / need_rag / tools_to_call）
  ▼
③ 按意图分支：
   - diet_plan     → RAG 检索 → 约束构建 → 天气 → 生成 → 校验 → 输出
   - diet_revise   → 同上，并插入「取上一版食谱」环节
   - nutrition_qa  → 条件 RAG → QA 回答
   - health_calc   → BMI/BMR/蛋白质工具 → LLM 解读
   - food_eval     → 条件 RAG → 忌口校验工具 → 综合结论
   - profile_update→ 档案更新工具写库 → 确认回复
   - casual_chat   → 直接礼貌回复
   - info_collection → 输出追问
  ▼
④ SSE 流式：阶段事件 + 最终答复打字机输出
```

### Agent 工具清单

| 工具 | 功能 |
|------|------|
| `bmi_calc_tool` | 计算 BMI、分类、健康体重区间 |
| `bmr_calc_tool` | Mifflin-St Jeor 公式计算基础代谢 |
| `protein_target_tool` | 按目标计算每日蛋白质目标 |
| `food_taboo_check_tool` | 食材禁忌/慢病食材校验 |
| `user_profile_update_tool` | 更新用户健康档案 |
| `rag_search_tool` | 检索本地营养学知识库 |
| `region_adapt_tool` | 按地域饮食特点适配方案 |
| `weather_tool` | 查询天气并生成膳食提示 |

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | HTML + Tailwind CSS v3 + 原生 JS | 零构建，marked.js 渲染 Markdown |
| 前端服务 | Node.js 内置 http | 静态服务器，端口 8501 |
| 后端 | FastAPI + Uvicorn | 异步 API，工厂模式 + lifespan |
| Agent | LangChain 1.x | LCEL / Planner / @tool / bind_tools / Runnable |
| LLM | DeepSeek-Chat（默认） | 兼容 Qwen / OpenAI，统一 `ChatOpenAI` |
| 嵌入 | BAAI/bge-small-zh-v1.5 | 本地 512 维，单例缓存 |
| 向量库 | Chroma | 本地持久化 |
| 数据库 | MySQL + SQLAlchemy 2.0 async + aiomysql | 表自动创建 |
| 记忆 | Redis（可选）/ 内存降级 | MemoryManager 自动选择 |
| 鉴权 | JWT + bcrypt | python-jose |
| 流式 | SSE / StreamingResponse | 阶段进度 + 打字机 |
| 日志 | loguru + InterceptHandler | 统一日志桥接 |
| 部署 | Docker Compose | backend / frontend / mysql / redis |

---

## 项目结构

```text
DietAgent_LC/
├── backend/
│   ├── Dockerfile                  # 后端镜像（CPU torch + 本地 BGE 模型）
│   ├── requirements-docker.txt     # Docker/Linux pip 依赖
│   └── app/
│       ├── main.py                 # FastAPI 工厂 + lifespan + CORS + 异常 + /health
│       ├── core/                   # 配置 / 安全 / 日志 / 异常
│       │   ├── config/             # config.yaml / dev / prod
│       │   ├── config_handler.py   # Pydantic 配置 + ${ENV_VAR} 解析
│       │   ├── security.py         # JWT + bcrypt
│       │   └── logger.py           # loguru 桥接
│       ├── api/
│       │   ├── dependencies.py     # JWT 依赖注入
│       │   └── routers/            # user / agent / knowledge / chat
│       ├── agent/
│       │   ├── chain.py            # Planner + 8 意图 + LCEL 子链 + 流式
│       │   ├── llm_client.py       # LLM 统一封装
│       │   ├── memory.py           # Redis / 内存记忆
│       │   ├── prompts/            # planner / system / diet / validate
│       │   └── tools/              # 8 个 @tool 工具
│       ├── rag/                    # embeddings / vector_store / retriever / loader / splitter
│       ├── services/               # agent_service / knowledge_service
│       ├── db/                     # session / models / crud
│       ├── schemas/                # Pydantic 请求响应模型
│       └── data/                   # chroma / models（本地 BGE）
├── frontend/
│   ├── Dockerfile                  # Node 静态服务器镜像
│   ├── index.html                  # 豆包风格 UI
│   ├── app.js                      # SSE / 档案 / 知识库 / 历史逻辑
│   └── server.js                   # 静态服务器（0.0.0.0:8501）
├── docker-compose.yml              # 4 服务编排
├── .env.example                    # 环境变量模板
├── .dockerignore
├── .gitignore
├── docs/                           # 架构 / 部署 / API / 准备
└── requirements.txt                # conda 环境导出（参考）
```

---

## API 接口

所有接口统一前缀 `/api`，分为 user / agent / knowledge / chat。

### 用户 `/api/user`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/user/register` | 注册 |
| POST | `/api/user/login` | 登录，返回 JWT |
| GET | `/api/user/profile` | 获取当前用户档案（需 JWT） |
| PUT | `/api/user/profile` | 更新档案 |

### Agent `/api/agent`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agent/chat` | 同步膳食咨询 |
| POST | `/api/agent/chat/stream` | SSE 流式咨询 |
| GET | `/api/agent/user/{user_id}/profile` | 获取健康档案 |
| PUT | `/api/agent/user/{user_id}/profile` | 更新健康档案 |
| GET | `/api/agent/user/{user_id}/history` | 对话历史 |
| POST | `/api/agent/user/{user_id}/diet-history` | 保存膳食方案 |
| GET | `/api/agent/user/{user_id}/diet-history` | 膳食方案历史 |
| DELETE | `/api/agent/user/{user_id}/history` | 清空对话历史 |
| POST | `/api/agent/validate` | 校验膳食方案 |
| GET | `/api/agent/weather/current` | 当前天气与膳食提示 |
| GET | `/api/agent/health` | Agent 健康检查 |

### 知识库 `/api/knowledge`（需 JWT）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/knowledge/upload` | 上传文档 |
| POST | `/api/knowledge/batch` | 批量上传 |
| GET | `/api/knowledge/search` | 语义检索 |
| GET | `/api/knowledge/list` | 文档列表 |
| DELETE | `/api/knowledge/{doc_id}` | 删除文档 |
| DELETE | `/api/knowledge/clear` | 清空知识库 |
| GET | `/api/knowledge/stats` | 统计信息 |

### SSE 事件格式

```text
data: {"stage":"collect_info","status":"start","message":"正在收集您的健康信息..."}
data: {"stage":"plan_execution","status":"complete","intent":"diet_plan","reasoning":"..."}
data: {"stage":"diet_linear_chain","status":"complete","message":"膳食方案生成与校验完成"}
data: {"stage":"finalize","status":"stream","chunk":"为您定制..."}
data: {"stage":"output","status":"complete","data":{...}}
data: {"done": true}
```

---

## 知识库入库流程

```text
上传文件 → DocumentLoader 解析（txt/md/pdf/docx）
        → TextSplitter 递归切分
        → EmbeddingModel.embed（BGE 512 维）
        → ChromaVectorStore 入库（source/category 元数据）
        → 检索时 Top-K 相似度 + category 过滤
```

---

## 常见问题

### 1. 浏览器打不开 `localhost:8501`

请使用 `http://127.0.0.1:8501`。当前机器 `localhost` 会优先解析到 IPv6 `::1`，可能被其他进程占用。

### 2. Docker 构建时拉取镜像失败

国内网络常见问题。可通过本地代理或 Docker Desktop 镜像加速解决；若 BuildKit 无法拉取 `python` / `node` 基础镜像，先执行：

```powershell
docker pull python:3.11-slim
docker pull node:20-alpine
```

### 3. 聊天报「LLM 未初始化」或生成失败

检查 `.env` 中 `DEEPSEEK_API_KEY` 是否有效，以及网络能否访问 `api.deepseek.com`。

### 4. MySQL 连接失败

确认 `DATABASE_URL` 指向的 MySQL 账号密码正确，`dietapp` 数据库已创建；表会在启动时自动创建。

### 5. 嵌入模型加载失败

确认 `backend/data/models/bge-small-zh-v1.5/` 存在完整模型文件；Docker 镜像中已内置该模型。

### 6. SSE 流式无响应

检查前端 `app.js` 的 `API_BASE`，本地默认 `http://127.0.0.1:8000`；后端 CORS 默认 `["*"]`。

### 7. 想查看接口文档

生产环境 `ENV=prod` 会关闭 `/docs`。将 compose 中 `ENV` 改为 `dev` 后重启 backend 即可。

---

## 相关文档

- [docs/部署方案.md](docs/部署方案.md)：本地开发 + cpolar + Cloudflare Tunnel 公网访问方案。
- `docs/API文档.md`：接口细节。
- `backend/app/working_docs/`：各阶段任务规划与实现说明。

---

本项目仅供学习、面试与演示使用。
