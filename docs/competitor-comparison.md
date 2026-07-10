# 竞品架构对比：风行故事 vs Fiction Academy

> 基于风行故事源码分析文档，与 Fiction Academy 当前实现做批判性对比

---

## 一、架构哲学对比

| 维度 | 风行故事 | Fiction Academy | 评价 |
|------|---------|-----------------|------|
| 核心理念 | **工业管线** — 创作是流水线 | **对话共创** — 创作是聊天 | 两种思路互补，不是替代 |
| 架构风格 | 单文件巨石（server.js 3400行） | 分层模块（backend/api/ 多文件） | ✅ 我们的更清晰 |
| 前端框架 | 纯 HTML/JS，零框架 | 纯 HTML/JS，零框架 | 一致 |
| 数据库 | SQLite | SQLite | 一致 |
| AI 调用 | 多模型可配置，有重试/回退 | 单模型（小米 MiMo），无重试 | ❌ 我们缺容错 |

**结论**：架构层面我们更干净，但缺少健壮性（重试、多模型回退）。

---

## 二、我们比他们做得好的

### 2.1 三层知识模型（独有）

风行故事没有「作者全知 vs 读者已知 vs 伏笔」的概念。所有信息对 AI 都是等价的。

我们有 truth / revealed / foreshadow 三层，这对小说创作至关重要——因为小说的核心魅力就是**信息不对称**。

**优势保持**：这是我们的核心差异化，必须持续深化。

### 2.2 编年史系统（独有）

风行故事没有时间线追踪。他们的阶段是「金种→灵根→发枝→散叶」这种加工管线，不是故事内的时间线。

我们有 chronicle 表，追踪：
- 时间线推进
- 角色状态变化
- 未解决伏笔

**优势保持**：编年史是连载小说的刚需。

### 2.3 工作台状态机（更好）

风行故事的阶段是线性的：上一个阶段完成才能进入下一个。

我们的 workspace_items 有 `draft → finalized → locked` 状态机，更灵活——用户可以同时维护多个草稿，按需定稿。

### 2.4 统合文档架构（更好）

我们的「同类型一个文档，新内容以 ## 副标题追加」比风行故事的「每个阶段独立字段」更实用。因为小说设定是渐进积累的，不是一次成型的。

### 2.5 可定制助理系统（更好）

风行故事的 AI 角色是固定的（头脑风暴、架构师、写手、审校等），硬编码在代码里。

我们的助理支持用户自定义 system_prompt、名称、描述，甚至指定模型。更灵活。

---

## 三、值得我们借鉴的

### 3.1 🔴 高优先级：SOP 文件外部化

**他们怎么做**：
```
skills/
├── skill_brainstorming.md     ← 头脑风暴 SOP
├── skill_plotting.md           ← 情节架构 SOP
├── skill_writing.md            ← 正文写作 SOP
├── skill_s04_refine.md         ← 精修 SOP
└── ...
```

每个创作阶段对应一个 Markdown 文件，定义 AI 角色、规则、输出格式。

**我们现在的问题**：
```python
# workspace.py 里硬编码了所有 prompt
SUMMARIZE_MSG_PROMPTS = { ... }
SYNC_WORKSPACE_PROMPT = """..."""
INSPIRATION_PROMPT = """..."""
```

prompt 散落在 Python 代码里，修改需要改代码重启服务。

**建议改造**：
```
backend/prompts/                    ← 新建目录
├── chat_default.md                 ← 默认对话 prompt
├── summarize_world.md              ← 世界观总结 SOP
├── summarize_character.md          ← 角色总结 SOP
├── summarize_outline.md            ← 大纲总结 SOP
├── summarize_chapter.md            ← 章节总结 SOP
├── sync_workspace.md               ← 同步工作台 SOP
├── inspiration.md                  ← 灵感笔记 SOP
├── chronicle_update.md             ← 编年史更新 SOP
├── extract_questions.md            ← 待确认提取 SOP
└── kg_extract.md                   ← 知识图谱提取 SOP（未来）
```

好处：
- 修改 prompt 不用改代码，不用重启
- 可以做 prompt 版本管理
- 未来可以让用户自定义 prompt

### 3.2 🔴 高优先级：模板变量注入

**他们怎么做**：
```javascript
const VARS = [
    { key: '{{金种}}',  field: '金种' },
    { key: '{{灵根}}',  field: '灵根' },
    { key: '{{散叶}}',  field: '散叶' },
];
function inject(template, data) {
    for (const v of VARS) {
        template = template.split(v.key).join(data[v.field] || '');
    }
    return template;
}
```

**我们现在的问题**：
```python
# chat.py 里用 f-string 拼接
context_parts = []
if world_setting:
    context_parts.append(f"【世界观设定】\n{world_setting}")
if chronicle_data:
    context_parts.append(f"【编年史】\n{chronicle_data}")
```

每新增一种上下文就要改 Python 代码。

