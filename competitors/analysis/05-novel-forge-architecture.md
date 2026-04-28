# novel-forge 技术架构分析

## 一、项目概述

### 1.1 项目定位

novel-forge 是一个基于 **pydantic-graph 有向图** 的全流程 AI 小说创作系统，拥有 **40+ 节点的图工作流** 和 **21 个专业化 Agent**。其核心设计理念是将小说出版流程工程化为可编排、可检查点、可回滚的图状态机。

### 1.2 核心目标

- **全生命周期覆盖**：从市场分析、题材定位、概念开发、大纲构建、世界观设计、角色塑造、章节撰写、编辑审校到最终出版的完整链条
- **图驱动编排**：使用 pydantic-graph 构建复杂的 DAG（有向无环图）工作流
- **版本控制与回滚**：内置完整的版本管理系统，支持章节级和全局级的状态快照与恢复
- **多轮迭代优化**：支持 Review → Rewrite 循环，带收敛检测和反馈上限

### 1.3 技术特点

| 特性 | 说明 |
|------|------|
| 编排框架 | pydantic-graph（BaseNode + GraphRunContext） |
| 语言 | Python |
| Agent 数量 | 21 个专业化 Agent |
| 图节点数 | 40+ 个 |
| 检查点 | 6 个关键阶段 |

---

## 二、技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| **编排引擎** | pydantic-graph | 基于 Pydantic 的图工作流框架 |
| **语言** | Python | 类型安全 + 数据验证 |
| **数据模型** | Pydantic v2 | 状态管理 + 序列化 |
| **状态管理** | BookGenerationState | ~50 字段的中央状态对象 |

---

## 三、系统架构

### 3.1 40+ 节点图工作流

```
StartGeneration
  ↓
MarketAnalysis → GenrePositioning → AudienceTargeting → ComparativeTitles
  ↓
StrategicOutlineGenerator → GenerateProposal → GenerateTitle
  ↓
DevelopConcept → CreateOutline
  ↓
BuildWorld → DevelopCharacters → RefineWorldWithCharacters → RefineCharactersWithWorld
  ↓
WriteCoordinator
  ↓
WriteChapter ←──────────────────────┐
  ↓                                  │
VerifyCrossReferences               │
  ↓                                  │
GenerateSummaries                   │
  ↓                                  │
  ├── StructuralEditor ──┐          │
  ├── LineEditor ────────┤          │
  ├── PeerReviewSimulator┤          │
  ├── StyleGuideEnforcer─┤          │
  └── FormattingOptimizer┘          │
  ↓                                  │
MultiStageReviewHub                 │
  ↓                                  │
EvaluateQualityMetrics               │
  ↓                                  │
ReviewBook ──── (需修订) ────────────┘
  ↓ (通过)
MarketMetadataGenerator → PlatformExporter
  ↓
GenerateFrontMatter → GenerateBackMatter
  ↓
AssembleBook → PolishBook → FormatBook → SaveFinalBook
  ↓
End
```

### 3.2 5 并行审校子流

ReviewBook 节点触发 5 个并行审校子流，聚合到 ReviewAggregator：

```
ReviewBook
  ├── PeerReview（同行评审）
  ├── EditorialReview（编辑审校）
  ├── ConsistencyCheck（一致性检查）
  ├── StyleRefinement（风格优化）
  └── FlowEnhancement（流畅度提升）
  ↓
ReviewAggregator（聚合评审结果）
  ↓
EvaluateQualityMetrics（评估质量指标）
  ↓
决策：通过 → 继续出版流程
      不通过 → 回到 WriteChapter 重新撰写
```

### 3.3 核心文件结构

| 文件 | 行数 | 职责 |
|------|------|------|
| `novelForge_architecture.md` | 329 | 完整架构文档（含 Mermaid 图） |
| `graph_state.py` | 479 | 中央状态管理（~50 字段 + 版本控制） |
| `graph_nodes.py` | 1000+ | 40+ 图节点实现 |

---

## 四、Agent 设计

### 4.1 21 个专业化 Agent

系统将小说创作流程分解为 21 个高度专业化的 Agent，按功能可分为以下几组：

