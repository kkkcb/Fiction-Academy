# Fiction Academy 代码审查报告

> 审查日期: 2026-06-22
> 审查范围: backend/ 全部 + frontend/ 全部 + 架构/数据/部署
> 方法: 3 个并行子代理深度静态分析 + 关键争议点人工验证

---

## 严重程度统计

| 级别 | 后端 | 前端 | 架构 | 合计 |
|------|------|------|------|------|
| 🔴 致命/严重 | 11 | 11 | 6 | 28 |
| 🟡 中等 | 18 | 10 | 11 | 39 |
| 🟢 轻微 | 9 | 5 | 7 | 21 |
| **合计** | **38** | **26** | **24** | **88** |

---

## ⚠️ 已纠正的误报

### ❌ 误报:`execute_fetchall` 不存在导致应用不可用

子代理报告 C3 称 aiosqlite 没有 `execute_fetchall` 方法。**经人工验证为误报**:
```
aiosqlite 版本: 0.22.1
'execute_fetchall' in dir(Connection): True
```
该方法在 aiosqlite 0.20+ 已内置(封装了 execute+fetchall)。应用运行正常。

**仍存在的隐患**: 这是非标准 API,文档未广泛记载。建议未来抽出 `fetch_all/fetch_one` 封装,降低对未文档化 API 的依赖。

---

## 一、🔴 致命问题(必须优先修复)

### 安全类

