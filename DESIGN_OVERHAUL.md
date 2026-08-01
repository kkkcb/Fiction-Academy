# Fiction Academy 前端视觉重构设计方案

> 本方案为完整可交付给另一个 AI 执行的设计实施文档。包含：现状诊断、全局设计系统、11 个组件/页面的逐条改造规范、SVG 图标清单、动效规范、实现步骤与验收标准。

---

## 一、项目背景与现状诊断

### 1.1 当前代码结构

新版前端位于 `frontend-vue/`，已 100% TypeScript 化。主要文件：

```
src/
├── App.vue                    # 路由容器：projects / workspace
├── components/
│   ├── ProjectsPage.vue       # 项目列表页（首屏）
│   ├── WorkspacePage.vue      # 工作区三栏布局容器
│   ├── Sidebar.vue            # 左侧边栏（点位导航 + 自由对话）
│   ├── MessageList.vue        # 消息滚动区
│   ├── ChatMessage.vue        # 单条消息组件
│   ├── ChatInput.vue          # 输入框 + 斜杠命令弹窗
│   ├── ConsultFlow.vue        # 专家圆桌会诊视图
│   ├── OverviewPanel.vue      # 右侧设定/编年录面板
│   ├── ThinkingBlock.vue      # AI 思考过程折叠块
│   └── ToastHost.vue          # 全局 Toast 通知
├── styles/main.css            # 2369 行，全局样式核心
├── utils/format.ts            # 常量、标签、格式化函数
└── types/index.ts             # 类型定义
```

### 1.2 当前视觉问题

| 问题 | 影响 | 位置 |
|---|---|---|
| emoji 作为图标/头像 | 廉价感、风格不统一 | 空状态、斜杠命令、专家头像、思考块、Toast |
| 项目卡片样式曾完全失效 | 首屏最丑（已临时修复基础版） | ProjectsPage |
| 全系统字体为系统默认 | 缺乏高级感与品牌气质 | 全局 |
| 背景为纯色/简单渐变 | 扁平、无沉浸感 | 全局 |
| 侧边栏无玻璃拟态 | 与主内容区分隔感弱 | Sidebar |
| 消息气泡设计简陋 | 对话区像简陋聊天框 | ChatMessage |
| 专家圆桌 emoji 头像 | 破坏「AI 专家」的高级感 | ConsultFlow |
| 按钮/输入框视觉不统一 | 组件状态感知弱 | 全局 |
| 无暗色主题 | 长时间写作刺眼 | 全局 |
| 动效过于简单或缺失 | 交互反馈弱 | 全局 |

### 1.3 本次重构范围

**全量视觉重构**，不动业务逻辑，不动 TypeScript 类型。改造覆盖：

1. 全局设计系统升级（CSS 变量、双主题、字体、间距、阴影、玻璃拟态）
2. SVG 图标系统替换全部 emoji
3. 11 个组件/页面逐一视觉改造
4. 全局动效系统
5. 深色模式支持

---

## 二、设计目标

为 Fiction Academy 打造 **"暖调文学编辑器"** 的高级视觉风格：

- **文学气质**：衬线标题 + 暖白纸张质感，像打开一本精装手稿
- **沉浸式写作**：弱化 UI 存在感，突出对话与内容本身
- **专业可信**：克制的高级橙铜色强调，无花哨渐变
- **双主题支持**：浅色（日间）+ 深色（夜间写作）
- **全 SVG 图标**：彻底消除 emoji
- **细腻动效**：每个交互都有 100-300ms 的优雅反馈

---

## 三、全局设计系统

### 3.1 CSS 变量系统（核心）

替换/升级 `src/styles/main.css` 中 `:root` 的全部变量为以下系统：

