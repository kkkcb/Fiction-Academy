# ai-book-writer (book.ai) 技术架构深度分析

## 一、项目概览

| 属性 | 详情 |
|------|------|
| **项目名称** | book.ai |
| **GitHub** | https://github.com/cheesejaguar/book.ai |
| **定位** | 生产级 AI 图书创作系统 — 将作者简报在数小时内转化为完整书稿 |
| **核心价值** | 将"从构思到初稿"的时间从数周缩短到数小时 |
| **许可证** | MIT |
| **版本** | 0.1.0 |

---

## 二、技术栈

### 后端

| 组件 | 技术 | 版本 |
|------|------|------|
| Web 框架 | FastAPI (async/await) | 0.115.4 |
| ASGI 服务器 | Uvicorn | 0.32.0 |
| ORM | SQLAlchemy 2.0 (async) | 2.0.36 |
| 异步 PG 驱动 | asyncpg | 0.30.0 |
| 数据库迁移 | Alembic | 1.14.0 |
| 缓存 | Redis | 5.2.0 |
| AI 框架 | CrewAI | 0.80.0 |
| LLM 路由 | LiteLLM | >=1.49.0 |
| 认证 | python-jose + authlib + passlib | JWT/OAuth2 |
| 监控 | prometheus-client | 0.21.0 |
| SSE | sse-starlette | 2.1.3 |

### 前端

| 组件 | 技术 | 版本 |
|------|------|------|
| 框架 | Next.js 14 (App Router) | 14.2.5 |
| 语言 | TypeScript (strict) | 5.5.3 |
| 样式 | Tailwind CSS + shadcn/ui | 3.4.6 |
| 状态管理 | Zustand | 4.5.4 |
| UI 组件库 | Radix UI (8+ 组件) | 各版本 |
| 测试 | Vitest + Testing Library | 3.2.4 |

### 基础设施

| 组件 | 技术 |
|------|------|
| 容器化 | Docker (multi-stage builds) |
| 编排 | Kubernetes (GKE ready) + Helm |
| 数据库 | PostgreSQL 16 |
| 缓存 | Redis 7 (clustering) |
| 反向代理 | Nginx 1.25 |
| 监控 | Prometheus + Grafana |
| CI/CD | GitHub Actions |

---

## 三、系统架构图

```
                         ┌─────────────────────────────────────────────┐
                         │              Internet / Users                │
                         └─────────────────┬───────────────────────────┘
                                           │
                              ┌─────────────▼──────────────┐
                              │   Nginx Ingress Controller  │
                              │   (TLS/SSL, Let's Encrypt)  │
                              └──────┬─────────────┬────────┘
                                     │             │
                    ┌────────────────▼──┐    ┌──────▼──────────────────┐
                    │   Next.js 14      │    │   FastAPI Backend       │
                    │   Frontend (x3)   │    │   (x2~10, HPA)         │
                    │   ├─ App Router   │    │   ├─ /api/v1/*          │
                    │   ├─ Zustand      │    │   ├─ /auth/*            │
                    │   ├─ SSE Client   │◄──SSE──┤ SSE Streaming       │
                    │   └─ API Route    │    │   └─ /api/metrics       │
                    │     (代理层)       │    │                         │
                    └───────────────────┘    └───────┬────────────────┘
                                                     │
                          ┌──────────────────────────┼───────────────────┐
                          │                          │                   │
               ┌──────────▼──────────┐    ┌──────────▼──────┐  ┌───────▼────────┐
               │   PostgreSQL 16     │    │   Redis 7       │  │   LiteLLM       │
               │   ├─ users          │    │   ├─ SSE Cache  │  │   Router        │
               │   ├─ projects       │    │   ├─ Rate Limit │  │   ├─ gpt-5      │
               │   ├─ sessions       │    │   └─ Session    │  │   ├─ claude     │
               │   ├─ events         │    │                 │  │   └─ gemini     │
               │   ├─ artifacts      │    └─────────────────┘  └───────┬────────┘
               │   └─ costs          │                                   │
               └─────────────────────┘                          ┌───────▼────────┐
                                                                │   CrewAI Agents │
                                                                │   ├─ ConceptGen │
                                                                │   ├─ Outliner   │
                                                                │   ├─ Writer     │
                                                                │   ├─ Editor     │
                                                                │   └─ Continuity │
                                                                └─────────────────┘
```

