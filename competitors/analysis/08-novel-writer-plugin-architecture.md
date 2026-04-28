# novel-writer-plugin (Claude Code Plugin) 技术架构分析

## 一、项目概述

### 1.1 项目定位

novel-writer-plugin（cc-novel-writer）是一个基于 **Claude Code 原生插件体系** 的中文网文多 Agent 协作创作系统，当前版本 **v3.1.0**，经过 10 个里程碑（M1-M10）的迭代。其核心创新在于将 **Spec-Driven（规范驱动）** 思想系统性引入小说创作，通过四层契约体系实现可度量、可验证、可追溯的质量管理。

### 1.2 核心目标

- **全流程自动化**：世界观构建 → 卷级规划 → 章节续写 → 质量验收
- **去 AI 化输出**：四层反 AI 检测策略，使生成文本接近人类写作
- **Spec-Driven 规范**：四层契约体系（L1 世界规则 / L2 角色契约 / L3 章节契约 / LS 故事线）
- **长篇可持续**：500+ 章创作连贯性保证（摘要替代全文、滑窗校验、伏笔生命周期）
- **多平台适配**：番茄小说/起点中文网/晋江文学城差异化标准

### 1.3 用户交互模型

| 命令 | 用途 |
|------|------|
| `/novel:start` | 冷启动新项目（含 50 分钟 Quick Start 黄金三章） |
| `/novel:continue [N]` | 续写 1-5 章（含中断恢复） |
| `/novel:dashboard` | 只读项目状态仪表盘 |

---

## 二、技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| **宿主平台** | Claude Code CLI | Anthropic 的 AI 编程助手 |
| **插件体系** | `.claude-plugin/` | 原生插件格式（plugin.json + skills/ + agents/） |
| **辅助脚本** | Python 3.10+（stdlib-only） | 零第三方依赖 |
| **CI** | GitHub Actions | Markdown lint + 链接检查 + Manifest 校验 |

### 2.1 AI 模型配置

| 用途 | 模型 | 说明 |
|------|------|------|
| 章节初稿 | gemini-3-flash-preview | 通过第三方 API 绕过工程向系统提示 |
| ChapterWriter | Claude Opus | 核心创作 Agent |
| StyleRefiner | Claude Sonnet | 成本优化（机械性去 AI 任务） |
| Summarizer/QualityJudge/ContentCritic | Opus / Codex | 双后端可选，默认 Codex |
| PlotArchitect/WorldBuilder | Claude Opus | 规划类 Agent |

### 2.2 关键设计特点

- **无传统 Web 框架**：Claude Code 原生插件，Markdown 定义的 Skills 和 Agents
- **Manifest Mode v2**：Agent 间通过文件路径引用传递上下文，非完整内容注入
- **零第三方 Python 依赖**：所有辅助脚本仅用标准库

---

## 三、系统架构

### 3.1 五层架构

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: 用户交互层                                     │
│  /novel:start | /novel:continue | /novel:dashboard      │
├─────────────────────────────────────────────────────────┤
│  Layer 2: 编排层（Orchestrator）                          │
│  状态机(7 states) + Context Assembly + Gate Decision     │
│  + Checkpoint Recovery + Concurrency Control            │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Agent 执行层                                   │
│  ChapterWriter | StyleRefiner | Summarizer              │
│  QualityJudge | ContentCritic | PlotArchitect | WorldBuilder │
├─────────────────────────────────────────────────────────┤
│  Layer 4: 辅助脚本层                                     │
│  api-writer.py | codex-eval.py | lint-*.sh | calibrate  │
├─────────────────────────────────────────────────────────┤
│  Layer 5: 存储与基础设施层                                │
│  Staging 事务模型 | Spec 四层规范 | 评估管线 | CI/CD     │
└─────────────────────────────────────────────────────────┘
```

### 3.2 核心目录结构

```
novel-writer-plugin/
  .claude-plugin/plugin.json        — 插件元数据
  CLAUDE.md                         — 架构约定总纲
  agents/                           — 7 个 Agent 定义（Markdown + YAML frontmatter）
  skills/                           — 4 个 Skill（3 用户入口 + 1 知识库）
  prompts/                          — Codex 后端专用提示词（4 个）
  scripts/                          — Python/Shell 辅助脚本（20+）
  templates/                        — 模板文件
  hooks/hooks.json                  — Claude Code Hooks（5 类安全 Hook）
  eval/                             — 评估基础设施
