# -*- coding: utf-8 -*-
"""批量写完第一卷（第 4-40 章）：默认精细思考模式，逐章串行，失败重试。"""
import json
import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://localhost:8100"
PID = "7df594d9-ed04-446b-b13d-a6e356fad06f"
TARGET = 40

HINT = (
    "卷一《茶还没凉》（1-40章）推进：日常立人设+洪流撞门。核心冲突线：血神教执事夜袭被灭的余波"
    "→仙门招考撞镇→盘缠危机→香主血阵（欲屠五千生灵）→沈青梧查案三断线。"
    "爽点节奏：憋势→一招平事→哈欠回屋；小高潮：天骄之剑当街碎成渣；李小满获'呼吸操'承法线同步推进。"
    "严格按倒推因果链与既定设定，人物红线不破，每章结尾留断章钩子。"
)


def write_one(c: httpx.Client, t0: float) -> dict:
    done = {}
    with c.stream("POST", f"{BASE}/api/projects/{PID}/chapters/write-stream",
                  json={"user_hint": HINT}) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("phase") == "writing" and obj.get("chapter_number"):
                print(f"[{time.time()-t0:6.0f}s] 第{obj['chapter_number']}章《{obj.get('chapter_title')}》执笔", flush=True)
            if obj.get("message"):
                print(f"[{time.time()-t0:6.0f}s]   {obj['message']}", flush=True)
            if obj.get("done"):
                done = obj
            if obj.get("error"):
                return {"error": obj["error"]}
    return done


def main():
    t0 = time.time()
    with httpx.Client(timeout=1200, trust_env=False) as c:
        for ch in range(4, TARGET + 1):
            for attempt in range(1, 4):
                try:
                    result = write_one(c, t0)
                except Exception as e:
                    result = {"error": str(e)[:120]}
                if result.get("done"):
                    print(f"[{time.time()-t0:6.0f}s] ✅ 第{result['chapter_number']}章《{result['chapter_title']}》"
                          f"{result['word_count']}字（第 {ch-3}/{TARGET-3} 章）", flush=True)
                    break
                print(f"[{time.time()-t0:6.0f}s] ⚠ 第{ch}章失败（尝试{attempt}/3）：{result.get('error')}", flush=True)
                time.sleep(5)
            else:
                print(f"第{ch}章三次失败，终止批次", flush=True)
                sys.exit(1)
    print(f"\n===== 第一卷完成：4-{TARGET} 章全部写完，总耗时 {(time.time()-t0)/60:.0f} 分钟 =====", flush=True)


if __name__ == "__main__":
    main()