**建议改造**：
```python
VARIABLES = [
    ('{{world_setting}}',      lambda p: get_locked_content(p, 'world_setting')),
    ('{{character_setting}}',  lambda p: get_locked_content(p, 'character_setting')),
    ('{{outline}}',            lambda p: get_locked_content(p, 'outline')),
    ('{{chronicle}}',          lambda p: get_chronicle_text(p)),
    ('{{prev_chapters}}',      lambda p: get_prev_chapters_summary(p)),
    ('{{genre}}',              lambda p: get_genre(p)),
]

def inject_prompt(template_path: str, project_id: str) -> str:
    template = load_prompt_file(template_path)
    for key, resolver in VARIABLES:
        template = template.replace(key, resolver(project_id) or '')
    return template
```

### 3.3 🟡 中优先级：AI 调用重试与容错

**他们怎么做**：
- 429 限频：指数退避（2^n × 5s + 随机抖动）
- 401 密钥错误：立即失败，不重试
- 多模型回退：指定模型不可用时自动切换

**我们现在的问题**：
```python
# base.py — 零容错，失败直接抛异常
stream = await client.chat.completions.create(...)
```

没有任何重试机制，网络抖动就直接报错。

**建议改造**（简单版）：
```python
async def chat_stream_with_retry(messages, system_prompt=None, model="", max_retries=3):
    for attempt in range(max_retries):
        try:
            async for chunk in chat_stream(messages, system_prompt, model):
                yield chunk
            return
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait = (2 ** attempt) * 3 + random.random() * 2
            logger.warning("LLM call failed (attempt %d), retry in %.1fs: %s", attempt + 1, wait, e)
            await asyncio.sleep(wait)
```

### 3.4 🟡 中优先级：阶段式创作管线

**他们怎么做**：
```
金种 → 灵根 → 发枝 → 散叶 → 开花 → 点蕊 → 结果
梗概    逻辑    人设    正文    审计    张力    润色
```

每个阶段有专属 AI 角色，上阶段输出自动注入下阶段。

**我们现在的状态**：

我们已经有雏形了（workspace 的 4 种 item_type），但缺少：
- 阶段间的自动衔接（写完大纲不会自动建议下一步）
- 每个阶段的专属 SOP（所有对话共用一个默认 prompt）
- 创作进度可视化（用户不知道下一步该做什么）

**建议**（与 Goal 模式结合）：
- 检测项目当前阶段（有大纲吗？有角色吗？有章节吗？）
- 在 UI 上显示创作进度条
- AI 对话时根据当前阶段自动选择 SOP
- 每个阶段完成时提示下一步

### 3.5 🟢 低优先级：知识库标签匹配

**他们怎么做**：
- 维护一个电影故事知识库，每条打标签（类型、情绪、节奏）
- 用户选灵感时，级联匹配（精确→类型→随机）
- LRU 防撞车，避免重复推荐

**我们可以参考**：
- 建立写作技法知识库（三幕式、英雄之旅、起承转合...）
- 按小说类型和当前情节匹配推荐技法
- 这个和世界观模板体系（Phase 5）可以结合

### 3.6 🟢 低优先级：推理模式自动适配

**他们怎么做**：
- 逻辑审计、情节架构等需要深度思考的环节，自动切换到 CoT 推理模式
- 温度为空时自动启用深度推理

**我们可以参考**：
- 编年史更新、一致性检测等任务用低温度
- 创意发散、灵感生成用高温度
- 当前我们的温度全部硬编码为 0.8

---

## 四、不建议借鉴的

| 他们的做法 | 不建议的原因 |
|-----------|------------|
| 单文件巨石后端 3400 行 | 维护困难，我们的分层更清晰 |
| 固定 7 阶段管线不可跳跃 | 太死板，创作不应该强制线性 |
| 电影 DNA 灵感系统 | 与我们的定位不符，我们是创作工具不是灵感工具 |
| 硬件指纹鉴权 | 过早考虑商业化 |
| Ollama 本地精炼 | 增加复杂度，当前阶段不必要 |

---

## 五、行动计划

按优先级排序，与现有 TODO 对齐：

| 优先级 | 改造项 | 对应 TODO | 预估 |
|--------|-------|----------|------|
| 🔴 高 | Prompt 外部化为 Markdown 文件 | 新增 | 2h |
| 🔴 高 | 模板变量注入系统 | Phase 1.1（上下文注入） | 2h |
| 🟡 中 | AI 调用重试容错 | 新增 | 1h |
| 🟡 中 | 创作阶段检测 + 进度提示 | Phase 4（Goal 模式） | — |
| 🟡 中 | 按任务类型调整温度 | 新增 | 30min |
| 🟢 低 | 写作技法知识库 | Phase 5（世界观模板） | — |

**建议**：在 Phase 0 清理代码时，顺手把 prompt 外部化 + 重试容错做了，投入不大但收益明显。

---

## 六、工作流哲学对比

### 风行故事：管线驱动（工厂模式）