```

---

## 四、Agent 设计

### 4.1 7 个专业化 Agent

| Agent | 模型 | 职责 | 写入权限 |
|-------|------|------|---------|
| **WorldBuilder** | Opus | 世界观 + L1 硬规则 + 角色 L2 契约 + 风格提取（8 种模式） | staging |
| **PlotArchitect** | Opus | 卷级大纲 + L3 章节契约 + 故事线调度 + 伏笔计划 | staging |
| **ChapterWriter** | Opus | 2500-3500 字章节续写，"有态度的说书人"人设 | staging |
| **StyleRefiner** | Sonnet | 机械性去 AI 后处理（黑名单扫描 + 标点修正 + AI 模式替换） | staging |
| **Summarizer** | Opus/Codex | 300 字摘要 + 状态增量 ops + 串线检测 + canon_hints | staging |
| **QualityJudge** | Opus/Codex | Track 1 合规检查 + Track 2 九维度评分 | evaluations |
| **ContentCritic** | Opus/Codex | Track 3 读者参与度 + Track 4 内容实质 + Track 5 POV 边界 | evaluations |

**Color 约束**：同色 Agent 不可并发（ChapterWriter + StyleRefiner = green → 串行）

### 4.2 WorldBuilder 的 8 种运行模式

| Mode | 触发场景 | 输出 |
|------|---------|------|
| `world_init_light` | Quick Start | ≤3 条 L1 硬规则 + 精简叙述 |
| `world_init_full` | 正式卷规划 | 完整 L1 规则集 + 世界观文档 |
| `world_update` | 规则变更 | 增量规则更新 |
| `character_create` | 新角色出场 | .md 档案 + .json L2 契约 |
| `character_update` | 角色状态变更 | 契约更新 |
| `character_retire` | 角色退场 | 三重退休保护检查 + 归档 |
| `style_extract` | 风格提取 | style-profile.json + style-samples.md |
| `style_drift` | 每 5 章 | 风格漂移检测 + style-drift.json |

### 4.3 Agent 协作模型

Task 派发 + Manifest 传递：
1. 编排器（Skill）使用 `Task` 工具派发 Agent
2. 编排器组装 Context Manifest（文件路径 + 内联计算值）
3. Agent 通过 `Read` 工具按需加载 Manifest 引用的文件
4. Agent 输出写入 `staging/` 目录，编排器统一 commit

---

## 五、核心工作流程

### 5.1 状态机（7 状态）

```
INIT → QUICK_START → VOL_PLANNING → WRITING ⟲ → VOL_REVIEW → VOL_PLANNING ...
                                     ↑         │
                                     └── ERROR_RETRY
```

### 5.2 单章续写流水线（核心路径）

```
Step 1: 并发锁获取 + Checkpoint 恢复
  ↓
Step 2: Context Assembly（确定性 7 步）
  2.0 大纲提取 → 2.1 L1 规则预过滤 → 2.2 L2 角色裁剪
  → 2.3 L3 契约 → 2.4 摘要窗口 → 2.5 故事线记忆
  → 2.6 附加注入 → 2.7 Manifest 组装
  ↓
Step 3: Agent Pipeline
  3.1 API Writer（初稿）→ 降级 ChapterWriter
  3.2 StyleRefiner（去 AI）
  3.3 Summarizer（摘要 + 状态增量）
  3.4 [QualityJudge ∥ ContentCritic]（并行评估）
  3.5 Gate Decision（多信号门控）
  3.6 Commit（staging → 正式目录）
  ↓
Step 4: 周期性维护
  每 5 章：滑窗一致性 + 风格漂移 + 人性化技法干旱检测
  每 10 章：伏笔盘点 + 故事线节奏分析
  卷末：自动全卷核查