```css
:root {
  /* === 浅色主题 === */
  --bg-page: #fbfaf9;
  --bg-page-gradient: radial-gradient(ellipse 90% 60% at 50% -10%, rgba(197, 93, 59, 0.08), transparent 60%),
                      linear-gradient(180deg, #fbfaf9 0%, #f7f4f0 100%);
  --bg-card: #ffffff;
  --bg-card-hover: #fdfcfa;
  --bg-secondary: #f5f2ee;
  --bg-tertiary: #eeeae5;
  --bg-input: #ffffff;
  --bg-hover: rgba(197, 93, 59, 0.05);
  --bg-active: rgba(197, 93, 59, 0.10);

  --text-primary: #1a1715;
  --text-secondary: #5e5853;
  --text-tertiary: #9c9690;
  --text-muted: #b8b2ab;

  --accent: #c55d3b;
  --accent-hover: #a64a2e;
  --accent-light: rgba(197, 93, 59, 0.10);
  --accent-lighter: rgba(197, 93, 59, 0.06);
  --accent-border: rgba(197, 93, 59, 0.25);
  --accent-glow: rgba(197, 93, 59, 0.18);

  --border-color: #e8e4e0;
  --border-subtle: rgba(0, 0, 0, 0.05);
  --border-strong: #d9d4ce;

  --status-draft: #78716c;
  --status-draft-bg: rgba(120, 113, 108, 0.10);
  --status-finalized: #2d7a5e;
  --status-finalized-bg: rgba(45, 122, 94, 0.10);
  --status-locked: #b8860b;
  --status-locked-bg: rgba(184, 134, 11, 0.10);

  --danger: #dc2626;
  --danger-bg: rgba(220, 38, 38, 0.08);

  /* 阴影系统 */
  --shadow-xs: 0 1px 2px rgba(26, 23, 21, 0.04);
  --shadow-sm: 0 1px 3px rgba(26, 23, 21, 0.05), 0 1px 2px rgba(26, 23, 21, 0.03);
  --shadow-md: 0 4px 16px rgba(26, 23, 21, 0.06), 0 1px 3px rgba(26, 23, 21, 0.03);
  --shadow-lg: 0 12px 32px rgba(26, 23, 21, 0.08), 0 2px 8px rgba(26, 23, 21, 0.03);
  --shadow-xl: 0 24px 56px rgba(26, 23, 21, 0.10), 0 4px 12px rgba(26, 23, 21, 0.04);
  --shadow-glow: 0 8px 24px rgba(197, 93, 59, 0.16);

  /* 字体系统 */
  --font-serif: 'Noto Serif SC', 'Source Han Serif SC', Georgia, serif;
  --font-sans: 'Noto Sans SC', -apple-system, 'PingFang SC', sans-serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;

  /* 间距系统（4px 基准） */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;

  /* 圆角系统 */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --radius-xl: 20px;
  --radius-full: 9999px;

  /* 动效系统 */
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1);
  --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
  --duration-fast: 120ms;
  --duration-normal: 200ms;
  --duration-slow: 350ms;

  /* 玻璃拟态（浅色） */
  --glass-bg: rgba(255, 255, 255, 0.78);
  --glass-border: rgba(255, 255, 255, 0.60);
}
```

### 3.2 深色主题变量

通过 `html[data-theme="dark"]` 覆盖：

```css
html[data-theme="dark"] {
  --bg-page: #12100e;
  --bg-page-gradient: radial-gradient(ellipse 90% 60% at 50% -10%, rgba(217, 139, 110, 0.10), transparent 60%),
                      linear-gradient(180deg, #12100e 0%, #1a1714 100%);
  --bg-card: #1a1714;
  --bg-card-hover: #211d19;
  --bg-secondary: #1f1b17;
  --bg-tertiary: #2a2520;
  --bg-input: #211d19;
  --bg-hover: rgba(217, 139, 110, 0.06);
  --bg-active: rgba(217, 139, 110, 0.12);

  --text-primary: #f3f0ed;
  --text-secondary: #b8b0a8;
  --text-tertiary: #6b655e;
  --text-muted: #4a4540;

  --accent: #d98b6e;
  --accent-hover: #e6a88e;
  --accent-light: rgba(217, 139, 110, 0.12);
  --accent-lighter: rgba(217, 139, 110, 0.06);
  --accent-border: rgba(217, 139, 110, 0.30);
  --accent-glow: rgba(217, 139, 110, 0.22);

  --border-color: #2d2824;
  --border-subtle: rgba(255, 255, 255, 0.05);
  --border-strong: #3d3630;

  --status-draft: #a8a29e;
  --status-draft-bg: rgba(168, 162, 158, 0.10);
  --status-finalized: #4ade80;
  --status-finalized-bg: rgba(74, 222, 128, 0.10);
  --status-locked: #fbbf24;
  --status-locked-bg: rgba(251, 191, 36, 0.10);

  --shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.25);
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.30), 0 1px 2px rgba(0, 0, 0, 0.20);
  --shadow-md: 0 4px 16px rgba(0, 0, 0, 0.35), 0 1px 3px rgba(0, 0, 0, 0.25);
  --shadow-lg: 0 12px 32px rgba(0, 0, 0, 0.40), 0 2px 8px rgba(0, 0, 0, 0.25);
  --shadow-xl: 0 24px 56px rgba(0, 0, 0, 0.45), 0 4px 12px rgba(0, 0, 0, 0.30);
  --shadow-glow: 0 8px 24px rgba(217, 139, 110, 0.20);

  --glass-bg: rgba(26, 23, 20, 0.78);
  --glass-border: rgba(255, 255, 255, 0.08);
}
```

### 3.3 主题切换实现

