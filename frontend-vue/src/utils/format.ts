import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { ConsultRecord, PointKey } from '../types'

marked.setOptions({ breaks: false, gfm: true })

export interface PointNavEntry {
  key: PointKey
  label: string
  desc: string
}

export const POINT_NAV: PointNavEntry[] = [
  { key: 'story_core', label: '故事核', desc: '一句话核心 · 书名' },
  { key: 'world_setting', label: '世界观', desc: '力量体系 · 金手指' },
  { key: 'character_setting', label: '核心人物', desc: '动机 · 红线' },
  { key: 'outline_reverse', label: '倒推大纲', desc: '终局 · 因果链' },
  { key: 'outline', label: '正向大纲', desc: '三幕 · 结局' },
]

export const TYPE_LABELS: Record<string, string> = {
  story_core: '故事核', world_setting: '世界观', character_setting: '人物',
  outline_reverse: '倒推大纲', outline: '正向大纲', foreshadow: '伏笔',
  chapter_plan: '章纲', chapter: '章节', plot: '情节', theme: '主题',
  character: '角色', setting: '设定', summary: '摘要',
}

export const STATUS_LABELS: Record<string, string> = {
  draft: '草稿', pending: '待审', finalized: '已定', locked: '已锁',
}

export type IconName = 'target' | 'bolt' | 'globe' | 'user' | 'refresh' | 'clapper'

export interface SlashCommand {
  cmd: string
  icon: IconName
  title: string
  desc: string
  pointOnly: boolean
}

export const SLASH_COMMANDS: SlashCommand[] = [
  { cmd: '/distill', icon: 'bolt', title: '总结分拣', desc: '总结新对话，自动归类到对应设定点位（增量，只处理新内容）', pointOnly: false },
  { cmd: '/build', icon: 'bolt', title: '一键抽骨架', desc: '从整段对话一次性生成缺失的五个骨架点位', pointOnly: false },
  { cmd: '/consult', icon: 'target', title: '专家会诊', desc: '召集五位创作专家圆桌讨论，主线策划统率全局后给出裁决', pointOnly: true },
  { cmd: '/gen', icon: 'bolt', title: '快速生成', desc: '根据一句话想法，AI 直接生成完整的点位设定', pointOnly: true },
  { cmd: '/goal', icon: 'bolt', title: '目标模式', desc: '给出创作目标，AI 自主拆解任务、逐步执行、反向确认', pointOnly: false },
]

export const EXPERT_COLORS: Record<string, string> = {
  '主线策划': '#c55d3b', '世界观架构师': '#7c3aed', '人物塑造师': '#0891b2', '逆向架构师': '#059669', '节奏导演': '#db2777',
}

/** 点位主导角色名：该点位的 AI 以此身份对话（与后端 POINT_PERSONAS 对应） */
export const POINT_PERSONA_NAMES: Record<string, string> = {
  world_setting: '铸世者-炳',
}

/** 属性/字段键 → 中文释意（点位字段 + 知识图谱提取常见键），展示层一律只显示中文 */
export const PROPERTY_LABELS: Record<string, string> = {
  // 故事核
  genre: '题材类型', trope: '故事模板', one_liner: '一句话核心', book_name: '书名', pitch: '文案',
  // 世界观
  power_system: '力量体系', power_limit: '硬限制', geography: '地理板块', social_class: '社会阶层',
  factions: '多方势力', history: '历史背景', golden_finger: '金手指规则',
  // 核心人物
  name: '名称', role: '角色定位', core_desire: '核心欲望', inner_void: '内心黑洞',
  red_lines: '红线', anchor_events: '行为锚点', speech_style: '语言体系', mbti: 'MBTI',
  // 倒推大纲
  endpoint_state: '终点状态', key_turning_points: '关键转折', start_state: '起点状态',
  gap_analysis: '落差分析', foreshadows_needed: '预埋伏笔',
  // 正向大纲
  act1: '第一幕', act2_up: '第二幕上', act2_down: '第二幕下', act3: '第三幕',
  ending: '结局方向', volumes: '分卷规划',
  // 知识图谱/事件常用
  subject: '主体', object: '客体', location: '地点', result: '结果', time: '时间', cause: '起因',
  gender: '性别', age: '年龄', appearance: '外貌', personality: '性格', ability: '能力',
  realm: '境界', status: '状态', description: '描述', level: '等级', origin: '来历',
}

