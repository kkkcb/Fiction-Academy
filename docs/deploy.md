# 免费部署指南

本应用是 **常驻进程 + SQLite 文件存储 + 流式长连接**，适合容器类托管或自有服务器，不适合 Vercel/Cloudflare Workers 等 Serverless。

## 方案一：自有云服务器（推荐，如火山引擎/阿里云轻量）

以火山引擎 ecs-c1m2.large（2C4G）为例，全程约 10 分钟。

### 1. 本地准备：构建前端 + 打包

```bash
cd frontend-vue && npm install && npm run build && cd ..
# 排除运行时数据与依赖，只传需要的部分
tar czf fa.tar.gz --exclude=.git --exclude=node_modules --exclude=.venv \
  --exclude=data --exclude=logs --exclude=.env.local \
  backend characters frontend-vue/dist scripts docs pytest.ini
scp fa.tar.gz root@你的服务器IP:/opt/
```

### 2. 服务器部署（一键脚本）

```bash
ssh root@你的服务器IP
cd /opt && mkdir -p fiction-academy && tar xzf fa.tar.gz -C fiction-academy && cd fiction-academy
sudo bash scripts/deploy-server.sh          # 首次会生成 .env.local 模板
vi .env.local                                # 填入 LLM_API_KEY
sudo bash scripts/deploy-server.sh          # 再次执行完成部署
```

脚本做的事：venv 装依赖 → systemd 守护（开机自启、崩溃 3 秒自动拉起）→ 健康检查。
服务只监听 `127.0.0.1:8000`，**不直接暴露公网**。

### 3. 对外访问：Nginx 反代 + 访问口令（重要）

⚠️ 应用本身没有登录系统，**绝不能直接把 8000 端口暴露公网**（任何人都能用你的 Key 聊天、看到你的稿子）。两种方式二选一：

**方式 A：Nginx + Basic Auth（推荐，手机/电脑浏览器直接用）**

```bash
# Debian/Ubuntu：apt install -y nginx apache2-utils
# CentOS：yum install -y nginx httpd-tools
printf "你的用户名:$(openssl passwd '你的密码')\n" | sudo tee /etc/nginx/.htpasswd
sudo tee /etc/nginx/conf.d/fiction.conf <<'EOF'
server {
    listen 80;
    server_name _;
    client_max_body_size 25m;
    location / {
        auth_basic "Fiction Academy";
        auth_basic_user_file /etc/nginx/.htpasswd;
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Connection "";
        proxy_read_timeout 300s;   # 流式对话需要长超时
        proxy_buffering off;       # 流式输出不缓冲
    }
}
EOF
sudo systemctl enable --now nginx && sudo nginx -s reload
```

然后到火山引擎控制台 **安全组**只放行 `22、80` 端口（不要放行 8000）。浏览器访问 `http://YOUR_VPS_IP`，输入用户名密码即可，流式打字机效果不受影响。

**方式 B：SSH 隧道（零配置，不开任何公网端口）**

```bash
ssh -N -L 8000:127.0.0.1:8000 root@你的服务器IP
# 然后本地浏览器打开 http://localhost:8000
```

### 4. 迁移本地数据（把现有稿子搬上去）

```bash
scp data/fiction_academy.db root@你的服务器IP:/opt/fiction-academy/data/
ssh root@你的服务器IP "sudo systemctl restart fiction-academy"
```

### 5. 日常更新

本地改完代码 → 重新构建 `npm run build` → 重新打包上传覆盖 → `sudo systemctl restart fiction-academy`。

---

## 方案二：免费容器平台（没有服务器时）

调研汇总参考：[free-vps（GitHub）](https://github.com/1837620622/free-vps)、[free-for.dev](https://free-for.dev)、[Render 免费层限制](https://render.com/docs/free)。

## 平台选择结论

| 平台 | 免费额度 | 数据持久 | 国内访问 | 结论 |
|---|---|---|---|---|
| **ClawCloud Run** | GitHub 账号注册≥180 天，每月 $5，无需绑卡 | 挂载持久卷到 `/app/data` | 快（阿里云系） | **首选** |
| HuggingFace Spaces | 2核16G 完全免费 | 免费层重启丢数据；48h 不活跃休眠 | 一般 | 适合试玩，勿存稿 |
| Render 免费层 | 750h/月 | 15 分钟休眠 + 文件系统重置 | 慢 | 不推荐（丢数据） |
| Oracle Cloud Always Free | 永久免费 4核24G（ARM） | 真 VPS 持久 | 一般 | 长期方案，注册需卡、配置复杂 |

## 部署前准备（任何平台通用）

```bash
# 前端先构建好（镜像只带 dist 产物）
cd frontend-vue && npm install && npm run build && cd ..
```

需要注入的环境变量（平台控制台配置，勿写进镜像/仓库）：

| 变量 | 说明 |
|---|---|
| `LLM_API_KEY` | 必填，模型服务密钥 |
| `LLM_BASE_URL` | 默认 bigmodel |
| `FA_DEFAULT_MODEL` | 默认 glm-5.2 |
| `PORT` | 平台分配的端口（Dockerfile 已自动适配） |

## ClawCloud Run 部署流程（推荐）

1. 用注册满 180 天的 GitHub 账号登录 [ClawCloud](https://run.claw.cloud)，每月自动获得 $5 免费额度
2. App Launchpad → Create App：
   - 镜像：把本仓库推到 Docker Hub / GHCR 后填镜像地址；或用平台从 Dockerfile 构建（关联 GitHub 仓库）
   - 规格：0.1 CPU / 256MB 内存（本应用足够，jieba 加载后约 150MB）
   - 网络：开启公网访问，记下分配的域名
   - 环境变量：填上表变量
3. **关键**：挂载 Volume（持久卷）→ 挂载路径 `/app/data`（SQLite 在这里，丢了就没稿子了）
4. 部署后访问分配的域名验证 `/api/health` 返回 `{"status":"ok"}`

## 本地验证镜像

```bash
docker build -t fiction-academy .
docker run -p 8000:8000 -v fa-data:/app/data \
  -e LLM_API_KEY=你的KEY fiction-academy
# 打开 http://localhost:8000
```

## 数据备份

SQLite 就是单文件。定期从平台下载 `/app/data/fiction_academy.db`（或写个定时任务把它推到对象存储/网盘）。
