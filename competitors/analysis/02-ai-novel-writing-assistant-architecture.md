# AI Novel Writing Assistant 技术架构深度分析

## 一、项目概览

| 维度 | 内容 |
|------|------|
| **项目名称** | AI Novel Writing Assistant v2 / AI 小说创作工作台 |
| **定位** | 面向长篇小说的 AI Native 生产系统，非聊天补全工具 |
| **核心价值** | 目标用户为完全不懂写作的新手；优先解决"如何把整本书写完" |
| **许可** | MIT License |
| **工程形态** | pnpm workspace Monorepo (`client/` + `server/` + `shared/`) |

---

## 二、技术栈

| 层级 | 技术 |
|------|------|
| **前端** | React 19 + Vite + React Router + TanStack Query + Plate（富文本编辑器） |
| **后端** | Express 5 + Prisma 7（ORM） + Zod（校验） |
| **AI 编排** | LangChain + LangGraph（Agent Workflow） |
| **数据库** | SQLite（Prisma，开箱即用） |
| **RAG 向量库** | Qdrant（可选接入） |
| **LLM 提供商** | DeepSeek、OpenAI、Anthropic、Grok、Kimi、MiniMax、GLM、Qwen、Gemini、Ollama（10 家） |
| **类型共享** | TypeScript 共享包 `@ai-novel/shared` |
| **Node 要求** | ^20.19.0 \|\| ^22.12.0 \|\| >=24.0.0 |

---

## 三、系统架构图

```
+---------------------------------------------------------------+
|                     前端 (React 19 + Vite)                      |
|  +-----------+  +------------+  +-----------+  +-------------+  |
|  | Creative  |  | Novel      |  | Style     |  | Knowledge   |  |
|  | Hub       |  | Workspace  |  | Engine    |  | & World     |  |
|  +-----+-----+  +-----+------+  +-----+-----+  +------+------+ |
|        |               |              |               |          |
|  +-----+-----+  +------+------+     |          +-----+------+   |
|  | useSSE()  |  | TanStack    |     |          | Axios      |   |
|  | (SSE Hook)|  | Query hooks |     |          | apiClient  |   |
|  +-----------+  +-------------+     |          +------------+   |
+--------|---------------|------------|---------------|------------+
         |  SSE/REST     |  REST      |  REST         |  REST
+--------|---------------|------------|---------------|------------+
|        v               v            v               v            |
|                    后端 (Express 5)                               |
|  +-------------+  +------------------+  +---------------------+  |
|  | Agent       |  | LLM Integration  |  | Routes (40+ files)  |  |
|  | Runtime     |  | Layer            |  |                     |  |
|  | +---------+ |  | +-------------+  |  |  /api/novel/*       |  |
|  | | Planner | |  | | Model Router|  |  |  /api/creative-hub  |  |
|  | +---------+ |  | | (Task-based)|  |  |  /api/chat          |  |
|  | | Writer  | |  | +------+------+  |  |  /api/knowledge     |  |
|  | +---------+ |  | | Factory     |  |  |  /api/style-engine  |  |
|  | | Reviewer| |  | | (ChatOpenAI)|  |  |  /api/world         |  |
|  | +---------+ |  | +------+------+  |  |  /api/tasks         |  |
|  | |Continuity| | | | Structured  |  |  |  /api/agent-runs    |  |
|  | +---------+ |  | | Invoke      |  |  |  /api/rag           |  |
|  | | Repair  | |  | | (Zod+Repair)|  |  |  ...                |  |
|  | +---------+ |  | +-------------+  |  +---------------------+  |
|  +------+------+  +------------------+                           |
|         |                                                        |
|  +------v------+  +-------------+  +-------------------------+  |
|  | Tool        |  | Prompt      |  | RAG Config              |  |
|  | Registry    |  | Registry    |  | (Qdrant + Embedding)    |  |
|  | (8 domains) |  | (PromptAsset)|  |                         |  |
|  +------+------+  +-------------+  +-------------------------+  |
+---------|------------|-------------------------------------------+
          v            v
  +-------+---+  +-----+------+
  | SQLite    |  | Qdrant     |
  | (Prisma)  |  | (可选)     |
  +-----------+  +------------+
```

---

## 四、Agent / 工作流设计

### 执行态 Agent（5 个）

| Agent | 职责 |
|-------|------|
| **Planner** | 意图识别、结构化规划、工具编排，全权调度 |
| **Writer** | 章节正文生成、草稿保存、Patch 应用 |
| **Reviewer** | 审阅、一致性检查、角色/时间线/世界观校验 |
| **Continuity** | 连续性检查、事实提取、快照比对 |
| **Repair** | 修复、重写、Patch 应用 |