#### SEC-1 路径遍历漏洞 — 任意文件读写
**位置**: [agents/loader.py:64-77](file:///c:/Fiction-Academy/backend/agents/loader.py#L64-77)、[api/characters.py:21-39](file:///c:/Fiction-Academy/backend/api/characters.py#L21-39)
```python
filepath = Path(CHARACTERS_DIR) / dir_name / f"{char_name}.md"  # char_name 未校验
```
**风险**: `char_name="../../backend/main"` 即可写入项目任意位置甚至系统文件。
**修复**: 白名单正则 `^[A-Za-z0-9_\u4e00-\u9fa5-]{1,64}$` + `filepath.resolve()` 校验仍在 CHARACTERS_DIR 内。

#### SEC-2 CORS 完全开放 + 无鉴权
**位置**: [main.py:38-43](file:///c:/Fiction-Academy/backend/main.py#L38-43)
```python
allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
```
全工程无任何 auth 中间件。任何人知道 URL 即可 CRUD 全部数据。
**修复**: 环境变量配置白名单域名;加 API Token 中间件;projects 表加 owner_id。

#### SEC-3 前端 XSS:`esc()` 未转义单引号
**位置**: [app.js:14](file:///c:/Fiction-Academy/frontend/js/app.js#L14)
```js
const esc = s => s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''
// 漏掉单引号,但 onclick='...' 内用单引号包裹 ID
```
配合 [app.js:833,847,861,920](file:///c:/Fiction-Academy/frontend/js/app.js#L833) 的 `onclick="window._xxx('${esc(id)}')"` 模式,ID 含单引号即可注入。
**修复**: `esc()` 增加 `.replace(/'/g,'&#39;')`;或废弃 onclick 内联,改用 data-* + 事件委托。

### 数据完整性类

#### DATA-1 SQLite 外键约束未启用 — CASCADE 全部失效
**位置**: [database.py](file:///c:/Fiction-Academy/backend/database.py)
全局无 `PRAGMA foreign_keys = ON`。SQLite 默认 OFF,导致 `ON DELETE CASCADE` 形同虚设,删除 project 后 conversations/messages/workspace_items/chronicle 全部成为孤儿数据。
**修复**: `get_db()` 建连后立即 `await db.execute("PRAGMA foreign_keys = ON")`。

#### DATA-2 流式对话中断即丢失用户输入和 AI 回复
**位置**: [chat.py:166-190](file:///c:/Fiction-Academy/backend/api/chat.py#L166-190)
执行顺序:`开始流式 → 边收边发 → 接收完 → 插入 user → 插入 assistant → commit`。客户端中途断开 → 用户消息和 AI 回复全部不落库,token 白花。
**修复**: 先入库 user 消息并 commit 再开始流式;流式结束后立刻写 assistant。

#### DATA-3 编年史自动更新 fire-and-forget,异常被吞
**位置**: [workspace.py:368-371, 421-422](file:///c:/Fiction-Academy/backend/api/workspace.py#L368)
```python
asyncio.create_task(_trigger_chronicle_update(...))  # task 引用未保存,可能被 GC
except Exception as e: print(...)  # print 不走 logger,无 traceback
```
章节 finalized 后编年史可能静默失败,用户看到状态已 final 但编年史没更新。
**修复**: 维护 task 集合 + `logger.exception`;引入持久化任务表便于重试。

#### DATA-4 `regenerate` 删除后流式失败导致永久丢失
**位置**: [chat.py:85-92](file:///c:/Fiction-Academy/backend/api/chat.py#L85-92)
先删最后 2 条消息再开始流式,流式失败则被删消息永久丢失。
**修复**: 软删除标记或事务包裹"删旧+流式+写新"。

### 前端流式致命 bug

#### FE-1 JSON 行跨 chunk 被切断,数据丢失
**位置**: [api.js:80-94](file:///c:/Fiction-Academy/frontend/js/api.js#L80-94)
```js
const newData = xhr.responseText.substring(buffer.length)
const lines = newData.split('\n')
for (const line of lines) {
  try { JSON.parse(line) } catch {}  // 半行 JSON 解析失败被静默吞掉
}
```
TCP 分包把一条 JSON 切到两个 progress 事件时,数据永久丢失。中文 UTF-8 多字节截断还会产生乱码。
**修复**: 维护行缓冲区 `pending`,只处理以 `\n` 结尾的完整行,`pending = lines.pop()` 保留尾部。

#### FE-2 流式切换对话导致跨对话消息污染
**位置**: [store.js:133-164](file:///c:/Fiction-Academy/frontend/js/store.js#L133)
`streamChat` 返回的 `abort()` 函数从未保存。流式中切换对话 → 旧流的 chunk 污染新对话 UI,onDone 把旧对话消息写入 state 覆盖新对话。
**修复**: state 保存 abort;selectConversation 中调用 abort;回调校验 `currentConversationId === conversationId`。

### 死代码

#### DEAD-1 generate.py + workflow/ 完全不可用
**位置**: [api/generate.py](file:///c:/Fiction-Academy/backend/api/generate.py)、[workflow/graph.py](file:///c:/Fiction-Academy/backend/workflow/graph.py)
引用不存在的 `characters`/`chapters` 表、不存在的列(writer_id 等)、不存在的 `BaseAgent` 类。导入路径也不统一(`from agents.base` vs `from backend.agents.base`)。因 main.py 未注册该 router,侥幸不影响运行。
**修复**: 删除(对应 TODO Phase 0.1)。

---

## 二、🟡 中等问题(架构性缺陷)

### 性能类

#### PERF-1 单一全局 DB 连接 — 并发瓶颈
**位置**: [database.py:70-80](file:///c:/Fiction-Academy/backend/database.py#L70-80)
全进程共享一条 aiosqlite 连接,所有 DB 操作串行排队。叠加流式聊天独占连接数十秒 → 一次长对话卡死全站写入。
**修复**: 自建 N 连接池或迁移 SQLAlchemy async。并发上限估算 10-30 人。

#### PERF-2 流式渲染 O(n²) — 每个 chunk 全量 innerHTML
**位置**: [app.js:351-360](file:///c:/Fiction-Academy/frontend/js/app.js#L351-360)
```js
contentEl.innerHTML = formatMd(s.streamingContent) + '<span class="streaming-cursor"></span>'
```
2000 字回复分 100 chunk → formatMd 调用 100 次 × 全文 7 轮正则 + innerHTML 重建 100 次。长回复明显卡顿。
**修复**: requestAnimationFrame 合并;流式只追加 textContent,结束再 Markdown 渲染。

#### PERF-3 全量 render() 销毁整个 DOM
**位置**: [app.js:46-55](file:///c:/Fiction-Academy/frontend/js/app.js#L46-55) + 38 处手动 render() 调用
每次 setState 后 subscribe 已触发 smartRender,但代码中还有 38 处冗余手动 render(),导致同帧多次全量重绘。
**修复**: 移除手动 render();引入 morphdom 做轻量 diff。

#### PERF-4 数据库零索引
全表扫描:`conversations WHERE project_id`、`messages WHERE conversation_id ORDER BY created_at`、`workspace_items WHERE project_id AND item_type AND status`。
**修复**: 补 `idx_conversations_project_id`、`idx_messages_conversation_id`、`idx_workspace_project_type_status`。

### 业务逻辑 bug

#### BIZ-1 refresh_chronicle 的 raw_text 永远是空字符串
**位置**: [chronicle.py:126-138](file:///c:/Fiction-Academy/backend/api/chronicle.py#L126) + [agents/chronicle.py:42-64](file:///c:/Fiction-Academy/backend/agents/chronicle.py#L42)
`update_chronicle` 不输出 raw_text,但 chat.py 优先读 raw_text → 通过 refresh 写入的编年史聊天时读不到。
**修复**: 让 update_chronicle 输出 raw_text,或 chat.py 在 raw_text 空时 fallback。

#### BIZ-2 put_chronicle 把 SQL 函数当字符串
**位置**: [chronicle.py:85-90](file:///c:/Fiction-Academy/backend/chronicle.py#L85-90)
```python
fields["updated_at"] = "datetime('now')"  # 当成参数值传入
```
最终 updated_at 字段被写入字面字符串 "datetime('now')" 而非当前时间。
**修复**: updated_at 单独拼到 set_clause 不带占位符。

#### BIZ-3 状态机可绕过
**位置**: [workspace.py:327, 350-376](file:///c:/Fiction-Academy/backend/api/workspace.py#L327)
locked 防编辑可被"locked→draft→编辑"绕过;status 字段无 Enum 校验。
**修复**: Pydantic `Literal["draft","finalized","locked"]` + 合法转换表。

#### BIZ-4 历史截断可能违反消息顺序
**位置**: [chat.py:162](file:///c:/Fiction-Academy/backend/api/chat.py#L162)
`history[-40:]` 若第 40 条是 assistant,则 messages 以 assistant 开头 → OpenAI API 直接 400。
**修复**: 截断后检查首条 role;用 token 计数替代条数。

#### BIZ-5 summarize 合并无限堆叠 + subtitle 被清空
**位置**: [workspace.py:495-504](file:///c:/Fiction-Academy/backend/api/workspace.py#L495)
同类型第一次创建后,后续 summarize 全部追加到同一条 → 内容无限增长超 context。subtitle 强制清空丢元信息。
**修复**: 去重/截断机制;保留 subtitle。

#### BIZ-6 编年史触发条件有 bug
**位置**: [workspace.py:368, 387-391](file:///c:/Fiction-Academy/backend/api/workspace.py#L387)
只在 `finalized` 触发,跳到 `locked` 不触发;`finalized→draft→finalized` 重复触发;读世界观只取 locked,章节可能在世界观未 locked 时就 finalize。

### LLM / Prompt 类

#### LLM-1 chat_json 未捕获 JSONDecodeError
**位置**: [agents/base.py:79-91](file:///c:/Fiction-Academy/backend/agents/base.py#L79)
LLM 返回非法 JSON 时直接抛异常,所有调用方无 try/except → 500。
**修复**: chat_json 内部 try/except + 重试。

#### LLM-2 期望 JSON 却用 chat_text 调用
**位置**: [workspace.py:216-237, 467-485](file:///c:/Fiction-Academy/backend/api/workspace.py#L216)
prompt 要求 JSON 却走 chat_text(高温、无 json_object),再手动 parse,失败率高。
**修复**: 统一用 chat_json。

#### LLM-3 无 max_tokens、timeout、重试
**位置**: [agents/base.py:42-91](file:///c:/Fiction-Academy/backend/agents/base.py#L42)
网络抖动或长回复无限挂起,叠加单连接独占 → 全站阻塞。
**修复**: timeout=60、max_tokens 上限、指数退避重试。

#### LLM-4 日志泄漏用户创作内容
**位置**: [chat.py:165](file:///c:/Fiction-Academy/backend/api/chat.py#L165)
`user_content[:50]` 写入日志文件。创作内容可能涉隐私/版权。
**修复**: 只记长度与 hash。

### 前端状态/内存类

#### FE-3 selectConversation 异步竞态
**位置**: [store.js:99-102](file:///c:/Fiction-Academy/frontend/js/store.js#L99)
快速点击 A、B,若 B 请求先返回、A 后返回 → UI 显示 A 消息但高亮 B。
**修复**: 请求版本号或 AbortController。

#### FE-4 onerror 未保存已接收的部分内容
**位置**: [api.js:90](file:///c:/Fiction-Academy/frontend/js/api.js#L90) + [store.js:153-160](file:///c:/Fiction-Academy/frontend/js/store.js#L153)
流中途错误时 fullContent 被丢弃,不写入 messages。
**修复**: onError 也保存部分内容。

#### FE-5 `_mdCache` 无上限无淘汰
**位置**: [app.js:1362-1378](file:///c:/Fiction-Academy/frontend/js/app.js#L1362)
流式每个中间状态都缓存,一次长回复产生数百条前缀子串缓存。
**修复**: LRU 限制 + 切换对话清空。

### 配置/部署类

#### OPS-1 API Key 缺失不 fail-fast
**位置**: [config.py:6](file:///c:/Fiction-Academy/backend/config.py#L6)
默认空字符串,启动正常,首个请求才 401。
**修复**: 启动校验非空。

#### OPS-2 数据库迁移机制脆弱
**位置**: [database.py:82-86](file:///c:/Fiction-Academy/backend/database.py#L82)
写死检查 subtitle 列,无 schema_version 表,无回滚。
**修复**: 引入 alembic 或自建 schema_migrations 表。

#### OPS-3 静态文件全部 no-cache
**位置**: [main.py:45-53](file:///c:/Fiction-Academy/backend/main.py#L45)
每次刷新重下 JS/CSS。
**修复**: 只 .html 禁缓存,JS/CSS 用内容哈希 + 长缓存。

#### OPS-4 `_ensure_builtins` 每次 list 执行
**位置**: [assistants.py:54-59](file:///c:/Fiction-Academy/backend/api/assistants.py#L54)
应在 lifespan 启动时执行一次。

---

## 三、🟢 轻微问题(优化建议)

| 编号 | 问题 | 位置 |
|------|------|------|
| MINOR-1 | 函数中间 import json | workspace.py:229,479 |
| MINOR-2 | 硬编码魔法数(history[-40:]、temperature=0.8) | chat.py:162, base.py:44 |
| MINOR-3 | update_assistant builtin/普通分支完全相同(死代码) | assistants.py:80-89 |
| MINOR-4 | updated_at 格式不统一(isoformat vs datetime('now')) | projects.py:98 |
| MINOR-5 | 无请求关联 ID(X-Request-ID) | 全局 |
| MINOR-6 | 日志无轮转(FileHandler 撑爆磁盘) | main.py:25 |
| MINOR-7 | 列表接口零分页 | 多处 |
| MINOR-8 | 健康检查过浅(不探 DB/LLM) | main.py:61 |
| MINOR-9 | formatMd 列表渲染 bug(多列表场景) | app.js:1373-1375 |
| MINOR-10 | .rstrip 死代码(JS 无此方法) | app.js:480 |
| MINOR-11 | 错误处理混用 alert/toast/confirm | app.js 全文 |
| MINOR-12 | 14 个 window._* 全局函数 | app.js:398-581 |
| MINOR-13 | 内联 style 上百处,缺 CSS 类抽象 | app.js 全文 |
| MINOR-14 | 按钮加载状态代码重复 6 次 | app.js 多处 |
| MINOR-15 | 动态 import CDN marked 无 SRI(且是死代码) | app.js:23 |

---

## 四、根因分层与架构整改建议

按"避免单点补丁、全局架构优化"原则,88 个问题可归结为 **5 个根因**:

### 根因 1:数据访问层缺失
**衍生问题**: DATA-1、PERF-1、PERF-4、M18 重复代码
**整改**: 新建 `backend/db/pool.py`,提供连接池 + `async with get_conn() as db` + `fetch_all/fetch_one/get_or_404` 封装。开启 `PRAGMA foreign_keys`。补索引。

### 根因 2:Service 层未抽离
**衍生问题**: DATA-2、DATA-3、LLM-1/2/3、BIZ 全部
**整改**: 新建 `backend/services/{chat,workspace,chronicle}.py`,路由层只做 HTTP 适配,业务逻辑(含 LLM 调用、事务、后台任务)下沉。LLM 调用统一包装重试/超时/JSON 容错。

### 根因 3:前端渲染机制落后
**衍生问题**: PERF-2、PERF-3、FE-1、XSS-2/3/4、MINOR-9/13
**整改**: 引入 morphdom 轻量 diff 或 lit-html;流式改 fetch + ReadableStream + 行缓冲;Markdown 用 marked + DOMPurify 构建时打包。

### 根因 4:状态管理缺乏版本控制
**衍生问题**: FE-2、FE-3、FE-4、STATE-4/5
**整改**: 引入请求 token / AbortSignal 管理异步竞态;listener 调用加 try-catch;state 返回值冻结。

### 根因 5:安全基线缺失
**衍生问题**: SEC-1、SEC-2、OPS-1、LLM-4
**整改**: 路径校验白名单;CORS 环境变量配置;API key 启动校验;日志脱敏。

---

## 五、可扩展性评估

| 维度 | 当前上限 | 瓶颈 |
|------|---------|------|
| 同时在线用户 | 10-30 人 | 单进程 + 单 DB 连接 + LLM 速率 |
| 每秒并发聊天 | 5-10 条 | 单 DB 连接串行 + 流式占连接 30-120s |
| 单项目章节数 | >50 章 refresh 即不可用 | refresh_chronicle 串行重放 |
| 横向扩展 | **不可扩展** | SQLite 单文件 + 全局单连接 |

**升级路径**: DB → Postgres + 连接池;任务 → arq/RQ;缓存 → Redis;部署 → gunicorn workers + nginx。

---

## 六、推荐修复顺序

### 第 1 步:止血(对应 TODO Phase 0,~1 天)
- 删除 generate.py + workflow/(DEAD-1)
- 修外键 pragma(DATA-1)
- 修路径遍历(SEC-1)
- chat 流式先存 user 消息(DATA-2)
- 前端 JSON 行缓冲(FE-1)

### 第 2 步:地基(Phase 1,~2 天)
- DB 连接池 + 索引(PERF-1、PERF-4)
- LLM 重试/超时/JSON 容错(LLM-1/2/3)
- 状态机 Enum + 转换表(BIZ-3)
- 配置强校验(OPS-1)

### 第 3 步:前端重构(Phase 2,~3 天)
- 渲染层引入 morphdom(PERF-2/3)
- 流式改 fetch + ReadableStream(FE-1 徹底解决)
- 状态管理加 token/AbortSignal(FE-2/3)

### 第 4 步:规范(持续)
- 统一响应信封、URL 风格、错误码
- 健康检查、日志轮转、分页、metrics

---

## 附:零测试覆盖

全工程无任何 `test_*.py`。建议至少补齐:
- database 层(建表、迁移、级联)
- 状态机转换合法性
- 路径校验
- 前端 JSON 行缓冲(STREAM-1 的回归测试)
- LLM mock 测试
