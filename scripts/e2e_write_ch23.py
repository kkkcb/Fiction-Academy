# -*- coding: utf-8 -*-
"""生成黄金三章的第 2、3 章（真实 LLM，串行两轮）。"""
import sys
import time
import json

import httpx

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://localhost:8100"
PID = "7df594d9-ed04-446b-b13d-a6e356fad06f"

for round_no in (1, 2):
    t0 = time.time()
    content_len = 0
    done_info = {}
    with httpx.Client(timeout=900, trust_env=False) as c:
        with c.stream("POST", f"{BASE}/api/projects/{PID}/chapters/write-stream", json={}) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get("phase") == "writing":
                    print(f"[{time.time()-t0:5.0f}s] 第{obj.get('chapter_number')}章《{obj.get('chapter_title')}》开始执笔")
                if obj.get("content"):
                    content_len += len(obj["content"])
                if obj.get("done"):
                    done_info = obj
                if obj.get("error"):
                    print("错误:", obj["error"])
                    sys.exit(1)
    print(f"[{time.time()-t0:5.0f}s] 完成：第{done_info.get('chapter_number')}章《{done_info.get('chapter_title')}》{done_info.get('word_count')}字")
