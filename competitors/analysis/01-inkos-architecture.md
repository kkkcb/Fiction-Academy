# InkOS 技术架构深度分析

## 一、项目概览

| 项目 | 详情 |
|------|------|
| **名称** | InkOS |
| **GitHub** | https://github.com/Narcooo/inkos |
| **npm 包** | @actalk/inkos (CLI), @actalk/inkos-core (核心引擎) |
| **许可证** | AGPL-3.0-only |
| **定位** | 自主化小说写作 CLI AI Agent — 写、审、改，全程接管 |
| **版本** | v1.2.0 |
| **语言** | TypeScript 5.x (ESM), Node.js >= 20 |
| **Monorepo** | packages/core (引擎), packages/cli (命令行), packages/studio (Web UI) |

InkOS 是一个面向中文网络小说（玄幻、仙侠、都市等）的全自动 AI 写作系统，支持从建书到导出的完整生命周期。

---

## 二、技术栈

| 层次 | 技术 |
|------|------|
| **语言** | TypeScript 5.x (ESM modules) |
| **运行时** | Node.js >= 20（SQLite 需要 Node 22+） |
| **LLM 接入** | OpenAI SDK, Anthropic SDK, 兼容 OpenAI 格式的 custom provider |
| **数据校验** | Zod (schema validation for all structured output) |
| **配置/序列化** | YAML (js-yaml), JSON, Markdown |
| **持久存储** | 文件系统 (Markdown + JSON + SQLite 可选) |
| **构建** | tsc, pnpm workspace |
| **测试** | Vitest |
| **CLI 框架** | Commander.js |
| **Web UI** | Vite + React + Hono (Studio) |
| **TUI** | Ink + React (终端仪表盘) |
| **通知** | Telegram, 飞书, 企业微信, Webhook (HMAC-SHA256) |

### AI 模型策略

- **多模型路由**: 每个 Agent 可独立配置不同模型/Provider
- **温度控制**: 写作 0.7, 观察 0.5, 结算 0.3, 审计 0, 归一化 0.2
- **Thinking 模型兼容**: 自动强制 temperature=1
- **Stream 降级**: SSE 不支持时自动回退 sync

---

## 三、系统架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                     InkOS 完整章节写作管线                           │
│                                                                     │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐   │
│  │  Radar   │───>│ Planner  │───>│ Composer │───>│   Writer     │   │
│  │ (可选)   │    │ 规划意图 │    │ 编排上下文│    │  Phase 1:    │   │
│  └─────────┘    └──────────┘    └──────────┘    │  创意写作     │   │
│       │              │               │          │  (temp=0.7)  │   │
│       │         .intent.md    .context.json     └──────┬───────┘   │
│       │         .conflicts    .rule-stack.yaml         │           │
│       │                       .trace.json        ┌──────▼───────┐   │
│       │                                       │   Observer    │   │
│       │                                       │  Phase 2a:    │   │
│       │                                       │  过度提取事实  │   │
│       │                                       │  (temp=0.5)   │   │
│       │                                       └──────┬───────┘   │
│       │                                              │           │
│       │                                       ┌──────▼───────┐   │
│       │                                       │   Settler    │   │
│       │                                       │  Phase 2b:   │   │
│       │                                       │  JSON Delta  │   │
│       │                                       │  状态结算     │   │
│       │                                       │  (temp=0.3)  │   │
│       │                                       └──────┬───────┘   │
│       │                                              │           │
│       │              ┌───────────────────────────────┘           │
│       │        ┌─────▼──────┐     ┌──────────────┐              │
│       │        │  Normalizer│────>│   Auditor    │              │
│       │        │  字数归一化 │     │ 33维审计     │              │
│       │        └────────────┘     │ +AI痕迹检测  │              │
│       │                           └──────┬───────┘              │
│       │                    ┌─────────────┼─────────────┐        │
│       │              通过 │             │ 有问题       │        │
│       │              ┌────▼────┐  ┌──────▼──────┐     │        │
│       │              │  保存    │  │   Reviser   │     │        │
│       │              │ truth   │  │ 修订/spot-fix│─────┘        │
│       │              │ files   │  └─────────────┘  再审计       │
│       │              │ 快照    │                                  │
│       │              └─────────┘                                  │
│       │                    │                                      │
│       │              ┌─────▼──────┐                               │
│       │              │  State     │                               │
│       │              │  Validator │                               │
│       │              │  校验变更  │                               │
│       │              └────────────┘                               │
└─────────────────────────────────────────────────────────────────────┘
```

### 建书流程

```
inkos book create / inkos fanfic init / inkos import chapters
        │
        ▼
