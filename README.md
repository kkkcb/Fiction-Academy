# Fiction Academy

AI 驱动的中文网文创作平台，支持多助理协作、骨架引导、世界观管理、知识图谱、章节生成和编年录追踪。

## 功能

- **项目管理** — 多小说项目，各自独立管理世界观、角色、大纲和章节
- **骨架引导** — 五点位引导（故事核/世界观/核心人物/倒推大纲/正向大纲），支持 `/gen` 快速生成与 `/consult` 专家圆桌会诊
- **Goal 模式** — `/goal` 给出创作目标，AI 拆解任务逐步执行（状态持久化，重启不丢）
- **知识图谱** — 实体/关系结构化管理，三层知识（事实/已揭示/伏笔），按章节切片注入，写章时自动屏蔽伏笔层防剧透
- **一致性检测** — 对全部设定做矛盾/冲突/缺漏检查
- **三段式写章** — 章纲（备稿）→ 执笔 → 独立审校（Loop 验证器）
- **统一上下文管道** — 守则/点位/章纲/图谱/设定/编年录/前情按优先级与 token 预算统一组装
- **AI 对话** — 流式输出（含思考链）、上下文自动携带设定、重新生成、手动停止

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.13, FastAPI, Uvicorn, aiosqlite, jieba |
| LLM | OpenAI SDK（默认智谱 bigmodel，兼容任意 OpenAI 协议服务） |
| 前端 | Vue 3 + TypeScript + Pinia + Vite（`frontend-vue/`，主线） |
| 数据库 | SQLite（WAL，autocommit + 显式事务） |
| 测试 | pytest + pytest-asyncio + httpx（`backend/tests/`） |

## 快速开始

### 1. 环境准备

```bash
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt   # 测试依赖（可选）

cd frontend-vue && npm install && npm run build   # 构建前端产物（后端直接托管）
```

### 2. 配置

在项目根目录创建 `.env.local`：

```env
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
FA_DEFAULT_MODEL=glm-5.2
```

### 3. 启动

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 http://localhost:8000 （FastAPI 自动托管 `frontend-vue/dist`）。

前端开发模式（热更新）：

```bash
cd frontend-vue && npm run dev    # http://localhost:5173，/api 代理到 8000
```

### 4. 测试

```bash
python -m pytest          # 后端测试（LLM 已打桩，不消耗 token）
cd frontend-vue && npm run typecheck && npm run build
```

## 项目结构

```
Fiction-Academy/
├── backend/
│   ├── agents/           # LLM Agent 层
│   │   ├── base.py       # LLM 网关：统一重试/错误分类/结构化校验/用量记录
│   │   ├── expert_panel.py    # 专家圆桌（断开自动取消，无孤儿调用）
│   │   ├── reviewer.py  # 独立审校
│   │   └── ...
│   ├── api/              # FastAPI 路由（参数校验 + 编排）
│   ├── services/
│   │   ├── context_builder.py # 统一上下文管道（Provider + token 预算）
│   │   ├── repo.py       # 共享数据访问助手（metadata 解析/upsert/归属校验）
│   │   ├── goal.py       # Goal 模式状态机（goals/goal_steps 表持久化）
│   │   ├── kg.py         # 知识图谱（含注入预算）
│   │   ├── wiki.py       # 设定检索（jieba 分词）
│   │   └── ...
│   ├── tests/            # pytest 测试
│   ├── config.py         # 配置（LLM_*，兼容旧 XIAOMI_* 别名）
│   ├── database.py       # SQLite（顺序迁移、失败即启动失败、事务助手）
│   └── main.py           # 入口（托管 frontend-vue/dist）
├── frontend-vue/         # 主线前端（Vue3 + TS + Pinia）
│   └── src/
│       ├── api.ts        # HTTP/流式封装（空闲超时、错误详情、可中断）
│       ├── stores/app.ts # Pinia store（流式节流、停止生成、竞态防护）
│       └── components/   # DOMPurify 消毒所有 Markdown 渲染
├── frontend/             # 旧版原生 JS 前端（已冻结，仅存档；不再被托管）
├── characters/           # 预置角色定义
├── docs/                 # 设计文档
└── data/                 # 运行时数据（gitignore）
```

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_API_KEY` | 空 | 必填，模型服务密钥 |
| `LLM_BASE_URL` | bigmodel | OpenAI 兼容接入点 |
| `FA_DEFAULT_MODEL` | glm-5.2 | 默认模型 |
| `FA_DATABASE_PATH` | `data/fiction_academy.db` | SQLite 路径 |
| `FA_CORS_ORIGINS` | localhost:8000/5173 | CORS 白名单 |
| `FA_CHAT_HISTORY_LIMIT` | 40 | 携带的历史消息数 |

## 斜杠命令（前端）

| 命令 | 场景 | 说明 |
|---|---|---|
| `/gen <想法>` | 点位对话 | 快速生成该点位设定 |
| `/consult <想法>` | 点位对话 | 五位专家圆桌会诊 |
| `/goal <目标>` | 任意 | Goal 模式：拆解任务逐步执行 |

## 回归测试（每次更新代码后必须执行）

任何代码改动推送前，依次跑完三层验证，全部通过才算完成：

```bash
# ① 单元/桩测（LLM 打桩，覆盖业务逻辑）
python -m pytest backend/tests -q

# ② 前端构建 + 类型检查（vue-tsc）
cd frontend-vue && npm run build && cd ..

# ③ 按钮级活体回归（需本地后端已启动；在一次性项目上逐一验证所有 UI 按钮的后端行为）
python scripts/regression.py            # 快速模式（无 LLM 调用，约 3 秒）
python scripts/regression.py --with-llm # 含真实聊天流冒烟
```

`scripts/regression.py` 覆盖：新建/重命名/删除项目、创作守则、五个点位进入、
新建/重命名/删除对话、消息右键删除、添加/编辑/审批/锁定/解锁/删除设定、
知识图谱实体增删、写作守卫（无骨架 409）、各类异常路径（404/409/422）。

## 换机续写（数据随私有仓库走）

小说数据（全部项目/章节/素材库）存于 `data/fiction_academy.db`，已随仓库同步（WAL 运行时文件除外）。

**写完内容后推送数据：**
```bash
python scripts/push_data.py "备注"   # 自动 checkpoint + commit + push
```

**在新机器上继续：**
```bash
git clone https://github.com/kkkcb/Fiction-Academy.git
cd Fiction-Academy
# 1) 拷贝 .env.local（只有一行 API Key，不在 git 里，从旧机器复制或重写）
# 2) 安装依赖并启动（Windows 双击 启动本地版.bat），或：
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**注意：**
- 数据库是二进制文件**不能合并**——不要两台机器同时写作后各自 push；固定"一台写完 push、另一台 pull 再写"
- API Key 永远不进 git（含 Token 的 .env.local 已被忽略）
- 服务器（YOUR_VPS_IP）的数据库独立于 git；如需把服务器数据拉回本地：`scp root@YOUR_VPS_IP:/opt/fiction-academy/data/fiction_academy.db data/`

## License

MIT