---

## 四、Agent / 工作流设计

### 五大 Agent

| Agent | 角色 | 目标 | 核心方法 |
|-------|------|------|---------|
| **ConceptGenerator** | 概念生成器 | 将情节种子和简报转化为丰富的创意概念 | `generate_concepts()` |
| **Outliner** | 故事大纲师 | 从概念创建逐章详细大纲 | `create_outline()` |
| **Writer** | 章节写手 | 按风格指南撰写生动的章节内容 | `write_chapter()` |
| **Editor** | 结构编辑 | 执行结构/行文/文字/校对四级编辑 | `edit_content()` |
| **ContinuityChecker** | 连贯性检查 | 确保名字/年龄/时间线/事实一致 | `check_continuity()` |

### 编排方式

**流水线式顺序编排**：

```
Brief → ConceptGenerator → Outliner → Writer (per chapter) → Editor → ContinuityChecker
```

关键设计：

1. **单 Agent Crew 模式**: 每个方法内部创建只包含单个 Agent 的 Crew，通过 `asyncio.to_thread(crew.kickoff)` 将同步 CrewAI 调用包装为异步
2. **并行章节写作**: `ParallelChapterWriter` 支持批量并行章节生成，默认 `max_parallel=3`，通过 `asyncio.gather` 并发执行
3. **上下文传递**: Writer Agent 接收最近 2 章的内容作为上下文（截断到每章最后 500 字符）
4. **四级编辑体系**: structural/line/copy/proof

### 模型路由策略（LiteLLM）

| 策略 | 说明 |
|------|------|
| **usage-based-routing** | 基于使用量的智能路由 |
| **fallback** | gpt-5 (主) → claude-sonnet-4 (备) |
| **overflow** | 上下文超限时路由到 gemini-2.5-pro |
| **cheap_fallback** | 成本敏感场景使用 claude/gemini |

**预算分配**: Writer 60%, Editor 25%, ContinuityChecker 10%, ConceptGenerator 3%, Outliner 2%

---

## 五、核心功能模块

### 5.1 大纲生成（SSE 流式）

1. 验证用户预算（查询当月已用费用 vs monthly_budget_usd）
2. 检查 Redis 缓存（基于 brief 的 MD5 hash）
3. 调用 ConceptGenerator 生成概念
4. 通过 `litellm.acompletion()` 直接流式调用 LLM 生成大纲
5. 每 100 个 token 发送一次 checkpoint 事件
6. 完成后将结果存入 artifacts 表和 Redis 缓存

SSE 事件协议：token / checkpoint / complete / error

### 5.2 前端 SSE 代理

Next.js API Route 作为 SSE 代理层：
- 从浏览器 cookies 中提取 access_token 和 refresh_token
- 转发请求到后端 FastAPI，附加认证 cookies
- 直接将后端的 SSE 流透传给前端浏览器

解决了浏览器 EventSource API 不支持自定义 Headers 的限制。

### 5.3 OAuth 认证流程

完整 Google OAuth2 + PKCE 流程，签发自有 JWT (access_token + refresh_token)，通过 HttpOnly cookies 返回。

### 5.4 成本追踪

每次 LLM 调用记录到 costs 表：agent 名称、model 名称、prompt_tokens / completion_tokens、usd 金额。

---

## 六、数据流与存储