1. 在 `src/utils/theme.ts` 新建主题工具：
   - `getTheme(): 'light' | 'dark'` 读取 `localStorage` 或系统偏好
   - `setTheme(theme)` 设置 `document.documentElement.dataset.theme`
   - `toggleTheme()` 切换
2. 在 `src/main.js` 初始化时调用 `setTheme(getTheme())`
3. 在 `App.vue` 或 `WorkspacePage.vue` 右上角添加主题切换按钮（月亮/太阳 SVG）

### 3.4 字体系统

已在 `index.html` 引入 Google Fonts：

```html
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;600;700&family=Noto+Serif+SC:wght@500;700;900&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
```

**字体用途规范**：

| 用途 | 字体 | 示例 |
|---|---|---|
| 页面大标题/书名 | var(--font-serif) | Fiction Academy、项目名称 |
| 正文/UI 文字 | var(--font-sans) | 按钮、消息、描述 |
| 标签/徽章/代码 | var(--font-mono) | 体裁标签、状态徽章 |

### 3.5 字号层级

| 层级 | 字号 | 字重 | 行高 | 字距 | 用途 |
|---|---|---|---|---|---|
| Display | 44px | 900 | 1.1 | -0.04em | 首屏大标题 |
| H1 | 28px | 800 | 1.2 | -0.03em | 页面标题 |
| H2 | 20px | 700 | 1.3 | -0.02em | 卡片标题 |
| H3 | 16px | 700 | 1.4 | 0 | 小标题 |
| Body | 15px | 400 | 1.65 | 0 | 长文本 |
| UI | 13px | 500 | 1.4 | 0 | 导航、按钮 |
| Caption | 11px | 500 | 1.3 | 0.08em uppercase | 标签、徽章 |

### 3.6 全局玻璃拟态

用于顶部栏、侧边栏、浮动面板：

```css
.glass {
  background: var(--glass-bg);
  backdrop-filter: blur(16px) saturate(180%);
  -webkit-backdrop-filter: blur(16px) saturate(180%);
  border-bottom: 1px solid var(--glass-border);
}
```

### 3.7 全局动效关键帧

在 `main.css` 中补充/统一：

```css
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
```

---

## 四、SVG 图标系统

### 4.1 图标规范

- 全部使用内联 SVG，禁止用 emoji 作为图标
- viewBox="0 0 24 24" 为主，少量 16×16
- stroke-width="1.5"，stroke-linecap="round"，stroke-linejoin="round"
- 颜色使用 `currentColor`，便于通过 CSS 控制

### 4.2 图标清单与替换映射

| 当前 emoji | 位置 | 替换为 SVG | 建议 svg 文件名/组件 |
|---|---|---|---|
| ✍️ (空状态) | MessageList | 羽毛笔/铅笔图标 | `icon-write` |
| 💬 (空状态) | MessageList | 对话气泡图标 | `icon-chat` |
| 🎯 (专家会诊命令) | ChatInput/ChatMessage/format.ts | 靶心图标 | `icon-target` |
| ⚡ (快速生成命令) | ChatInput/ChatMessage/format.ts | 闪电图标 | `icon-bolt` |
| 💭 (思考块) | ThinkingBlock | 云/大脑图标 | `icon-thinking` |
| ⚖️ (终局裁决) | ConsultFlow | 天平图标 | `icon-scale` |
| 🌍 (世界观专家) | format.ts EXPERT_ICONS | 地球图标 | `icon-globe` |
| 👤 (人物专家) | format.ts EXPERT_ICONS | 人物轮廓图标 | `icon-user` |
| 🔁 (逆向架构师) | format.ts EXPERT_ICONS | 循环箭头图标 | `icon-refresh` |
| 🎬 (节奏导演) | format.ts EXPERT_ICONS | 导演板/播放图标 | `icon-clapper` |
| 🎯 (主线策划) | format.ts EXPERT_ICONS | 靶心图标 | `icon-target` |
| ⚠️ (Toast 错误) | ToastHost | 警告三角图标 | `icon-alert` |
| ✓ (Toast 成功) | ToastHost | 对勾图标 | `icon-check` |
| ℹ (Toast 信息) | ToastHost | 信息图标 | `icon-info` |

### 4.3 专家头像 SVG 实现

在 `src/components/icons/ExpertAvatar.vue` 新建组件，接受 `name` prop，返回对应几何 SVG：

```vue
<script setup lang="ts">
const props = defineProps<{ name: string; size?: number }>()
const colorMap: Record<string, string> = {
  '主线策划': '#c55d3b',
  '世界观架构师': '#7c3aed',
  '人物塑造师': '#0891b2',
  '逆向架构师': '#059669',
  '节奏导演': '#db2777',
}
const bg = (colorMap[props.name] || '#78716c') + '1a'
</script>
```