```

### 5.3 Context Assembly（确定性上下文组装）

7 步确定性规则确保 context 注入可重现：

| Step | 操作 | 说明 |
|------|------|------|
| 2.0 | 大纲提取 | 正则 `^### 第 {C} 章` 提取本章区块 |
| 2.1 | L1 规则预过滤 | 按 canon_status 分为 established/planned |
| 2.2 | L2 角色裁剪 | 契约角色全注入，其余取 top-15 |
| 2.3 | L3 契约加载 | Markdown 优先，JSON 回退 |
| 2.4 | 摘要窗口 | 前 2 章完整 + 最近 8 章精简 |
| 2.5 | 故事线记忆 | 过滤休眠线 |
| 2.6 | 附加注入 | 风格漂移/黑名单/伏笔/NER 实体 |

**Context 预算**：ChapterWriter ~19-24K tokens（普通章），~24-30K（交汇章）。第 500 章时仍保持稳定。

### 5.4 Gate Decision（多信号门控合并）

```
Step A: QJ 基础判定 → pass/polish/revise/review/rewrite
Step B: CC 内容实质硬门 → 任一维度 < 3.0 无条件强制 revise
Step C: CC 读者参与度叠加 → 仅降级，不升级
Step D: 最终合并 → max severity wins
```

### 5.5 修订回环

**Targeted 修订**（~35-45K tokens）：
```
CW(targeted, failed_dimensions) → SR(lite) → [Sum ∥ QJ ∥ CC]
```
最多 1 轮 → direct-fix + force_passed

**Full 修订**（~90K tokens）：
```
完整流水线重跑
```
最多 2 轮 → force_passed 或 pause_for_user

---

## 六、存储方案

### 6.1 项目目录结构

```
{novel_project}/
  .checkpoint.json              — 状态持久化（状态机 + pipeline 阶段）
  .novel.lock                   — 文件级并发锁（30min 僵尸检测）
  brief.md                      — 创作纲领
  style-profile.json            — 风格指纹（7 维可量化特征）
  style-samples.md              — 风格样本（7 场景类型）
  ai-blacklist.json             — AI 黑名单（~120 词，13 分类）
  style-drift.json              — 风格漂移状态
  world/rules.json              — L1 世界规则
  characters/active/            — 活跃角色档案 + L2 契约
  storylines/                   — 故事线定义 + 记忆
  foreshadowing/global.json     — 全局伏笔索引（事实层）
  volumes/vol-XX/               — 卷大纲 + L3 契约 + 伏笔计划
  chapters/chapter-XXX.md       — 章节正文
  summaries/                    — 章节摘要（≤300 字）
  evaluations/                  — 最终评估（QJ + CC 合并）
  state/                        — 全局状态 + 状态增量 + 串线检测
  staging/                      — 临时写入目录（Agent 输出中间产物）
```

### 6.2 Staging 事务模型

- 所有 Agent 输出先写入 `staging/`，编排器统一原子 commit
- PreToolUse Hook 强制限制写入仅限 staging
- 中断时 staging 可安全丢弃

### 6.3 Spec-Driven 四层规范

