from typing import TypedDict, Optional

class ChapterState(TypedDict, total=False):
    project_id: str
    chapter_number: int
    chapter_outline: str
    world_setting: str
    character_setting: str
    prev_summaries: str
    writer_char: dict
    peer_char: dict
    operator_char: dict
    content_reviewer_char: dict
    compliance_reviewer_char: dict
    reader_char: dict
    chapter_content: str
    peer_feedback: dict
    operator_feedback: dict
    content_result: dict
    compliance_result: dict
    reader_result: dict
    decision: str
    revision_notes: str
    revision_count: int
    max_revisions: int
    final_content: str
    events: list