每个专家对应一个抽象几何图形：
- 主线策划：同心圆靶心
- 世界观架构师：六边形/网格球
- 人物塑造师：人脸轮廓
- 逆向架构师：双向箭头
- 节奏导演：节拍波形

### 4.4 图标组件化

推荐在 `src/components/icons/` 目录创建以下单文件组件（每个组件一个 `.vue`）：

```
src/components/icons/
├── IconWrite.vue
├── IconChat.vue
├── IconTarget.vue
├── IconBolt.vue
├── IconThinking.vue
├── IconScale.vue
├── IconGlobe.vue
├── IconUser.vue
├── IconRefresh.vue
├── IconClapper.vue
├── IconAlert.vue
├── IconCheck.vue
├── IconInfo.vue
├── IconMoon.vue
├── IconSun.vue
├── IconMenu.vue
├── IconChevronDown.vue
├── IconTrash.vue
├── IconEdit.vue
├── IconLock.vue
├── IconCheckCircle.vue
├── IconMore.vue
└── ExpertAvatar.vue
```

每个图标组件模板示例：

```vue
<template>
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" :width="size" :height="size">
    <!-- path here -->
  </svg>
</template>
```

---

## 五、组件/页面逐条改造规范

### 5.1 App.vue（路由容器）

**当前状态**：简单 `v-if` 切换 ProjectsPage/WorkspacePage。

**改造要求**：

1. 页面切换添加淡入淡出过渡：
   ```vue
   <Transition name="page" mode="out-in">
     <ProjectsPage v-if="route === 'projects'" key="projects" />
     <WorkspacePage v-else key="workspace" />
   </Transition>
   ```
2. 全局背景通过 `body` 应用 `--bg-page-gradient`
3. 不添加额外 wrapper，避免破坏布局

**CSS 动画**：

```css
.page-enter-from { opacity: 0; transform: translateY(8px); }
.page-enter-active { transition: all 0.35s var(--ease-out); }
.page-leave-to { opacity: 0; transform: translateY(-4px); }
.page-leave-active { transition: all 0.2s var(--ease-out); }
```

---

### 5.2 ProjectsPage.vue（项目列表页）

**当前问题**：首屏是用户第一印象，虽然基础样式已修复，但仍是普通网格卡片。

**改造要求**：

1. **布局**：全屏滚动容器，最大宽度 1200px，居中，顶部 80px padding
2. **标题区**：
   - 主标题 "Fiction Academy" 使用 `--font-serif`，44px，字重 900，渐变文字（从 `#1a1715` 到 `--accent`）
   - 副标题 "沉浸式 AI 小说创作平台" 13px，大写，字距 0.1em，颜色 `--text-tertiary`
   - 新建项目按钮使用主按钮样式，右侧悬浮小图标
3. **统计条**（新增）：显示项目总数，mono 字体小标签
4. **卡片网格**：
   - 3 列响应式：`grid-template-columns: repeat(auto-fill, minmax(300px, 1fr))`
   - gap: 20px
   - 卡片入场 stagger 动画，每个延迟 50ms
5. **项目卡片**：
   - 背景：`--bg-card`
   - 边框：1px solid `--border-color`
   - 圆角：`--radius-lg`
   - 内边距：24px
   - hover：translateY(-4px) + `--shadow-lg` + 边框变 `--accent-border`
   - active：scale(0.99)
   - 顶部光晕装饰：右上角径向渐变 `--accent-lighter`
   - 体裁标签：mono 字体，10px，uppercase，字距 0.08em，背景 `--accent-lighter`，边框 `--accent-border`
   - 项目名称：serif 字体，22px，字重 700，颜色 `--text-primary`
   - 删除按钮：hover 时从右侧滑入
6. **新建项目弹窗**：
   - 模态 overlay：`rgba(0,0,0,0.35)` 带模糊
   - 弹窗卡片：`--bg-card`，圆角 `--radius-xl`，阴影 `--shadow-xl`
   - 输入框：底部细线风格或圆角边框，聚焦时 `--accent` 光晕
   - 下拉选择：与输入框统一风格
7. **空状态**：大图标 + 衬线标题 + 提示文字

**新增/修改的 class**：全部使用已有的 `projects-page`、`projects-header`、`projects-title`、`projects-grid`、`project-card` 等 class，按新规范重写 CSS。

---

### 5.3 WorkspacePage.vue（工作区三栏布局）

**当前状态**：左侧 Sidebar（260px 可变）+ 中间 chat-area + 右侧 OverviewPanel（400px 可变），有 resize-handle。

**改造要求**：

1. **整体布局**：
   - 高度 100vh，无水平滚动
   - 左侧边栏固定宽度 260px（最小 220px，最大 360px），右侧面板固定 400px（最小 320px，最大 520px）
   - 中间区域 flex:1