### 域 Agent（7 个）

| 域 Agent | 职责 | 资源范围 |
|----------|------|----------|
| **Coordinator** | 跨模块规划、状态汇总、任务诊断 | global, task, agent_run |
| **NovelAgent** | 小说/章节/快照/创作决策 | novel, chapter, snapshot |
| **BookAnalysisAgent** | 拆书分析、知识沉淀 | book_analysis, knowledge_document |
| **KnowledgeAgent** | 知识文档、索引、召回 | knowledge_document |
| **WorldAgent** | 世界观、冲突诊断、快照 | world, snapshot, novel |
| **FormulaAgent** | 写作公式、风格沉淀 | writing_formula, novel |
| **CharacterAgent** | 角色库、模板复用 | base_character, novel |

### Agent Runtime 架构

```
AgentRuntime (入口)
  ├── AgentTraceStore (Prisma 持久化)
  │     ├── createRun / getRun / listRuns
  │     ├── addStep / addApproval
  │     └── findToolResultByIdempotencyKey (幂等去重)
  ├── RunExecutionService (执行引擎)
  │     ├── runActionPlan() -- 遍历 PlannedAction，逐工具执行
  │     ├── executeToolWithRetry() -- 内置重试逻辑
  │     ├── 权限检查 (canAgentUseTool)
  │     └── 审批拦截 (evaluateApprovalRequirement)
  └── ApprovalContinuationService (审批续跑)
        ├── resolve() -- 用户审批后从断点恢复
        └── reconcileWaitingApprovalRun() -- 过期自动清理
```

### 导演模式（Auto Director）

从"一句灵感"到"整本可写"的自动化流水线，支持：
- 按重要阶段审核
- 自动推进到可开写
- 继续自动执行前 10 章

### 工具注册体系

工具按 **8 个域** 组织，统一使用 `AgentToolDefinition` 接口：

| 域 | 核心工具 |
|----|----------|
| Novel Workspace | create_novel, select_novel_workspace |
| Novel Read | list_chapters, get_chapter_content, get_story_bible |
| Novel Production | start_full_novel_pipeline, sync_chapters_from_structured_outline |
| Write | save_chapter_draft, apply_chapter_patch |
| Book Analysis | list_book_analyses, get_book_analysis_detail |
| Knowledge | list_knowledge_documents, search_knowledge |
| World | list_worlds, get_world_detail, explain_world_conflict |
| Character/Formula/Task | 角色管理、公式管理、任务管理 |

### 审批策略

矩阵式权限控制，每个 Agent 有独立的工具白名单。高风险操作自动触发审批（整章覆盖、批量改写、启动流水线）。

---

## 五、核心功能模块

### 5.1 RAG 知识库

| 参数 | 默认值 | 说明 |
|------|--------|------|
| embeddingProvider | openai | 支持 openai / siliconflow |
| chunkSize | 800 | 分块大小 |
| chunkOverlap | 120 | 分块重叠 |
| vectorCandidates | 40 | 向量召回候选数 |
| keywordCandidates | 40 | 关键词召回候选数 |
| finalTopK | 8 | 最终返回条数 |

支持混合检索（向量 + 关键词），文档版本管理，知识绑定。

### 5.2 写法引擎（Style Engine）

四维规则集：NarrativeRules、CharacterRules、LanguageRules、RhythmRules

反 AI 规则体系：forbidden/risk/encourage 三级，支持自动重写。

### 5.3 故事模式（Story Mode）

结构化的故事驱动模式，定义核心驱动、读者回报、推进单位、冲突形式、天花板、必选/禁止信号等。

### 5.4 任务中心

统一任务模型，支持：book_analysis | novel_pipeline | knowledge_document | image_generation | agent_run | novel_workflow

状态机：queued → running → waiting_approval → succeeded/failed/cancelled

### 5.5 Creative Hub（创作中枢）

统一创作入口，Thread 模型绑定资源，支持消息、中断、检查点、审批、生产状态看板。

### 5.6 伏笔账本（Payoff Ledger）

追踪伏笔的 setup/hint/payoff 全生命周期，含状态和压力提示，解决"挖坑不填"问题。

### 5.7 LLM 集成层

- **Structured Output 三级降级**: json_schema → json_object → prompt_json + LLM 修复器 + fallback 模型
- **模型路由**: 按任务类型分配不同 provider + model + temperature
- **Prompt Registry**: 统一的 Prompt 资产管理，版本化、元数据化

