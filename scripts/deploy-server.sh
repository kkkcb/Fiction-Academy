#!/usr/bin/env bash
# ============================================================================
# Fiction Academy 一键部署脚本（Ubuntu 20.04/22.04/24.04，需 root）
#
# 服务器上执行：
#   git clone https://github.com/kkkcb/Fiction-Academy.git /opt/fiction-academy
#   bash /opt/fiction-academy/scripts/deploy-server.sh
#
# 做了什么：
#   1. 安装依赖（python3-venv / nginx / apache2-utils）
#   2. 创建虚拟环境并安装 Python 依赖
#   3. 生成 .env.local（API Key 通过环境变量 LLM_API_KEY 或交互输入）
#   4. 注册 systemd 服务（开机自启、崩溃自动拉起，只监听 127.0.0.1:8000）
#   5. 配置 Nginx 反向代理 + Basic Auth（自动生成随机密码）
#   6. 健康检查并打印访问地址
#
# 幂等：重复执行 = 更新代码 + 重启服务，密码只在首次生成。
# ============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/fiction-academy}"
SERVICE="fiction-academy"
PYTHON_BIN="${PYTHON_BIN:-python3}"
# 对外端口（nginx 监听）；80 被其他服务占用时可用 PUBLIC_PORT=8080 bash deploy-server.sh
PUBLIC_PORT="${PUBLIC_PORT:-80}"

say() { echo -e "\n\033[1;36m==> $1\033[0m"; }
die() { echo -e "\n\033[1;31m[失败] $1\033[0m" >&2; exit 1; }

[ "$(id -u)" = "0" ] || die "请用 root 运行：sudo bash $0"
[ -f "$APP_DIR/backend/main.py" ] || die "未找到代码，请先：git clone https://github.com/kkkcb/Fiction-Academy.git $APP_DIR"
command -v "$PYTHON_BIN" >/dev/null || die "未找到 python3"

# ---------------------------------------------------------------- 1. 系统依赖
say "安装系统依赖（python3-venv / nginx / apache2-utils）..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y -qq
apt-get install -y -qq python3-venv nginx apache2-utils >/dev/null

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

# ---------------------------------------------------------------- 6. Nginx + Basic Auth
say "配置 Nginx（${PUBLIC_PORT} 端口 + Basic Auth）..."
AUTH_USER="admin"
HTPASSWD="/etc/nginx/.htpasswd-fiction"
if [ ! -f "$HTPASSWD" ]; then
    # 注意：不能用 tr < /dev/urandom | head 的写法——pipefail 下 head 提前退出
    # 会令 tr 因 SIGPIPE 以 141 退出，set -e 直接终止脚本
    AUTH_PASS="$(openssl rand -hex 6 2>/dev/null || head -c9 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    htpasswd -bc "$HTPASSWD" "$AUTH_USER" "$AUTH_PASS" >/dev/null 2>&1
    echo "$AUTH_PASS" > /root/fiction-academy-password.txt
    chmod 600 /root/fiction-academy-password.txt
else
    AUTH_PASS="(沿用之前生成的密码，见 /root/fiction-academy-password.txt)"
fi

cat > "/etc/nginx/sites-available/${SERVICE}" <<EOF
server {
    listen ${PUBLIC_PORT} default_server;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header Connection "";

        # SSE 流式输出必需
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;

        auth_basic "Fiction Academy";
        auth_basic_user_file /etc/nginx/.htpasswd-fiction;
    }
}
EOF
rm -f /etc/nginx/sites-enabled/default
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
echo "  用户名：   ${AUTH_USER}"
echo "  密码：     ${AUTH_PASS}"
echo "  （密码也保存在服务器 /root/fiction-academy-password.txt）"
echo "------------------------------------------------------------"
echo "  常用命令："
echo "    更新重部署： cd ${APP_DIR} && git pull && bash scripts/deploy-server.sh"
echo "    看运行日志： journalctl -u ${SERVICE} -f"
echo "    重启服务：   systemctl restart ${SERVICE}"
echo "============================================================"
