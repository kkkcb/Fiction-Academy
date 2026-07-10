# Fiction Academy 待办事项

**当前版本**: v1.1
**最后更新**: 2026-05-18

---

## Phase 0：代码清理（→ v1.2）

- [ ] 0.1 删除损坏模块 `backend/api/generate.py` + `backend/workflow/`（10min）
- [ ] 0.2 对话精华沉淀 — AI回复可标注「可沉淀」，一键追加到工作台（4h）
- [ ] 0.3 打 tag v1.2，推送 GitHub（5min）

## Phase 1：知识注入（→ v1.3）

- [ ] 1.1 扩展上下文注入 — locked世界观 + 角色设定 + 大纲全部注入 prompt（3h）
- [ ] 1.2 章节上下文注入 — 写第N章时自动注入前N-1章摘要（3h）
- [ ] 1.3 编年史精简注入 — 压缩为结构化摘要，省 token（2h）
- [ ] 1.4 打 tag v1.3，推送 GitHub（5min）

## Phase 2：知识图谱数据层（→ v1.4）

- [ ] 2.1 建表 `kg_entities` + `kg_relations`（1h）
- [ ] 2.2 AI实体提取 prompt — 对话后异步提取实体和关系（4h）
- [ ] 2.3 三层知识标记 — truth / revealed / foreshadow + 章节范围（2h）
- [ ] 2.4 知识注入升级 — 图谱查询替代全文注入，按章节过滤三层知识（3h）
- [ ] 2.5 打 tag v1.4，推送 GitHub（5min）

## Phase 3：知识图谱可视化（→ v1.5）

- [ ] 3.1 复用力导向引擎 — 接入数据库动态数据（4h）
- [ ] 3.2 节点详情面板 — 点击展示属性和关联（3h）
- [ ] 3.3 三层切换视图 — 全知/读者/伏笔视角（2h）
- [ ] 3.4 时序滑块 — 拖动章节号看图谱变化（3h）
- [ ] 3.5 打 tag v1.5，推送 GitHub（5min）

## Phase 4：Goal 模式（→ v1.6）

- [ ] 4.1 `/goal` 命令解析 + 完整性检查引擎（4h）
- [ ] 4.2 任务拆解 + 计划展示 + 用户可编辑（4h）
- [ ] 4.3 逐步执行 + 反向确认 + 进度条（4h）
- [ ] 4.4 完成汇总报告（2h）
- [ ] 4.5 打 tag v1.6，推送 GitHub（5min）

## Phase 5：世界观模板 + 体验打磨（→ v2.0）

- [ ] 5.1 五层世界观引导问卷（6h）
- [ ] 5.2 角色卡模板（3h）
- [ ] 5.3 一致性检测 Lint — 扫描文档找矛盾/缺漏（4h）
- [ ] 5.4 跨条目联动 — 一个新信息同时更新多个条目（3h）
- [ ] 5.5 知识图谱导出 JSON / Markdown / Mermaid（2h）
- [ ] 5.6 打 tag v2.0，推送 GitHub（5min）

---

## 快速参考

- 项目路径: `c:\Fiction-Academy`
- 启动: `python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000`
- 详细文档: `任务进度总结.md`
- 力导向引擎参考: `.trae/skills/html-ppt-skill/assets/animations/fx/knowledge-graph.js`