---

## 六、数据流与存储

### Prisma 数据模型

```
Novel (核心)
  ├── Chapter[] (章节)
  ├── Character[] (角色)
  │     ├── CharacterRelation[] (关系)
  │     ├── CharacterTimeline[] (时间线)
  │     └── CharacterState[] (状态快照)
  ├── NovelBible? (圣经)
  ├── VolumePlan[] (卷规划)
  ├── StoryMacroPlan? (宏观规划)
  ├── BookContract? (契约)
  ├── StoryStateSnapshot[] (故事状态快照)
  ├── OpenConflict[] (开放冲突)
  ├── PayoffLedgerItem[] (伏笔账本)
  ├── StoryPlan[] (故事计划)
  ├── AuditReport[] (审计报告)
  ├── CreativeDecision[] (创作决策)
  ├── NovelSnapshot[] (小说快照)
  ├── QualityReport[] (质量报告)
  └── AgentRun[] (Agent 运行记录)

World (世界观)
  ├── WorldDeepeningQuestion[] (深化问答)
  └── WorldConsistencyIssue[] (一致性检查)

KnowledgeDocument (知识文档)
  ├── KnowledgeDocumentVersion[] (版本)
  └── KnowledgeBinding[] (绑定)

CreativeHubThread (创作中枢线程)
  ├── 消息 + 中断 + 检查点
```

### SSE 流式推送

服务端事件类型：chunk / reasoning / done / error / ping / tool_call / tool_result / approval_required / approval_resolved / run_status / runtime_package

客户端 useSSE Hook 封装完整的 SSE 生命周期。

---

## 七、亮点与创新点

1. **AI-First 架构哲学**: 禁止用固定关键词匹配、硬编码正则路由等非 AI 方式实现核心行为
2. **完整的 Agent 运行时**: 幂等执行、审批断点续跑、Trace 全量记录、并发锁
3. **多层结构化输出保障**: 三级策略降级 + LLM 修复器 + fallback 模型
4. **写法引擎闭环**: 特征提取 → 编辑 → 编译 → 绑定 → 检测 → 修复
5. **伏笔账本**: 追踪长篇叙事中的 setup/payoff 状态，带压力提示
6. **Prompt Registry**: 统一 Prompt 资产管理，版本化、元数据化
7. **Creative Hub 统一入口**: 对话 + 工具调用 + 审批 + 状态卡片的一体化体验
8. **模型路由**: 按任务类型分配不同 provider + model + temperature

---

## 八、对 Fiction Academy 的启示

### 值得借鉴的设计

| 启示点 | 说明 |
|--------|------|
| Agent Runtime + Trace Store | 完整的运行时生命周期管理（创建/执行/审批/回放/诊断） |
| 幂等工具执行 | idempotencyKey + 结果缓存，应对 LLM 调用不稳定 |
| 审批断点续跑 | 序列化 continuation payload，审批后从断点恢复 |
| Structured Output 三级降级 | 多策略 + LLM 修复 + fallback，显著提高稳定性 |
| 写法引擎闭环 | 特征提取→编辑→编译→绑定→检测→修复，完整风格控制 |
| 伏笔账本 | 追踪长篇叙事 setup/payoff 状态，解决一致性问题 |
| Prompt Registry | 统一 Prompt 资产管理，避免散落在代码各处 |
| Creative Hub | 对话+工具调用+审批+状态卡片的一体化体验 |

### 架构差异与改进

| 维度 | 本项目 | Fiction Academy 方向 |
|------|--------|---------------------|
| 数据库 | SQLite（单机优先） | 多用户并发需要 PostgreSQL |
| 向量库 | Qdrant（可选） | 可评估更轻量方案 |
| AI 编排 | LangChain/LangGraph | 可评估是否需要重度依赖或自建轻量编排 |
| 前端编辑器 | Plate | 可评估 TipTap/ProseMirror |
| 目标用户 | 完全不懂写作的新手 | 可差异化定位，覆盖新手+进阶 |

### 核心壁垒

1. **整本生产主链**的完整度：从灵感到整本可写的端到端链路
2. **Agent 运行时**的成熟度：审批、断点续跑、回放、诊断形成闭环
3. **知识沉淀与回灌**：世界观 + 角色 + 拆书 + 知识库 + 写法资产的联合系统

Fiction Academy 建议优先建设 Agent Runtime 和 Tool Registry 两个基础设施，再逐步扩展域工具。
