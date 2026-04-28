# NovelGenerator 技术架构分析

## 一、项目概述

### 1.1 项目定位

NovelGenerator 是一个基于 **Slot-Based Multi-Agent** 架构的 AI 小说章节生成系统。其核心创新在于将"写作"这一高度耦合的创造性任务，分解为 **三个专业化 Agent 按序填充 [SLOT] 标记** 的流水线，实现了结构、角色、场景三个维度的解耦生成。

### 1.2 核心目标

- **专业化分工**：将章节创作拆分为结构（Structure）、角色（Character）、场景（Scene）三个独立维度
- **Slot 标记系统**：通过 `[DIALOGUE_X]`、`[ACTION_X]`、`[INTERNAL_X]`、`[DESCRIPTION_X]`、`[TRANSITION_X]` 五类占位符实现维度解耦
- **顺序编排**：Structure Agent 先生成带标记的骨架 → Character Agent 填充对话/内心 → Scene Agent 填充描写/动作
- **前端一体化**：React 19 + Gemini AI 的纯前端应用，无需后端服务

### 1.3 技术特点

| 特性 | 说明 |
|------|------|
| 运行环境 | 纯前端（浏览器） |
| AI 模型 | Google Gemini（@google/generative-ai） |
| 构建工具 | Vite 6 + TypeScript 5.8 |
| UI 框架 | React 19 |
| Agent 数量 | 3 个专业 Agent + 1 个协调器 |

---

## 二、技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| **前端框架** | React 19 | 最新版本 |
| **构建工具** | Vite 6 | 极速开发体验 |
| **语言** | TypeScript 5.8 | 严格类型检查 |
| **AI SDK** | @google/generative-ai | Google Gemini API 官方 SDK |
| **状态管理** | React State + 自定义 Hook | 无第三方状态库 |

**依赖极简**：package.json 仅 5 个核心依赖（react, react-dom, @google/generative-ai, vite, @vitejs/plugin-react），体现了"小而精"的设计哲学。

---

## 三、系统架构

### 3.1 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    React UI Layer                        │
│  (章节展示 / 进度跟踪 / 交互控制 / 故事上下文 DB)         │
├─────────────────────────────────────────────────────────┤
│                 AgentCoordinator                         │
│  (6 阶段流水线编排 / 内容修正 / 故事上下文管理)           │
├──────────┬──────────┬───────────────────────────────────┤
│ Structure│ Character│         SceneAgent                │
│  Agent   │  Agent   │ (五感沉浸 / 场景类型感知 / 节奏)    │
│(骨架+标记)│(对话+内心)│                                   │
├──────────┴──────────┴───────────────────────────────────┤
│              Gemini AI API (@google/generative-ai)       │
└─────────────────────────────────────────────────────────┘
```

### 3.2 核心文件结构

| 文件 | 行数 | 职责 |
|------|------|------|
| `types.ts` | 203 | 全局类型定义（30+ 类型/枚举） |
| `utils/agentCoordinator.ts` | 1064 | Agent 编排器（6 阶段流水线） |
| `utils/specialistAgents.ts` | 1443 | 三个专业 Agent 实现 |

---

## 四、Agent 设计

### 4.1 三 Agent 分工模型

```
StructureAgent ──→ [带SLOT标记的散文骨架]
       │
       ▼
CharacterAgent ──→ [填充对话和内心独白的半成品]
       │
       ▼