2. **玻璃顶栏**：chat-header 使用 `glass` 类，固定在聊天区顶部
3. **项目名称**：serif 字体，18px，字重 700
4. **点位徽章**：mono 字体，10px，uppercase，背景 `--accent-light`，颜色 `--accent`，圆角 `--radius-sm`
5. **存档按钮**：
   - 完成前：幽灵按钮（边框 `--accent-border`，颜色 `--accent`），hover 时实心主按钮
   - 加载中：显示 spinner，文字变 "存档中..."
   - 已存档：绿色 finalized 徽章
6. **resize-handle**：
   - 宽度 6px，背景透明，hover 时 `--accent` 1px 竖线
   - 拖拽时 cursor: col-resize
7. **主题切换按钮**（新增）：放在 chat-header 右侧

**布局 class 结构保持**：`.workspace-layout`、`.chat-area`、`.sidebar-left`、`.sidebar-right`、`.resize-handle`。

---

### 5.4 Sidebar.vue（左侧边栏）

**当前状态**：包含返回按钮、项目名称、点位导航、自由对话、旧点位对话、助理选择。

**改造要求**：

1. **整体风格**：
   - 背景：`--bg-page-gradient` 或纯色 `--bg-secondary`
   - 右侧边框：`1px solid --border-color`
   - 内边距：0（内部 section 16px）
2. **顶部项目区**：
   - 返回按钮：图标按钮，圆形，hover 背景 `--bg-hover`
   - 项目名称：serif 字体，16px，字重 700，单行截断
3. **点位导航**：
   - 标题 "创作流程"：caption 样式（11px uppercase，颜色 `--text-tertiary`）
   - 每个 item：
     - padding: 10px 12px
     - 圆角：`--radius-md`
     - hover：背景 `--bg-hover`
     - active：背景 `--accent-light`，左侧 3px `--accent` 竖线，文字颜色 `--accent`
     - 状态点：
       - pending：空心圆，边框 `--text-tertiary`
       - active：实心 `--accent` + pulse 动画
       - done：绿色对勾 SVG
     - 点位名称：sans 13px，字重 600
     - 点位描述：11px，`--text-tertiary`
4. **自由对话区**：
   - 标题 "自由对话" + 新建按钮，与点位区同样 caption 标题风格
   - 对话 item：
     - padding: 8px 12px
     - 圆角 `--radius-md`
     - active：背景 `--accent-light`，文字 `--accent`
     - 重命名输入框：与 OverviewPanel 编辑区风格一致
     - 删除按钮：hover 显示，红色
5. **助理选择器**：
   - 底部固定
   - 使用自定义下拉样式，不是原生 `<select>` 外观（可用样式覆盖）
6. **滚动条**：自定义细滚动条（6px，圆角）

**禁止**：继续使用原生 `<select>` 的默认外观（必须 CSS 覆盖）。

---

### 5.5 MessageList.vue（消息滚动区）

**当前状态**：消息列表 + 空状态 + 流式消息 + consult 流。

**改造要求**：

1. **滚动容器**：
   - flex:1
   - padding: 24px 32px
   - 滚动条自定义
2. **空状态**：
   - 图标：SVG（`IconWrite` 或 `IconChat`）
   - 标题：serif 字体，22px，字重 700
   - 提示：15px，`--text-tertiary`
3. **消息间距**：消息之间 24px，同角色连续消息 12px
4. **流式消息卡片**：
   - 与 AI 消息样式一致
   - "正在思考..." 使用 fade 动画 + 闪烁点
5. **ConsultFlow 容器**：
   - 独立卡片样式
   - 标题 "专家圆桌" 使用 ExpertAvatar 组件

---

### 5.6 ChatMessage.vue（单条消息）

**当前状态**：三种消息（用户命令、专家圆桌、普通对话）。

**改造要求**：

1. **整体消息结构**：
   - 用户消息：右对齐，气泡背景 `--accent`，文字白色
   - AI 消息：左对齐，气泡背景 `--bg-card`，边框 `--border-color`
2. **角色标签**：
   - 用户：不显示 "你"，直接用右对齐气泡
   - AI：左侧小标签 "AI" 或 "专家圆桌"，11px，`--text-tertiary`
3. **命令卡片**（`/consult` `/goal`）：
   - 背景 `--accent-lighter`
   - 边框 `--accent-border`
   - 图标替换为 SVG（IconTarget / IconBolt）
   - 命令名大写，mono 字体
4. **专家圆桌卡片**：
   - 专用背景：微弱渐变 `--bg-secondary` 到 `--bg-card`
   - 标题区：ExpertAvatar + "专家圆桌"
   - ConsultFlow 嵌套其中
5. **消息操作按钮**：
   - 复制、重新生成使用图标按钮（IconEdit/IconRefresh 等）
   - 默认透明度 0，hover 消息时显示
