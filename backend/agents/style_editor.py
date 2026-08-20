"""AI味审查 Agent —— 每章写完后针对性优化 AI 痕迹。

独立于写作者（"修复者不能给自己打分"），专门识别并改写 AI 统计特征：
- 高频套话词（仿佛/宛如/似乎/不禁/一丝/渐渐/淡淡...）
- 句长均匀、三连排比、"不是...而是..."句式
- 空洞的环境/心理描写（无信息量的氛围渲染）
- 情绪直给（"愤怒""悲伤"而非动作呈现）
- 对话无毛边、人人腔调相同

输出：优化后的完整正文 + 修改点清单。
"""
import logging
import re
import statistics

from backend.agents.base import chat_json

logger = logging.getLogger(__name__)

# 统计层黑名单（与执笔铁律一致）
AI_WORDS = [
    "仿佛", "宛如", "似乎", "不禁", "一丝", "格外", "渐渐", "淡淡",
    "静静", "悄然", "瞬间", "微微", "轻轻", "缓缓", "弥漫", "嘴角",
    "眼神", "忽然", "空气", "某种", "莫名",
]

STYLE_AUDIT_PROMPT = """你是一位从起点连载时代走过来的老编辑。你面前是一章刚写好的修仙小说，你的任务是：**把所有不像人写的段落，改成像人写的**。

你的标杆是《凡人修仙传》——忘语的文笔被吐槽"平实"甚至"流水账"，但这恰恰是它200万字不崩的秘密：**白描、务实、心理写实、不炫技**。你要的不是"换个说法"，是把AI的"表演感"去掉。

## 核心诊断标准（最重要）

AI写的段落有一种"表演感"——它在向读者表演"我会写小说"，而不是在讲一个故事。具体症状：

### 症状一：意象堆砌
AI原文："竹杖点地的声音一下一下，混着怀里那捆蓝布的死寂。布底下，剑僵着，半点颤都没有，像一口屏了半天的气，还没敢吐。"
问题：一个简单动作（拄拐走近）用了三个意象（声音混死寂→剑屏气→不敢吐气），读者被淹死了。
凡人写法："宋迟拄着竹杖，一步一步挪到院门口。怀里的剑裹在蓝布里，一路上没动过。"
——凡人不搞意象叠加，一句话说完就完。读者自己会紧张，不需要你演。

### 症状二：对仗工整
AI原文："比街面上的沉，也比街面上的暖。"
问题：工整的对称句是AI的标志。人在写小说时不会刻意造对仗。
凡人写法："茶香比外头浓。"
——不对称、不呼应、说到哪算哪。

### 症状三：节奏均匀
AI原文：段落长短一致，每段都在80-120字，像流水线产品。
凡人写法：一段可能200字（打斗/对话密集），下一段可能就一句话（"韩立没说话。"）。**长短差就是人味。**

### 症状四：感官轰炸
AI原文："空气里弥漫着一股说不清的味道，像是铁锈，又像是某种更古老的东西。"
凡人写法："有股铁锈味。"
——不堆叠感官，点到为止。

### 症状五：心理描写用意象代替内容
AI原文："他心中一动，仿佛有什么东西从记忆深处浮现。"
凡人写法："韩立心里咯噔一下——这瓶子他见过。"
——心理活动写**具体想法**，不写"仿佛""似乎"的氛围。

## 改写方法（逐段操作）

1. 诊断：这段有没有上述5个症状？没有→跳过不改
2. 有→用白描重写：删掉意象层，只留"谁做了什么"
3. 心理活动改为具体想法（韩立式腹黑独白）
4. 对话加生活毛边：废话、打断、跑偏
5. 段落节奏打散：长的砍短、短的偶尔加长
6. **改完后整体读一遍**：如果像在看表演，继续改；如果在看故事，完成

## 铁律
- 情节、人物、对话核心内容、伏笔、数字、专有名词**完全不变**
- 不是删字数，是改写法——总字数变化不超过±15%
- 改完的正文的段落长度应该参差不齐
- 允许有些段落"难看"——粗糙比精致更人

输出 JSON：
{
  "revised_text": "优化后的完整章节正文（纯文本）",
  "changes": [
    {"type": "意象堆砌|对仗工整|节奏均匀|感官轰炸|心理空泛|对话无毛边",
     "original": "原文片段", "revised": "改后片段", "reason": "一句说明"}
  ],
  "ai_score_before": "原稿AI概率(0-100)",
  "ai_score_after": "改后AI概率(0-100)"
}"""


def stat_ai_flags(text: str) -> list[str]:
    """统计层体检（同执笔后置检查的维度）。"""
    flags = []
    for w in AI_WORDS:
        n = text.count(w)
        if n > 2:
            flags.append(f"“{w}”x{n}")
    sents = [x.strip() for x in re.split(r"[。！？]", text) if x.strip()]
    lens = [len(x) for x in sents]
    if len(lens) > 5 and statistics.mean(lens) > 0:
        cv = statistics.stdev(lens) / statistics.mean(lens)
        if cv < 0.50:
            flags.append(f"句长CV={cv:.2f}")
    tri = len(re.findall(r"[\u4e00-\u9fff]{1,3}，[\u4e00-\u9fff]{1,3}，[\u4e00-\u9fff]{1,3}[，。]", text))
    if tri > 4:
        flags.append(f"三连排比x{tri}")
    if text.count("不是") + text.count("而是") > 4:
        flags.append("不是/而是句式多")
    return flags


async def audit_and_rewrite(chapter_content: str) -> dict:
    """审查并改写一章的 AI 痕迹。

    返回 {revised_text, changes, ai_score_before, ai_score_after, stat_flags}。
    失败时 revised_text 为空，调用方保留原稿。
    """
    stat_flags = stat_ai_flags(chapter_content)

    prompt = (
        f"（统计层体检提示，供参考：{'; '.join(stat_flags) or '统计层未超标，但仍需逐段排查内容层AI味'}）\n\n"
        f"章节正文：\n{chapter_content[:12000]}"
    )

    try:
        result = await chat_json(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=STYLE_AUDIT_PROMPT,
            temperature=0.4,
        )
    except Exception as e:
        logger.warning("[style-editor] audit failed: %s", e)
        return {"revised_text": "", "changes": [], "stat_flags": stat_flags,
                "ai_score_before": None, "ai_score_after": None, "error": str(e)[:100]}

    revised = (result.get("revised_text") or "").strip()
    # 合理性检查：改写后不能太短（丢内容）或完全一样
    if revised and len(revised) > len(chapter_content) * 0.6 and revised[:50] != chapter_content[:50]:
        return {
            "revised_text": revised,
            "changes": result.get("changes") or [],
            "stat_flags": stat_flags,
            "ai_score_before": result.get("ai_score_before"),
            "ai_score_after": result.get("ai_score_after"),
        }
    return {"revised_text": "", "changes": result.get("changes") or [], "stat_flags": stat_flags,
            "ai_score_before": result.get("ai_score_before"), "ai_score_after": None}
