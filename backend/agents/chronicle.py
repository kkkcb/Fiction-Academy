import json

from backend.agents.base import chat_json

CHRONICLE_PROMPT = """你是一位编年史记录员。你的职责是根据新完成的小说章节，更新故事的编年记录。

编年记录包含以下部分：
1. timeline: 故事内的时间线推进（如"灵历1年春→灵历1年夏"）
2. characters: 每个角色在不同时期的状态变化，包括实力、性格、关系、能力等
3. key_events: 重要事件记录
4. unresolved_threads: 尚未解决的伏笔和悬念

请根据当前编年记录和新章节内容，输出更新后的完整编年记录。

输出JSON格式：
{
  "timeline": ["时间点1", "时间点2", ...],
  "characters": [
    {
      "name": "角色名",
      "periods": [
        {
          "time": "时期",
          "status": "当前状态描述",
          "abilities": "能力描述",
          "relations": "与其他角色关系",
          "personality": "性格特点"
        }
      ]
    }
  ],
  "key_events": ["事件1", "事件2", ...],
  "unresolved_threads": ["伏笔1", "伏笔2", ...]
}

注意：
- 保留之前的记录，只追加或更新变化的部分
- 角色的 periods 是追加式的，新的时期追加到数组末尾
- 如果某个角色的状态没有变化，保持不变
- 仔细捕捉所有伏笔和悬念"""

async def update_chronicle(
    current_chronicle: dict,
    chapter_title: str,
    chapter_content: str,
    world_setting: str,
) -> dict:
    current_text = json.dumps(current_chronicle, ensure_ascii=False, indent=2) if current_chronicle else "（空）"

    messages = [
        {"role": "user", "content": f"""## 世界观设定
{world_setting}

## 当前编年记录
{current_text}

## 新完成的章节：{chapter_title}
{chapter_content}

请输出更新后的完整编年记录（JSON格式）。"""}
    ]

    result = await chat_json(messages, system_prompt=CHRONICLE_PROMPT)
    return result
