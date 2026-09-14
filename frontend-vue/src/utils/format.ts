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
