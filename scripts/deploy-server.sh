#!/usr/bin/env bash
# ============================================================================
# Fiction Academy 一键部署脚本（Ubuntu 20.04/22.04/24.04，需 root）
#
# 服务器上执行：
#   git clone https://github.com/kkkcb/Fiction-Academy.git /opt/fiction-academy
#   bash /opt/fiction-academy/scripts/deploy-server.sh
#
# 做了什么：
#   1. 安装依赖（python3-venv / nginx）
#   2. 创建虚拟环境并安装 Python 依赖
#   3. 生成 .env.local（API Key 通过环境变量 LLM_API_KEY 或交互输入）
#   4. 注册 systemd 服务（开机自启、崩溃自动拉起，只监听 127.0.0.1:8000）
#   5. 配置 Nginx 反向代理 + 密码门（仅密码无用户名：输对密码发 90 天 cookie）
#   6. 健康检查并打印访问地址
#
# 幂等：重复执行 = 更新代码 + 重启服务；密码沿用 /root/fiction-academy-password.txt，
#       换密码用：GATE_PASSWORD=新密码 bash scripts/deploy-server.sh（仅字母数字）
# ============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/fiction-academy}"
SERVICE="fiction-academy"
PYTHON_BIN="${PYTHON_BIN:-python3}"
# 对外端口（nginx 监听）；80 被其他服务占用时用 PUBLIC_PORT=8080 指定，
# 首次写入后会记在 $APP_DIR/.public-port，之后重跑无需再传
PUBLIC_PORT="${PUBLIC_PORT:-$(cat "$APP_DIR/.public-port" 2>/dev/null || echo 80)}"

say() { echo -e "\n\033[1;36m==> $1\033[0m"; }
die() { echo -e "\n\033[1;31m[失败] $1\033[0m" >&2; exit 1; }

[ "$(id -u)" = "0" ] || die "请用 root 运行：sudo bash $0"
[ -f "$APP_DIR/backend/main.py" ] || die "未找到代码，请先：git clone https://github.com/kkkcb/Fiction-Academy.git $APP_DIR"
command -v "$PYTHON_BIN" >/dev/null || die "未找到 python3"

# ---------------------------------------------------------------- 1. 系统依赖
say "安装系统依赖（python3-venv / nginx / apache2-utils）..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y -qq
apt-get install -y -qq python3-venv nginx >/dev/null

# ---------------------------------------------------------------- 2. 更新代码
if [ -d "$APP_DIR/.git" ]; then
    say "更新代码（git pull）..."
    git -C "$APP_DIR" pull --ff-only || echo "  git pull 失败（可能是网络问题），继续使用本地代码"
fi

# ---------------------------------------------------------------- 3. Python 依赖
say "安装 Python 依赖..."
[ -d "$APP_DIR/.venv" ] || "$PYTHON_BIN" -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null \
  || "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/backend/requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null \
  || "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/backend/requirements.txt"

# ---------------------------------------------------------------- 4. API Key
if [ ! -f "$APP_DIR/.env.local" ]; then
    say "配置 API Key..."
    if [ -n "${LLM_API_KEY:-}" ]; then
        KEY="$LLM_API_KEY"
    else
        echo "请粘贴你的 API Key（智谱开放平台，输入时不会显示）："
        read -rs KEY
        echo
    fi
    [ -n "$KEY" ] || die "API Key 不能为空。重新运行本脚本即可重试。"
    printf 'LLM_API_KEY=%s\n' "$KEY" > "$APP_DIR/.env.local"
    chmod 600 "$APP_DIR/.env.local"
    echo "已写入 $APP_DIR/.env.local"
else
    echo "沿用已有 $APP_DIR/.env.local"
fi

# ---------------------------------------------------------------- 5. systemd
say "注册 systemd 服务..."
mkdir -p "$APP_DIR/data" "$APP_DIR/logs"
cat > "/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=Fiction Academy
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
Environment=FA_DATABASE_PATH=${APP_DIR}/data/fiction_academy.db
Environment=FA_LLM_TIMEOUT=600
Environment=FA_LLM_MAX_TOKENS=16384
Environment=FA_LLM_MAX_RETRIES=2

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null 2>&1
systemctl restart "$SERVICE"

# 等健康检查通过
say "等待服务启动..."
HEALTH_OK=0
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then HEALTH_OK=1; break; fi
    sleep 1
done
[ "$HEALTH_OK" = "1" ] || { journalctl -u "$SERVICE" -n 30 --no-pager; die "服务启动失败，请把上面的日志发给我。"; }
echo "后端已启动（127.0.0.1:8000）"

# ---------------------------------------------------------------- 6. Nginx + 密码门
# 应用无登录系统，公网必须挡一道。方案：仅密码（无用户名）——
#   打开站点 → 401 跳密码页 → 输对密码（GET /__enter?k=密码）→ 发 90 天 HttpOnly cookie → 正常使用
# cookie 值是与密码无关的随机密钥（单独存 /root/.fa-gate-secret），
# 改密码不吊销已发 cookie，重装不强制所有人重新输密码。
say "配置 Nginx（${PUBLIC_PORT} 端口 + 仅密码门）..."
PASS_FILE="/root/fiction-academy-password.txt"
SECRET_FILE="/root/.fa-gate-secret"
echo "$PUBLIC_PORT" > "$APP_DIR/.public-port"

