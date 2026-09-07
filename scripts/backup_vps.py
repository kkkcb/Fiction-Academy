# -*- coding: utf-8 -*-
"""Fiction-Academy VPS 数据自动备份（Windows 计划任务调用，每天首次登录触发，幂等跳过）。

备份内容：服务器 /opt/fiction-academy/data/ → 本机 backups/vps-日期/
日志：backups/backup.log（成功/失败静默记录，不打扰用户）
密码：读项目根 .vps-pass（gitignored，不进仓库）
手动补一次也用它：python scripts/backup_vps.py
"""
import os
import sys
import datetime
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/ 的上级
BACKUP_DIR = os.path.join(ROOT, "backups")
LOG_FILE = os.path.join(BACKUP_DIR, "backup.log")
PASS_FILE = os.path.join(ROOT, ".vps-pass")

VPS_IP = "YOUR_VPS_IP"
VPS_USER = "root"
APP_DIR = "/opt/fiction-academy"


def log(msg):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")


def main():
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    dest = os.path.join(BACKUP_DIR, f"vps-{stamp}")
    # 幂等：今天的归档已存在（任何时刻）则跳过——计划任务每次登录都触发，
    # 一天只真正备份一次
    if os.path.exists(os.path.join(dest, "data")):
        log(f"今日已备份（{dest}），跳过")
        return 0

    try:
        with open(PASS_FILE, encoding="utf-8") as f:
            pw = f.read().strip()
        import paramiko
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(VPS_IP, username=VPS_USER, password=pw, timeout=20)
        # 整目录打包（含 -wal/-shm），比单拷 db 文件更稳
        _, out, _ = ssh.exec_command(
            f"cd {APP_DIR} && tar czf /tmp/fa-backup.tar.gz data 2>/dev/null", timeout=120)
        out.channel.recv_exit_status()
        sftp = ssh.open_sftp()
        os.makedirs(dest, exist_ok=True)
        sftp.get("/tmp/fa-backup.tar.gz", os.path.join(dest, "fa-backup.tar.gz"))
        sftp.close()
        ssh.exec_command("rm -f /tmp/fa-backup.tar.gz")
        ssh.close()
        # 解包（python tarfile：Windows 自带 tar.exe 对中文路径会 exit 1）
        import tarfile
        with tarfile.open(os.path.join(dest, "fa-backup.tar.gz")) as t:
            t.extractall(dest, filter="data")
        os.remove(os.path.join(dest, "fa-backup.tar.gz"))
        # 只保留最近 30 份归档
        archives = sorted(d for d in os.listdir(BACKUP_DIR) if d.startswith("vps-"))
        for old in archives[:-30]:
            subprocess.run(["rm", "-rf", os.path.join(BACKUP_DIR, old)], capture_output=True)
        db = os.path.join(dest, "data", "fiction_academy.db")
        size = os.path.getsize(db) if os.path.exists(db) else -1
        log(f"备份成功 → {dest}（db {size} 字节）")
        return 0
    except Exception as e:
        log(f"备份失败: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
