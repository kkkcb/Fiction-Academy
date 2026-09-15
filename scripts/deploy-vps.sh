#!/usr/bin/env bash
# ============================================================================
# Fiction Academy 一键更新 VPS（本机执行，非服务器上执行）
#
#   bash scripts/deploy-vps.sh            # 只发代码（不动服务器数据）
#   bash scripts/deploy-vps.sh --data     # 代码 + 本机数据库覆盖服务器（危险，慎用）
#   VPS_PW=xxx bash scripts/deploy-vps.sh  # 密码走环境变量，否则交互输入
#
# 做了什么：本地 build 前端 → 打包 后端+dist+characters → 上传
# /opt/fiction-academy 解包 → 重启 systemd 服务 → 版本自检。
# 不动 nginx/systemd 配置；基础设施变更需 SSH 上服务器跑 scripts/deploy-server.sh。
#
# 数据方向（重要）：用户在网页版创作，服务器库是活数据——默认部署绝不覆盖它；
# 数据库迁移随服务重启在服务器上自动执行。要把本机数据推上去必须显式 --data。
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

echo "→ 部署前先备份线上数据（防误操作事故）"
python scripts/backup_vps.py || echo "  （备份失败不阻塞部署，查看 backups/backup.log）"

VPS_IP="${VPS_IP:-YOUR_VPS_IP}"
VPS_USER="${VPS_USER:-root}"
APP_DIR="${APP_DIR:-/opt/fiction-academy}"
WITH_DATA="${1:-}"

echo "→ 本地构建前端"
(cd frontend-vue && npm run build --silent >/dev/null 2>&1 || npm run build >/dev/null)

GIT_SHA=$(git rev-parse --short HEAD)
echo "$GIT_SHA $(date +%F\ %T)" > backend/DEPLOY_VERSION
if [ "$WITH_DATA" = "--data" ]; then
  echo "→ ⚠️  --data：本机数据库将覆盖服务器（服务器上的新对话会丢失！）"
  tar czf ./.deploy-fa.tar.gz --exclude='__pycache__' --exclude='backend.log' \
    backend characters frontend-vue/dist scripts data/fiction_academy.db
else
  tar czf ./.deploy-fa.tar.gz --exclude='__pycache__' --exclude='backend.log' \
    backend characters frontend-vue/dist scripts
fi

echo "→ 上传到 $VPS_IP 并部署（版本 $GIT_SHA）"
# MSYS_NO_PATHCONV：Git Bash 会把「VAR=/opt/...」前缀env 误转成 C:/Program Files/Git/opt/...
# （曾导致远端 tar -C 收到 Windows 路径而失败），这里禁掉转换
export MSYS_NO_PATHCONV=1
VPS_IP="$VPS_IP" VPS_USER="$VPS_USER" APP_DIR="$APP_DIR" LOCAL_SHA="$GIT_SHA" python - <<'PYEOF'
import os, paramiko, sys

ip, user = os.environ["VPS_IP"], os.environ["VPS_USER"]
# 兜底：万一 APP_DIR 再被壳层改坏，退回服务器约定路径
app_dir = os.environ.get("APP_DIR") or "/opt/fiction-academy"
if not app_dir.startswith("/"):
    app_dir = "/opt/fiction-academy"
local_sha = os.environ["LOCAL_SHA"]
pw = os.environ.get("VPS_PW") or input("VPS 密码: ")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(ip, username=user, password=pw, timeout=15, allow_agent=False, look_for_keys=False)
sftp = ssh.open_sftp()
# 上传/解包一律绝对路径：sftp 相对路径落在登录家目录，曾导致解包静默失败
sftp.put("./.deploy-fa.tar.gz", "/tmp/deploy-fa.tar.gz")
sftp.close()

failed = False
for c in [f"tar xzf /tmp/deploy-fa.tar.gz -C {app_dir}",
          "systemctl restart fiction-academy", "sleep 3",
          "systemctl is-active fiction-academy && curl -s http://127.0.0.1:8000/api/health"]:
    _, out, err = ssh.exec_command(c, timeout=120)
    rc = out.channel.recv_exit_status()
    o, e = out.read().decode().strip(), err.read().decode().strip()
    if o: print(o)
    if rc != 0:
        print(f"[命令失败 rc={rc}] {c}\n{e[:300]}")
        failed = True
        break
if not failed:
    # 版本自检：解包后的 DEPLOY_VERSION 必须与本地 SHA 一致
    _, out, _ = ssh.exec_command(f"cat {app_dir}/backend/DEPLOY_VERSION", timeout=15)
    remote = out.read().decode().strip()
    if not remote.startswith(local_sha):
        print(f"[版本不一致] 本地 {local_sha} vs 线上 {remote!r} — 解包可能失败！")
        failed = True
    else:
        print(f"版本自检通过: {remote}")
_, out, _ = ssh.exec_command("rm -f /tmp/deploy-fa.tar.gz", timeout=15)
out.channel.recv_exit_status()
ssh.close()
sys.exit(1 if failed else 0)
PYEOF

echo "→ 线上地址: http://$VPS_IP:8080/（密码门，访问密码见服务器 /root/fiction-academy-password.txt）"
