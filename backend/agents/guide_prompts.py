"""骨架点位的引导 prompt。

每个点位的 prompt 包含三部分：
1. POINT_INTRO - 点位开场（解释作用 + 第一个问题）
2. FIELDS - 该点位需要确定的结构化字段
3. COMPLETE_CRITERIA - 完成判定标准
"""

# ============================================================
# ① 故事核 story_core
# ============================================================
STORY_CORE_INTRO = """【故事核】是一切的起点。它不是题材，不是类型，而是那个让读者一听就想看、
让你写几十万字不跑偏的锚点。

猫腻写《将夜》的故事核是"天不生夫子，万古长如夜"——一句话撑起了整本书。
乌贼写《诡秘之主》的故事核是维多利亚 + 克苏鲁 + 22 条序列体系。

现在，请用一句话告诉我：你想写一个什么样的故事？
不用追求完美，先说出你脑海里最强烈的那个画面或冲突。"""

STORY_CORE_FIELDS = {
    "genre": "题材类型（玄幻/都市/末世/修仙/科幻/言情等）",
    "trope": "故事模板（夺宝翻盘/天才变废物/寻人解难/复仇重生等）",
    "one_liner": "一句话核心（25字以内，包含主角+核心冲突+爽点预期）",
    "book_name": "书名（15字以内，要有反差/悬念/强结果）",
    "pitch": "文案（直接写主线冲突和爽点，不要写世界观介绍）",
}
STORY_CORE_COMPLETE = ["one_liner", "book_name"]


# ============================================================
# ② 世界观 world_setting
# ============================================================
WORLD_SETTING_INTRO = """【世界观】不是设定的堆砌，而是一个世界自然生长出来的样子。

我不急着动笔，先听你说。像考古学家一样，我会从你给出的零散线索里，还原出一个地理、历史、文化相互咬合的自洽世界——先立核心法则，再让一切从中生长。我构建它的全部，但只在该出现的时候，向你展示它的一角。

那么，先从力量的根开始：这个世界里，一个普通人想变得更强，靠什么？
（修仙/异能/科技/血脉/系统/魔法？选一条主线，或者说你自己的答案）"""

WORLD_SETTING_FIELDS = {
    "power_system": "力量体系（核心修炼/成长方式）",
    "power_limit": "硬限制（没有限制的金手指会让读者觉得假。常见的：消耗资源/反噬/条件触发/冷却）",
    "geography": "地理板块（核心主城、特殊秘境、区域规则）",
    "social_class": "社会阶层（等级划分、上升通道、阶层矛盾）",
    "factions": "多方势力（至少三大派系，目标 + 合作/敌对关系）",
    "history": "历史背景（两件改变当下主线的关键过往事件）",
    "golden_finger": "金手指规则（主角的特殊优势 + 运行逻辑 + 隐藏禁忌）",
}
WORLD_SETTING_COMPLETE = ["power_system", "power_limit", "golden_finger"]


# ============================================================
# ③ 核心人物 character_setting
# ============================================================
CHARACTER_SETTING_INTRO = """【核心人物】决定读者会不会追读。人设崩坏（OOC）是长篇连载的头号杀手，
根治方法是两个机制：

1. 行为锚点：用具体事件而非形容词定义性格。
   ❌ "他温和" → ✅ "他在师门屠戮时放走了最后一个孩子，自此被逐出山门"
2. 红线：每个角色明确"绝对不能做的 3 件事"。

先定主角。第一个问题：主角最大的【核心欲望】是什么？
（这辈子最想得到什么？这个欲望会驱动整本书的所有行动）"""

CHARACTER_SETTING_FIELDS = {
    "name": "姓名",
    "role": "角色定位（主角/反派/女主/男二/导师）",
    "core_desire": "核心欲望（最想得到什么）",
    "inner_void": "内心黑洞（最害怕失去什么，与核心欲望形成反差）",
    "red_lines": "红线（绝对不会做的 3 件事）",
    "anchor_events": "行为锚点（3 个不同人生阶段的事件）",
    "speech_style": "语言体系（口头禅/怪癖/语速）",
    "mbti": "MBTI（可选）",
}
CHARACTER_SETTING_COMPLETE = ["name", "core_desire", "red_lines"]