### 数据库模型（6 张表）

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    users     │     │   projects   │     │   sessions   │
├──────────────┤     ├──────────────┤     ├──────────────┤
│ id (UUID PK) │     │ id (UUID PK) │◄────│ project_id FK│
│ email (uniq) │     │ name         │     │ user_id FK   │
│ provider     │     │ settings     │     │ context JSONB│
│ budget_usd   │     └──────────────┘     └──────┬───────┘
└──────────────┘                                 │
                      ┌──────────────────────────┼───────────────┐
                      │                          │               │
             ┌────────▼──────┐  ┌────────▼──────┐  ┌─────▼────────┐
             │    events     │  │   artifacts   │  │    costs     │
             ├──────────────┤  ├──────────────┤  ├──────────────┤
             │ session_id FK│  │ session_id FK│  │ session_id FK│
             │ type         │  │ kind         │  │ agent        │
             │ payload JSONB│  │ path         │  │ model        │
             └──────────────┘  │ blob (bytea) │  │ usd          │
                               └──────────────┘  └──────────────┘
```

### Redis 缓存策略

| 用途 | TTL | 说明 |
|------|-----|------|
| 响应缓存 | 3600s (1h) | LLM 生成结果缓存 |
| 会话历史 | 86400s (24h) | 对话上下文保持 |
| OAuth State | 临时 | PKCE state/verifier 存储 |
| 速率限制 | 窗口式 | 60 RPM per key |

### K8s 部署

- HPA: 2-10 Pod 自动扩缩（基于 CPU + Memory + active_sessions 自定义指标）
- 安全加固：非 root 容器、只读根文件系统、Drop ALL capabilities
- 滚动更新零停机
- Docker Compose 生产部署：6 个服务，三层网络隔离

---

## 七、亮点与创新点

1. **LiteLLM 统一路由层**: 主备切换 + 溢出路由 + 成本优化 + 预算分配 + 统一缓存
2. **完善的成本管控**: 按月预算限制、实时 token 追踪、写作前成本预估
3. **SSE 代理模式**: Next.js API Route 代理 SSE 流，解决浏览器原生 EventSource 限制
4. **生产级 K8s 部署**: HPA + 三层健康检查 + 滚动更新 + 安全加固
5. **全面可观测性**: Prometheus 自定义指标 + 结构化日志 + X-Request-ID 全链路追踪
6. **prompt.xml 规范**: 使用结构化 XML 定义项目需求、验收标准、架构决策

---

## 八、对 Fiction Academy 的启示

### 可直接借鉴的架构模式

| 模式 | 说明 |
|------|------|
| LiteLLM 统一路由层 | failover、成本控制、缓存开箱即用 |
| Agent 预算分配 | 按 Agent 分配预算百分比，确保核心创作 Agent 获得大部分预算 |
| SSE 代理模式 | Next.js API Route 代理 SSE 流的方案 |
| 成本全链路管控 | 预估算 → 预算检查 → 实时追踪 → 月度汇总的完整闭环 |
| K8s 生产部署 | 从项目初期考虑部署、健康检查、监控 |

### 架构差异与改进空间

| 维度 | book.ai | Fiction Academy 可改进方向 |
|------|---------|--------------------------|
| Agent 编排 | 线性流水线，单 Agent Crew | 可考虑多 Agent 协作 Crew |
| 上下文管理 | 硬编码取最近 2 章，截断 500 字符 | 应实现智能上下文窗口管理 |
| 数据模型 | 6 表，JSONB 存储 | 已有更丰富的数据模型规划 |
| 前端交互 | 单页输入输出 | 可设计更丰富的编辑器和管理面板 |

### 关键教训

1. **MVP 优先**: Agent 系统设计简洁 — 每个 Agent 单任务，不搞复杂通信
2. **缓存策略至关重要**: Redis 缓存 + MD5 去重可减少约 40% API 调用
3. **生产就绪**: 从初期就考虑 K8s、健康检查、监控、安全
4. **成本透明**: 前端实时显示费用和预算，提升用户信任度
