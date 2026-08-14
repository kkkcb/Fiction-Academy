#!/usr/bin/env bash
# ============================================================================
# Fiction Academy 自动更新（装在服务器上）
#
# 安装定时任务（只需执行一次）：
#   bash /opt/fiction-academy/scripts/auto-update.sh --install
#
# 安装后：每 2 分钟自动检查 GitHub 是否有新提交，
#   有 → 拉代码 + 装依赖 + 重启服务（日志见 logs/auto-update.log）
#   无 → 什么都不做
# 因此本地的工作流是：改代码 → git push → 几分钟内服务器自动更新。
#
# 手动触发一次： bash scripts/auto-update.sh
# 卸载：         crontab -e 删掉那一行
#
# 注意：本脚本走轻量路径（pull/pip/restart）。若仓库改了 Nginx/systemd
# 等基础设施配置，需手动跑一次 scripts/deploy-server.sh。
# ============================================================================
set -uo pipefail

APP_DIR="${APP_DIR:-/opt/fiction-academy}"
LOG="$APP_DIR/logs/auto-update.log"

if [ "${1:-}" = "--install" ]; then
  mkdir -p "$APP_DIR/logs"
  CRON_LINE="*/2 * * * * bash $APP_DIR/scripts/auto-update.sh"
  (crontab -l 2>/dev/null | grep -vF "$APP_DIR/scripts/auto-update.sh"; echo "$CRON_LINE") | crontab -
  echo "✅ 已安装：每 2 分钟自动检查更新（有新提交才会动，日志 $LOG）"
  exit 0
fi

cd "$APP_DIR" || exit 1

git fetch origin main --quiet 2>/dev/null || exit 0   # 网络抖动就等下个周期
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse origin/main)"
[ "$LOCAL" = "$REMOTE" ] && exit 0                     # 没有新提交，静默退出

{
  echo "---- $(date '+%F %T') 发现新版本，开始更新 ----"
  if git pull --ff-only --quiet; then
    "$APP_DIR/.venv/bin/pip" install -q -r backend/requirements.txt 2>/dev/null
    systemctl restart fiction-academy
    for i in $(seq 1 30); do
      if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
        echo "✅ 更新完成并已重启（$LOCAL → $REMOTE）"
        exit 0
      fi
      sleep 1
    done
    echo "❌ 重启后健康检查失败，请查看 journalctl -u fiction-academy -n 30"
  else
    echo "❌ git pull 失败（本地有改动？），跳过本次更新"
  fi
} >> "$LOG" 2>&1
