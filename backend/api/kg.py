from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from backend.database import get_db, fetch_all, fetch_one
from backend.agents.base import chat_json, LLMError
from backend.services import kg as kg_service

router = APIRouter(prefix="/api", tags=["knowledge-graph"])


EXTRACT_SYSTEM_PROMPT = """你是一位小说知识图谱信息提取专家。你的任务是从小说创作的对话或文本中，精准提取实体、关系和事件，构建结构化知识图谱。

## 实体类型
- character（角色）：人物
- location（地点）：大陆/城市/山脉/秘境/宗门驻地等
- faction（势力）：门派/组织/国家/家族
- item（物品）：武器/丹药/法宝/功法/灵物
- event（事件）：战斗/交易/结盟/背叛/突破/死亡等关键事件

## 三层知识标记（核心，必须判断）
每个实体和关系都要标注 knowledge_layer：
- truth（既定事实）：作者明确设定、作为世界观基础的事实。如角色身份、背景、能力体系规则。
- revealed（已揭示）：已在正文中向读者展示、读者已知的信息。
- foreshadow（伏笔）：作者埋下的暗示、悬念、未揭露的秘密、未来才会揭示的设定。
  注意：伏笔类信息对作者规划剧情很重要，但写作正文时不能提前泄露给读者。

## 输出 JSON 格式
{
  "entities": [
    {
      "type": "character",
      "name": "实体名称",
      "aliases": ["别名1", "绰号"],
      "properties": {"性别": "男", "境界": "金丹期", "身份": "青云宗弟子"},
      "knowledge_layer": "truth",
      "summary": "一句话概括这个实体（可选，新实体才填）"
    }
  ],
  "relations": [
    {
      "subject": "主体名称",
      "subject_type": "character",
      "predicate": "关系谓词（如：师徒/敌对/所属/持有/位于/暗恋）",
      "object": "客体名称",
      "object_type": "character",
      "direction": "bidirectional 或 directed",
      "knowledge_layer": "truth"
    }
  ]
}

## 提取规则
1. 只提取明确出现的实体和关系，不要臆造。
2. 关系谓词用简洁中文（师徒/恋人/敌对/所属/持有/位于/附庸/同盟/包含/因果等）。
3. 双向关系（师徒/恋人/敌对/同盟）用 bidirectional，单向关系（所属/持有/位于）用 directed。
4. 事件类实体可在 properties 中记录 subject/object/location/result 等。
5. 如果信息不足以判断，默认 knowledge_layer 为 truth。
6. 没有实体时返回 {"entities": [], "relations": []}。

只返回 JSON，不要任何解释。"""


class EntityCreate(BaseModel):
    entity_type: str
    name: str
    aliases: list[str] = []
    properties: dict = {}
    knowledge_layer: str = "truth"
    chapter_from: int | None = None
    chapter_to: int | None = None
    summary: str = ""


class EntityUpdate(BaseModel):
    entity_type: str | None = None
    name: str | None = None
    aliases: list[str] | None = None
    properties: dict | None = None
    knowledge_layer: str | None = None
    chapter_from: int | None = None
    chapter_to: int | None = None
    summary: str | None = None


class RelationCreate(BaseModel):
    subject_id: str
    predicate: str
    object_id: str
    direction: str = "directed"
    properties: dict = {}
    knowledge_layer: str = "truth"
    chapter_from: int | None = None
    chapter_to: int | None = None


class ExtractRequest(BaseModel):
    text: str | None = None
    conversation_id: str | None = None
    message_limit: int = 20


@router.get("/projects/{project_id}/kg/graph")
async def get_graph(project_id: str, chapter: int | None = None, layers: str = ""):
    layer_list = [l.strip() for l in layers.split(",") if l.strip()] if layers else None
    return await kg_service.get_graph(project_id, chapter=chapter, layers=layer_list)


@router.get("/projects/{project_id}/kg/entities")
async def list_entities(project_id: str, type: str = "", layer: str = ""):
    return await kg_service.list_entities(project_id, entity_type=type, layer=layer)


@router.post("/projects/{project_id}/kg/entities")
async def create_entity(project_id: str, body: EntityCreate):
    return await kg_service.create_entity(project_id, body.model_dump())


@router.put("/kg/entities/{entity_id}")
async def update_entity(entity_id: str, body: EntityUpdate):
    data = body.model_dump(exclude_none=True)
    return await kg_service.update_entity(entity_id, data)


@router.delete("/kg/entities/{entity_id}")
async def delete_entity(entity_id: str):
    await kg_service.delete_entity(entity_id)
    return {"ok": True}


@router.post("/projects/{project_id}/kg/relations")
async def create_relation(project_id: str, body: RelationCreate):
    return await kg_service.create_relation(project_id, body.model_dump())


@router.delete("/kg/relations/{relation_id}")
async def delete_relation(relation_id: str):
    await kg_service.delete_relation(relation_id)
    return {"ok": True}


@router.post("/projects/{project_id}/kg/extract")
async def extract_from_text(project_id: str, body: ExtractRequest):
    db = await get_db()
    if body.conversation_id and not body.text:
        rows = await fetch_all(
            db,
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
            (body.conversation_id, body.message_limit),
        )
        rows = list(reversed(rows))
        text = "\n\n".join(f"{'作者' if r['role'] == 'user' else 'AI'}：{r['content']}" for r in rows)
    else:
        text = body.text or ""
    if not text.strip():
        raise HTTPException(status_code=400, detail="没有可提取的文本")

    existing = await kg_service.list_entities(project_id)
    existing_hint = ""
    if existing:
        names = [f"{e['name']}({e['entity_type']})" for e in existing[:30]]
        existing_hint = f"\n\n## 图谱中已存在的实体（提取时注意消歧，名称匹配则视为更新）\n{', '.join(names)}"

    try:
        result = await chat_json(
            messages=[{"role": "user", "content": text + existing_hint}],
            system_prompt=EXTRACT_SYSTEM_PROMPT,
            temperature=0.2,
        )
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"AI 提取失败，请重试（{str(e)[:100]}）")

    stats = await kg_service.merge_extraction(project_id, result, source="ai")
    return {"extraction": result, "stats": stats}


@router.post("/projects/{project_id}/kg/extract-item/{item_id}")
async def extract_from_item(project_id: str, item_id: str):
    db = await get_db()
    row = await fetch_one(
        db,
        "SELECT item_type, title, content FROM workspace_items WHERE id = ? AND project_id = ?",
        (item_id, project_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="工作台条目不存在")
    text = f"【{row['title'] or row['item_type']}】\n{row['content']}"
    try:
        result = await chat_json(
            messages=[{"role": "user", "content": text}],
            system_prompt=EXTRACT_SYSTEM_PROMPT,
            temperature=0.2,
        )
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"AI 提取失败，请重试（{str(e)[:100]}）")
    stats = await kg_service.merge_extraction(project_id, result, source="workspace")
    return {"extraction": result, "stats": stats}


@router.get("/projects/{project_id}/kg/export")
async def export_graph(project_id: str, format: str = "json"):
    if format not in ("json", "markdown", "mermaid"):
        raise HTTPException(status_code=400, detail="格式仅支持 json / markdown / mermaid")
    content = await kg_service.export_graph(project_id, format)
    ext = {"json": "json", "markdown": "md", "mermaid": "mmd"}.get(format, "txt")
    media_type = {"json": "application/json", "markdown": "text/markdown", "mermaid": "text/plain"}.get(format, "text/plain")
    headers = {"Content-Disposition": f'attachment; filename="knowledge_graph.{ext}"'}
    return PlainTextResponse(content=content, media_type=media_type, headers=headers)
