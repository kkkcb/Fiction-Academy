# -*- coding: utf-8 -*-
"""按钮级回归测试：在一次性项目上逐一验证所有 UI 按钮对应的后端行为。

用法（需本地后端已启动）:
  python scripts/regression.py             # 快速模式：全部 CRUD/校验路径，无 LLM 调用
  python scripts/regression.py --with-llm  # 追加一次真实聊天流冒烟

每次更新代码后应运行：pytest（桩测）→ npm run build → 本脚本（活体回归）。
"""
import json
import sys
import time
import uuid

import httpx

sys.stdout.reconfigure(encoding="utf-8")
import os
BASE = os.getenv("FA_BASE", "http://localhost:8000")

PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    mark = "✅" if cond else "❌"
    print(f"  {mark} {name}" + (f"  [{detail[:80]}]" if detail and not cond else ""))
    PASS += cond
    FAIL += not cond


def _cleanup_leftovers():
    """防泄漏兜底：删除任何残留的「回归测试-*」项目（即使回归中途崩溃也不留在用户列表）。"""
    try:
        c = httpx.Client(timeout=30, trust_env=False)
        for p in c.get(f"{BASE}/api/projects").json():
            if str(p.get("name", "")).startswith("回归测试"):
                c.delete(f"{BASE}/api/projects/{p['id']}")
                print(f"  [兜底清理] 删除残留测试项目 {p['name']}")
    except Exception as e:
        print("  [兜底清理] 跳过：", e)


def main():
    try:
        _run()
    finally:
        _cleanup_leftovers()


