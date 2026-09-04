# AGENTS.md — AI 协作约定

## 每次修复/更新完成后必须做的事

1. **附上本地访问地址**：回复末尾必须包含本地服务地址和健康状态，方便用户直接查看：
   - 本地：http://localhost:8000 （后端 + 前端同端口）
   - 服务器版：http://YOUR_VPS_IP:8080/ （nginx 反代 + Basic Auth；更新：`bash scripts/deploy-vps.sh`，密码 VPS_PW 传入；Basic Auth 密码在服务器 /root/fiction-academy-password.txt）
   - 提醒用户刷新方式：Ctrl+F5（旧标签页不会自动更新）
2. **三层回归验证全过才算完成**（见 README「回归测试」）：
   - `python -m pytest backend/tests -q`
   - `cd frontend-vue && npm run build`（失败不提交）
   - `python scripts/regression.py`（需本地后端已启动）
3. **提交推送**：全部改动 commit + push 到 origin main；服务器不会自动同步，需手动
   `bash scripts/deploy-vps.sh` 更新线上（含数据库覆盖，本机为准）。

## 环境备忘

- 本地后端启动：项目根目录 `启动本地版.bat`（双击）或
  `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`
- API Key 在 `.env.local`（不进 git）；LLM 限额/超时也在该文件
- 数据库：`data/fiction_academy.db`（SQLite，迁移随启动自动执行）
- 本机有系统代理会干扰部分外部 API：网络请求注意 `trust_env=False`
- 后台 shell 管道（`| tail`）会假死：跑长命令不要接管道，输出直接落文件