```
用户输入一句话灵感
       ↓
  ┌─ 系统接管 ──────────────────────────────────────────────┐
  │                                                          │
  │  S00 金种    用户输入梗概                                  │
  │    ↓                                                     │
  │  S01 灵根    AI自动生成逻辑脉络 ← 注入金种                  │
  │    ↓                                                     │
  │  S02 发枝    AI自动生成人设 ← 注入金种+灵根                 │
  │    ↓                                                     │
  │  S03 散叶    AI自动写正文 ← 注入金种+灵根+发枝              │
  │    ↓                                                     │
  │  S04 开花    AI自动审计逻辑 ← 注入全文                      │
  │    ↓                                                     │
  │  S05 点蕊    AI自动优化张力 ← 注入全文+审计结果              │
  │    ↓                                                     │
  │  S06 结果    AI自动润色 ← 注入全部                         │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
       ↓
  成品输出（用户全程几乎不需要动脑）
```

特点：严格线性、不可跳跃、每步有专属 AI 角色、上步输出自动注入下步。

### Fiction Academy：对话驱动（工作室模式）

```
用户创建项目
       ↓
  ┌─ 自由对话 ──────────────────────────────────────────────┐
  │                                                          │
  │  用户: "我想写一个修仙世界..."                              │
  │  AI: 回复设定建议 → 📝 总结 → 存为「世界观」               │
  │                                                          │
  │  用户: "主角叫张三..."                                    │
  │  AI: 回复角色建议 → 📝 总结 → 补充到「角色设定」            │
  │                                                          │
  │  用户: "帮我写第一章"                                     │
  │  AI: 写正文（自动注入世界观+角色+编年史）                   │
  │    → 📝 总结 → 存为「章节」→ finalized → 编年史自动更新     │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
       ↓
  用户随时可以回头改设定、加角色、重写章节
```

特点：自由对话、用户决定节奏、手动沉淀知识、可随时回头修改。

### 核心差异

> **风行故事 = 工厂流水线**，一键出成品，用户被动接受
> **Fiction Academy = 作家工作室**，自由创作，用户主动掌控

| | 风行故事 | Fiction Academy |
|--|---------|-----------------|
| 优点 | 上手快，零门槛，一键出文 | 自由度高，设定可深度迭代 |
| 缺点 | 死板，改一个设定要重跑管线 | 用户需要自己组织工作流 |
| 适合 | 想快速出网文的新手 | 想认真打磨作品的作者 |
| 最大问题 | 无法迭代——改了世界观后面的不会自动更新 | 缺少引导——新手不知道下一步该做什么 |

### 可借鉴方向：可选引导层

不照搬管线，而是加一层**可选的创作进度引导**：

```
┌──────────────────────────────────────┐
│  📋 大纲  ✅ 已完成                    │
│  🌍 世界观  ✅ 已完成                  │
│  👤 角色设定  ⚠️ 草稿中               │
│  📖 第1章  ⬜ 未开始                   │
│  📖 第2章  ⬜ 未开始                   │
│                                      │
│  💡 建议下一步：完善角色设定            │
└──────────────────────────────────────┘
```

保留自由度的同时给方向感，即 Goal 模式的轻量版——不强制执行，只提示建议。

对应 TODO Phase 4（Goal 模式）中的创作阶段检测功能。

---

## 七、html-anything 启发：富格式输出层

> 来源：https://mp.weixin.qq.com/s/QgiNczY1L3XHIW2INcReAw
> 项目：https://github.com/nexu-io/html-anything
> 核心理念：Markdown 是草稿，HTML 才是成品

### 现状问题

工作台内容以 Markdown 存储，展示时只做了最基础的渲染，体验平淡。

### 可演进方向

```
现在的数据流：
  对话 → Markdown → 存到工作台 → 简单渲染展示

演进为：
  对话 → Markdown（存储层）→ HTML（展示/导出层）→ 多平台发布
```

### 短期：HTML 模板渲染（提升可视化体验）

| 内容类型 | 现在 | 可以做到 |
|---------|------|---------|
| 角色卡 | Markdown 列表 | 卡片式布局 + 属性条 + 关系标签 |
| 编年史 | 纯文本列表 | 交互式时间轴，点击展开事件 |
| 世界观 | 长文 Markdown | 分层折叠面板，按类别浏览 |
| 知识图谱 | 无 | Canvas 力导向图（已规划） |

### 长期：多平台导出（创作到发布闭环）

网文作者最终要发布到各平台，支持一键导出：

| 导出格式 | 目标平台 | 说明 |
|---------|---------|------|
| 起点中文网格式 | 起点中文网 | 章节分段、自动排版 |
| 微信公众号排版 | 微信公众号 | CSS 内联，直接粘贴 |
| PDF / ePub | 通用 | 离线阅读、投稿 |
| Markdown | 通用 | 纯文本备份 |

### 与现有 TODO 的关系

- 短期 HTML 模板渲染 → 归入 Phase 5（体验打磨）
- 长期多平台导出 → 新增为独立 Phase 或归入 v2.0+