6. **Markdown 内容**：
   - 代码块背景 `--bg-tertiary`
   - 引用左侧 3px `--accent` 竖线
   - 列表项有合适缩进

---

### 5.7 ChatInput.vue（输入区）

**当前状态**：底部输入框 + 助理选择 + 斜杠命令弹窗 + 发送按钮。

**改造要求**：

1. **输入区容器**：
   - 固定在聊天区底部
   - 背景 `--bg-card` 或 glass
   - 上边框 `1px solid --border-color`
   - padding: 16px 24px
2. **输入框**：
   - 背景 `--bg-secondary`
   - 边框：`1px solid --border-color`
   - 圆角 `--radius-xl`（胶囊形）
   - padding: 14px 18px
   - min-height: 52px，max-height: 160px
   - 聚焦：边框 `--accent-border`，box-shadow: `0 0 0 3px var(--accent-lighter)`
   - placeholder 颜色 `--text-muted`
3. **发送按钮**：
   - 圆形，32px
   - 背景 `--accent`，hover `--accent-hover`
   - 图标：纸飞机 SVG
   - 加载中显示 spinner
4. **助理选择器**：
   - 放在输入框左侧上方或集成到输入框内
   - 自定义下拉样式
5. **斜杠命令弹窗**：
   - 背景 `--bg-card`
   - 边框 `--border-color`
   - 圆角 `--radius-lg`
   - 阴影 `--shadow-lg`
   - 每个 item：
     - padding: 10px 14px
     - active/hover：背景 `--bg-hover`
     - 图标：SVG（替换 emoji）
     - 命令名：mono 字体，13px
     - 描述：12px，`--text-tertiary`

---

### 5.8 ConsultFlow.vue（专家圆桌）

**当前状态**：时间线式展示 leader、各轮专家、裁决。使用 emoji 头像。

**改造要求**：

1. **整体布局**：
   - 左侧时间线（2px 竖线，颜色 `--border-color`）
   - 每个节点一个圆形 ExpertAvatar
   - 右侧气泡内容
2. **Leader（统率者定调）**：
   - 节点：ExpertAvatar（主线策划）
   - 名字：字重 700，颜色专家色
   - 角色标签：caption 样式
3. **轮次分隔线**：
   - 文字 "第 N 轮 · 讨论"，caption 样式，居中于时间线
4. **专家消息气泡**：
   - 背景 `--bg-card`
   - 边框 `--border-color`
   - 圆角 `--radius-md`
   - ExpertAvatar + 名字 + 观点标签
5. **终局裁决**：
   - 特殊节点：天平 SVG IconScale
   - 名字颜色 `--accent`
   - 气泡左侧 3px `--accent` 竖线
6. **加载状态**：
   - pending 文字 + 闪烁点
7. **错误状态**：
   - 红色背景卡片，IconAlert

**禁止**：继续使用 `expertIcon()` 返回的 emoji。`format.ts` 中的 `EXPERT_ICONS` 应移除或改为返回组件名，但为最小改动，优先在 ConsultFlow 内直接映射 name → ExpertAvatar。

---

### 5.9 OverviewPanel.vue（右侧设定面板）

**当前状态**：总览标题、已存档设定卡片、其他设定、编年录、添加设定弹窗。

**改造要求**：

1. **整体风格**：
   - 背景：`--bg-page-gradient` 或 `--bg-secondary`
   - 左侧边框：`1px solid --border-color`
2. **面板标题**：
   - "总览" 使用 H2 样式（20px serif 700）
   - 右侧添加按钮：圆形图标按钮
3. **设定卡片**：
   - 背景 `--bg-card`
   - 边框 `--border-color`
   - 圆角 `--radius-lg`
   - 标题：serif 字体，16px
   - 状态徽章：caption 样式
     - draft：灰色
     - finalized：绿色
     - locked：琥珀色
   - 内容区：15px，行高 1.65
   - 元数据字段：小标签 + 值，两列
   - 操作按钮：编辑、通过、锁定、删除，使用图标按钮或文字链接
4. **空状态**：
   - 居中，IconInfo + "还没有存档的设定"
5. **编年录**：
   - 时间线样式
   - 每个事件左侧小圆点
6. **添加设定弹窗**：
   - 与 ProjectsPage 弹窗风格统一

---

### 5.10 ThinkingBlock.vue（思考过程）

**当前状态**：`<details>` 折叠块，emoji 图标。

**改造要求**：

1. 图标替换为 IconThinking（云/大脑 SVG）
2. summary 样式：
   - 字体 12px，字重 600
   - 颜色 `--text-tertiary`
   - hover 颜色 `--text-secondary`
3. 展开内容：
   - 背景 `--bg-secondary`
   - 圆角 `--radius-md`
   - padding: 12px
   - 字体 13px，行高 1.6
