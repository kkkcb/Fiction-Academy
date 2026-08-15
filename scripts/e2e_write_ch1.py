# -*- coding: utf-8 -*-
"""E2E：真实调用一键写章端点，为晒太阳项目写第 1 章。"""
import sys
import time
import json

import httpx

sys.stdout.reconfigure(encoding="utf-8")
PID = "7df594d9-ed04-446b-b13d-a6e356fad06f"

t0 = time.time()
phase_shown = set()
content_len = 0
done_info = {}

with httpx.Client(timeout=900, trust_env=False) as c:
    with c.stream("POST", f"http://localhost:8000/api/projects/{PID}/chapters/write-stream", json={}) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("phase") and obj["phase"] not in phase_shown:
                phase_shown.add(obj["phase"])
                print(f"[{time.time()-t0:5.0f}s] 阶段: {obj['phase']} {obj.get('message') or obj.get('chapter_title', '')}")
                if obj.get("plan"):
                    print("  章纲前 100 字:", obj["plan"].replace(chr(10), " ")[:100])
            if obj.get("content"):
                content_len += len(obj["content"])
                if content_len % 800 < 120:
                    print(f"[{time.time()-t0:5.0f}s] 已生成 {content_len} 字…")
            if obj.get("done"):
                done_info = obj
            if obj.get("error"):
                print("错误:", obj["error"])
                sys.exit(1)

print(f"\n=== 完成（{time.time()-t0:.0f}s）===")
print(f"第{done_info.get('chapter_number')}章《{done_info.get('chapter_title')}》 共 {done_info.get('word_count')} 字")
