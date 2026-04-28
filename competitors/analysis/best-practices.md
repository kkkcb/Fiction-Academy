# 八大竞品可取之处汇总

> 从每个项目中提炼出对 Fiction Academy 最有价值的设计思想、技术方案和创新点，按能力维度分类整理。

---

## 一、架构与编排

### 1.1 LangGraph 图工作流 — 来自 AI-Novel-Writing-Assistant (02)

**可取之处**：LangGraph 提供了图可视化、条件分支、并行执行、检查点恢复四大核心能力，且 TypeScript 生态与 React 前端天然契合。02 号项目已验证了 LangGraph + React 19 + Express 5 全栈架构的可行性。

**具体参考**：
- Agent Runtime 完整生命周期管理（创建/执行/审批/回放/诊断）
- 幂等工具执行：idempotencyKey + 结果缓存，应对 LLM 调用不稳定
- 审批断点续跑：序列化 continuation payload，审批后从断点恢复

### 1.2 pydantic-graph 图驱动编排 — 来自 novel-forge (05)

**可取之处**：40+ 节点的 DAG 工作流展示了"将创作全流程工程化为图"的可能性。节点继承 BaseNode，通过 GraphRunContext 访问共享状态，Edge 决定下一个节点。

**具体参考**：
- 收敛检测 + 反馈上限：max_iterations=2, max_feedback_items=6，防止无限循环修订
- 冻结标志：用户可控的锁定机制（concept/outline/characters/world/chapters）
- 5 并行审校子流聚合到 ReviewAggregator

### 1.3 Spec-Driven 状态机编排 — 来自 novel-writer-plugin (08)

**可取之处**：7 状态有限状态机（INIT → QUICK_START → VOL_PLANNING → WRITING ⟲ → VOL_REVIEW），结合 Checkpoint 持久化和 pipeline_stage 粒度的中断恢复。

**具体参考**：
- pipeline_stage 8 个枚举值对应不同恢复策略
- 并发锁获取 + 僵尸锁检测（30min 超时）

### 1.4 Planner-Composer-Writer 三阶段分离 — 来自 inkos (01)

**可取之处**：将"写什么"（Planner）和"用什么写"（Composer）和"实际写"（Writer）三阶段分离。关键：plan 和 compose **不需要 LLM 调用**，完全通过规则实现，零 token 成本。

**具体参考**：
- Planner：读取 8 个源文件 → 输出 ChapterIntent（goal, mustKeep, mustAvoid, hook agenda）
- Composer：从全量 truth files 按相关性选择上下文 → 编译 ContextPackage + RuleStack + Trace

---

## 二、Agent 设计模式

### 2.1 读写分离双 Agent — 来自 webnovel-writer (06)

**可取之处**：避免单个 Agent 在同一上下文中既要理解大量历史数据又要生成新内容的注意力分散。

**具体参考**：
- **Context Agent（只读）**：6 步管道，读取 state.json + index.db + summaries → 组装 Context Pack
- **Data Agent（只写）**：10 步管道，实体提取 → 消歧 → DB 写入 → 摘要 → 向量索引

### 2.2 Slot-Based 三 Agent 解耦 — 来自 NovelGenerator (04)

**可取之处**：将章节创作拆分为结构/角色/场景三个正交维度，通过 [SLOT] 标记实现解耦。

**具体参考**：
- StructureAgent 生成带 [DIALOGUE_X]/[ACTION_X]/[INTERNAL_X]/[DESCRIPTION_X]/[TRANSITION_X] 标记的骨架
- CharacterAgent 填充对话和内心独白
- SceneAgent 填充描写和动作
- 情感曲线量化控制：开篇 4-6/10 → 上升 3-7/10 → 高潮 8-10/10 → 收束 5-7/10

### 2.3 创作与去 AI 分离 — 来自 novel-writer-plugin (08)

**可取之处**：ChapterWriter（Opus）专注创作质量，StyleRefiner（Sonnet）做机械性去 AI 后处理。模型降级实现 5-10 倍成本优化。