4. 流式状态：summary 颜色变为 `--accent`，左侧添加脉冲点

---

### 5.11 ToastHost.vue（通知）

**当前状态**：顶部居中 Toast，emoji 图标。

**改造要求**：

1. 图标替换：
   - error：IconAlert
   - success：IconCheck
   - info：IconInfo
2. 样式：
   - 背景：`--bg-card`
   - 边框：`1px solid --border-color`
   - 圆角 `--radius-lg`
   - 阴影 `--shadow-lg`
   - error 边框使用 `rgba(220,38,38,0.25)`
   - success 边框使用 `rgba(45,122,94,0.25)`
3. 位置：右上角（更现代）或保持顶部居中
4. 动画保持现有 `toast-enter/leave`

---

## 六、通用组件状态规范

### 6.1 按钮

```css
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 14px;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 600;
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.btn-primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.btn-primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); transform: translateY(-1px); box-shadow: var(--shadow-glow); }
.btn-primary:active { transform: scale(0.97); }

.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
  border-color: var(--border-color);
}
.btn-ghost:hover { background: var(--bg-hover); border-color: var(--border-strong); color: var(--text-primary); }

.btn-sm {
  padding: 5px 10px;
  font-size: 12px;
  border-radius: var(--radius-sm);
}

.btn-icon {
  width: 32px;
  height: 32px;
  padding: 0;
  border-radius: 50%;
}
```

### 6.2 输入框

```css
.input, .modal-input, .chat-input, .ov-edit-area, .conv-rename-input {
  font-family: var(--font-sans);
  background: var(--bg-input);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  font-size: 14px;
  transition: border-color var(--duration-fast) var(--ease-out), box-shadow var(--duration-fast) var(--ease-out);
}
.input:focus, .modal-input:focus {
  outline: none;
  border-color: var(--accent-border);
  box-shadow: 0 0 0 3px var(--accent-lighter);
}
```

### 6.3 卡片

```css
.card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  transition: transform var(--duration-normal) var(--ease-out), box-shadow var(--duration-normal) var(--ease-out), border-color var(--duration-normal) var(--ease-out);
}
.card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--border-strong);
}
```

### 6.4 徽章

```css
.badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
```

### 6.5 弹窗/Modal

```css
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s var(--ease-out);
}
.modal-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xl);
  padding: 28px;
  min-width: 360px;
  max-width: 90vw;
  animation: msgIn 0.3s var(--ease-spring);
}
```

---

## 七、动效规范

### 7.1 页面级

- **页面切换**：0.35s fade + 8px translateY
- **页面入场**：内容 stagger，每个元素 50ms 延迟

### 7.2 卡片/列表

- **hover**：translateY(-2px 到 -4px) + shadow 增强
- **active/click**：scale(0.98)
- **stagger 入场**：`animation-delay: calc(var(--index) * 50ms)`

### 7.3 消息

- 新消息从下方淡入：0.25s
- AI 流式内容：光标闪烁，文字不动画

### 7.4 按钮/输入

- hover：背景色/边框色 0.15s
- focus：box-shadow 光晕 0.15s
- active：scale(0.97)

### 7.5 Toast

- 入场：从上方滑入 + fade，0.25s spring
- 退场：向上淡出 + scale(0.96)，0.15s

### 7.6 滚动条

```css
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--text-muted); border-radius: var(--radius-full); }
::-webkit-scrollbar-thumb:hover { background: var(--text-tertiary); }
```

### 7.7 prefers-reduced-motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 八、深色模式实现细节

1. 所有颜色必须来自 CSS 变量，禁止在组件中写死 hex
2. 渐变背景在 dark 模式下自动通过变量切换
3. 图片/插图如需适配，使用 CSS filter: brightness(0.9) 或准备 dark 版本
4. Toast 在 dark 模式下背景使用 `--bg-card`，边框 `--border-color`
5. 代码块在 dark 模式下背景 `--bg-tertiary`

---

## 九、需要修改的文件清单

### 9.1 新增文件

```
frontend-vue/src/
├── utils/theme.ts                # 主题切换工具
├── components/icons/
│   ├── IconWrite.vue
│   ├── IconChat.vue
│   ├── IconTarget.vue
│   ├── IconBolt.vue
│   ├── IconThinking.vue
│   ├── IconScale.vue
│   ├── IconGlobe.vue
│   ├── IconUser.vue
│   ├── IconRefresh.vue
│   ├── IconClapper.vue
│   ├── IconAlert.vue
│   ├── IconCheck.vue
│   ├── IconInfo.vue
│   ├── IconMoon.vue
│   ├── IconSun.vue
│   ├── IconTrash.vue
│   ├── IconEdit.vue
│   ├── IconLock.vue
│   ├── IconCheckCircle.vue
│   └── ExpertAvatar.vue
```