┌──────────────┐     ┌────────────────────┐     ┌───────────────┐
│  Architect   │────>│ Foundation Reviewer │────>│ 写入 truth    │
│ 生成基础设定  │     │ 5维评分 (>=80通过)  │     │ files + 快照  │
│ 5个section    │     │ 不通过则重新生成    │     │               │
└──────────────┘     └────────────────────┘     └───────────────┘
```

---

## 四、Agent / 工作流设计

### Agent 全览表

| Agent | 职责 | LLM 依赖 | 温度 |
|-------|------|----------|------|
| **ArchitectAgent** | 生成基础设定 (story_bible, volume_outline, book_rules, current_state, pending_hooks) | 是 | - |
| **FoundationReviewerAgent** | 审核基础设定质量，5维评分 (>=80通过) | 是 | 0 |
| **PlannerAgent** | 规划本章意图 (goal, mustKeep, mustAvoid, hook agenda) | 是 | - |
| **ComposerAgent** | 编排上下文 (context package + rule stack + trace) | 是 | - |
| **WriterAgent** | 三阶段写作: 创意写作(0.7) + 观察(0.5) + 结算(0.3) | 是 | 0.7/0.5/0.3 |
| **ContinuityAuditor** | 33+维度连续性审计 | 是 | 0 |
| **ReviserAgent** | 5种修订模式 (polish/rewrite/rework/anti-detect/spot-fix) | 是 | - |
| **StateValidatorAgent** | 校验 Settler 输出的一致性 | 是 | 0 |
| **LengthNormalizerAgent** | 单 pass 压缩/扩展到目标字数区间 | 是 | 0.2 |
| **RadarAgent** | 扫描番茄/起点平台排行榜，分析市场趋势 | 是 | - |
| **ConsolidatorAgent** | 卷级摘要压缩，管理长书上下文 | 是 | - |
| **StyleAnalyzer** | 统计文风指纹 (句长, TTR, 开头模式, 修辞) | **否** (纯计算) | - |
| **AITellsDetector** | 4维结构化AI痕迹检测 | **否** (纯规则) | - |
| **PostWriteValidator** | 11+条硬规则 + 跨章重复检测 + 段落漂移 | **否** (纯规则) | - |
| **DetectorAgent** | AIGC 检测 (GPTZero / Originality.ai) | **否** (外部API) | - |

### Agent 基类设计

BaseAgent 极简基类（仅100行），只提供 `chat()` 和 `chatWithSearch()` 两个核心方法。AgentContext 注入 LLMClient, model, projectRoot, bookId, logger, onStreamProgress。

### 编排方式

**Pipeline 编排模式**，核心编排器是 PipelineRunner（~2950行）：

1. **PipelineRunner.writeNextChapter()** — 完整管线: Plan → Compose → Write → Normalize → Audit → Revise → Validate → Persist → Snapshot
2. **PipelineRunner.writeDraft()** — 只写草稿
3. **PipelineRunner.auditDraft()** — 只审计
4. **PipelineRunner.reviseDraft()** — 只修订
5. **Scheduler** — 守护进程模式，cron 驱动的自动写章循环

另有 **Agent Loop 模式**：LLM 通过 tool-use 自主编排 18 个工具的调用顺序。

---

## 五、核心功能模块

### 5.1 Truth Files（真相文件系统）

InkOS 的核心创新 — 7+ 个 Markdown 文件作为"唯一事实来源"：

| 文件 | 用途 | 更新频率 |
|------|------|----------|
| `story_bible.md` | 世界观设定 | 建书时 |
| `volume_outline.md` | 卷纲规划 | 建书时 |
| `book_rules.md` | 书级规则 | 建书时 + 可编辑 |
| `current_state.md` | 当前世界状态 | 每章 |
| `particle_ledger.md` | 资源账本 | 每章 |
| `pending_hooks.md` | 伏笔池 | 每章 |
| `chapter_summaries.md` | 章节摘要 | 每章 |
| `subplot_board.md` | 支线进度板 | 每章 |
| `emotional_arcs.md` | 情感弧线 | 每章 |
| `character_matrix.md` | 角色交互矩阵 | 每章 |

**双重存储**: v0.6.0 起真相文件权威来源从 Markdown 迁移到 `story/state/*.json`（Zod schema 校验）。Settler 输出 JSON delta，由代码层做 immutable apply + 结构校验后写入。Markdown 保留为人类可读投影。

### 5.2 33+ 维度审计系统

37 个审计维度（ID 1-37），按题材条件启用：

| 维度范围 | 类别 | 示例 |
|----------|------|------|
| 1-10 | 核心连续性 | 角色记忆、位置连续性、物资追踪、时间线 |
| 11-19 | 叙事质量 | 情感弧线、伏笔推进、大纲偏离、节奏 |
| 20-26 | 题材特定 | 数值系统 (玄幻/仙侠)、时代研究 (都市) |
| 27-31 | 结构检测 | AI痕迹 (词汇疲劳、句式单调、过度总结) |
| 32-33 | 全局 | 读者期望、大纲漂移 |
| 34-37 | 同人专用 | 角色忠实度、世界合规、正典一致性 |

### 5.3 Planner-Composer-Writer Pipeline

v2 输入治理模式：

**Phase 1: Planner** — 读取 8 个源文件，输出 ChapterIntent (goal, mustKeep, mustAvoid, hook agenda, hook budget)

**Phase 2: Composer** — 从全量真相文件中按相关性选择上下文，编译 ContextPackage + RuleStack + ChapterTrace

**Phase 3: Writer** — 基于 Composer 产出的精简上下文生成正文

关键: `plan` 和 `compose` **不需要 LLM 调用**。

### 5.4 Observer-Settler 模式

Writer Agent 内部两阶段状态提取：

**Observer (Phase 2a)**: 从正文中"过度提取"9 类事实（Characters, Locations, Resources, Relationships, Emotions, Information flow, Plot threads, Time, Physical state）

**Settler (Phase 2b)**: 将观察结果合并到真相文件，输出 Runtime State Delta (JSON)。Delta 经 `applyRuntimeStateDelta` 做 immutable 更新 + `validateRuntimeState` Zod 校验后才写入。

### 5.5 去AI味系统

三层防护：

1. **Prompt 层**: 词汇疲劳词表、禁用句式、文风指纹注入
2. **规则层** (~850行): 11+条中文硬规则 — 禁用"不是...而是..."句式、破折号禁用、惊叹号密度控制、疲劳词检测、元叙事检测等
3. **结构层** (~160行): 4维结构化检测 — 段落均匀度、模糊词密度、公式化过渡、列表式结构

### 5.6 Genre Profile（题材配置系统）

每个题材是一个 Markdown 文件（YAML frontmatter + Markdown 规则），支持 15 个内置题材。

### 5.7 其他核心功能

- **字数治理**: soft range / hard range, 最多一次归一化纠偏
- **文风仿写**: style analyze 提取统计指纹 + LLM 定性分析
- **续写/导入**: 从已有小说逆向工程全部真相文件
- **同人创作**: 4种模式 (canon/AU/OOC/CP), 正典导入器
- **市场雷达**: 扫描番茄/起点排行榜
- **守护进程**: cron 驱动, 质量门控
- **快照/回滚**: 每章自动创建状态快照
- **SQLite 时序记忆**: Node 22+ 自动启用

---

## 六、数据流与存储

### 存储结构

```
project-root/
├── .env                          # LLM 配置
├── inkos.json                    # 项目配置
├── books/
│   └── {book-id}/
│       ├── book.json             # BookConfig
│       ├── chapters/
│       │   └── 0001_第一章.md    # 章节正文
│       ├── story/
│       │   ├── story_bible.md    # 世界观设定
│       │   ├── volume_outline.md # 卷纲
│       │   ├── book_rules.md     # 书级规则
│       │   ├── current_state.md  # 当前世界状态
│       │   ├── pending_hooks.md  # 伏笔池
│       │   ├── chapter_summaries.md # 章节摘要
│       │   ├── state/            # Zod-validated JSON state
│       │   ├── snapshots/        # 状态快照 (每章一个)
│       │   ├── memory.db         # SQLite 时序记忆
│       │   └── runtime/          # 运行时产物
│       └── chapter-index.json    # 章节索引
├── genres/                       # 自定义题材
└── skills/SKILL.md              # OpenClaw Skill 定义
```

### 数据流

```
External Context → Planner: 8个源文件 → ChapterIntent (Zod validated)
  → Composer: intent + truth files → ContextPackage + RuleStack + Trace
  → Writer Phase 1: context + rules → 章节正文
  → Writer Phase 2a (Observer): 正文 → 9类事实提取
  → Writer Phase 2b (Settler): 事实 → Runtime State Delta (JSON)
  → applyRuntimeStateDelta (immutable) → validateRuntimeState (Zod)
  → Post-write validator: 规则检查
  → Length normalizer (如需)
  → Auditor: 33维审计 + AI痕迹 + 敏感词
  → Reviser (如不通过): spot-fix patches → 再审计
  → State Validator: 新旧 truth files 对比 → PASS/FAIL
  → Persist: 章节文件 + truth files (md+json) + index + snapshot + memory.db
```

---

## 七、亮点与创新点

1. **Truth Files 多文件专职化**: 不是简单的"记忆"或"摘要"，而是 7+ 个专职化的 Markdown 文件 + Zod-validated JSON。Settler 输出 delta 而非全量重写，immutable apply 确保数据一致性
2. **Planner-Composer 分离的输入治理**: 将"写什么"和"用什么写"分离，`plan`/`compose` 不需要 LLM
3. **Observer-Settler 两阶段状态提取**: "宽松提取、严格合并"模式比一次性让 LLM 输出完整 truth file 更可靠
4. **三层去AI味体系**: Prompt 层预防 + 规则层硬检测（零 LLM 成本）+ 结构层模式检测
5. **Genre Profile 可扩展**: 题材知识是可插拔的配置文件
6. **State Validator 守门人**: LLM 输出的状态变更必须经过独立校验才能持久化，"宁可暂停不可坏数据"
7. **极简 Agent 基类**: BaseAgent 仅 100 行，chat() + chatWithSearch()，业务逻辑完全内聚
8. **多入口统一内核**: TUI、Studio Web UI、interact JSON、OpenClaw Skill 共用同一套运行时

---

## 八、对 Fiction Academy 的启示

### 值得借鉴的设计

| 设计 | 启示 |
|------|------|
| Truth Files 多文件专职化 | 不要把所有状态塞进一个"记忆"对象，拆分为角色矩阵、资源账本、伏笔池等专职文件 |
| Runtime State Delta (JSON) | 状态更新用 delta 而非全量重写，配合 Zod 校验 |
| Planner-Composer-Writer 三阶段 | 将意图规划、上下文选择、创意写作分离 |
| 规则优先的去AI味 | 能用正则和统计解决的不调 LLM，零 token 成本 |
| State Validator 守门人 | LLM 输出的状态变更必须独立校验才能持久化 |
| Genre Profile 可扩展 | 题材知识应该是可插拔的配置文件 |
| 快照+回滚 | 每章一个状态快照，rewrite 时可安全回滚 |
| 多模型路由 | 不同 Agent 用不同模型，平衡质量与成本 |

### InkOS 的局限性（Fiction Academy 可改进的方向）

| 局限 | 改进方向 |
|------|----------|
| Pipeline 硬编码 | PipelineRunner 近 3000 行，流程写死。可考虑更灵活的 DAG/工作流编排 |
| 单语言强绑定 | 核心提示词有大量中文硬编码。可抽象为 i18n 模板 |
| 无数据库 | 所有持久化基于文件系统。大规模使用时需要真正的数据库 |
| Agent 无插件 | 没有 Agent 插件系统。可设计 Agent 注册机制 |
| 缺少用户画像 | 没有读者反馈回路。可从平台数据构建读者画像，反向指导写作 |

### 架构建议

1. **事件驱动 + Pipeline 混合模式**: 保留 Pipeline 的确定性，关键节点引入事件机制
2. **Graph-based Agent 编排**: 用 DAG 定义 Agent 依赖关系，支持条件分支和并行执行
3. **版本化 Truth Files**: Truth Files 应该有版本历史和 diff 能力
4. **分层 LLM 策略**: 自动根据任务复杂度选择模型
5. **实时协作 API**: 提供 WebSocket/gRPC 接口，支持前端实时展示写作进度
6. **插件化 Genre System**: Genre 不只是配置文件，而是可注册自定义 Agent 和 Validator 的插件