| 组别 | Agent | 职责 |
|------|-------|------|
| **市场与策划** | MarketAnalyst, GenrePositioner, AudienceTargeter, ComparativeTitleAnalyst | 市场分析、题材定位、读者画像、竞品分析 |
| **创意开发** | ProposalGenerator, TitleGenerator, ConceptDeveloper | 提案、书名、概念开发 |
| **结构与规划** | OutlineCreator, StrategicOutlineGenerator | 大纲构建 |
| **世界观与角色** | WorldBuilder, CharacterDeveloper, WorldCharacterRefiner | 世界观、角色、交叉优化 |
| **写作执行** | WriteCoordinator, ChapterWriter | 写作协调、章节撰写 |
| **审校编辑** | StructuralEditor, LineEditor, PeerReviewSimulator, StyleGuideEnforcer, FormattingOptimizer | 结构/行文/同行/风格/格式编辑 |
| **质量管控** | QualityMetricsEvaluator, ReviewAggregator, CrossReferenceVerifier, SummaryGenerator | 质量评估、评审聚合、交叉引用、摘要生成 |
| **出版** | MarketMetadataGenerator, PlatformExporter, BookAssembler | 元数据、平台导出、书籍组装 |

### 4.2 pydantic-graph BaseNode 模式

每个图节点继承 `pydantic_graph.BaseNode`：

```python
@dataclass
class PlotScaffolding(BaseNode):
    """图节点基类模式"""
    
    def run(self, ctx: GraphRunContext[BookGenerationState, BookAgents]) -> Edge:
        # 1. 从 ctx.state 读取当前状态
        # 2. 调用 Agent 执行任务
        # 3. 更新 ctx.state
        # 4. 返回下一个 Edge（决定下一个节点）
        return Edge(to="next_node")
```

`GraphRunContext` 提供两个泛型参数：
- `BookGenerationState`：全局共享状态
- `BookAgents`：Agent 注册表

### 4.3 BookCrew 编排模式

所有 Agent 通过 `BookAgents` 注册表统一管理，由图节点按需调用。BookCrew 负责在节点执行时注入正确的 Agent 实例和上下文。

---

## 五、核心数据模型

### 5.1 BookGenerationState（中央状态）

约 50 个字段的全局状态对象，是整个图工作流的"唯一真相源"：

| 字段组 | 关键字段 | 说明 |
|--------|---------|------|
| **版本控制** | version_history | 版本快照列表 |
| | save_version() | 深拷贝当前状态为快照 |
| | restore_version() | 恢复到指定版本 |
| | diff_versions() | 对比两个版本的差异 |
| **章节版本** | chapter_versions: Dict[int, List[ChapterResult]] | 每章多个版本 |
| | current_chapter_status | draft/review_pending/needs_rewrite/approved |
| **冻结标志** | freeze_flags | concept/outline/characters/world/chapters |
| **用户交互** | user_feedback | 用户反馈字典 |
| **Agent 指标** | agent_metrics: Dict[str, AgentMetrics] | 各 Agent 的性能指标 |
| **反馈历史** | feedback_history: List[PolishingFeedback] | 审校反馈记录 |
| **变更追踪** | applied_changes: Dict[int, List[AppliedChange]] | 已应用的变更 |
| **写作统计** | writing_stats | 写作统计数据 |

### 5.2 版本控制系统

```python
# 保存版本（深拷贝快照）
state.save_version("before_chapter_5_rewrite")

# 恢复版本
state.restore_version("before_chapter_5_rewrite")

# 版本对比
diff = state.diff_versions("v1", "v2")
```

版本控制应用于三个粒度：
- **全局级**：整个 BookGenerationState 的快照
- **章节级**：每章维护多个 ChapterResult 版本
- **变更级**：记录每次修改的 AppliedChange

### 5.3 PolishingFeedback（审校反馈）

```python
@dataclass
class PolishingFeedback:
    chapter: int
    category: str        # structural / line_editing / style / consistency / flow
    priority: str        # critical / high / medium / low
    agent_source: str    # 来源 Agent
    before_context: str  # 修改前
    after_context: str   # 修改后
```

### 5.4 GenerationConfig（生成配置）

