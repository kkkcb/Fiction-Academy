# 竞品架构横向对比总结

> 对 Fiction Academy（多 Agent 中文网文创作生态系统）的架构设计参考

---

## 一、八大项目概览

| # | 项目 | 定位 | 语言 | 编排框架 | Agent 数 | 核心创新 |
|---|------|------|------|---------|---------|---------|
| 01 | **inkos** | 规范驱动长篇创作 | TypeScript | 自研 Planner-Composer-Writer | 5+ | Truth Files + Observer-Settler + 33 维审计 |
| 02 | **AI-Novel-Writing-Assistant** | LangGraph Agent 运行时 | TypeScript | LangGraph | 12 | Idempotent 执行 + Structured Output 3 级降级 |
| 03 | **ai-book-writer** | CrewAI 管线 + SSE 流式 | Python | CrewAI | 5 | LiteLLM 统一路由 + K8s 部署 |
| 04 | **NovelGenerator** | Slot-Based 多 Agent | TypeScript | 自研 AgentCoordinator | 3 | [SLOT] 标记解耦 + 6 策略容错解析器 |
| 05 | **novel-forge** | pydantic-graph 图工作流 | Python | pydantic-graph | 21 | 40+ 节点 DAG + 版本控制 + 收敛检测 |
| 06 | **webnovel-writer** | Claude Code 插件 + 双 Agent | TypeScript | Claude Code 原生 | 2+ | 追读力评分 + 爽点引擎 + SQLite RAG |
| 07 | **AI-automatically-generates-novels** | 提示词驱动生产力工具 | Python + JS | 无（单次 API） | 0 | 三层提示词 + 右键菜单 + AI 迭代 |
| 08 | **novel-writer-plugin** | Claude Code 插件 + Spec-Driven | Python + Shell | Claude Code 原生 | 7 | Spec-Driven 四层契约 + 去 AI 四层策略 |

---

## 二、编排框架对比

| 维度 | LangGraph | CrewAI | pydantic-graph | Claude Code | 自研 |
|------|-----------|--------|---------------|-------------|------|
| **项目** | 02 | 03 | 05 | 06, 08 | 01, 04 |
| **图可视化** | ✅ | ❌ | ✅ | ❌ | ❌ |
| **条件分支** | ✅ | ✅ | ✅ | ✅（状态机） | ✅ |
| **并行执行** | ✅ | ❌（线性） | ✅ | ✅（Color 约束） | ✅ |
| **检查点/恢复** | ✅ | ❌ | ✅（6 阶段） | ✅（pipeline_stage） | 部分 |
| **状态管理** | 内置 State | 自动传递 | BookGenerationState | 文件系统 | 自定义 |
| **适合场景** | 复杂 Agent 图 | 简单线性管线 | 复杂 DAG | CLI 插件 | 轻量定制 |

**Fiction Academy 推荐**：**LangGraph**（已在 PRD 中选定），兼具图可视化、条件分支、并行执行、检查点恢复，且 TypeScript 生态与 React 前端契合。

---

## 三、Agent 设计模式对比

### 3.1 Agent 分工策略

| 模式 | 项目 | 优点 | 缺点 |
|------|------|------|------|
| **极致分工**（21 Agent） | novel-forge | 每个 Agent 高度聚焦 | 维护成本高，可能过度设计 |
| **角色分工**（5-7 Agent） | 06, 08, 02 | 平衡聚焦与复杂度 | 需要精心设计边界 |
| **Slot 解耦**（3 Agent） | NovelGenerator | 维度正交，无重叠 | 仅覆盖单章生成 |
| **线性管线**（5 Agent） | ai-book-writer | 简单可靠 | 缺乏灵活性 |
| **无 Agent**（0 Agent） | 07 | 最低门槛 | 无协作优化 |

**Fiction Academy 推荐**：**角色分工模式（5-7 Agent）**，参考 08 的 Writer/Reviewer/Advisor 分层，每个角色内可含子 Agent。

### 3.2 Agent 协作模式

| 模式 | 项目 | 数据传递 | 并行能力 |
|------|------|---------|---------|
| **Task 派发 + Manifest** | 08 | 文件路径引用 | Color 约束控制 |
| **LangGraph 图节点** | 02 | State 共享 | 原生并行 |
| **CrewAI 线性传递** | 03 | 上下文传递 | 不支持 |
| **pydantic-graph Edge** | 05 | BookGenerationState | 原生并行 |
| **Slot 标记链** | 04 | 文本标记 | 顺序执行 |

**Fiction Academy 推荐**：**LangGraph State + 条件边**，既有共享状态又有灵活的路由控制。

---

## 四、核心能力对比

### 4.1 去 AI 化能力

| 项目 | 策略 | 成熟度 |
|------|------|--------|
| **novel-writer-plugin (08)** | 四层策略：风格锚定 + 约束注入（隔离设计） + Sonnet 后处理 + 10 项量化检测 | ⭐⭐⭐⭐⭐ |
| **webnovel-writer (06)** | 三定律 + 统计反制 + 语域微注入 | ⭐⭐⭐⭐ |
| **NovelGenerator (04)** | 5 个内容修正函数（Phase 4） | ⭐⭐⭐ |
| **inkos (01)** | 3 层去 AI 系统 | ⭐⭐⭐ |
| **其他** | 提示词中要求"避免 AI 味" | ⭐ |

