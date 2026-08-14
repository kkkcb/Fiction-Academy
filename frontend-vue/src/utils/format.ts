import { marked } from 'marked'
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
  { cmd: '/consult', icon: 'target', title: '专家会诊', desc: '召集五位创作专家圆桌讨论，主线策划统率全局后给出裁决', pointOnly: true },
  { cmd: '/gen', icon: 'bolt', title: '快速生成', desc: '根据一句话想法，AI 直接生成完整的点位设定', pointOnly: true },
  { cmd: '/goal', icon: 'bolt', title: '目标模式', desc: '给出创作目标，AI 自主拆解任务、逐步执行、反向确认', pointOnly: false },
]

export const EXPERT_COLORS: Record<string, string> = {
  '主线策划': '#c55d3b', '世界观架构师': '#7c3aed', '人物塑造师': '#0891b2', '逆向架构师': '#059669', '节奏导演': '#db2777',
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
    const d = new Date(ts)
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return ts
  }
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

function _normalizeMd(text: string): string {
  let t = text.replace(/\r\n/g, '\n')
  t = t.replace(/\n{3,}/g, '\n\n')
  return t
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

export function formatMd(text: string | null | undefined): string {
  if (!text) return ''
  if (_mdCache.has(text)) return _mdCache.get(text) as string
  const normalized = _normalizeMd(text)
  let h: string
  try { h = marked.parse(normalized) as string } catch { h = _fallbackMd(text) }
  if (text.length < 8000) {
    if (_mdCache.size >= _MD_CACHE_MAX) {
      const firstKey = _mdCache.keys().next().value as string
      _mdCache.delete(firstKey)
    }
    _mdCache.set(text, h)
  }
  return h
}