/** 字段键显示为中文释意；已是中文的键原样返回，未收录的下划线转空格 */
export function propertyLabel(key: string): string {
  return PROPERTY_LABELS[key] || (/[\u4e00-\u9fff]/.test(key) ? key : key.replace(/_/g, ' '))
}

export function pointPersonaName(point: string | null | undefined): string {
  return point ? POINT_PERSONA_NAMES[point] || '' : ''
}

export function expertColor(name: string): string {
  return EXPERT_COLORS[name] || '#78716c'
}

export function esc(s: unknown): string {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string))
}

export function formatContent(text: string | null | undefined): string {
  if (!text) return ''
  return esc(text).replace(/\n/g, '<br>')
}

export function formatTime(ts: string | null | undefined): string {
  if (!ts) return ''
  try {
    const d = new Date(normalizeTs(ts))
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return ts
  }
}

/** SQLite datetime('now') 产出 "YYYY-MM-DD HH:MM:SS"（UTC 无时区标记），补 Z 后再解析 */
function normalizeTs(ts: string): string {
  const s = ts.replace(' ', 'T')
  return /[Zz]|[+-]\d{2}:?\d{2}$/.test(s) ? s : s + 'Z'
}

export function relativeTime(ts: string | null | undefined): string {
  if (!ts) return ''
  const t = new Date(normalizeTs(ts)).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`
  return formatTime(ts).split(' ')[0]
}

/** 网文场景的字数格式：1234 → "1,234 字" */
export function charCount(text: string | null | undefined): string {
  const n = (text || '').length
  return n.toLocaleString('zh-CN') + ' 字'
}

export interface ParsedCommand {
  type: 'consult' | 'gen' | 'mission'
  icon: IconName
  label: string
  idea: string
}

export function parseCommand(content: unknown): ParsedCommand | null {
  if (typeof content !== 'string') return null
  const consult = content.match(/^\/consult\s+([\s\S]+)/i)
  if (consult) return { type: 'consult', icon: 'target', label: '专家会诊', idea: consult[1].trim() }
  const gen = content.match(/^\/gen\s+([\s\S]+)/i)
  if (gen) return { type: 'gen', icon: 'bolt', label: '快速生成', idea: gen[1].trim() }
  const mission = content.match(/^\/goal\s+([\s\S]+)/i)
  if (mission) return { type: 'mission', icon: 'bolt', label: '目标模式', idea: mission[1].trim() }
  return null
}

export function parseConsultRecord(content: unknown): ConsultRecord | null {
  if (typeof content !== 'string' || !content) return null
  const t = content.trim()
  if (t.charAt(0) !== '{') return null
  try {
    const obj = JSON.parse(t) as ConsultRecord
    if (obj && obj.kind === 'consult_record') return obj
  } catch {}
  return null
}

const _mdCache = new Map<string, string>()
const _MD_CACHE_MAX = 100

// CommonMark 对中文的边界判定坑：**粗体** 的收尾 ** 前面是标点（如 “”）后面紧跟汉字时
// 不算 right-flanking，marked 会漏出原始星号（例：**“古生物”+“生命的循环”**这…）。
// 修法（同 ICE 踩坑实录 fixInlineSyntax 思路）：这类 marked 必错/等价的场景手工转 <strong>。
// 先把行内/围栏代码换成私用区占位符（\uE000…\uE001），避免误伤代码示例里的 **。
const _CJK = '\\u4e00-\\u9fff\\u3400-\\u4dbf'
const _CODE_SPAN_RE = /(```[\s\S]*?```|`[^`\n]+`)/g
const _BOLD_BEFORE_CJK_RE = new RegExp(`\\*\\*([^*\\n]+?)\\*\\*(?=[${_CJK}])`, 'g')
const _BOLD_AFTER_CJK_RE = new RegExp(`(?<=[${_CJK}])\\*\\*([^*\\n]+?)\\*\\*`, 'g')

function _fixCjkBold(t: string): string {
  const kept: string[] = []
  const shielded = t.replace(_CODE_SPAN_RE, m => `\uE000${kept.push(m) - 1}\uE001`)
  const fixed = shielded
    .replace(_BOLD_BEFORE_CJK_RE, '<strong>$1</strong>')
    .replace(_BOLD_AFTER_CJK_RE, '<strong>$1</strong>')
  return fixed.replace(/\uE000(\d+)\uE001/g, (_, i) => kept[Number(i)])
}

function _normalizeMd(text: string): string {
  let t = text.replace(/\r\n/g, '\n')
  t = t.replace(/\n{3,}/g, '\n\n')
  return _fixCjkBold(t)
}

// ---- 系统回执（分拣/抽骨架/大纲生成）的显示归一化 ----
// 历史上这些回执用「段内单换行」拼接（前端 breaks:false 全折叠成一行），
// ①②③ 编号和 ✅ 标签也挤在一起。新模板已是列表；这里把旧格式的存量消息
// 在渲染时重排成同样的列表，避免再写一轮数据迁移。只对回执开头的消息生效。
const _RECEIPT_PREFIX_RE = /^(已把本轮讨论分拣进设定|骨架生成完成|大纲草稿已生成)/
const _NUM_MARK_RE = /(?<!\n- )([\u2460-\u2473])/g // ①-⑳

function _normalizeReceipt(t: string): string {
  let s = t
  // 旧式「- ✅【点位】」或「✅【点位】」→ 粗体点位行
  s = s.replace(/(?:^|\n)(?:- )?✅【([^】]+)】/g, (_m, label) => `\n- **${label}** ·`)
  // 旧式「✅ 点位（n字）」行（build/大纲回执）→ 列表
  s = s.replace(/(?:^|\n)✅\s*([^\n（]{1,12})（(\d+)字）/g, (_m, label, n) => `\n- **${label}** · ${n} 字`)
  // ①②③ 各自成行成列表项
  s = s.replace(_NUM_MARK_RE, '\n- $1')
  // 「另：」起的新段落单独成段
  s = s.replace(/(?<!\n)(另：)/g, '\n\n$1')
  return s.replace(/\n{3,}/g, '\n\n').trim()
}

export function formatReceiptMd(text: string | null | undefined): string {
  if (!text) return ''
  const t = text.trim()
  if (!_RECEIPT_PREFIX_RE.test(t)) return formatMd(text)
  return formatMd(_normalizeReceipt(t))
}

// ---- 可点击选项（Trae 式选择交互）----
// AI 消息末尾出现「选项列表 + 提问」时，解析成可点选项，点击即作为用户消息发送。
// 识别的列表形态：A. / ① / 1. 各自成行（2-6 条，每条不太长），列表后（或列表前一句）
// 有提问特征（？/吗/选/挑/倾向/哪个）。宁可漏判不可误判——普通设定列举不带提问就不出选项。
export interface ChoiceOption {
  label: string
  value: string
}

const _OPT_MARKERS: RegExp[] = [
  /^([A-H])[.、:：)）]\s*(\S.*)$/,        // A. 方向一
  /^([\u2460-\u2467])[.、:：)）]?\s*(\S.*)$/, // ① 方向一
  /^(\d)[.、:：)）]\s*(\S.*)$/,            // 1. 方向一
]