**Fiction Academy 应采纳**：08 的四层策略 + 06 的语域微注入 + 04 的内容修正函数库。

### 4.2 长篇连贯性管理

| 项目 | 策略 | 可支撑章节数 |
|------|------|------------|
| **novel-writer-plugin (08)** | Manifest Mode v2 + 摘要替代全文 + 角色裁剪 + 滑窗校验 + 伏笔生命周期 | 500+ 章 |
| **inkos (01)** | Truth Files + 7+ 专职化文件 + Observer-Settler | 200+ 章 |
| **webnovel-writer (06)** | Context Contract v2 + SQLite RAG + BM25 + Graph-Hybrid | 200+ 章 |
| **AI-Novel-Writing-Assistant (02)** | Story Context DB + Payoff Ledger | 100+ 章 |
| **其他** | 无专门机制 | < 50 章 |

**Fiction Academy 应采纳**：08 的 Manifest Mode + 01 的 Truth Files + 06 的 Context Contract。

### 4.3 质量评估体系

| 项目 | 评估维度 | 校准机制 |
|------|---------|---------|
| **novel-writer-plugin (08)** | 9 维度评分 + 4 Track 验收 + 平台加权 | Pearson 相关系数 + 人工标注数据集 |
| **webnovel-writer (06)** | 追读力 5 维评分 + 6 维并行审查 + 爽点识别 | — |
| **novel-forge (05)** | 5 并行审校子流 + ReviewAggregator + 质量指标 | 收敛检测 |
| **inkos (01)** | 33 维审计 | — |
| **AI-automatically-generates-novels (07)** | AI 自评分（100 分制） | — |

**Fiction Academy 应采纳**：08 的多 Track 验收 + 06 的追读力评分 + 08 的 Pearson 校准。

### 4.4 上下文管理

| 项目 | Context 预算 | 第 500 章稳定性 | 策略 |
|------|-------------|----------------|------|
| **novel-writer-plugin (08)** | ~19-24K tokens | ✅ 稳定 | Manifest 路径引用 + 摘要 + 裁剪 |
| **webnovel-writer (06)** | 动态 token 预算 | ✅ 稳定 | Priority-ordered + freshness/frequency |
| **inkos (01)** | 中等 | ⚠️ 需 Truth Files | Observer-Settler 精确提取 |
| **AI-Novel-Writing-Assistant (02)** | 模型窗口 | ⚠️ 依赖窗口大小 | Story Context DB |
| **其他** | 无管理 | ❌ 不支持 | — |

**Fiction Academy 应采纳**：08 的 Manifest Mode + 06 的动态 token 预算。

---

## 五、架构分层模式对比

| 层级 | 08 (最成熟) | 02 (参考) | 05 (参考) | Fiction Academy 建议 |
|------|------------|-----------|-----------|-------------------|
| **用户交互层** | Skills (3 入口) | React UI | 无 | Next.js/React Web UI |
| **编排层** | 状态机 + Context Assembly | LangGraph Runtime | pydantic-graph DAG | **LangGraph** 图工作流 |
| **Agent 层** | 7 专业 Agent | 12 Agent | 21 Agent | 4 角色集群（~12-16 Agent） |
| **规范层** | L1/L2/L3/LS 四层契约 | Structured Output | 无 | **四层契约体系** |
| **存储层** | Staging 事务 + 文件系统 | 数据库 | 内存状态 | SQLite + 文件系统 + Staging |
| **评估层** | QJ + CC + Codex 校准 | 无专门评估 | 5 并行审校 | Reviewer Agent + 校准管线 |

---

## 六、关键创新点排名

### 6.1 最值得借鉴的 Top 10 设计决策

| 排名 | 创新点 | 来源项目 | 价值 |
|------|--------|---------|------|
| 1 | **Spec-Driven 四层契约** | 08 | 将小说质量从"直觉"提升为"可度量工程" |
| 2 | **Manifest Mode v2（路径引用）** | 08 | 解决长篇上下文爆炸，500+ 章仍稳定 |
| 3 | **去 AI 四层策略 + 隔离设计** | 08 | 最完整的去 AI 化方法论 |
| 4 | **Truth Files + Observer-Settler** | 01 | 精确的状态提取与事实管理 |
| 5 | **追读力评分 + 爽点引擎** | 06 | 网文特有质量度量 |
| 6 | **Staging 事务模型** | 08 | 数据库级安全保证 |
| 7 | **多信号门控合并** | 08 | 多维质量信号精确融合 |
| 8 | **Slot-Based 解耦生成** | 04 | 结构/角色/场景维度解耦 |
| 9 | **收敛检测 + 反馈上限** | 05 | 防止无限循环修订 |
| 10 | **Context Contract v2（动态预算）** | 06 | 自适应 token 分配 |

### 6.2 各项目独特贡献

