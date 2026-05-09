# Fiction Academy

AI 驱动的中文网文创作平台，支持多助理协作、世界观管理、章节生成和编年录追踪。

## 功能

- **项目管理** — 创建多个小说项目，每个项目独立管理世界观、角色、大纲和章节
- **多助理系统** — 内置小说创作助手，支持自定义助理（独立 System Prompt + 模型配置）
- **世界观工作区** — 结构化管理世界观设定、角色卡、大纲和章节
- **AI 对话** — 流式输出，上下文自动携带世界观和编年录信息
- **编年录** — 章节定稿后自动提取时间线、角色、关键事件和未解线索
- **重新生成** — 对 AI 回复不满意可一键重新生成
- **重命名** — 项目和对话均支持内联重命名

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.13, FastAPI, Uvicorn, aiosqlite |
| LLM | OpenAI SDK (兼容小米 mimo API) |
| 前端 | 原生 JS (ES Module), 无框架无构建 |
| 数据库 | SQLite (aiosqlite) |

## 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install -r backend/requirements.txt
```

### 2. 配置

在项目根目录创建 `.env.local`：

```env
XIAOMI_API_KEY=your_api_key_here
XIAOMI_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
DEFAULT_MODEL=mimo-v2.5-pro
```

### 3. 启动

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

浏览器打开 http://localhost:8000

## 项目结构

```
Fiction-Academy/
├── backend/
│   ├── agents/          # LLM 调用层
│   │   ├── base.py      # chat_stream / chat_text / chat_json
│   │   ├── chronicle.py # 编年录生成
│   │   └── loader.py    # 角色加载
│   ├── api/             # API 路由
│   │   ├── assistants.py  # 助理 CRUD
│   │   ├── chat.py        # 对话 + 流式聊天
│   │   ├── chronicle.py   # 编年录
│   │   ├── projects.py    # 项目管理
│   │   └── workspace.py   # 工作区条目
│   ├── workflow/        # 工作流（规划中）
│   ├── config.py        # 配置
│   ├── database.py      # 数据库初始化
│   └── main.py          # FastAPI 入口
├── characters/          # 预置角色定义
│   ├── writers/         # 作者角色
│   ├── readers/         # 读者角色
│   ├── operators/       # 运营角色
│   ├── peers/           # 同行角色
│   ├── content-reviewers/  # 内容审核
│   └── compliance-reviewers/ # 合规审核
├── frontend/
│   ├── js/
│   │   ├── api.js       # HTTP 请求封装
│   │   ├── app.js       # UI 渲染 + 事件处理
│   │   └── store.js     # 状态管理
│   ├── index.html
│   └── style.css
├── docs/                # 设计文档
│   └── worldbuilding-design.md  # 世界观模板设计
└── data/                # 运行时数据（gitignore）
    └── fiction_academy.db
```

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects` | 项目列表 |
| POST | `/api/projects` | 创建项目 |
| GET | `/api/projects/{id}/conversations` | 对话列表 |
| POST | `/api/conversations/{id}/chat/stream` | 流式聊天 |
| GET | `/api/projects/{id}/workspace` | 工作区条目 |
| GET | `/api/projects/{id}/chronicle` | 编年录 |
| GET | `/api/assistants` | 助理列表 |
| POST | `/api/assistants` | 创建助理 |
| PUT | `/api/assistants/{id}` | 更新助理 |

## 规划中

- **世界观引导模板** — 五层世界观体系，引导用户逐步构建完整世界观
- **循环模式** — 多角色基于世界观自然演绎，类似斯坦福小镇
- **角色卡结构化** — 标准化角色定义（性格、动机、人际关系、与世界观的关联）

## License

MIT
