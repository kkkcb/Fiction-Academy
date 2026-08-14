import json
import uuid
from typing import Any

from backend.database import get_db, fetch_all, fetch_one


ENTITY_TYPE_LABELS = {
    "character": "角色",
    "location": "地点",
    "faction": "势力",
    "item": "物品",
    "event": "事件",
}

LAYER_LABELS = {
    "truth": "既定事实",
    "revealed": "已揭示",
    "foreshadow": "伏笔",
}


def _entity_row_to_dict(row) -> dict:
    d = dict(row)
    for k in ("aliases", "properties"):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k]) if d[k] else ([] if k == "aliases" else {})
            except (json.JSONDecodeError, TypeError):
                d[k] = [] if k == "aliases" else {}
    return d


def _relation_row_to_dict(row) -> dict:
    d = dict(row)
    if "properties" in d and isinstance(d["properties"], str):
        try:
            d["properties"] = json.loads(d["properties"]) if d["properties"] else {}
        except (json.JSONDecodeError, TypeError):
            d["properties"] = {}
    return d


async def list_entities(project_id: str, entity_type: str = "", layer: str = "") -> list[dict]:
    db = await get_db()
    sql = "SELECT * FROM kg_entities WHERE project_id = ?"
    params: list[Any] = [project_id]
    if entity_type:
        sql += " AND entity_type = ?"
        params.append(entity_type)
    if layer:
        sql += " AND knowledge_layer = ?"
        params.append(layer)
    sql += " ORDER BY entity_type, name"
    rows = await fetch_all(db, sql, tuple(params))
    return [_entity_row_to_dict(r) for r in rows]


async def list_relations(project_id: str) -> list[dict]:
    db = await get_db()
    rows = await fetch_all(
        db,
        """SELECT r.*, s.name as subject_name, s.entity_type as subject_type,
                  o.name as object_name, o.entity_type as object_type
           FROM kg_relations r
           JOIN kg_entities s ON r.subject_id = s.id
           JOIN kg_entities o ON r.object_id = o.id
           WHERE r.project_id = ?
           ORDER BY r.predicate, s.name""",
        (project_id,),
    )
    return [_relation_row_to_dict(r) for r in rows]


async def get_graph(project_id: str, chapter: int | None = None, layers: list[str] | None = None) -> dict:
    db = await get_db()
    layer_filter = layers or ["truth", "revealed", "foreshadow"]
    placeholders = ",".join("?" for _ in layer_filter)

    ent_sql = f"SELECT * FROM kg_entities WHERE project_id = ? AND knowledge_layer IN ({placeholders})"
    ent_params: list[Any] = [project_id, *layer_filter]
    if chapter is not None:
        ent_sql += " AND (chapter_from IS NULL OR chapter_from <= ?) AND (chapter_to IS NULL OR chapter_to >= ?)"
        ent_params.extend([chapter, chapter])
    ent_sql += " ORDER BY entity_type, name"
    ent_rows = await fetch_all(db, ent_sql, tuple(ent_params))
    entities = [_entity_row_to_dict(r) for r in ent_rows]
    ent_ids = {e["id"] for e in entities}

    rel_sql = f"""SELECT r.*, s.name as subject_name, s.entity_type as subject_type,
                         o.name as object_name, o.entity_type as object_type
                  FROM kg_relations r
                  JOIN kg_entities s ON r.subject_id = s.id
                  JOIN kg_entities o ON r.object_id = o.id
                  WHERE r.project_id = ? AND r.knowledge_layer IN ({placeholders})"""
    rel_params: list[Any] = [project_id, *layer_filter]
    if chapter is not None:
        rel_sql += " AND (r.chapter_from IS NULL OR r.chapter_from <= ?) AND (r.chapter_to IS NULL OR r.chapter_to >= ?)"
        rel_params.extend([chapter, chapter])
    rel_rows = await fetch_all(db, rel_sql, tuple(rel_params))
    relations = [_relation_row_to_dict(r) for r in rel_rows if r["subject_id"] in ent_ids and r["object_id"] in ent_ids]

    return {"entities": entities, "relations": relations}