SceneAgent ──→ [最终完整的章节正文]
```

### 4.2 StructureAgent（结构 Agent）

**职责**：生成流畅的散文骨架，嵌入五类 SLOT 标记

**SLOT 标记体系**：
| 标记 | 含义 | 填充者 |
|------|------|--------|
| `[DIALOGUE_X]` | 对话内容 | CharacterAgent |
| `[ACTION_X]` | 动作描写 | SceneAgent |
| `[INTERNAL_X]` | 内心独白/思维 | CharacterAgent |
| `[DESCRIPTION_X]` | 环境描写 | SceneAgent |
| `[TRANSITION_X]` | 场景转换 | SceneAgent |

**情感曲线控制**：
- 开篇：4-6/10（中等张力，建立氛围）
- 上升：3-7/10（波动递增，制造悬念）
- 高潮：8-10/10（最高张力，关键转折）
- 收束：5-7/10（适度回落，留有余韵）

**设计亮点**：StructureAgent 不仅仅生成结构大纲，而是生成**带标记的流畅散文**。这意味着骨架本身就是可读的文本，SLOT 标记自然嵌入在叙事流中，而非生硬的占位符。

### 4.3 CharacterAgent（角色 Agent）

**职责**：填充对话（DIALOGUE）和内心独白（INTERNAL）两类 SLOT

**核心能力**：
- **Subtext Mastery（潜文本掌控）**：对话表面意思与真实意图的分层
- **Show-vs-Tell 规则**：通过行为和对话展现性格，而非直接叙述
- **6 策略 Slot 提取解析器**：处理 AI 返回格式不稳定的鲁棒性设计

**输入**：StructureAgent 输出的骨架 + structureSlots（标记列表）+ 角色信息

### 4.4 SceneAgent（场景 Agent）

**职责**：填充描写（DESCRIPTION）、动作（ACTION）、转换（TRANSITION）三类 SLOT

**核心能力**：
- **五感沉浸**：视觉、听觉、嗅觉、触觉、味觉的多感官场景构建
- **场景类型感知**：战斗/浪漫/悬疑/日常等不同场景类型的差异化描写策略
- **节奏适配**：根据上下文情感强度调整描写密度

**输入**：CharacterAgent 输出的半成品 + structureSlots + tone awareness（语调感知）

### 4.5 AgentCoordinator（编排器）

**6 阶段流水线**：

```
Phase 1: Context Preparation（上下文准备）
  ├── 加载章节计划（ParsedChapterPlan）
  ├── 提取角色信息、情感弧线
  └── 构建故事上下文

Phase 2: Coordinated Specialist Generation（协调专业生成）
  ├── StructureAgent → 带标记骨架
  ├── CharacterAgent → 填充对话/内心
  └── SceneAgent → 填充描写/动作

Phase 3: Synthesis & Macro Validation（综合与宏观验证）
  ├── 合并三个 Agent 的输出
  └── 宏观一致性检查

Phase 4: Light Polish（轻度润色）
  ├── 凝缩内心独白（condenseInternalMonologue）
  ├── 插入微动作（insertMicroActions）
  ├── 降低描写密度（reduceDescriptionDensity）
  ├── 打断内心独白（breakUpInternalMonologue）
  └── 插入动作节拍（insertActionBeats）

Phase 5: Repetition Check（重复检查）
  └── 检测并修复文本重复

Phase 6: Coherence Update（连贯性更新）
  └── 更新故事上下文数据库
```

---

## 五、核心数据模型

### 5.1 ParsedChapterPlan（章节计划）

这是系统最核心的数据结构，包含 30+ 字段：

| 字段组 | 字段 | 说明 |
|--------|------|------|
| **场景** | detailedScenes | 详细场景列表 |
| **事件** | chapterEvents | 章节事件序列 |
| **对话** | dialogueBeats | 对话节拍 |
| **角色弧线** | characterArcs | 角色情感弧线 |
| **动作** | actionSequences | 动作序列 |
| **象征** | symbolism | 象征/隐喻 |
| **伏笔** | foreshadowing | 伏笔设置 |
| **回调** | callbacks | 对前文的呼应 |
| **SLOT** | requiredSlots | 必须填充的标记数 |
| **复杂度** | complexityLevel | 章节复杂度等级 |

### 5.2 ChapterGenerationStage（章节生成阶段枚举）

```typescript
enum ChapterGenerationStage {
  NotStarted → StructureGeneration → CharacterGeneration → 
  SceneGeneration → Synthesis → FirstDraft → LightPolish → 
  ConsistencyCheck → FinalDraft → Complete
}
```

8 个生成阶段，支持细粒度的进度跟踪和断点恢复。

### 5.3 Agent 日志系统

```typescript
type AgentLogType = 'decision' | 'execution' | 'evaluation' | 
                     'iteration' | 'warning' | 'success' | 'diff';
```

每个 Agent 的决策、执行、评估过程都被记录，支持完整的生成过程审计。

---

## 六、数据流

### 6.1 章节生成完整数据流

```
用户输入（故事设定/角色/大纲）
       │
       ▼