| 项目 | 独特贡献 | Fiction Academy 可直接复用 |
|------|---------|------------------------|
| **inkos (01)** | Truth Files 概念、Observer-Settler 两阶段提取、33 维审计 | Truth Files → 世界观/角色/情节状态管理 |
| **AI-Novel-Writing-Assistant (02)** | LangGraph + React 全栈架构、Idempotent 工具执行、Style Engine | 整体架构参考 |
| **ai-book-writer (03)** | LiteLLM 多模型路由、SSE 代理模式、K8s 部署 | LiteLLM → 模型路由层 |
| **NovelGenerator (04)** | [SLOT] 标记系统、6 策略容错解析器、5 个内容修正函数 | 内容修正函数库 |
| **novel-forge (05)** | 版本控制系统、收敛检测、冻结标志、市场分析前置 | 版本控制 + 冻结标志 |
| **webnovel-writer (06)** | 追读力评分、爽点识别引擎、Context Contract、SQLite RAG | 追读力 + 爽点引擎 |
| **AI-auto-novels (07)** | 三层提示词体系、右键菜单交互、双通道成本优化 | 提示词模板 + 右键交互 |
| **novel-writer-plugin (08)** | 几乎所有核心创新 | 全面借鉴 |

---

## 七、Fiction Academy 架构决策建议

### 7.1 编排框架：LangGraph ✅（已确认）

理由：
- 图可视化 + 条件分支 + 并行执行 + 检查点恢复
- TypeScript 生态与 React 前端契合
- 02 号项目已验证 LangGraph + React 19 的可行性

### 7.2 规范体系：采纳 08 的四层契约

```
L1 世界规则（不可违反） → Truth Files 概念（来自 01）
L2 角色契约（可变更需协议）
L3 章节契约（消耗型逐章验收）
LS 故事线约束（卷级作用域）
```

### 7.3 Agent 设计：4 角色集群

```
Writer 集群（4 Agent）：
  ├── OutlineWriter（大纲）
  ├── ChapterWriter（章节初稿）
  ├── DialogueWriter（对话专家）
  └── SceneWriter（场景描写）

Advisor 集群（4 Agent）：
  ├── WorldBuilder（世界观）
  ├── CharacterDesigner（角色设计）
  ├── PlotArchitect（情节架构）
  └── StyleAdvisor（风格顾问）

Reviewer 集群（4 Agent）：
  ├── ConsistencyChecker（一致性）
  ├── QualityJudge（质量评分）
  ├── ContentCritic（读者视角）
  └── DeAIChecker（去 AI 检测）

Reader 集群（2 Agent）：
  ├── EngagementScorer（追读力评分）
  └── ForeshadowingTracker（伏笔追踪）
```

### 7.4 上下文管理：混合策略

```
Manifest Mode（路径引用）← 08
  + Truth Files（状态文件）← 01
  + Context Contract（动态预算）← 06
  + 摘要替代全文 + 角色裁剪 + 休眠线过滤 ← 08
```

### 7.5 质量保障：多轨验收

```
Track 1: L1/L2/L3 契约合规检查 ← 08
Track 2: 追读力评分（5 维） ← 06
Track 3: 去AI检测（10 项量化指标） ← 08
Track 4: 内容实质评估 ← 08
Gate Decision: 多信号门控合并 ← 08
```

### 7.6 修订策略：分层 + 收敛

```
Targeted 修订（仅修改失败维度）← 08
  + 收敛检测（指标不再改善则终止）← 05
  + 反馈上限（每轮 ≤ 6 条）← 05
  + 最大迭代次数（2 轮）← 05
```

---

## 八、技术风险与注意事项

| 风险 | 说明 | 缓解措施 |
|------|------|---------|
| **过度工程** | 05 号项目 21 Agent/40+ 节点维护成本过高 | Fiction Academy 控制在 12-16 Agent |
| **上下文爆炸** | 长篇创作必然面临 | 必须实现 Manifest Mode + 摘要替代 |
| **去 AI 效果衰减** | AI 模型更新可能绕过黑名单 | 需要持续更新检测策略 + 量化校准 |
| **成本控制** | 多 Agent 并行执行 token 消耗大 | LiteLLM 路由 + 好模型生成/便宜模型迭代 |
| **用户门槛** | Spec-Driven 体系学习曲线陡 | 提供 Quick Start + 可视化配置界面 |

---

## 九、总结

通过对 8 个竞品项目的深度分析，我们可以得出以下核心结论：

1. **novel-writer-plugin (08) 是架构最成熟的项目**，其 Spec-Driven 四层契约、Manifest Mode、去 AI 四层策略、Staging 事务模型、多信号门控等设计都是行业最佳实践，Fiction Academy 应全面借鉴。

2. **LangGraph 是最佳编排框架**，兼具灵活性、可视化、并行能力和生态成熟度。

3. **长篇创作的核心挑战是上下文管理**，Manifest Mode + Truth Files + Context Contract 的混合策略是最优解。

4. **去 AI 化必须系统性设计**，不能仅靠提示词，需要四层策略 + 量化检测 + 持续校准。

5. **质量评估需要多维度 + 可校准**，追读力评分（网文特色）+ 契约合规（工程规范）+ 读者视角（用户体验）三管齐下。