async def create_entity(project_id: str, data: dict) -> dict:
    db = await get_db()
    eid = str(uuid.uuid4())
    aliases = data.get("aliases", [])
    properties = data.get("properties", {})
    await db.execute(
        """INSERT INTO kg_entities
           (id, project_id, entity_type, name, aliases, properties, knowledge_layer,
            chapter_from, chapter_to, source, confidence, summary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            eid, project_id, data["entity_type"], data["name"],
            json.dumps(aliases, ensure_ascii=False),
            json.dumps(properties, ensure_ascii=False),
            data.get("knowledge_layer", "truth"),
            data.get("chapter_from"), data.get("chapter_to"),
            data.get("source", "manual"), data.get("confidence", 1.0),
            data.get("summary", ""),
        ),
    )
    await db.commit()
    row = await fetch_one(db, "SELECT * FROM kg_entities WHERE id = ?", (eid,))
    return _entity_row_to_dict(row)


async def update_entity(entity_id: str, data: dict) -> dict:
    db = await get_db()
    allowed = {"entity_type", "name", "aliases", "properties", "knowledge_layer",
               "chapter_from", "chapter_to", "summary", "confidence"}
    sets: list[str] = []
    params: list[Any] = []
    for k, v in data.items():
        if k not in allowed:
            continue
        if k in ("aliases", "properties"):
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f"{k} = ?")
        params.append(v)
    if not sets:
        row = await fetch_one(db, "SELECT * FROM kg_entities WHERE id = ?", (entity_id,))
        return _entity_row_to_dict(row)
    sets.append("updated_at = datetime('now')")
    params.append(entity_id)
    await db.execute(f"UPDATE kg_entities SET {', '.join(sets)} WHERE id = ?", tuple(params))
    await db.commit()
    row = await fetch_one(db, "SELECT * FROM kg_entities WHERE id = ?", (entity_id,))
    return _entity_row_to_dict(row)


async def delete_entity(entity_id: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM kg_entities WHERE id = ?", (entity_id,))
    await db.commit()


async def create_relation(project_id: str, data: dict) -> dict:
    db = await get_db()
    rid = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO kg_relations
           (id, project_id, subject_id, predicate, object_id, direction,
            properties, knowledge_layer, chapter_from, chapter_to, confidence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            rid, project_id, data["subject_id"], data["predicate"], data["object_id"],
            data.get("direction", "directed"),
            json.dumps(data.get("properties", {}), ensure_ascii=False),
            data.get("knowledge_layer", "truth"),
            data.get("chapter_from"), data.get("chapter_to"),
            data.get("confidence", 1.0),
        ),
    )
    await db.commit()
    row = await fetch_one(db, "SELECT * FROM kg_relations WHERE id = ?", (rid,))
    return _relation_row_to_dict(row)


async def delete_relation(relation_id: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM kg_relations WHERE id = ?", (relation_id,))
    await db.commit()


async def _find_entity_by_name(db, project_id: str, entity_type: str, name: str) -> dict | None:
    row = await fetch_one(
        db,
        "SELECT * FROM kg_entities WHERE project_id = ? AND entity_type = ? AND name = ?",
        (project_id, entity_type, name),
    )
    if row:
        return _entity_row_to_dict(row)
    rows = await fetch_all(
        db,
        "SELECT * FROM kg_entities WHERE project_id = ? AND entity_type = ?",
        (project_id, entity_type),
    )
    target = name.strip().lower()
    for r in rows:
        d = _entity_row_to_dict(r)
        for a in d.get("aliases", []):
            if isinstance(a, str) and a.strip().lower() == target:
                return d
    return None


async def merge_extraction(project_id: str, extraction: dict, source: str = "ai") -> dict:
    db = await get_db()
    stats = {"entities_new": 0, "entities_updated": 0, "relations_new": 0, "relations_dup": 0}
    name_to_id: dict[tuple[str, str], str] = {}

    for ent in extraction.get("entities", []):
        etype = ent.get("type", "character").lower()
        if etype not in ENTITY_TYPE_LABELS:
            etype = "character"
        name = (ent.get("name") or "").strip()
        if not name:
            continue
        existing = await _find_entity_by_name(db, project_id, etype, name)
        props = ent.get("properties", {})
        aliases = ent.get("aliases", [])
        layer = ent.get("knowledge_layer", ent.get("layer", "truth"))
        if layer not in LAYER_LABELS:
            layer = "truth"
        if existing:
            new_props = {**existing.get("properties", {}), **props}
            merged_aliases = list(dict.fromkeys([*existing.get("aliases", []), *aliases]))
            need_update = new_props != existing.get("properties") or merged_aliases != existing.get("aliases")
            if ent.get("summary") and not existing.get("summary"):
                need_update = True
            if need_update:
                await db.execute(
                    """UPDATE kg_entities SET properties = ?, aliases = ?, summary = COALESCE(NULLIF(?, ''), summary), updated_at = datetime('now') WHERE id = ?""",
                    (json.dumps(new_props, ensure_ascii=False), json.dumps(merged_aliases, ensure_ascii=False), ent.get("summary", ""), existing["id"]),
                )
                stats["entities_updated"] += 1
            name_to_id[(etype, name)] = existing["id"]
        else:
            eid = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO kg_entities
                   (id, project_id, entity_type, name, aliases, properties, knowledge_layer, source, summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (eid, project_id, etype, name,
                 json.dumps(aliases, ensure_ascii=False),
                 json.dumps(props, ensure_ascii=False),
                 layer, source, ent.get("summary", "")),
            )
            name_to_id[(etype, name)] = eid
            stats["entities_new"] += 1

    await db.commit()

    for rel in extraction.get("relations", []):
        subj_name = (rel.get("subject") or "").strip()
        obj_name = (rel.get("object") or "").strip()
        subj_type = (rel.get("subject_type") or "character").lower()
        obj_type = (rel.get("object_type") or "character").lower()
        if subj_type not in ENTITY_TYPE_LABELS:
            subj_type = "character"
        if obj_type not in ENTITY_TYPE_LABELS:
            obj_type = "character"
        subj_id = name_to_id.get((subj_type, subj_name)) or await _resolve_id_by_name(db, project_id, subj_type, subj_name)
        obj_id = name_to_id.get((obj_type, obj_name)) or await _resolve_id_by_name(db, project_id, obj_type, obj_name)
        if not subj_id or not obj_id:
            continue
        predicate = (rel.get("predicate") or "").strip()
        if not predicate:
            continue
        dup = await fetch_one(
            db,
            "SELECT id FROM kg_relations WHERE project_id = ? AND subject_id = ? AND predicate = ? AND object_id = ?",
            (project_id, subj_id, predicate, obj_id),
        )
        if dup:
            stats["relations_dup"] += 1
            continue
        layer = rel.get("knowledge_layer", rel.get("layer", "truth"))
        if layer not in LAYER_LABELS:
            layer = "truth"
        rid = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO kg_relations
               (id, project_id, subject_id, predicate, object_id, direction, properties, knowledge_layer, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rid, project_id, subj_id, predicate, obj_id,
             rel.get("direction", "directed"),
             json.dumps(rel.get("properties", {}), ensure_ascii=False),
             layer, rel.get("confidence", 1.0)),
        )
        stats["relations_new"] += 1

    await db.commit()
    return stats


async def _resolve_id_by_name(db, project_id: str, etype: str, name: str) -> str | None:
    if not name:
        return None
    ent = await _find_entity_by_name(db, project_id, etype, name)
    return ent["id"] if ent else None


async def build_kg_injection(project_id: str, scene: str = "", chapter: int | None = None,
                             max_tokens: int = 2000) -> str:
    db = await get_db()
    is_writing = scene in ("write_chapter", "edit_chapter")
    layers = ["truth", "revealed"] if is_writing else ["truth", "revealed", "foreshadow"]
    graph = await get_graph(project_id, chapter=chapter, layers=layers)
    entities = graph["entities"]
    relations = graph["relations"]
    if not entities and not relations:
        return ""
    by_type: dict[str, list[dict]] = {}
    for e in entities:
        by_type.setdefault(e["entity_type"], []).append(e)

    # token 预算：按类型重要性裁剪，优先保留角色/势力；关系网络最后保留
    type_priority = ("character", "faction", "location", "item", "event")

    def _estimate(entity: dict) -> int:
        text = entity["name"] + str(entity.get("properties") or "") + (entity.get("summary") or "")
        return max(10, len(text) * 3 // 5)

    used = 0
    kept: dict[str, list[dict]] = {}
    for etype in type_priority:
        items = sorted(by_type.get(etype, []), key=lambda e: -float(e.get("confidence") or 0))
        kept_list = []
        for e in items:
            cost = _estimate(e)
            if used + cost > max_tokens:
                break
            used += cost
            kept_list.append(e)
        if kept_list:
            kept[etype] = kept_list
    kept_entity_names = {e["name"] for items in kept.values() for e in items}
    kept_relations = [
        r for r in relations
        if r.get("subject_name") in kept_entity_names and r.get("object_name") in kept_entity_names
    ][: max(10, (max_tokens - used) // 20)]

    lines: list[str] = []
    layer_note = "（仅注入已确立事实与已揭示信息，伏笔层未注入以防剧透）" if is_writing else "（全知视角：含伏笔层）"
    lines.append(f'<knowledge_graph priority="high">{layer_note}')
    lines.append("以下是本项目知识图谱中已结构化的设定，创作时必须保持一致：")
    lines.append("")

    for etype in type_priority:
        items = kept.get(etype, [])
        if not items:
            continue
        label = ENTITY_TYPE_LABELS[etype]
        lines.append(f"【{label}】")
        for e in items:
            parts: list[str] = [e["name"]]
            props = e.get("properties", {})
            for pk, pv in props.items():
                if pv:
                    parts.append(f"{pk}：{pv}")
            if e.get("summary"):
                parts.append(e["summary"])
            layer_tag = f"[{LAYER_LABELS.get(e.get('knowledge_layer', 'truth'), '')}]"
            ch_tag = ""
            cf, ct = e.get("chapter_from"), e.get("chapter_to")
            if cf or ct:
                ch_tag = f"[第{cf or '?'}-{ct or '今'}章]"
            lines.append(f"- {'，'.join(str(x) for x in parts)} {layer_tag}{ch_tag}")
        lines.append("")

    if kept_relations:
        lines.append("【关系网络】")
        for r in kept_relations:
            arrow = "↔" if r.get("direction") == "bidirectional" else "→"
            layer_tag = f"[{LAYER_LABELS.get(r.get('knowledge_layer', 'truth'), '')}]"
            lines.append(f"- {r.get('subject_name')} {arrow}{r['predicate']}{arrow} {r.get('object_name')} {layer_tag}")
        lines.append("")

    lines.append("如果后续创作与上述设定冲突，请优先遵守图谱设定；如确需变更，请明确提示作者。")
    lines.append("</knowledge_graph>")
    lines.append("")
    return "\n".join(lines)


async def export_graph(project_id: str, fmt: str = "json") -> str:
    graph = await get_graph(project_id)
    entities = graph["entities"]
    relations = graph["relations"]

    if fmt == "json":
        return json.dumps(graph, ensure_ascii=False, indent=2)

    if fmt == "markdown":
        lines = [f"# 知识图谱导出（{len(entities)} 实体 / {len(relations)} 关系）", ""]
        by_type: dict[str, list[dict]] = {}
        for e in entities:
            by_type.setdefault(e["entity_type"], []).append(e)
        for etype in ("character", "faction", "location", "item", "event"):
            items = by_type.get(etype, [])
            if not items:
                continue
            lines.append(f"## {ENTITY_TYPE_LABELS.get(etype, etype)}（{len(items)}）")
            for e in items:
                props = e.get("properties", {})
                prop_str = "，".join(f"{k}：{v}" for k, v in props.items() if v) if props else ""
                layer = LAYER_LABELS.get(e.get("knowledge_layer", "truth"), "")
                aliases = "、".join(e.get("aliases", [])) if e.get("aliases") else ""
                parts = [f"**{e['name']}**"]
                if aliases:
                    parts.append(f"（别名：{aliases}）")
                if prop_str:
                    parts.append(f" — {prop_str}")
                if e.get("summary"):
                    parts.append(f"\n  > {e['summary']}")
                parts.append(f" `[{layer}]`")
                lines.append("- " + " ".join(parts))
            lines.append("")
        if relations:
            lines.append(f"## 关系网络（{len(relations)}）")
            for r in relations:
                arrow = "↔" if r.get("direction") == "bidirectional" else "→"
                layer = LAYER_LABELS.get(r.get("knowledge_layer", "truth"), "")
                lines.append(f"- {r.get('subject_name')} {arrow} {r['predicate']} {arrow} {r.get('object_name')} `[{layer}]`")
            lines.append("")
        return "\n".join(lines)

    if fmt == "mermaid":
        lines = ["graph LR"]
        name_to_id: dict[str, str] = {}
        for e in entities:
            safe_id = e["id"].replace("-", "_")
            name_to_id[e["name"]] = safe_id
            label = e["name"].replace('"', "'")
            color = {"character": "#c55d3b", "location": "#0891b2", "faction": "#7c3aed", "item": "#d97706", "event": "#db2777"}.get(e["entity_type"], "#78716c")
            shape = "([" if e["entity_type"] == "event" else "("
            shape_close = "]])" if e["entity_type"] == "event" else ")"
            if e["entity_type"] == "location":
                shape, shape_close = "[", "]"
            elif e["entity_type"] == "item":
                shape, shape_close = "((", "))"
            lines.append(f'    {safe_id}{shape}"{label}"{shape_close}')
        lines.append("")
        for r in relations:
            s_id = name_to_id.get(r.get("subject_name", ""), r.get("subject_id", "unknown").replace("-", "_"))
            o_id = name_to_id.get(r.get("object_name", ""), r.get("object_id", "unknown").replace("-", "_"))
            arrow = "---" if r.get("direction") == "bidirectional" else "-->"
            pred = r["predicate"].replace("|", "/")
            lines.append(f"    {s_id} {arrow}|{pred}| {o_id}")
        return "\n".join(lines)

    return json.dumps(graph, ensure_ascii=False, indent=2)