**具体参考**：
- ChapterWriter **不看黑名单**（隔离设计），靠内隐参照实现自然写作
- StyleRefiner 执行黑名单扫描、标点修正、AI 模式替换等机械任务
- 6 策略 Slot 提取解析器处理 AI 输出格式不稳定的容错

### 2.4 极简 Agent 基类 — 来自 inkos (01)

**可取之处**：BaseAgent 仅 100 行，只提供 chat() 和 chatWithSearch() 两个核心方法。业务逻辑完全内聚，通过 AgentContext 注入 LLMClient, model, projectRoot, logger 等。

### 2.5 多模型按任务路由 — 来自多个项目

**可取之处**：不同 Agent 使用不同模型，平衡质量与成本。

| 项目 | 策略 |
|------|------|
| inkos (01) | 写作 0.7, 观察 0.5, 结算 0.3, 审计 0, 归一化 0.2 |
| AI-Novel-Writing-Assistant (02) | 按任务类型分配 provider + model + temperature |
| ai-book-writer (03) | LiteLLM 路由：Writer 60%, Editor 25%, ContinuityChecker 10% |
| novel-writer-plugin (08) | Opus 创作, Sonnet 去AI, Codex 评估 |

---

## 三、规范与质量保障

### 3.1 Spec-Driven 四层契约体系 — 来自 novel-writer-plugin (08)

**可取之处**：借鉴软件工程 TDD/BDD 思想，将小说创作规范化为四层契约：