ParsedChapterPlan 解析（30+ 字段结构化计划）
       │
       ▼
AgentCoordinator Phase 1: 上下文准备
       │
       ▼
StructureAgent
  输入：章节计划 + 角色信息 + 情感弧线
  输出：带 [SLOT] 标记的散文骨架
       │
       ▼
CharacterAgent
  输入：骨架 + structureSlots + 角色信息
  输出：对话和内心独白已填充的半成品
       │
       ▼
SceneAgent
  输入：半成品 + structureSlots + tone awareness
  输出：完整章节正文
       │
       ▼
AgentCoordinator Phase 3-6: 综合/润色/检查/更新
       │
       ▼
最终章节（ChapterData）
  ├── content: string
  ├── pacingScore: number
  ├── dialogueRatio: number
  ├── foreshadowing: array
  └── draftVersions: array
```

### 6.2 内容修正辅助函数

Phase 4（Light Polish）包含 5 个针对性修正函数：

| 函数 | 解决问题 |
|------|---------|
| `condenseInternalMonologue` | 内心独白过于冗长 |
| `insertMicroActions` | 对话间缺少动作描写 |
| `reduceDescriptionDensity` | 环境描写过于密集 |
| `breakUpInternalMonologue` | 内心独白连续过长 |
| `insertActionBeats` | 动作节拍不足 |

这些修正函数体现了对 AI 生成文本常见缺陷的深刻理解。

---

## 七、亮点与创新

### 7.1 Slot-Based 解耦生成

这是本项目的核心创新。传统 AI 写作是"一次性生成全文"，而 NovelGenerator 将写作拆分为：

1. **结构层**（骨架）：决定叙事流向和情感节奏
2. **角色层**（对话+内心）：注入人物性格和情感深度
3. **场景层**（描写+动作）：构建沉浸感和画面感

这种解耦使得每个 Agent 可以专注于自己的维度，避免了"既要结构好、又要角色活、又要场景美"的多目标冲突。

### 7.2 6 策略 Slot 提取解析器

AI 模型返回的格式经常不稳定（多余空格、换行、编号变化等）。CharacterAgent 和 SceneAgent 各自实现了 **6 种策略的容错解析器**，确保即使 AI 输出格式有偏差，SLOT 内容也能被正确提取。这是工程实践中非常实用的设计。

### 7.3 情感曲线工程化

StructureAgent 的情感曲线控制不是模糊的"写好一点"，而是**量化为 4 段数值范围**（4-6 → 3-7 → 8-10 → 5-7），使得章节的情感节奏可以被精确控制。

### 7.4 纯前端架构

整个系统无需后端服务，直接在浏览器中调用 Gemini API。这降低了部署门槛，用户只需一个 API Key 即可使用。

### 7.5 内容修正后处理

Phase 4 的 5 个修正函数针对 AI 生成文本的典型缺陷（内心独白冗长、描写过密、动作节拍缺失等）进行定向修复，体现了"生成 + 后处理"的两阶段设计思想。

---

## 八、局限性与改进空间

### 8.1 局限性

| 局限 | 说明 |
|------|------|
| **仅支持 Gemini** | 硬绑定 Google Gemini，无法切换其他模型 |
| **无长篇管理** | 缺少跨章节的连贯性管理和上下文维护机制 |
| **无质量评估** | 没有 Reader/Reviewer 角色对生成内容进行评估 |
| **单模型编排** | 三个 Agent 使用同一个模型，无法按任务复杂度分配不同模型 |
| **无存储持久化** | 纯前端无数据库，刷新即丢失 |

### 8.2 对 Fiction Academy 的启示

1. **Slot-Based 思想可借鉴**：将章节创作拆分为结构/角色/场景三个维度是有效的分工策略
2. **情感曲线量化**：用数值范围控制情感节奏的方法可以直接复用
3. **内容修正函数库**：5 个修正函数是经过实践验证的"去 AI 味"工具
4. **6 策略解析器**：AI 输出格式不稳定的容错方案值得学习
5. **需要增强**：长篇管理、多模型路由、质量评估、持久化存储