```python
max_iterations: int = 2        # 最大修订轮数
max_feedback_items: int = 6    # 每轮最大反馈数
```

---

## 六、数据流与工作流

### 6.1 检查点机制（6 个关键阶段）

系统在 6 个关键阶段设置检查点，支持中断恢复：

1. **概念确认后**（Concept Approved）
2. **大纲完成后**（Outline Complete）
3. **角色/世界观完成后**（World & Characters Complete）
4. **每章撰写后**（Chapter Written）
5. **审校完成后**（Review Complete）
6. **最终组装后**（Book Assembled）

### 6.2 Review → Rewrite 循环

```
WriteChapter → ReviewBook
                    │
                    ├── 质量达标 → 继续出版流程
                    │
                    └── 质量不达标 → 回到 WriteChapter
                                    │
                                    ├── iteration < max_iterations → 继续修订
                                    └── iteration >= max_iterations → 强制通过或暂停
```

**收敛检测**：
- 每轮修订后对比质量指标
- 如果指标不再改善 → 提前终止（避免无意义循环）
- 反馈上限：每轮最多 6 条反馈，避免 Agent 被过多反馈淹没

### 6.3 冻结标志（用户控制）

```python
freeze_flags = {
    "concept": False,      # 概念是否锁定
    "outline": False,      # 大纲是否锁定
    "characters": False,   # 角色是否锁定
    "world": False,        # 世界观是否锁定
    "chapters": False      # 已完成章节是否锁定
}
```

用户可以冻结已完成的部分，防止后续修订意外修改。

---

## 七、亮点与创新

### 7.1 图驱动编排（pydantic-graph）

这是本项目最核心的架构创新。40+ 节点的 DAG 工作流使得：
- **流程可视化**：完整的工作流可以通过图结构清晰表达
- **灵活编排**：新增/删除/调整节点不影响整体结构
- **并行执行**：5 个审校子流可以自然并行
- **条件分支**：ReviewBook 的通过/不通过分支自然表达

### 7.2 完整的版本控制系统

深拷贝快照 + 章节级版本 + 变更追踪的三层版本控制，使得：
- 任何修改都可以回滚
- 可以对比任意两个版本的差异
- 章节级版本支持"选择最佳版本"

### 7.3 收敛检测与反馈上限

```python
max_iterations = 2
max_feedback_items = 6
```

这两个简单但有效的参数防止了 AI 创作中常见的"无限循环修订"问题：
- 最多修订 2 轮 → 强制终止
- 每轮最多 6 条反馈 → 避免信息过载
- 收敛检测 → 提前终止无改善的修订

### 7.4 21 Agent 极致分工

将小说创作流程分解为 21 个专业化 Agent，每个 Agent 只负责一个极窄的领域。这种极致分工确保了每个 Agent 的 prompt 可以高度聚焦，输出质量更高。

### 7.5 FSM + 收敛检查

图工作流本质是一个有限状态机（FSM），结合收敛检查形成了"图驱动 + 自动终止"的混合模式，兼具灵活性和可控性。

---

## 八、局限性与改进空间

### 8.1 局限性

| 局限 | 说明 |
|------|------|
| **Python 生态** | 纯 Python 实现，无前端 UI |
| **无实时交互** | 图工作流是批处理模式，缺乏用户实时参与 |
| **Agent 同质化** | 21 个 Agent 可能共用同一底层模型，分工虽细但能力可能重叠 |
| **复杂度高** | 40+ 节点的图工作流维护成本高 |
| **缺少去 AI 化** | 没有专门的去 AI 味处理环节 |

### 8.2 对 Fiction Academy 的启示

1. **图驱动编排思想**：LangGraph 本身就是图工作流框架，novel-forge 的 40+ 节点设计可以精简后借鉴
2. **版本控制系统**：章节级版本 + 全局快照的方案非常值得学习
3. **收敛检测机制**：max_iterations + max_feedback_items + 收敛检测的"三保险"设计可直接复用
4. **冻结标志**：用户可控的锁定机制保证了创作安全感
5. **市场分析前置**：在创作前进行市场/读者/竞品分析的思想值得借鉴
6. **需要增强**：前端 UI、实时交互、去 AI 化、多模型路由
