# -*- coding: utf-8 -*-
"""数据同步：把小说数据库（含全部项目/章节/素材）随仓库推送到 GitHub。

用法（在写完内容后执行）：
  python scripts/push_data.py "备注（可选，如：卷一1-10章）"

做了什么：
  1. SQLite WAL checkpoint —— 把缓存写盘完整并入主库文件（否则直接提交会丢最近的内容）
  2. git add data/fiction_academy.db + commit + push

新机器拉取：git pull 后直接启动即可。
注意：数据库是二进制文件，不能合并——请勿两台机器同时写作后各自 push（后推的会覆盖，
   冲突时需手动选择保留哪份：git checkout --ours/--theirs data/fiction_academy.db）。
"""
import sqlite3
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
DB = "data/fiction_academy.db"


def main() -> None:
    msg = "data: sync novel database " + (sys.argv[1] if len(sys.argv) > 1 else "")
    print("1/3 WAL checkpoint…")
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    print("2/3 提交…")
    subprocess.run(["git", "add", "-f", DB], check=True)
    subprocess.run(["git", "commit", "-m", msg], check=True)
    print("3/3 推送…")
    subprocess.run(["git", "push"], check=True)
    print("✅ 数据已同步到 GitHub（私有仓库）")


if __name__ == "__main__":
    main()