if [ -n "${GATE_PASSWORD:-}" ]; then
    GATE_PW="$GATE_PASSWORD"
elif [ -f "$PASS_FILE" ]; then
    GATE_PW="$(head -n1 "$PASS_FILE")"
else
    # 不能用 tr|head 取随机串——pipefail 下 SIGPIPE(141) 会静默杀死脚本（见踩坑实录）
    GATE_PW="$(openssl rand -hex 6 2>/dev/null || head -c9 /dev/urandom | od -An -tx1 | tr -d ' \n')"
fi
[[ "$GATE_PW" =~ ^[A-Za-z0-9]+$ ]] || die "密码仅限字母数字（会写进 nginx 配置做字符串比较）"
printf '%s\n' "$GATE_PW" > "$PASS_FILE"; chmod 600 "$PASS_FILE"

if [ -s "$SECRET_FILE" ]; then
    GATE_SECRET="$(head -n1 "$SECRET_FILE")"
else
    openssl rand -hex 32 > "$SECRET_FILE" 2>/dev/null \
      || head -c32 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$SECRET_FILE"
    chmod 600 "$SECRET_FILE"
    GATE_SECRET="$(head -n1 "$SECRET_FILE")"
fi

mkdir -p /var/www
cat > /var/www/gate.html <<'HTMLEOF'
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fiction Academy</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#151823;font-family:system-ui,-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif}
  .card{background:#1e2333;border-radius:14px;padding:36px 32px;width:min(92vw,340px);box-shadow:0 10px 40px rgba(0,0,0,.45)}
  h1{margin:0 0 6px;font-size:20px;color:#e8eaf2}
  p{margin:0 0 22px;font-size:13px;color:#8b93a8}
  input{width:100%;box-sizing:border-box;padding:12px 14px;border-radius:9px;border:1px solid #333a4e;background:#151823;color:#e8eaf2;font-size:15px;outline:none}
  input:focus{border-color:#5b7cfa}
  button{width:100%;margin-top:14px;padding:12px;border:0;border-radius:9px;background:linear-gradient(135deg,#5b7cfa,#8a5bfa);color:#fff;font-size:15px;cursor:pointer}
</style>
</head>
<body>
  <form class="card" method="GET" action="/__enter">
    <h1>Fiction Academy</h1>
    <p>请输入访问密码</p>
    <input type="password" name="k" autofocus autocomplete="current-password">
    <button type="submit">进入</button>
  </form>
</body>
</html>
HTMLEOF

cat > "/etc/nginx/sites-available/${SERVICE}" <<EOF
# cookie 密钥 64 字符，超过 map 默认桶宽（64），必须显式放宽
map_hash_bucket_size 128;
map \$cookie_fa_gate \$fa_gate_ok { default 0; "${GATE_SECRET}" 1; }

server {
    listen ${PUBLIC_PORT} default_server;
    server_name _;
    charset utf-8;
    client_max_body_size 25m;

    # 验证入口：/?k=密码 正确则发 cookie 并跳回首页
    location = /__enter {
        if (\$arg_k != "${GATE_PW}") { return 401; }
        add_header Set-Cookie "fa_gate=${GATE_SECRET}; Path=/; Max-Age=7776000; HttpOnly; SameSite=Lax" always;
        return 302 /;
    }

    # 密码页（免 cookie，输错密码也会回到这里）
    location = /gate.html {
        default_type text/html;
        root /var/www;
    }
    error_page 401 /gate.html;

    location / {
        if (\$fa_gate_ok = 0) { return 401; }
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header Connection "";

        # SSE 流式输出必需
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
EOF
chmod 600 "/etc/nginx/sites-available/${SERVICE}"
rm -f /etc/nginx/sites-enabled/default /etc/nginx/.htpasswd-fiction
ln -sf "/etc/nginx/sites-available/${SERVICE}" "/etc/nginx/sites-enabled/${SERVICE}"
systemctl enable nginx >/dev/null 2>&1 || true
nginx -t 2>/dev/null || { nginx -t; die "Nginx 配置有误。"; }
systemctl reload nginx 2>/dev/null || systemctl restart nginx

# ---------------------------------------------------------------- 7. 完成
PUB_IP="$(curl -sf --max-time 5 https://ifconfig.me 2>/dev/null || curl -sf --max-time 5 http://ip.sb 2>/dev/null || echo '服务器公网IP')"
echo
echo "============================================================"
echo -e "\033[1;32m  ✅ 部署完成！\033[0m"
echo "------------------------------------------------------------"
PORT_SUFFIX=""
[ "$PUBLIC_PORT" = "80" ] || PORT_SUFFIX=":${PUBLIC_PORT}"
echo "  访问地址： http://${PUB_IP}${PORT_SUFFIX}/"
echo "  访问密码： ${GATE_PW}（仅密码无用户名，输对后 90 天免输）"
echo "  （密码也保存在服务器 ${PASS_FILE}；换密码：GATE_PASSWORD=新密码 bash scripts/deploy-server.sh）"
echo "------------------------------------------------------------"
echo "  常用命令："
echo "    更新重部署： cd ${APP_DIR} && git pull && bash scripts/deploy-server.sh"
echo "    看运行日志： journalctl -u ${SERVICE} -f"
echo "    重启服务：   systemctl restart ${SERVICE}"
echo "============================================================"