# ============================================================
# ④ 倒推大纲 outline_reverse（B 方案核心）
# ============================================================
OUTLINE_REVERSE_INTRO = """【倒推大纲】是你独特的因果链设计方法。

传统写法从起点往前走，每一步都是即兴选择，走着走着就飘了。
倒推法反过来：先锚定终局状态，再问"达成它需要什么前置条件"，层层倒推回起点。
这样每一段情节都有"为什么"——都是为了支撑结局。

推理小说先定凶手再埋线索，就是这个逻辑。
乌贼的诡秘之主 22 序列体系，明显是先有神话终局再倒推出每层序列。

第一个问题：你希望这本书的【终点状态】是什么？
（主角最终站在哪里？反派什么下场？最大的真相是什么？先大胆说出结局）"""

OUTLINE_REVERSE_FIELDS = {
    "endpoint_state": "终点状态（主角最终达成什么/反派如何覆灭/真相如何揭示）",
    "key_turning_points": "关键转折（达成终点必须经过的不可省略节点）",
    "start_state": "起点状态（故事开篇时主角处于什么处境）",
    "gap_analysis": "落差分析（从起点到终点，主角需要补齐什么）",
    "foreshadows_needed": "必须预埋的伏笔（倒推链条上每个前置条件 = 一个伏笔）",
}
OUTLINE_REVERSE_COMPLETE = ["endpoint_state", "key_turning_points"]


# ============================================================
# ⑤ 正向大纲 outline
# ============================================================
OUTLINE_INTRO = """【正向大纲】把倒推的因果链，和正向的世界规则合成最终主线。

到这里，你已经有了：
- 倒推链：从终点倒推出的必经节点
- 世界观：允许发生什么
- 人物：谁在演

现在把它们合成三幕主线：第一幕（觉醒/起步）→ 第二幕（成长+挫折）→ 第三幕（决战/收尾）。

第一个问题：基于你的倒推链，第一幕的核心冲突是什么？
（主角从起点状态出发，遇到的第一个大挑战是什么？）"""

OUTLINE_FIELDS = {
    "act1": "第一幕（1-40章）：主角觉醒金手指，解决第一个危机",
    "act2_up": "第二幕上（41-80章）：进入新地图，结识伙伴，与反派第一次交锋",
    "act2_down": "第二幕下（81-120章）：遭遇重大挫折，跌入谷底",
    "act3": "第三幕（121-160章）：涅槃重生，与反派最终决战",
    "ending": "结局方向（悲剧/大团圆/开放式）",
    "volumes": "分卷规划（每卷核心冲突 + 3-5 节点 + 爽点分布）",
}
OUTLINE_COMPLETE = ["act1", "act3", "ending"]


# ============================================================
# 点位配置注册表
# ============================================================
POINT_CONFIGS = {
    "story_core": {
        "intro": STORY_CORE_INTRO,
        "fields": STORY_CORE_FIELDS,
        "complete_fields": STORY_CORE_COMPLETE,
    },
    "world_setting": {
        "intro": WORLD_SETTING_INTRO,
        "fields": WORLD_SETTING_FIELDS,
        "complete_fields": WORLD_SETTING_COMPLETE,
    },
    "character_setting": {
        "intro": CHARACTER_SETTING_INTRO,
        "fields": CHARACTER_SETTING_FIELDS,
        "complete_fields": CHARACTER_SETTING_COMPLETE,
    },
    "outline_reverse": {
        "intro": OUTLINE_REVERSE_INTRO,
        "fields": OUTLINE_REVERSE_FIELDS,
        "complete_fields": OUTLINE_REVERSE_COMPLETE,
    },
    "outline": {
        "intro": OUTLINE_INTRO,
        "fields": OUTLINE_FIELDS,
        "complete_fields": OUTLINE_COMPLETE,
    },
}


def _short_labels(fields: dict) -> dict:
    """取字段说明中括号前的主干作为简短中文标签。"""
    return {k: v.split("（")[0].strip() for k, v in fields.items()}


# 字段键 → 简短中文标签（点位字段 + 知识图谱/事件常用键），供消息渲染使用
FIELD_LABELS: dict[str, str] = {
    **_short_labels(STORY_CORE_FIELDS),
    **_short_labels(WORLD_SETTING_FIELDS),
    **_short_labels(CHARACTER_SETTING_FIELDS),
    **_short_labels(OUTLINE_REVERSE_FIELDS),
    **_short_labels(OUTLINE_FIELDS),
    "subject": "主体",
    "object": "客体",
    "location": "地点",
    "result": "结果",
    "time": "时间",
    "cause": "起因",
}