| 层级 | 文件 | 可变性 | 软件工程类比 |
|------|------|--------|-------------|
| **L1** 世界规则 | world/rules.json | 不可违反 | 类型系统 |
| **L2** 角色契约 | characters/active/*.json | 可变更需协议 | 接口定义 |
| **L3** 章节契约 | volumes/vol-*/chapter-contracts/*.md | 消耗型（逐章验收） | 单元测试 |
| **LS** 故事线 | storylines/storyline-spec.json | 卷级作用域 | 并发安全规则 |

验收四轨制：合规检查 = 编译通过 → 质量评分 = Code Review → 内容实质 = Regression Test → 读者参与度 = User Testing

### 3.2 33+ 维度连续性审计 — 来自 inkos (01)

**可取之处**：37 个审计维度按题材条件启用，覆盖核心连续性(1-10)、叙事质量(11-19)、题材特定(20-26)、结构检测(27-31)、全局(32-33)、同人专用(34-37) 六大类。

**具体参考**：
- AI 痕迹检测维度：词汇疲劳、句式单调、过度总结
- State Validator 守门人：LLM 输出的状态变更必须独立校验才能持久化

### 3.3 多信号门控合并 — 来自 novel-writer-plugin (08)

**可取之处**：四步门控决策实现多维质量信号的精确融合：

```
Step A: QJ 基础判定 → pass/polish/revise/review/rewrite
Step B: CC 内容实质硬门 → 任一维度 < 3.0 无条件强制 revise
Step C: CC 读者参与度叠加 → 仅降级，不升级
Step D: 最终合并 → max severity wins
```

### 3.4 六维并行审查 — 来自 webnovel-writer (06)

**可取之处**：6 个 Checker 可并行执行，按需启用：

| Checker | 类型 | 检查内容 |
|---------|------|---------|
| 一致性 | 核心 | 战力一致、地点一致、角色一致 |
| 连续性 | 核心 | 时间线、因果链、伏笔回收 |
| OOC | 核心 | 轻微偏离、中度失真、严重崩坏 |
| 追读力 | 条件 | 钩子设计、信息差构建、微观回报 |
| 爽点 | 条件(5章) | 8 种爽点模式、30/40/30 结构 |
| 节奏 | 条件(10章) | Quest/Fire/Constellation 三线平衡 |

问题分级：Critical(阻断) → High(必须修) → Medium/Low(建议)

### 3.5 Structured Output 三级降级 — 来自 AI-Novel-Writing-Assistant (02)

**可取之处**：多策略 + LLM 修复 + fallback，显著提高结构化输出的稳定性：

```
json_schema → json_object → prompt_json + LLM 修复器 + fallback 模型
```

---

## 四、去 AI 化策略

### 4.1 去 AI 四层策略 — 来自 novel-writer-plugin (08)

**可取之处**：目前最系统化的去 AI 方案：

| 层 | 策略 | 创新点 |
|----|------|--------|
| L1 | 风格锚定 | 7 维可量化指纹（句长/TTR/开头模式/修辞/段落/对话比/情感弧），4 种来源 |
| L2 | 约束注入 | ChapterWriter 不看黑名单（隔离设计），靠内隐参照实现自然写作 |
| L3 | 后处理 | Sonnet 做机械任务，成本优化 5-10x |
| L4 | 检测度量 | 10 项量化指标 + 3 区范围判定（安全/警告/危险） |

### 4.2 语域微注入 — 来自 novel-writer-plugin (08)

**可取之处**：在同一段落内刻意制造语域跳变（正式→粗口、文言→白话），连续同调超过 800 字即视为问题。这是直接针对"AI 文本语域单一"这一核心特征的解决方案。

### 4.3 人性化技法工具箱 — 来自 novel-writer-plugin (08)

**可取之处**：12 种随机采样技法（思维中断、感官突入、自我纠正、情感急转等），"不用"本身构成随机性。连续 5 章零技法触发 humanize_drought 警告。

### 4.4 统计反制设计 — 来自 webnovel-writer (06)

**可取之处**：针对 AI 生成文本的 6 维统计异常提供反方向约束：
- 句长方差过小 → 要求方差范围
- 段落长度过于均匀 → 要求长段/短段交替
- 词汇重复 → 疲劳词检测
- 叙述连接词过多 → 禁用列表
- 语域单一 → 语域跳变要求
- 情感弧线平滑 → 要求波动

### 4.5 规则层零成本去 AI — 来自 inkos (01)

**可取之处**：11+ 条中文硬规则通过正则和统计实现，零 token 成本：
- 禁用"不是...而是..."句式
- 破折号禁用
- 惊叹号密度控制
- 疲劳词检测
- 元叙事检测
- 段落均匀度检测
- 模糊词密度检测

### 4.6 内容修正函数库 — 来自 NovelGenerator (04)

**可取之处**：5 个针对 AI 生成文本典型缺陷的修正函数：

| 函数 | 解决问题 |
|------|---------|
| condenseInternalMonologue | 内心独白过于冗长 |
| insertMicroActions | 对话间缺少动作描写 |
| reduceDescriptionDensity | 环境描写过于密集 |
| breakUpInternalMonologue | 内心独白连续过长 |
| insertActionBeats | 动作节拍不足 |

---

## 五、上下文与长篇管理

### 5.1 Manifest Mode v2（路径引用）— 来自 novel-writer-plugin (08)

**可取之处**：编排器仅向 Agent 传递文件路径（非完整内容），Agent 按需 Read 加载。配合摘要替代全文 + 角色裁剪 + 休眠线过滤，**第 500 章 context 仍 ~20K tokens**。

### 5.2 Truth Files 多文件专职化 — 来自 inkos (01)

**可取之处**：7+ 个 Markdown 文件作为"唯一事实来源"：

| 文件 | 用途 | 更新频率 |
|------|------|---------|
| story_bible.md | 世界观设定 | 建书时 |
| volume_outline.md | 卷纲规划 | 建书时 |
| book_rules.md | 书级规则 | 建书时 + 可编辑 |
| current_state.md | 当前世界状态 | 每章 |
| particle_ledger.md | 资源账本 | 每章 |
| pending_hooks.md | 伏笔池 | 每章 |
| chapter_summaries.md | 章节摘要 | 每章 |

双重存储：Markdown（人类可读）+ Zod-validated JSON（机器权威）。

### 5.3 Observer-Settler 两阶段状态提取 — 来自 inkos (01)

**可取之处**："宽松提取、严格合并"模式：

- **Observer**：从正文"过度提取"9 类事实（角色/地点/资源/关系/情感/信息流/情节线/时间/物理状态）
- **Settler**：将观察结果合并到 truth files，输出 JSON delta，immutable apply + Zod 校验后写入

比一次性让 LLM 输出完整 truth file 更可靠。

### 5.4 Context Contract v2 — 来自 webnovel-writer (06)

**可取之处**：优先级排序 + 新鲜度/频率/钩子加分 + 动态 Token 预算 + 分阶段预算。确保不同 Agent 在不同阶段获得适配的上下文量。

### 5.5 确定性上下文组装 7 步 — 来自 novel-writer-plugin (08)

**可取之处**：7 步确定性规则确保 context 注入可重现：

1. 大纲提取（正则匹配）
2. L1 规则预过滤（按 canon_status 分级）
3. L2 角色裁剪（契约角色全注入，其余 top-15）
4. L3 契约加载（Markdown 优先，JSON 回退）
5. 摘要窗口（前 2 章完整 + 最近 8 章精简）
6. 故事线记忆（过滤休眠线）
7. 附加注入（风格漂移/黑名单/伏笔/NER 实体）

---

## 六、创作理论与领域知识工程化

### 6.1 追读力评分系统 — 来自 webnovel-writer (06)

**可取之处**：将网文"追读体验"转化为可执行、可量化的评估体系：

- **5 种钩子**：危机钩、悬念钩、渴望钩、情绪钩、选择钩
- **8 种爽点**：装逼打脸、扮猪吃虎、越级反杀、打脸权威、反派翻车、甜蜜超预期、迪化误解、身份掉马
- **7 种微观回报**：小悬念揭示、小目标达成、新能力展示、关系进展、信息差揭晓、反派受挫、世界观碎片
- **硬性不变量**：每章至少 1 钩子 / 每 3 章至少 1 微观回报 / 爽点密度不低于题材基线

### 6.2 Strand Weave 三线编织 — 来自 webnovel-writer (06)

**可取之处**：将叙事学理论转化为可执行约束：

| 线 | 比例 | 职责 | 红线约束 |
|----|------|------|---------|
| Quest（主线） | 60% | 推进核心剧情 | 最大连续 5 章 |
| Fire（爽线） | 20% | 高潮/打脸/突破 | 最大间隔 10 章 |
| Constellation（伏线） | 20% | 伏笔/暗示/世界观展开 | 最大间隔 15 章 |

### 6.3 债务追踪系统 — 来自 webnovel-writer (06)

**可取之处**：弹性约束满足，违反记录"债务"并计算利息，后续章节必须超额完成来偿还。解决了"完美约束不现实"的问题。

### 6.4 防幻觉三定律 — 来自 webnovel-writer (06)

**可取之处**：
1. **大纲即法律**：不得偏离已确认大纲
2. **设定即物理**：世界观设定如同物理定律不可违反
3. **发明需识别**：创造新设定/角色必须明确标注

约束层分级：Hard（必须执行）/ Soft（建议执行）/ Style（可选执行）

### 6.5 伏笔生命周期管理 — 来自 novel-writer-plugin (08)

**可取之处**：双层模型：
- **事实层**（global.json）：Summarizer ops 驱动，记录实际状态变更
- **计划层**（vol-XX/foreshadowing.json）：PlotArchitect 生成，记录规划目标
- 状态单调递进：planted → advanced → resolved
- 范围语义：short（3-10 章）/ medium（跨卷）/ long（全书级）

### 6.6 伏笔账本 — 来自 AI-Novel-Writing-Assistant (02)

**可取之处**：追踪伏笔的 setup/hint/payoff 全生命周期，含状态和压力提示，解决"挖坑不填"问题。

### 6.7 平台差异化适配 — 来自 novel-writer-plugin (08)

**可取之处**：三大网文平台的差异化标准工程化：

| 平台 | 读者类型 | 核心要求 |
|------|---------|---------|
| 番茄小说 | 碎片阅读者 | 200 字主角登场 + 章末钩子 |
| 起点中文网 | 付费追更者 | 力量体系暗示 + immersion ≥ 3.5 |
| 晋江文学城 | 情感投入者 | 行为展现人设 + style_naturalness ≥ 3.5 |

---

## 七、存储与数据管理

### 7.1 Staging 事务模型 — 来自 novel-writer-plugin (08)

**可取之处**：借鉴数据库 ACID 思想：

| 特性 | 实现 |
|------|------|
| Atomicity | 所有 Agent 输出先写 staging，commit 时原子性 mv |
| Consistency | PreToolUse Hook 强制所有写入限于 staging |
| Isolation | 文件级并发锁 + 僵尸锁检测（30min 超时） |
| Durability | Checkpoint 持久化 + pipeline_stage 粒度的中断恢复 |

### 7.2 版本控制系统 — 来自 novel-forge (05)

**可取之处**：三层版本控制：
- **全局级**：save_version() 深拷贝快照 + restore_version() 恢复 + diff_versions() 对比
- **章节级**：每章维护多个 ChapterResult 版本（draft/review_pending/needs_rewrite/approved）
- **变更级**：记录每次修改的 AppliedChange

### 7.3 Runtime State Delta — 来自 inkos (01)

**可取之处**：状态更新用 delta 而非全量重写，配合 immutable apply + Zod 校验，确保数据一致性。

### 7.4 纯 SQLite 全栈存储 — 来自 webnovel-writer (06)

**可取之处**：向量存储（struct.pack BLOB）、BM25（自研实现）、图 RAG（SQLite 关系表 + 1-hop 扩展）全部基于 SQLite，零外部依赖。

### 7.5 Prisma 数据模型 — 来自 AI-Novel-Writing-Assistant (02)

**可取之处**：丰富的数据模型设计参考：
- Novel → Chapter/Character/VolumePlan/PayoffLedger/StoryStateSnapshot/OpenConflict/AuditReport
- Character → Relation/Timeline/State
- KnowledgeDocument → Version/Binding

### 7.6 LiteLLM 统一路由层 — 来自 ai-book-writer (03)

**可取之处**：failover + 溢出路由 + 成本优化 + 预算分配 + 统一缓存，开箱即用。

---

## 八、用户体验与交互

### 8.1 右键菜单驱动交互 — 来自 AI-automatically-generates-novels (07)

**可取之处**：24 个预设的右键操作覆盖创作全流程，"选中文本 → 右键操作 → 预览确认 → 应用替换"的交互流程直观高效。

三套菜单：大纲(8项) / 章节(8项) / 正文(8项)，每项包含完整提示词模板。

### 8.2 Quick Start 黄金三章 — 来自 novel-writer-plugin (08)

**可取之处**：50 分钟从零到前三章试写，包含世界观 → 角色 → 风格 → 迷你卷规划 → 试写的完整 pipeline，降低用户入门门槛。

### 8.3 SSE 流式推送 — 来自 AI-Novel-Writing-Assistant (02) + ai-book-writer (03)

**可取之处**：
- 02 号项目：useSSE Hook 封装完整 SSE 生命周期，支持 12 种事件类型
- 03 号项目：Next.js API Route 代理 SSE 流，解决浏览器 EventSource 不支持自定义 Headers 的限制

### 8.4 三层提示词体系 — 来自 AI-automatically-generates-novels (07)

**可取之处**：大纲提示词 → 章节提示词 → 内容提示词的三层递进，配合 ${variable} 变量替换系统，用户可完全自定义创作流程。零代码可配置。

### 8.5 拆书功能 — 来自 AI-automatically-generates-novels (07)

**可取之处**：将已有小说拆解为世界观设定、角色关系、情节脉络、写作风格，拆解结果可用于仿写学习。

### 8.6 Creative Hub 统一入口 — 来自 AI-Novel-Writing-Assistant (02)

**可取之处**：对话 + 工具调用 + 审批 + 状态卡片的一体化体验。Thread 模型绑定资源，支持消息、中断、检查点。

### 8.7 双通道成本优化 — 来自 AI-automatically-generates-novels (07)

**可取之处**：/gen（高质量模型）用于核心创作，/gen2（低成本模型）用于 AI 迭代和拆书。"好钢用在刀刃上"。

### 8.8 写法引擎闭环 — 来自 AI-Novel-Writing-Assistant (02)

**可取之处**：特征提取 → 编辑 → 编译 → 绑定 → 检测 → 修复，完整的风格控制闭环。四维规则集：NarrativeRules/CharacterRules/LanguageRules/RhythmRules。

---

## 九、运维与工程质量

### 9.1 完整评估基础设施 — 来自 novel-writer-plugin (08)

**可取之处**：
- 人工标注数据集（30 章 JSONL）
- 6 个 JSON Schema 校验
- Pearson 相关系数校准工具（Codex vs Human, CC vs Human 等 4 向）
- 阈值决策：r ≥ 0.85 + |bias| < 0.3 → 保持
- 回归运行 + 对比工具
- Quality Aggregation（按卷评分趋势 + 低分预警）

### 9.2 成本全链路管控 — 来自 ai-book-writer (03)

**可取之处**：预估算 → 预算检查 → 实时追踪 → 月度汇总的完整闭环。每次 LLM 调用记录到 costs 表（agent/model/prompt_tokens/completion_tokens/usd）。

### 9.3 Prompt Registry — 来自 AI-Novel-Writing-Assistant (02)

**可取之处**：统一的 Prompt 资产管理，版本化、元数据化。避免 prompt 散落在代码各处。

### 9.4 K8s 生产部署 — 来自 ai-book-writer (03)

**可取之处**：HPA(2-10 Pod) + 三层健康检查 + 滚动更新 + 安全加固（非 root 容器、只读根文件系统）。

### 9.5 故障隔离管道 — 来自 webnovel-writer (06)

**可取之处**：数据持久化失败不回滚创作成果。Step 5（Data Persist）的 G/H 子步骤失败不影响 Step 1-4 的创作成果。

### 9.6 三级置信度消歧 — 来自 webnovel-writer (06)

**可取之处**：人机协同的渐进式信任模型：
- >0.8 自动采纳
- 0.5-0.8 采纳 + 警告
- <0.5 挂起等待人类确认

---

## 十、按优先级排序的 Top 20 可取之处

| 排名 | 可取之处 | 来源项目 | 影响范围 |
|------|---------|---------|---------|
| 1 | Spec-Driven 四层契约体系 | 08 | 全局质量保障 |
| 2 | Manifest Mode v2 路径引用 | 08 | 上下文管理 |
| 3 | 去 AI 四层策略 + 隔离设计 | 08 | 去AI化 |
| 4 | Truth Files + Observer-Settler | 01 | 状态管理 |
| 5 | 追读力评分 + 爽点引擎 | 06 | 网文质量度量 |
| 6 | Staging 事务模型 | 08 | 数据安全 |
| 7 | 多信号门控合并 | 08 | 质量保障 |
| 8 | 读写分离双 Agent | 06 | Agent 设计 |
| 9 | Strand Weave 三线编织 | 06 | 叙事结构 |
| 10 | 收敛检测 + 反馈上限 | 05 | 修订控制 |
| 11 | 伏笔生命周期双层模型 | 08 | 长篇管理 |
| 12 | LangGraph Agent Runtime | 02 | 编排框架 |
| 13 | 版本控制 + 快照回滚 | 01, 05 | 数据安全 |
| 14 | 确定性上下文组装 7 步 | 08 | 上下文管理 |
| 15 | 6 策略容错解析器 | 04 | 工程健壮性 |
| 16 | 语域微注入 + 人性化技法 | 08 | 去AI化 |
| 17 | LiteLLM 统一路由 | 03 | 成本控制 |
| 18 | 右键菜单驱动交互 | 07 | 用户体验 |
| 19 | 伏笔账本 | 02 | 长篇管理 |
| 20 | Pearson 相关系数校准 | 08 | 评估体系 |
