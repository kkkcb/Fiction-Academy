# Fiction Academy · 网文创作 Agent

AI 驱动的中文网文创作平台：五点位骨架引导、三层知识图谱、统一上下文管道、三段式章节生成与编年录追踪，多助理协作覆盖从故事核到成章的全流程。个人项目，独立开发，已部署上线（v1.8）。

## 技术栈

- **后端**：Python 3.13 / FastAPI / SQLite（WAL，顺序迁移）/ aiosqlite
- **前端**：Vue 3 + TypeScript + Pinia + Vite（DOMPurify 消毒所有 Markdown 渲染）
- **模型层**：OpenAI SDK 统一网关（默认智谱 GLM，兼容任意 OpenAI 协议服务）
- **检索**：jieba 分词的设定检索（wiki）
- **测试与部署**：pytest + pytest-asyncio（LLM 打桩，零 token 跑测试）；systemd + nginx 密码门

## 核心设计

### 一次写章如何完成

```text
五点位骨架（故事核 → 世界观 → 核心人物 → 倒推/正向大纲）
  → 章纲备稿（chapter_plan）
  → 统一上下文管道组装（守则/点位/章纲/知识图谱/设定/编年录/前情）
      → 知识图谱按章节切片注入，自动屏蔽「伏笔层」防剧透
  → 执笔生成（流式，含思考链）
  → 独立审校（reviewer · Loop 验证器）
  → 编年录与知识图谱回写（新事实入图谱，剧情入编年录）
```

### 统一上下文管道

聊天注入 / Goal 执行 / 章纲审校**共用同一批数据加载与拼装逻辑**，消除此前三套平行体系（wiki 页面、metadata 字段、goal 自拼摘要）的漂移——同一份设定在所有场景下以同一形态进入 prompt。

预算策略：每个 Provider 自带内部预算（知识图谱 2K、设定 4K、前情正文截断等），管道最后按 priority 从低到高**整段裁剪**直到总 token 不超限；priority=1 的段落（守则 / 点位 / 章纲）永不裁剪。

### 三层知识图谱

- 实体（角色 / 地点 / 势力 / 物品 / 事件，含别名与属性）+ 带属性的关系
- 三层知识：**既定事实（truth）/ 已揭示（revealed）/ 伏笔（foreshadow）**
- 按章节切片注入：写到第 N 章时，只注入第 N 章之前已揭示的事实
- **写新章自动屏蔽伏笔层**——按任务动态控制上下文可见性，防止模型"偷看"后文剧透导致前文穿帮

### 多助理协作与质量环

- **三段式写章**：章纲（备稿）→ 执笔 → 独立审校（Loop 验证器），生成与校验分离
- **专家圆桌**（`/consult`）：多助理会诊，断开连接自动取消、无孤儿调用
- **一致性检测**：对全部设定做矛盾 / 冲突 / 缺漏检查
- **Goal 模式状态机**：`/goal` 拆解创作目标逐步执行，planning → executing → completed / cancelled，goals / goal_steps 表持久化（重启不丢、支持多实例）；内置 12 维度项目完整性检查（地理 / 势力 / 力量体系 / 角色关系网 / 核心冲突 / 故事结构等）

### LLM 网关

所有模型调用统一入口：认证错误不重试、限流 / 网络错误指数退避；`chat_json` 可带 pydantic response_schema，解析 / 校验失败自动重试；token 用量记录；流式调用在产出首个 chunk 前失败自动重试。

## 代码导航

| 路径 | 职责 |
|---|---|
| `backend/services/context_builder.py` | 统一上下文管道（Provider + 分层 token 预算 + 优先级裁剪） |
| `backend/services/kg.py` | 三层知识图谱（实体 / 关系 / 章节切片注入） |
| `backend/services/wiki.py` | 设定检索（jieba 分词 + token 预算） |
| `backend/services/goal.py` | Goal 模式状态机 + 12 维完整性检查 |
| `backend/agents/base.py` | LLM 网关：重试分类 / 结构化校验 / 用量记录 |
| `backend/agents/chapter_plan.py` | 章纲备稿 |
| `backend/agents/reviewer.py` | 独立审校（Loop 验证器） |
| `backend/agents/expert_panel.py` | 专家圆桌（断开自动取消） |
| `backend/agents/chronicle.py` | 编年录（情节长期记忆） |
| `backend/api/` | FastAPI 路由（参数校验 + 编排） |
| `backend/database.py` | SQLite（顺序迁移，失败即启动失败） |
| `frontend-vue/src/` | Vue3 前端（流式节流 / 停止生成 / 竞态防护） |
| `scripts/e2e_write_ch*.py`、`scripts/regression.py` | 端到端写章与回归脚本 |

各模块 docstring 记录了设计决策的背景（如上下文管道为何要消除三套平行体系），读代码建议从 docstring 入手。

## 数据模型

SQLite 单库（`data/fiction_academy.db`，已 gitignore）：`projects`（小说项目）、`workspace_items`（故事核 / 世界观 / 人物设定卡）、`kg_entities` / `kg_relations`（三层知识图谱）、`chronicle`（编年录）、`goals` / `goal_steps`（任务状态机）、`conversations` / `messages`、`assistants`、`materials`、`schema_migrations`。

## 开发与运行

```bash
pip install -r backend/requirements.txt
cd frontend-vue && npm install && npm run build && cd ..   # 后端托管前端产物

# 项目根目录创建 .env.local
# LLM_API_KEY=...（默认智谱，可换任意 OpenAI 协议服务）
# LLM_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
# FA_DEFAULT_MODEL=glm-5.2

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# 浏览器打开 http://localhost:8000；前端热更新开发模式：cd frontend-vue && npm run dev
```

```bash
python -m pytest                        # 后端测试（LLM 打桩，不消耗 token）
cd frontend-vue && npm run typecheck && npm run build
```

## 说明

个人项目，代码仅供学习参考。部署文档见 [docs/deploy.md](docs/deploy.md)（服务器地址以 `YOUR_VPS_IP` 占位，需自行替换）。