### 9.2 修改文件

```
frontend-vue/src/
├── main.js                         # 初始化主题
├── App.vue                         # 页面切换过渡
├── styles/main.css                 # 全局设计系统、组件样式
├── utils/format.ts                 # 移除/替换 emoji 映射
├── components/
│   ├── ProjectsPage.vue
│   ├── WorkspacePage.vue
│   ├── Sidebar.vue
│   ├── MessageList.vue
│   ├── ChatMessage.vue
│   ├── ChatInput.vue
│   ├── ConsultFlow.vue
│   ├── OverviewPanel.vue
│   ├── ThinkingBlock.vue
│   └── ToastHost.vue
```

### 9.3 不修改文件

```
src/api.ts
src/stores/app.ts
src/types/index.ts
src/composables/*.ts
```

---

## 十、实现步骤建议（给另一个 AI）

### 阶段 A：基础设施（先做这个，其他依赖它）

1. 创建 `src/utils/theme.ts` 和主题初始化
2. 创建 `src/components/icons/` 下所有 SVG 图标组件
3. 重写 `src/styles/main.css` 的 `:root` 变量系统 + 深色主题 + 通用组件样式
4. 在 `App.vue` 添加页面切换过渡

### 阶段 B：全局替换 emoji

1. 修改 `src/utils/format.ts`：
   - 将 `SLASH_COMMANDS` 的 `icon` 改为 SVG 组件名或移除 emoji
   - 移除 `EXPERT_ICONS` emoji 映射（ConsultFlow 改用 ExpertAvatar）
2. 修改 `MessageList.vue`：空状态 emoji → IconWrite/IconChat
3. 修改 `ChatInput.vue`：斜杠命令弹窗 emoji → IconTarget/IconBolt
4. 修改 `ChatMessage.vue`：命令卡片 emoji → IconTarget/IconBolt
5. 修改 `ConsultFlow.vue`：专家头像 emoji → ExpertAvatar；裁决 emoji → IconScale
6. 修改 `ThinkingBlock.vue`：思考图标 emoji → IconThinking
7. 修改 `ToastHost.vue`：图标 emoji → IconAlert/IconCheck/IconInfo

### 阶段 C：页面级视觉改造

1. `ProjectsPage.vue`：首屏高级化
2. `WorkspacePage.vue`：玻璃顶栏、主题切换
3. `Sidebar.vue`：玻璃侧边栏、点位导航 redesign
4. `MessageList.vue`：消息间距、空状态
5. `ChatMessage.vue`：消息气泡 redesign
6. `ChatInput.vue`：胶囊输入框、斜杠弹窗 redesign
7. `ConsultFlow.vue`：时间线 redesign
8. `OverviewPanel.vue`：设定卡片 redesign
9. `ThinkingBlock.vue`：折叠块 redesign
10. `ToastHost.vue`：Toast redesign + 位置

### 阶段 D：验证

1. `npm run typecheck` 通过
2. `npm run build` 通过
3. 浏览器验证：浅色/深色切换、所有页面无 emoji、动效正常

---

## 十一、验收标准

- [ ] 全局无 emoji 作为图标（允许文本内容中的 emoji，如用户输入）
- [ ] 浅色/深色主题可切换，且所有组件颜色正确
- [ ] `npm run typecheck` 0 错误
- [ ] `npm run build` 成功
- [ ] ProjectsPage 首屏有高级感（衬线标题、渐变、卡片 hover）
- [ ] WorkspacePage 三栏布局协调，玻璃顶栏/侧边栏
- [ ] 消息气泡区分用户/AI，命令卡片/专家圆桌有特色样式
- [ ] ConsultFlow 专家使用抽象几何 SVG 头像
- [ ] 所有交互有 hover/active 反馈
- [ ] 自定义滚动条生效
- [ ] 支持 `prefers-reduced-motion`

---

## 十二、反模式清单（严禁）

- ❌ 在组件中写死 `#ffffff`、`#000000` 或任何不在变量系统中的 hex
- ❌ 使用 emoji 作为功能图标
- ❌ 使用蓝紫渐变作为主色
- ❌ 所有元素统一大圆角
- ❌ 无意义的大面积投影扩散
- ❌ 移除 focus ring（可用 CSS 自定义 focus 样式）
- ❌ 改变任何业务逻辑或 TypeScript 类型
- ❌ 添加与视觉无关的第三方库

---

## 十三、参考文件

- 设计系统源文件：`design-system/fiction-academy/MASTER.md`
- 全局样式：`frontend-vue/src/styles/main.css`
- 类型定义：`frontend-vue/src/types/index.ts`
- 业务 store：`frontend-vue/src/stores/app.ts`