def _run():
    with_llm = "--with-llm" in sys.argv
    t0 = time.time()
    c = httpx.Client(timeout=60, trust_env=False)

    print("\n== 基础 ==")
    r = c.get(f"{BASE}/api/health")
    check("健康检查", r.status_code == 200 and r.json().get("llm_configured"))
    r = c.get(f"{BASE}/")
    check("前端页面托管", r.status_code == 200 and "index-" in r.text)

    print("\n== 项目页按钮 ==")
    r = c.post(f"{BASE}/api/projects", json={"name": "回归测试-" + uuid.uuid4().hex[:6], "genre": "测试"})
    check("新建项目", r.status_code == 200)
    pid = r.json()["id"]
    r = c.put(f"{BASE}/api/projects/{pid}", json={"name": "回归测试-改名"})
    check("重命名项目", r.status_code == 200 and r.json()["name"] == "回归测试-改名")
    r = c.put(f"{BASE}/api/projects/{pid}", json={"rules_text": "- 测试守则"})
    check("创作守则保存", r.status_code == 200 and r.json().get("rules_text") == "- 测试守则")

    print("\n== 侧栏按钮 ==")
    conv_ids = []
    for point in ["story_core", "world_setting", "character_setting", "outline_reverse", "outline"]:
        r = c.post(f"{BASE}/api/projects/{pid}/points/{point}/ensure-conversation")
        ok = r.status_code == 200
        if ok:
            conv_ids.append(r.json()["conversation_id"])
        check(f"点位进入: {point}", ok)
    r = c.post(f"{BASE}/api/projects/{pid}/conversations", json={"title": "自由对话"})
    check("新建对话", r.status_code == 200)
    free_cid = r.json()["id"]
    conv_ids.append(free_cid)
    r = c.put(f"{BASE}/api/conversations/{free_cid}", json={"title": "改名对话"})
    check("重命名对话", r.status_code == 200)
    r = c.get(f"{BASE}/api/conversations/{free_cid}/messages")
    check("选对话加载消息", r.status_code == 200 and isinstance(r.json(), list))
    r = c.get(f"{BASE}/api/projects/{pid}/points")
    check("点位状态面板", r.status_code == 200 and len(r.json()["points"]) == 5)

    print("\n== 总览面板按钮 ==")
    r = c.post(f"{BASE}/api/projects/{pid}/workspace", json={
        "item_type": "setting", "title": "回归设定", "content": "内容v1", "status": "draft"})
    check("添加设定", r.status_code == 200)
    item_id = r.json()["id"]
    r = c.put(f"{BASE}/api/workspace/{item_id}", json={"content": "内容v2"})
    check("编辑条目", r.status_code == 200 and r.json()["content"] == "内容v2")
    r = c.put(f"{BASE}/api/workspace/{item_id}/status", json={"status": "finalized"})
    check("审批（draft→finalized）", r.status_code == 200)
    r = c.put(f"{BASE}/api/workspace/{item_id}/status", json={"status": "locked"})
    check("锁定（finalized→locked）", r.status_code == 200)
    r = c.put(f"{BASE}/api/workspace/{item_id}/status", json={"status": "draft"})
    check("解锁路径（locked→draft 应 200）", r.status_code == 200)
    r = c.get(f"{BASE}/api/projects/{pid}/chronicle")
    check("编年录读取", r.status_code == 200)

    print("\n== 知识图谱按钮 ==")
    r = c.post(f"{BASE}/api/projects/{pid}/kg/entities", json={
        "entity_type": "character", "name": "回归角色", "properties": {}, "knowledge_layer": "truth"})
    check("KG 添加实体", r.status_code == 200)
    ent_id = r.json()["id"]
    r = c.get(f"{BASE}/api/projects/{pid}/kg/graph")
    check("KG 图谱加载", r.status_code == 200 and any(e["id"] == ent_id for e in r.json()["entities"]))
    r = c.delete(f"{BASE}/api/kg/entities/{ent_id}")
    check("KG 删除实体", r.status_code == 200)

    print("\n== 写作面板守卫 ==")
    r = c.post(f"{BASE}/api/projects/{pid}/chapter-plan/generate", json={})
    check("无骨架时生成章纲被拒（409）", r.status_code == 409)

    print("\n== 异常路径 ==")
    check("删除不存在消息 → 404", c.delete(f"{BASE}/api/messages/{uuid.uuid4().hex}").status_code == 404)
    check("删除不存在实体 → 404/200", c.delete(f"{BASE}/api/kg/entities/{uuid.uuid4().hex}").status_code in (200, 404))
    r = c.post(f"{BASE}/api/projects/{pid}/points/bad_point/ensure-conversation")
    check("非法点位名被拒（400/422）", r.status_code in (400, 422))

    print("\n== 热点素材库 ==")
    r = c.post(f"{BASE}/api/materials", json={"title": "回归热点", "source": "weibo", "hot": "10万热度"})
    check("收藏素材", r.status_code == 200)
    mat_id = r.json()["id"] if r.status_code == 200 else None
    check("重复收藏被拒（409）",
          c.post(f"{BASE}/api/materials", json={"title": "回归热点", "source": "weibo"}).status_code == 409)
    check("素材列表", any(m["id"] == mat_id for m in c.get(f"{BASE}/api/materials").json()) if mat_id else False)
    if mat_id:
        check("删除素材", c.delete(f"{BASE}/api/materials/{mat_id}").status_code == 200)
    check("非法热榜源被拒（400）", c.get(f"{BASE}/api/hot?source=bad").status_code == 400)

    print("\n== 创作对话分拣 ==")
    check("无 studio 对话时分拣 404",
          c.post(f"{BASE}/api/projects/{pid}/studio/distill").status_code == 404)
    sid = c.post(f"{BASE}/api/projects/{pid}/studio/ensure").json().get("conversation_id")
    check("studio 对话创建/获取", bool(sid))
    if sid:
        check("空对话分拣被拒（400）",
              c.post(f"{BASE}/api/projects/{pid}/studio/distill").status_code == 400)

    if with_llm:
        print("\n== LLM 冒烟（真实调用） ==")
        try:
            lines = []
            with c.stream("POST", f"{BASE}/api/conversations/{free_cid}/chat/stream",
                          json={"content": "只回复两个字：收到", "assistant_id": ""}) as r:
                for line in r.iter_lines():
                    if line.strip():
                        lines.append(json.loads(line))
            done = any(l.get("done") for l in lines)
            text = "".join(l.get("content", "") for l in lines)
            check("聊天流式往返", done and len(text) > 0, f"done={done} text={text[:40]}")
            msg_ids = [l for l in c.get(f"{BASE}/api/conversations/{free_cid}/messages").json()]
            check("消息落库（user+assistant）", sum(1 for m in msg_ids if m["role"] == "user") >= 1
                  and sum(1 for m in msg_ids if m["role"] == "assistant") >= 1)
            # 右键删除链路（真实消息）
            first_id = msg_ids[0]["id"]
            check("右键删除真实消息", c.delete(f"{BASE}/api/messages/{first_id}").status_code == 200
                  and all(m["id"] != first_id for m in c.get(f"{BASE}/api/conversations/{free_cid}/messages").json()))
        except Exception as e:
            check("聊天流式往返", False, str(e))

    print("\n== 清理 ==")
    for cid in conv_ids:
        c.delete(f"{BASE}/api/conversations/{cid}")
    r = c.delete(f"{BASE}/api/projects/{pid}")
    check("删除项目（清理）", r.status_code == 200)
    check("项目删除后 404", c.get(f"{BASE}/api/projects/{pid}").status_code == 404)

    print(f"\n===== 回归结果: {PASS} 通过 / {FAIL} 失败（{time.time()-t0:.0f}s） =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
