# -*- coding: utf-8 -*-
"""端到端跑通：创建项目 → 依次生成五个点位（槽位）→ 汇总结果。
用法:
  python scripts/run_slots_demo.py                 # 全新项目
  python scripts/run_slots_demo.py --resume <pid>  # 断点续跑（跳过已完成槽位）
（需本地后端已启动 + .env.local 配好 Key）
"""
import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://localhost:8000/api"

THEME = (
    "番茄小说平台风格的长篇修仙小说。主角是一个散漫的修仙者：大背景是大争之世"
    "（灵气复苏末法、宗门倾轧、妖乱将起），人人趋利逐势，而他随遇而安——"
    "城镇起热闹、众人扎堆逐利时，他偏偏独善其身，守着自己的小院小日子："
    "种灵茶、晒太阳、给街坊看看小病。但他实力深藏不露，来历成谜。"
    "基调是轻松日常流 + 偶尔露锋芒的反差爽点，主角不主动惹事但事来了也不怕。"
)

POINTS = [
    ("story_core", "重点产出：一句话卖点、题材定位（番茄免费阅读·轻松修仙日常流）、核心爽点（藏拙反差）、情绪基调、目标读者"),
    ("world_setting", "重点产出：大时代背景与危机、力量体系（境界划分）、主角所在小镇的生态、世界观规则与隐患"),
    ("character_setting", "重点产出：主角人设（性格、习惯、口头禅、隐藏实力层次）、2-3个配角（街坊/官府/暗线人物）、人物关系"),
    ("outline_reverse", "从大结局倒推：主角最终站在什么位置、各阶段关键节点、伏笔埋设与回收"),
    ("outline", "正向卷纲：前三卷的卷名、主线事件、每卷爽点与小高潮"),
]


def main() -> None:
    resume_pid = None
    if "--resume" in sys.argv:
        resume_pid = sys.argv[sys.argv.index("--resume") + 1]

    t0 = time.time()
    with httpx.Client(timeout=900, trust_env=False) as c:  # trust_env=False: localhost 不走代理
        if resume_pid:
            pid = resume_pid
            print(f"[续跑] 项目: {pid}")
        else:
            r = c.post(f"{BASE}/projects", json={"name": "", "genre": "仙侠·轻松日常流"})
            r.raise_for_status()
            pid = r.json()["id"]
            print(f"[新建] 项目: {pid}（名称留空，等故事核自动命名）")

        r = c.get(f"{BASE}/projects/{pid}/points")
        r.raise_for_status()
        done = {p["point"] for p in r.json()["points"] if p["status"] == "done"}

        for point, extra in POINTS:
            if point in done:
                print(f"[跳过] {point}（已完成）")
                continue
            idea = f"{THEME}\n\n{extra}"
            ts = time.time()
            try:
                r = c.post(f"{BASE}/projects/{pid}/points/{point}/auto-generate", json={"idea": idea})
                r.raise_for_status()
            except Exception as e:
                print(f"[失败] {point}: {type(e).__name__} {str(e)[:200]}")
                sys.exit(1)
            data = r.json()
            name = data.get("project_name") or ""
            fields = data.get("metadata") or data.get("fields") or {}
            n = len([v for v in fields.values() if v])
            summary = (data.get("summary") or data.get("content") or "").replace("\n", " ")
            print(f"[完成] {point:<20}（{time.time()-ts:.0f}s）字段 {n} 个"
                  f"{' | 项目命名 → ' + name if name else ''}")
            print(f"        {summary[:80]}...")

        r = c.get(f"{BASE}/projects/{pid}/points")
        items = r.json()["points"]
        print(f"\n[校验] 点位落库状态：")
        for it in items:
            print(f"  - {it['point']:<20} status={it['status']:<8} archived={it['has_archive']}")

        r = c.get(f"{BASE}/projects/{pid}")
        proj = r.json()
        print(f"\n=== 最终书名：《{proj.get('name')}》  总耗时 {time.time()-t0:.0f}s ===")


if __name__ == "__main__":
    main()