| 层级 | 文件 | 可变性 | 类比 |
|------|------|--------|------|
| **L1** | world/rules.json | 不可违反 | 类型系统 |
| **L2** | characters/active/*.json | 可变更需协议 | 接口定义 |
| **L3** | volumes/vol-*/chapter-contracts/*.md | 消耗型（逐章验收） | 单元测试 |
| **LS** | storylines/storyline-spec.json | 卷级作用域 | 并发安全规则 |

### 6.4 伏笔双层数据模型

- **global.json（事实层）**：Summarizer ops 驱动，记录实际状态变更
- **vol-XX/foreshadowing.json（计划层）**：PlotArchitect 生成，记录规划目标
- 状态单调递进：`planted` → `advanced` → `resolved`
- 范围语义：short（3-10 章）/ medium（跨卷）/ long（全书级）

---

## 七、亮点与创新

### 7.1 Spec-Driven Writing（规范驱动创作）

借鉴软件工程 TDD/BDD 思想，将小说创作规范化为四层契约：
- L1 = 硬约束（类型系统）
- L2 = 行为契约（接口定义）
- L3 = 验收标准（单元测试）
- LS = 并发安全（故事线规则）

验收四轨制：合规检查 = 编译通过 → 质量评分 = Code Review → 内容实质 = Regression Test → 读者参与度 = User Testing

### 7.2 去 AI 化四层策略

| 层 | 策略 | 创新点 |
|----|------|--------|
| L1 | 风格锚定 | 7 维可量化指纹，4 种来源 |
| L2 | 约束注入 | ChapterWriter 不看黑名单（隔离设计），靠内隐参照 |
| L3 | 后处理 | Sonnet 做机械任务，成本优化 5-10x |
| L4 | 检测度量 | 10 项量化指标 + 3 区范围判定 |

**语域微注入**：同一段落内刻意制造语域跳变（正式→粗口、文言→白话），连续同调超过 800 字即视为问题。

**人性化技法工具箱**：12 种随机采样技法，连续 5 章零技法触发 `humanize_drought` 警告。

### 7.3 Manifest Mode v2

- 编排器仅传递文件路径 + 少量内联值
- Agent 通过 Read 工具按需加载
- 配合摘要替代全文 + 角色裁剪 + 休眠线过滤
- **第 500 章 context 仍 ~20K tokens**

### 7.4 Staging 事务模型

借鉴数据库 ACID：Atomicity（原子 commit）+ Consistency（Hook 强制 staging）+ Isolation（文件锁 + 僵尸检测）+ Durability（Checkpoint 持久化 + pipeline_stage 粒度恢复）

### 7.5 多信号门控合并

四步门控：QJ 基础 → CC 实质硬门 → CC 参与度叠加 → max severity 合并。分层修订：targeted（~40K）vs full（~90K）。

### 7.6 双后端评估管线

Opus 路径 + Codex 路径（codex-eval.py），Pearson 相关系数校准，阈值决策（r ≥ 0.85 + |bias| < 0.3 → 保持）。

### 7.7 平台差异化适配

| 平台 | 读者类型 | 核心要求 |
|------|---------|---------|
| 番茄小说 | 碎片阅读者 | 200 字主角登场 + 章末钩子 |
| 起点中文网 | 付费追更者 | 力量体系暗示 + immersion ≥ 3.5 |
| 晋江文学城 | 情感投入者 | 行为展现人设 + style_naturalness ≥ 3.5 |

### 7.8 完整评估基础设施

- 人工标注数据集（30 章 JSONL）
- 6 个 JSON Schema 校验
- Pearson 相关系数校准工具
- 回归运行 + 对比工具
- Quality Aggregation（按卷评分趋势 + 低分预警）

---

## 八、局限性与改进空间

### 8.1 局限性

| 局限 | 说明 |
|------|------|
| **Claude Code 绑定** | 强依赖 Claude Code CLI，无法独立运行 |
| **成本较高** | 核心创作使用 Claude Opus，单章成本较高 |
| **学习曲线陡** | Spec-Driven 四层契约体系对普通用户门槛高 |
| **Markdown 即代码** | Agent 和 Skill 用 Markdown 定义，维护成本高 |
| **无 Web UI** | 仅 CLI 交互，无可视化界面 |

### 8.2 对 Fiction Academy 的启示

1. **Spec-Driven 是最佳实践**：四层契约体系是本项目中最重要的架构创新，Fiction Academy 应直接采用
2. **去 AI 化方法论最完整**：四层策略 + 语域微注入 + 统计反制是目前最系统的去 AI 方案
3. **Manifest Mode 解决上下文爆炸**：路径引用 + 摘要 + 裁剪的方案可确保长篇可持续
4. **Staging 事务模型**：数据库式的事务管理确保了创作过程的安全性
5. **多信号门控**：QJ + CC 并行评估 + 分层修订的方案成熟可靠
6. **伏笔生命周期管理**：双层模型（事实层 + 计划层）+ 状态单调递进是长篇创作的必备能力
7. **需要增强**：平台解耦（不绑定 Claude Code）、Web UI、降低使用门槛
