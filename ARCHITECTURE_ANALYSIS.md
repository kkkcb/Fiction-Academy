# 风行故事 — 架构分析与可化用设计模式

> 面向类似写小说项目的架构拆解，提炼可复用的核心设计模式

---

## 目录

1. [整体架构哲学](#1-整体架构哲学)
2. [核心设计模式提取](#2-核心设计模式提取)
3. [创作管线流转详解](#3-创作管线流转详解)
4. [AI 调度与多模型协作机制](#4-ai-调度与多模型协作机制)
5. [提示词工程架构](#5-提示词工程架构)
6. [数据流与状态管理](#6-数据流与状态管理)
7. [知识库与灵感系统](#7-知识库与灵感系统)
8. [流式通信架构 (SSE)](#8-流式通信架构-sse)
9. [本地优先与云端协同](#9-本地优先与云端协同)
10. [可化用清单：按优先级排序](#10-可化用清单按优先级排序)

---

## 1. 整体架构哲学

### 1.1 核心理念："工业管线"

风行故事将文学创作视为**工业制造流程**，而非单次 AI 对话。其核心思想是：

```
传统模式：  用户 → 一句话需求 → AI → 输出全文（质量不可控）

管线模式：  用户 → 金种 → 灵根 → 发枝 → 散叶 → 开花 → 点蕊 → 结果
                  梗概    逻辑    人设    正文    审计    张力    润色
                  ↓       ↓       ↓       ↓       ↓       ↓       ↓
               头脑风暴  架构师   写手   精修师   审计师   张力师   润色师
              (AI角色1) (AI角色2) ...     ...     ...     ...     ...
```

**可化用价值**：任何 AI 写作项目都应该将"一次生成"拆分为"多阶段流水线"，每个阶段由专门的 AI 角色负责，上阶段的输出作为下阶段的输入。这比一次生成质量高几个数量级。

### 1.2 架构分层

```
┌─────────────────────────────────────────┐
│          前端 (纯 HTML/JS/CSS)           │  ← 零框架、直接 DOM 操作
├─────────────────────────────────────────┤
│        Express API 层 (server.js)        │  ← 单文件巨石后端
├──────────┬──────────┬───────────────────┤
│ AI 服务层 │ 提示词层 │  数据库层 (SQLite) │  ← 三层核心抽象
├──────────┴──────────┴───────────────────┤
│     外部服务 (AI APIs / 云端 / Ollama)    │  ← 可插拔外部依赖
└─────────────────────────────────────────┘
```

**设计特点**：
- **单文件后端**（server.js ~3400 行）：快速迭代、零配置部署
- **SQLite 本地存储**：零运维、离线可用、单文件迁移
- **纯前端**：无需构建工具、直接浏览器运行

---

## 2. 核心设计模式提取

### 模式一：阶段式技能协议 (Stage-based Skill Protocol)

这是本项目最核心的设计模式。

```javascript
// 阶段与技能文件的映射表
const stageMap = {
    1: 'skills/skill_brainstorming.md',     // 头脑风暴
    2: 'skills/skill_plotting.md',           // 情节架构
    3: 'skills/skill_writing.md',            // 正文写作
    4: 'skills/skill_s04_refine.md',         // 精修
    5: 'skills/skill_s05_dianrui_tension.md', // 张力重塑
    6: 'skills/skill_s06_jieguo_polish.md',   // 最终润色
};
```

**运作方式**：

1. 每个创作阶段对应一个 **Markdown 技能文件**（SOP 协议）
2. 技能文件定义了该阶段 AI 的**角色、规则、输出格式**
3. 后端在运行时动态加载技能文件，替换占位符后注入 AI 上下文
4. 技能文件**本地优先、云端降级**（本地有就用本地的，没有就从云端拉）

**可化用方式**：

```
你的项目/
├── skills/                          ← 技能协议目录
│   ├── skill_outline.md             ← 大纲生成 SOP
│   ├── skill_chapter_write.md       ← 章节写作 SOP
│   ├── skill_character_design.md    ← 角色设计 SOP
│   └── skill_review.md              ← 审稿 SOP
├── server.js
└── ...
```

技能文件示例结构：

```markdown
# S02 情节架构师

## 你的角色
你是一位资深小说大纲架构师...

## 输入数据
- 初始梗概: {{金种}}
- 约束标签: {{标签}}

## 执行规则
1. 保持因果链严密
2. 拒绝工具人角色
...

## 输出格式
请按以下 JSON 格式输出：
{ "chapters": [...], "characters": [...] }
```

### 模式二：模板变量注入系统 (Template Variable Injection)

```javascript
// 变量定义表
const VariableDefinitions = [
    { key: '{{书名}}',   field: '书名',     desc: '小说名称' },
    { key: '{{金种}}',   field: '金种',     desc: 'S00 初期梗概' },
    { key: '{{灵根}}',   field: '灵根',     desc: 'S01 逻辑脉络' },
    { key: '{{散叶}}',   field: '散叶',     desc: 'S03 正文' },
    // ...每个阶段的输出都是下一个阶段的可用变量
];

// 替换逻辑
replace(text) {
    for (const def of VariableDefinitions) {
        const val = this.currentNovel[def.field] || '';
        result = result.split(def.key).join(val);
    }
    return result;
}
```

**可化用价值**：

- 任何阶段的 AI 提示词都可以通过 `{{变量名}}` 引用之前阶段的输出
- 变量定义集中管理，新增阶段只需扩展定义表
- 提示词模板与数据完全解耦——模板作者不需要知道数据从哪来

**在你的项目中可以这样用**：

```javascript
const VARS = [
    { key: '{{genre}}',       field: 'genre' },
    { key: '{{outline}}',     field: 'outline' },
    { key: '{{characters}}',  field: 'characters' },
    { key: '{{prevChapter}}', field: 'prev_chapter_content' },
    { key: '{{worldview}}',   field: 'worldview' },
];

function injectVariables(template, projectData) {
    let result = template;
    for (const v of VARS) {
        result = result.split(v.key).join(projectData[v.field] || '');
    }
    return result;
}
```

### 模式三：多 AI 角色配置 (Multi-AI Role Configuration)

```javascript
// 系统预置 5 个 AI 角色，每个角色有独立的模型/温度/密钥配置
// ID=1: 系统默认/灵根（头脑风暴）
// ID=2: 灵感设计师
// ID=3: 大纲架构师
// ID=4: 发布师
// ID=5: 绘图师
```

**设计要点**：
- 不同创作阶段可以使用不同的 AI 模型（比如创意阶段用 Claude，逻辑审计用 GPT-4）
- 每个角色有独立的温度参数（创意阶段温度高，审计阶段温度低）
- 用户可以自由配置和切换

**可化用方式**：

```javascript
// AI 配置表
const AI_ROLES = {
    'brainstorm': { model: 'claude-3-opus',  temperature: 0.9, role: '创意发散' },
    'architect':  { model: 'gpt-4',          temperature: 0.3, role: '逻辑架构' },
    'writer':     { model: 'deepseek-chat',  temperature: 0.7, role: '正文写作' },
    'reviewer':   { model: 'gpt-4',          temperature: 0.1, role: '审稿校对' },
};
```

### 模式四：SOP + 上下文双层组合 (SOP + Context Assembly)

这是提示词组装的核心模式：

```javascript
// 后端组装最终提示词
finalQuery = `【系统指令(SOP)】\n${skillText}\n\n---\n\n【用户上下文与任务】\n${userQuery}`;
```

**设计思路**：
- **SOP 层**（系统指令）：从技能文件加载，定义 AI 的角色、规则、输出格式
- **上下文层**（用户数据）：当前小说的所有阶段数据 + 用户的即时指令
- 两层分离，SOP 可独立更新（云端下发），不影响用户数据

**可化用价值**：你的项目中，每个创作环节都应该有固定的 SOP 协议，不要把所有规则都塞进一个 prompt 里。

### 模式五：渐进式数据库迁移 (Progressive Schema Migration)

```javascript
function initDb() {
    // 1. 创建基础表
    db.exec('CREATE TABLE IF NOT EXISTS 小说 (...)');

    // 2. 检查并添加新列（增量迁移）
    const existingCols = novelInfo.map(c => c.name);
    const newCols = ['金种', '灵根', '发枝', '散叶', '开花', '点蕊', '结果', ...];

    for (const col of newCols) {
        if (!existingCols.includes(col)) {
            db.prepare(`ALTER TABLE 小说 ADD COLUMN "${col}" TEXT`).run();
        }
    }
}
```

**可化用价值**：
- 不需要复杂的 ORM 或 migration 框架
- 每次启动自动检查并补齐缺失的列
- 向后兼容——老数据库升级后自动拥有新字段

---

## 3. 创作管线流转详解

### 3.1 完整生命周期

```
┌──────────── 灵感激荡 ────────────┐
│  用户选择：类型×情绪×时空          │
│       ↓                          │
│  电影DNA提取（本地知识库匹配）     │
│       ↓                          │
│  AI 生成灵感（金句 + 梗概）       │
│       ↓                          │
│  用户从灵感中选择 → 创建小说      │
└──────────────┬───────────────────┘
               ↓
┌──────────── 六阶段管线 ──────────────────────────────────────────────┐
│                                                                      │
│  S00 金种 ──→ S01 灵根 ──→ S02 发枝 ──→ S03 散叶 ──→ S04 开花 ──→ S05 点蕊 ──→ S06 结果 │
│  (用户输入)   (逻辑脉络)   (人设细节)   (正文生成)   (逻辑审计)   (张力优化)   (最终润色)   │
│      │           │           │           │           │           │           │       │
│      └───────────┴───────────┴───────────┴───────────┴───────────┴───────────┘       │
│                              ↓ 每阶段自动保存到 DB                                    │
│                                                                      │
└──────────────┬───────────────────────────────────────────────────────┘
               ↓
┌──────────── 扫地僧精炼（可选）───────────────────────────────────────┐
│  阶段1 → 阶段2 → ... → 阶段8                                        │
│  逻辑补全  修枝优化  比喻清理  形容词精简  句式修正  水词清洗  文风调整  排版   │
└─────────────────────────────────────────────────────────────────────┘
               ↓
┌──────────── 丹炉精炼（可选）─────────────────────────────────────────┐
│  本地 Ollama 模型做最终精炼                                          │
│  适合对隐私敏感或需要本地模型的场景                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 管线数据流转规则

1. **严格单向流动**：金种 → 灵根 → 发枝 → 散叶 → 开花 → 点蕊 → 结果，不可跳跃
2. **每阶段独立持久化**：每个阶段完成后单独保存到数据库的对应字段
3. **变量自动注入**：下一阶段的 AI 调用自动包含之前所有阶段的输出
4. **可回滚**：用户可以回到任意阶段重新生成

### 3.3 可化用的管线设计原则

| 原则 | 说明 | 你的项目可参考 |
|------|------|----------------|
| 阶段拆分 | 将复杂创作拆成 6-8 个独立阶段 | 大纲→角色→章节→审稿→润色 |
| 角色专业化 | 每个阶段有专属 AI 角色和 SOP | 写手、编辑、审校各司其职 |
| 上下文累积 | 后续阶段自动获得前序阶段输出 | 章节写作时自动带入大纲+角色设定 |
| 渐进精炼 | 先快速出粗稿，再逐层精修 | 先出初稿→逻辑审查→文笔润色→排版 |
| 人工介入点 | 关键节点允许用户编辑和确认 | 大纲确认、角色审核、章节审批 |

---

## 4. AI 调度与多模型协作机制

### 4.1 重试与容错

```javascript
// ai-service.js 核心逻辑
const callChatWithRetry = async (aiConfig, prompt) => {
    const maxRetries = 5;
    let retries = 0;

    while (retries < maxRetries) {
        // 429 限频：指数退避（2^n * 5s + 随机抖动）
        if (response.status === 429) {
            const waitTime = Math.pow(2, retries) * 5000 + (Math.random() * 2000);
            await new Promise(r => setTimeout(r, waitTime));
            retries++;
            continue;
        }

        // 401 密钥错误：静默拦截，不刷屏重试
        if (isAuthError) {
            throw new Error('AI API 未配置密钥或授权失败 (401)');
        }

        // 通用错误：固定 5s 重试
        await new Promise(r => setTimeout(r, 5000));
    }
};
```

**可化用要点**：
- 429（限频）用指数退避 + 随机抖动，避免雪崩
- 401（密钥错误）立即失败，不做无意义重试
- 兼容多种 AI API 格式（OpenAI 兼容、火山引擎等）

### 4.2 推理模式自动适配

```javascript
// 温度为空 → 自动启用 V4 深度推理模式
const isV4 = (aiConfig['温度'] === null || aiConfig['温度'] === '');

if (isV4) {
    payload.thinking = { type: 'enabled' };
    payload.reasoning_effort = aiConfig.reasoning_effort || 'high';
    payload.max_tokens = 65536;    // 推理模式给更多 token
} else {
    payload.temperature = parseFloat(aiConfig['温度']);
    payload.max_tokens = 8192;     // 普通模式限制
}
```

**可化用价值**：对于需要深度思考的创作环节（如逻辑审计、情节架构），可以自动切换到推理模式，给 AI 更多"思考空间"。

### 4.3 多模型回退策略

```javascript
// 指定 AI 不可用时，自动回退到第一个可用 AI
let ai = db.prepare('SELECT * FROM AI WHERE id = ?').get(targetId);
if (!ai || !ai['地址'] || !ai['密钥']) {
    ai = db.prepare(`
        SELECT * FROM AI
        WHERE "地址" IS NOT NULL AND "密钥" IS NOT NULL
        ORDER BY id ASC LIMIT 1
    `).get();
}
```

---

## 5. 提示词工程架构

### 5.1 三层提示词体系

```
┌─────────────────────────────────────────────────┐
│ 第一层：技能文件 (SOP)                            │
│ - Markdown 格式，独立文件                         │
│ - 定义 AI 角色、规则、输出格式                      │
│ - 本地优先，可云端更新                             │
│ - 包含占位符：${mbtiAwakening}, ${era}, ${genre}  │
├─────────────────────────────────────────────────┤
│ 第二层：数据库模板                                │
│ - 存储在 SQLite 的提示词模板表中                    │
│ - 包含占位符：{{金种}}, {{灵根}}, {{散叶}}         │
│ - 用户可自定义编辑                                │
├─────────────────────────────────────────────────┤
│ 第三层：运行时上下文                               │
│ - 当前小说的所有阶段数据                           │
│ - 用户的即时指令                                  │
│ - MBTI 人格、时代背景、类型标签等元数据             │
└─────────────────────────────────────────────────┘
```

### 5.2 动态占位符替换链

```
技能文件加载 → 替换 ${era}/${genre}/${tone} → 组合用户上下文 → 替换 {{金种}}/{{灵根}}/... → 发送给 AI
```

**可化用方式**：

```
你的提示词组装流程：
1. 加载 SOP 文件（定义角色和规则）
2. 替换全局变量（类型、风格、世界观）
3. 注入项目数据（大纲、角色、前文）
4. 追加用户即时指令
5. 发送给 AI
```

### 5.3 提示词模板的 CRUD 管理

```javascript
// 模板存储在数据库中，支持动态增删改
app.get('/api/templates', ...);          // 获取所有模板
app.post('/api/templates', ...);         // 新增/更新模板
app.delete('/api/templates/:id', ...);   // 删除模板
app.get('/api/prompt-template/:name', ...); // 按名称获取
```

**可化用价值**：让用户可以自定义和分享提示词模板，而不是硬编码在代码中。

---

## 6. 数据流与状态管理

### 6.1 前端状态管理（极简方案）

```javascript
// 全局变量管理器（单例模式）
window.NovelVariables = {
    currentNovel: null,           // 当前激活的小说（全量数据对象）
    setCurrentNovel(novel),       // 切换当前小说
    replace(text),                // 模板变量替换
    getCurrentValues()            // 获取所有变量快照
};
```

**设计特点**：
- **零状态管理框架**：不用 Redux/Vuex/Pinia
- **单源真相**：`currentNovel` 对象包含小说的所有阶段数据
- **纯函数替换**：`replace()` 是无副作用的模板渲染

### 6.2 数据持久化策略

```
前端 (localStorage)          后端 (SQLite)              云端 (Aliyun)
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│ Token/过期时间│ ──────→ │ 用户鉴权     │ ──────→ │ VIP 验证     │
│ UI 偏好      │         │ 小说全量数据  │         │ 系统配置下发 │
│ 窗口位置     │         │ 灵感数据     │         │ 技能文件     │
│ 收藏记录     │         │ AI 配置     │         │ 公告推送     │
└──────────────┘         │ 提示词模板   │         └──────────────┘
                         └──────────────┘
```

**可化用原则**：
- **创作数据永远在本地**：不依赖网络，不怕服务宕机
- **云端只做轻量同步**：鉴权、配置、公告
- **localStorage 只存 UI 状态**：不存创作数据（避免 5MB 限制）

### 6.3 阶段保存机制

```javascript
// 每个阶段独立保存，互不干扰
app.post('/api/novel/:id/save_step', (req, res) => {
    const { field, content } = req.body;
    // 只更新指定的阶段字段
    db.prepare(`UPDATE 小说 SET "${field}" = ? WHERE id = ?`).run(content, novelId);
});
```

**可化用价值**：不要每次保存都写整个小说对象，而是按阶段字段独立保存，减少数据冲突。

---

## 7. 知识库与灵感系统

### 7.1 电影 DNA 提取

这是项目最有创意的设计之一：

```
用户选择(类型=悬疑, 情绪=压抑, 时空=现代)
       ↓
movie_index.json 级联匹配
  ├── 第一轮：类型+情绪双维精确匹配
  ├── 第二轮：仅类型匹配（降级）
  └── 第三轮：全局随机盲抽（兜底）
       ↓
从 Story/xxx.md 读取电影故事
       ↓
截取 Blueprint 部分（脱水处理）
       ↓
注入到灵感生成提示词中
```

**防撞车机制**：

```javascript
// LRU 防撞车：记录近期已抽取的电影
const recentMovieMemory = new Set();       // 历史记录
const inFlightReservations = new Set();    // 并发预占座

// 抽取时排除已用和正在使用的
let available = candidates.filter(c =>
    !recentMovieMemory.has(c.name) &&
    !inFlightReservations.has(c.name)
);

// 容量超限时保留后半部分（类似 LRU 淘汰）
if (recentMovieMemory.size > 50) {
    const arr = Array.from(recentMovieMemory);
    recentMovieMemory.clear();
    arr.slice(25).forEach(m => recentMovieMemory.add(m));
}
```

**可化用方式**：

```
你的项目/
├── knowledge/                       ← 知识库目录
│   ├── index.json                   ← 标签索引
│   ├── 经典小说/
│   │   ├── 三体.md
│   │   └── 基地.md
│   └── 写作技法/
│       ├── 三幕式结构.md
│       └── 英雄之旅.md
└── ...
```

建立自己的创作知识库：
1. 每个知识条目打上标签（类型、情绪、节奏、视角）
2. 建立标签索引文件
3. 生成时根据用户需求级联匹配
4. 匹配到的知识作为 AI 上下文注入

### 7.2 灵感库缓存

```javascript
// 远程灵感库（带缓存）
let tishiciLibraryCache = null;

async function getLibrary() {
    if (tishiciLibraryCache) return tishiciLibraryCache;  // 命中缓存
    const res = await fetch('/api/skills/library');
    tishiciLibraryCache = await res.json();
    return tishiciLibraryCache;
}
```

---

## 8. 流式通信架构 (SSE)

### 8.1 重型 SSE 代理架构

这是项目处理长时间 AI 生成任务的核心架构：

```
浏览器                  Express                   AI API
  │                       │                        │
  │──POST /api/skill/generate──→                   │
  │                       │──建立 SSE 连接──→       │
  │                       │                        │
  │  ←──SSE: delta───    │  ←──stream chunk──     │
  │  ←──SSE: delta───    │  ←──stream chunk──     │
  │  ←──SSE: reasoning── │  ←──thinking chunk──   │
  │  ←──SSE: delta───    │  ←──stream chunk──     │
  │                       │                        │
  │──用户关闭页面──→       │                        │
  │                       │──destroy upstream──→   │  ← 物理断连
```

### 8.2 关键设计细节

```javascript
// 1. 物理剥夺 Node.js 的自动 Socket 释放
req.socket.setTimeout(0);

// 2. 15s 心跳保活（对抗网关/浏览器 Idle Timeout）
const heartbeatInterval = setInterval(() => {
    if (!res.writableEnded) {
        res.write(': keep-alive\n\n');  // SSE 注释格式
    }
}, 15000);

// 3. 20分钟上游超时
timeout: 1200000

// 4. 客户端断开 → 物理销毁上游请求
res.on('close', () => {
    upstreamReq.destroy();  // 不是 abort()，是物理销毁
});

// 5. 原生 http 模块（非 fetch），获得 Socket 绝对控制权
const transport = parsedUrl.protocol === 'https:' ? require('https') : require('http');
```

**可化用价值**：

如果你的项目需要长时间 AI 生成（超过 30 秒），这套 SSE 架构是最佳实践：
- 不要用 fetch/axios 代理流式请求，用原生 `http.request`
- 心跳保活防止中间层超时
- 客户端断开时主动销毁上游连接（省钱省 token）

### 8.3 双流透传（内容 + 推理）

```javascript
// 同时透传正式内容和推理过程
if (reasoning_content) {
    res.write(`data: ${JSON.stringify({ reasoning_content })}\n\n`);
}
if (delta) {
    res.write(`data: ${JSON.stringify({ delta })}\n\n`);
}
```

---

## 9. 本地优先与云端协同

### 9.1 配置合并策略

```
本地 SQLite (SystemConfig 表)
    ↓ 基础值
云端 API (/api/v1/public_configs)
    ↓ 覆盖值（云端优先）
    ↓
合并后返回给前端
```

**可化用原则**：
- 本地存默认值，云端覆盖——断网也能用默认配置
- 技能文件本地优先——开发者可以本地调试 SOP

### 9.2 技能文件双源加载

```javascript
// 本地优先
if (fs.existsSync(localSkillPath)) {
    skillText = fs.readFileSync(localSkillPath, 'utf8');
} else {
    // 云端降级
    const remoteRes = await fetch(`http://云端/api/v1/tishici/knowledge/${skillFilePath}`);
    skillText = remoteData.content;
}
```

**可化用方式**：你的提示词模板系统也应该支持本地文件 + 云端存储双源，方便开发和迭代。

---

## 10. 可化用清单：按优先级排序

### ⭐⭐⭐ 高优先级（强烈建议化用）

| # | 设计模式 | 化用价值 | 实现难度 |
|---|---------|---------|---------|
| 1 | **阶段式技能协议** | 将创作拆为多阶段流水线，每阶段有独立 SOP | 低 |
| 2 | **模板变量注入** | `{{变量}}` 占位符系统，提示词与数据解耦 | 低 |
| 3 | **SSE 流式代理** | 长时间 AI 生成的最佳通信方案 | 中 |
| 4 | **AI 重试与容错** | 指数退避 + 401 静默拦截 + 多模型回退 | 低 |
| 5 | **渐进式 DB 迁移** | 零框架的数据库自动升级方案 | 低 |

### ⭐⭐ 中优先级（建议参考）

| # | 设计模式 | 化用价值 | 实现难度 |
|---|---------|---------|---------|
| 6 | **多 AI 角色配置** | 不同阶段用不同模型和温度 | 中 |
| 7 | **知识库 + 标签匹配** | 创作素材的智能检索和注入 | 中 |
| 8 | **LRU 防撞车** | 并发请求时避免重复素材 | 低 |
| 9 | **推理模式自动适配** | 深度思考环节自动切换 CoT 模式 | 低 |
| 10 | **本地优先 + 云端降级** | 离线可用、开发友好 | 中 |

### ⭐ 低优先级（锦上添花）

| # | 设计模式 | 化用价值 | 实现难度 |
|---|---------|---------|---------|
| 11 | **硬件指纹鉴权** | 防止账号共享（商业化需要） | 高 |
| 12 | **悬浮窗组件** | 可拖拽的浮动 UI 面板 | 低 |
| 13 | **丹炉（Ollama 本地精炼）** | 本地模型做最终精修 | 中 |
| 14 | **动态背景系统** | Pexels 随机背景 + 交叉淡入 | 低 |

---

### 快速起步建议

如果你的项目要化用这套架构，建议按以下顺序实现：

```
第1周：搭建基础骨架
├── SQLite 数据库 + 自动迁移
├── Express API 层
└── 基础 CRUD（项目/章节管理）

第2周：实现 AI 管线核心
├── AI 服务封装（重试 + 多模型）
├── SSE 流式代理
├── 技能文件系统（SOP 协议）
└── 模板变量注入

第3周：创作管线搭建
├── 阶段映射表
├── 上下文累积机制
├── 章节级流式生成
└── 进度保存与回滚

第4周：知识库与增强
├── 素材知识库 + 标签索引
├── 灵感生成系统
└── 提示词模板管理 UI
```

---

> 本文档基于风行故事项目完整源码分析生成，聚焦于可化用的架构模式和设计思想。
