#!/usr/bin/env bash
# ============================================================================
# Fiction Academy 一键更新 VPS（本机执行，非服务器上执行）
#
#   bash scripts/deploy-vps.sh
#   VPS_PW=xxx bash scripts/deploy-vps.sh    # 密码走环境变量，否则交互输入
#
# 做了什么：本地 build 前端 → 打包 后端+dist+数据库+characters → 上传
# /opt/fiction-academy 解包 → 重启 systemd 服务 → 版本自检。
# 不动 nginx/systemd 配置；基础设施变更需 SSH 上服务器跑 scripts/deploy-server.sh。
#
# 注意：打包包含 data/fiction_academy.db，会覆盖服务器上的数据库（本机为准）。
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

echo "→ 部署前先备份线上数据（防数据库覆盖/误操作事故）"
python scripts/backup_vps.py || echo "  （备份失败不阻塞部署，查看 backups/backup.log）"

VPS_IP="${VPS_IP:-YOUR_VPS_IP}"
VPS_USER="${VPS_USER:-root}"
APP_DIR="${APP_DIR:-/opt/fiction-academy}"

echo "→ 本地构建前端"
(cd frontend-vue && npm run build --silent >/dev/null 2>&1 || npm run build >/dev/null)

GIT_SHA=$(git rev-parse --short HEAD)
echo "$GIT_SHA $(date +%F\ %T)" > backend/DEPLOY_VERSION
tar czf ./.deploy-fa.tar.gz --exclude='__pycache__' --exclude='backend.log' \
  backend characters frontend-vue/dist scripts data/fiction_academy.db

echo "→ 上传到 $VPS_IP 并部署（版本 $GIT_SHA）"
VPS_IP="$VPS_IP" VPS_USER="$VPS_USER" APP_DIR="$APP_DIR" LOCAL_SHA="$GIT_SHA" python - <<'PYEOF'
import os, paramiko, sys

ip, user, app_dir = os.environ["VPS_IP"], os.environ["VPS_USER"], os.environ["APP_DIR"]
local_sha = os.environ["LOCAL_SHA"]
pw = os.environ.get("VPS_PW") or input("VPS 密码: ")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(ip, username=user, password=pw, timeout=15)
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

echo "→ 线上地址: http://$VPS_IP:8080/（Basic Auth admin，密码见服务器 /root/fiction-academy-password.txt）"