const _QUESTION_CUE_RE = /[？?]|选哪|挑哪|哪个|哪条|倾向|你选|来选|定哪个/

export function parseChoiceOptions(text: string | null | undefined): ChoiceOption[] {
  const first = splitMessageWithChoices(text).find(s => s.choices)
  return first ? first.choices! : []
}

// ---- 按问题分组的选项（每个有选项的段落一组，Trae 式点选+确认）----
export interface MessageSegment {
  md: string
  choices: ChoiceOption[] | null
  open: boolean // 无枚举选项的开放问题：给行内输入框直接作答
  qno: number // 可作答的段落依次编号（1、2…），发送时作为问题号
}

export function splitMessageWithChoices(text: string | null | undefined): MessageSegment[] {
  if (!text) return []
  // 按行切块：LLM 的连续问题常只用单个换行分隔（渲染层 breaks:false 会糊成一段）。
  // 代码围栏内部保持合并；缩进行（嵌套列表/续行）并入上一块，避免拆散结构。
  const lines = text.trim().split('\n')
  const blocks: string[] = []
  let inFence = false
  for (const line of lines) {
    const fence = /^\s*(```|~~~)/.test(line)
    if (!inFence && line.trim() && !/^\s/.test(line)) {
      blocks.push(line)
    } else if (blocks.length) {
      blocks[blocks.length - 1] += '\n' + line
    } else if (line.trim()) {
      blocks.push(line)
    }
    if (fence) inFence = !inFence
  }
  const segs: MessageSegment[] = []
  let qno = 0
  for (const b of blocks) {
    if (!b.trim()) continue
    const { choices, open } = _optionsForBlock(b)
    if (choices || open) qno++
    segs.push({ md: b, choices: choices || null, open, qno: choices || open ? qno : 0 })
  }
  return segs
}

// 是否/要不要类问句 → 「要 / 不要」快捷项
const _YESNO_RE = /要不要|是否|能不能|可不可以|行不行/

function _optionsForBlock(block: string): { choices: ChoiceOption[] | null; open: boolean } {
  if (!_QUESTION_CUE_RE.test(block)) return { choices: null, open: false }
  // 1) 每行一个选项（A./①/1.）
  const lineOpts = _parseLineOptions(block.split('\n'), block.split('\n').length - 1)
  if (lineOpts.length) return { choices: lineOpts, open: false }
  // 2) 行内挤在一起的编号选项
  const inlineOpts = _parseInlineOptions(block)
  if (inlineOpts.length) return { choices: inlineOpts, open: false }
  // 3) 「是X，还是Y？」式二选一
  const binary = _parseBinaryChoice(block)
  if (binary.length) return { choices: binary, open: false }
  // 4) 要不要/是否类问句 → 「要/不要」快捷项 + 输入框（可点快答，也可打字补充）
  if (_YESNO_RE.test(block)) {
    return { choices: [{ label: '要', value: '要' }, { label: '不要', value: '不要' }], open: true }
  }
  // 5) 其余含问句的段落 → 开放问题，给行内输入框
  if (/？/.test(block)) return { choices: null, open: true }
  return { choices: null, open: false }
}

// 「…是X，还是Y？」→ 两个可点选项。逐句扫描（一个块里可能有多个问句，
// 如"…知道吗？…是X还是Y？"），句内恰好一个「还是」才判，防误伤。
function _parseBinaryChoice(block: string): ChoiceOption[] {
  const sentences = block.split(/(?<=[。！？；\n])/)
  for (const s of sentences) {
    const qIdx = s.indexOf('？')
    if (qIdx < 0) continue
    const q = s.slice(0, qIdx)
    if ((q.match(/还是/g) || []).length !== 1) continue
    const hIdx = q.indexOf('还是')
    const isIdx = q.lastIndexOf('是', hIdx)
    if (isIdx < 0 || q.slice(isIdx, isIdx + 2) === '还是') continue
    // 尾部只去引号/逗号，不去括号——选项常以完整的（）结尾，去掉会不成对
    const strip = (x: string) => x.replace(/^[，,、「'"“（(]+/, '').replace(/[，,、」'""]+$/, '').trim()
    const a1 = strip(q.slice(isIdx + 1, hIdx))
    const a2 = strip(q.slice(hIdx + 2))
    if (a1.length < 2 || a2.length < 2 || a1.length > 60 || a2.length > 60) continue
    return [
      { label: _clip(a1, 16), value: a1 },
      { label: _clip(a2, 16), value: a2 },
    ]
  }
  return []
}

function _parseLineOptions(lines: string[], lastIdx: number): ChoiceOption[] {
  for (const re of _OPT_MARKERS) {
    // 从末尾往回收集同形态的选项行
    let items: ChoiceOption[] = []
    const tailIsOption = re.test(lines[lastIdx].trim())
    let listEnd = tailIsOption ? lastIdx : lastIdx - 1
    while (listEnd >= 0 && !lines[listEnd].trim()) listEnd--
    let j = listEnd
    while (j >= 0) {
      const line = lines[j].trim()
      if (!line) { j--; continue }
      const m = line.match(re)
      if (!m) break
      const content = m[2].trim()
      if (content.length > 60 || content.length === 0) break
      items.unshift({ label: _clip(content, 18), value: line.replace(/^[*>\s]+/, '').trim() })
      j--
    }
    if (items.length >= 2 && items.length <= 6) {
      // 提问判定：列表后的剩余文本（提问行），或列表前一行
      const after = lines.slice(listEnd + 1).join(' ')
      const before = j >= 0 ? lines[j].trim() : ''
      if (_QUESTION_CUE_RE.test(after) || _QUESTION_CUE_RE.test(before)) {
        return items
      }
    }
  }
  return []
}

// 行内选项：在同一段文字里找 A. … B. … C. …（或 ①…②…）的连续序列。
// 要求字母序连续（A→B→C）、每项非空且 ≤100 字、整段有提问特征——防误伤普通行文。
function _parseInlineOptions(text: string): ChoiceOption[] {
  if (!_QUESTION_CUE_RE.test(text)) return []
  const chunk = text.slice(-1600)
  for (const markerRe of [_INLINE_LETTER_RE, _INLINE_CIRCLE_RE, _INLINE_DIGIT_RE]) {
    // 三个正则都是「边界组 + 标记组」结构：内容从标记字母/数字起切
    const marks: { idx: number; end: number; mark: string }[] = []
    for (const m of chunk.matchAll(markerRe)) {
      marks.push({ idx: m.index + m[1].length, end: m.index + m[0].length, mark: m[2] })
    }
    // 找最长的一段「编号递增」的连续 run（A→B→C…、①→②…、1→2…）
    let best: { idx: number; end: number; mark: string }[] = []
    let run: { idx: number; end: number; mark: string }[] = []
    const order = (mk: string): number => {
      const c = mk.charCodeAt(0)
      if (c >= 0x2460 && c <= 0x2473) return c - 0x2460 + 1 // ①-⑳
      return parseInt(mk, 10) || c - 64 // A=1..H=8；数字直接取值
    }
    for (let i = 0; i < marks.length; i++) {
      if (run.length && order(marks[i].mark) === order(run[run.length - 1].mark) + 1) {
        run.push(marks[i])
      } else {
        run = [marks[i]]
      }
      if (run.length > best.length) best = [...run]
    }
    if (best.length < 2 || best.length > 6) continue
    const items: ChoiceOption[] = []
    for (let i = 0; i < best.length; i++) {
      const start = best[i].idx
      let end: number
      if (i + 1 < best.length) {
        end = best[i + 1].idx
      } else {
        // 末选项：截到本段结束（后面可能还有别的问题段落，不是选项内容）
        const nl = chunk.indexOf('\n', start)
        end = nl >= 0 ? nl : chunk.length
      }
      const content = chunk.slice(start, end).trim().replace(/[。；;\s]+$/, '')
      if (content.length > 100 || content.length <= 2) { items.length = 0; break }
      // label 去掉 A./①/1. 序号前缀——问题号徽标已在，叠着显示难看；value 保留供 AI 对位
      const bare = content.replace(/^[A-H][.、]\s*|^[\u2460-\u2467][.、]?\s*|^\d[.、]\s*/, '')
      items.push({ label: _clip(bare, 18), value: content })
    }
    if (items.length >= 2) return items
  }
  return []
}

// 边界集：选项标记前的字符。注意 ？——「…是谁？A. …」是 LLM 最常见的行内接法
const _INLINE_LETTER_RE = /(^|[\s？?：:；;，,（(“"])([A-H])[.、]\s*/g
const _INLINE_CIRCLE_RE = /(^|[\s？?：:；;，,（(])([\u2460-\u2473])/g
const _INLINE_DIGIT_RE = /(^|[\s？?：:；;，,（(])(\d)[.、]\s+/g

function _clip(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '…' : s
}

function _fallbackMd(text: string): string {
  let h = esc(text)
  h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  h = h.replace(/^# (.+)$/gm, '<h2>$1</h2>')
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  h = h.replace(/\*(.+?)\*/g, '<em>$1</em>')
  h = h.replace(/`(.+?)`/g, '<code>$1</code>')
  h = h.replace(/^[-*] (.+)$/gm, '<li>$1</li>')
  h = h.replace(/\n\n/g, '<br><br>')
  h = h.replace(/\n/g, '<br>')
  return h
}

export function formatMd(text: string | null | undefined, opts: { cache?: boolean } = {}): string {
  if (!text) return ''
  const useCache = opts.cache !== false
  if (useCache && _mdCache.has(text)) return _mdCache.get(text) as string
  const normalized = _normalizeMd(text)
  let h: string
  try { h = marked.parse(normalized) as string } catch { h = _fallbackMd(text) }
  // AI 输出与用户输入都不可信，渲染前统一消毒（防存储型 XSS）
  h = DOMPurify.sanitize(h, { USE_PROFILES: { html: true } })
  if (useCache && text.length < 8000) {
    if (_mdCache.size >= _MD_CACHE_MAX) {
      const firstKey = _mdCache.keys().next().value as string
      _mdCache.delete(firstKey)
    }
    _mdCache.set(text, h)
  }
  return h
}
