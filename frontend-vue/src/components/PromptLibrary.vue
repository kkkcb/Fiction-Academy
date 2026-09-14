<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import * as api from '../api'
import type { PromptEntry } from '../types'
import { formatMd } from '../utils/format'
import { Search, Copy, Check, FileCode2, Pencil, RotateCcw, X, ArrowLeft, ChevronsDownUp, ChevronsUpDown } from 'lucide-vue-next'

const loading = ref(true)
const loadError = ref('')
const overriddenTotal = ref(0)
const items = ref<PromptEntry[]>([])

const keyword = ref('')
const selectedKey = ref('')

const selected = computed(() => items.value.find(e => e.key === selectedKey.value) ?? null)

const groupedFiltered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  const matched = items.value.filter(e =>
    !k ||
    e.name.toLowerCase().includes(k) ||
    e.node.toLowerCase().includes(k) ||
    e.group.toLowerCase().includes(k) ||
    e.text.toLowerCase().includes(k),
  )
  const out: { group: string; entries: PromptEntry[] }[] = []
  for (const e of matched) {
    if (!out.length || out[out.length - 1].group !== e.group) out.push({ group: e.group, entries: [] })
    out[out.length - 1].entries.push(e)
  }
  return out
})

// ---- 详情区状态 ----
const viewMode = ref<'render' | 'raw'>('render')
const editing = ref(false)
const editText = ref('')
const saving = ref(false)
const copied = ref(false)

const renderedHtml = computed(() => (selected.value ? formatMd(selected.value.text) : ''))

// ---- 渐进式披露：按 ## 小节切分，标题常驻、正文按需展开 ----
interface PromptSection {
  title: string
  html: string
  preview: string
  hasTitle: boolean
}

function stripTags(h: string): string {
  const d = document.createElement('div')
  d.innerHTML = h
  return d.textContent || ''
}

const sections = computed<PromptSection[]>(() => {
  const html = renderedHtml.value
  if (!html) return []
  const re = /<h2[^>]*>([\s\S]*?)<\/h2>/g
  const matches = [...html.matchAll(re)]
  if (!matches.length) return [{ title: '', html, preview: '', hasTitle: false }]
  const secs: PromptSection[] = []
  const pre = html.slice(0, matches[0].index!)
  if (pre.trim()) secs.push({ title: '', html: pre, preview: '', hasTitle: false })
  matches.forEach((m, i) => {
    const end = m.index! + m[0].length
    const nextStart = i + 1 < matches.length ? matches[i + 1].index! : html.length
    const body = html.slice(end, nextStart)
    secs.push({
      title: stripTags(m[1]).trim(),
      html: body,
      preview: stripTags(body).trim().replace(/\s+/g, ' ').slice(0, 64),
      hasTitle: true,
    })
  })
  return secs
})

// 展开状态：默认只展开第一个带标题小节（渐进式披露），其余看标题+预览按需点开
const expandedSecs = ref<Set<number>>(new Set())

function firstTitledIdx(): number {
  return sections.value.findIndex(s => s.hasTitle)
}

function toggleSec(i: number) {
  const s = new Set(expandedSecs.value)
  s.has(i) ? s.delete(i) : s.add(i)
  expandedSecs.value = s
}

function expandAll() {
  expandedSecs.value = new Set(sections.value.map((_, i) => i).filter(i => sections.value[i].hasTitle))
}

function collapseAll() {
  expandedSecs.value = new Set()
}

function select(e: PromptEntry) {
  selectedKey.value = e.key
  viewMode.value = 'render'
  editing.value = false
  const first = e.text.trim() && sections.value.length ? firstTitledIdx() : -1
  expandedSecs.value = first >= 0 ? new Set([first]) : new Set()
}

function startEdit() {
  if (!selected.value?.editable) return
  editText.value = selected.value.text
  editing.value = true
}

async function saveEdit() {
  if (!selected.value || saving.value) return
  const text = editText.value.trim()
  if (!text) return
  saving.value = true
  try {
    await api.savePromptOverride(selected.value.key, text)
    const d = await api.getPrompts()
    items.value = d.items
    overriddenTotal.value = d.overridden
    editing.value = false
    const first = firstTitledIdx()
    expandedSecs.value = first >= 0 ? new Set([first]) : new Set()
  } catch (e) {
    alert(`保存失败：${(e as Error).message}`)
  } finally {
    saving.value = false
  }
}

async function resetOverride() {
  if (!selected.value?.overridden) return
  if (!confirm('恢复为代码默认值？当前自定义将丢弃。')) return
  try {
    await api.resetPromptOverride(selected.value.key)
    const d = await api.getPrompts()
    items.value = d.items
    overriddenTotal.value = d.overridden
  } catch (e) {
    alert(`恢复失败：${(e as Error).message}`)
  }
}

async function copyText() {
  if (!selected.value) return
  try {
    await navigator.clipboard.writeText(selected.value.text)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch { /* 剪贴板不可用（http 环境）时静默 */ }
}

onMounted(async () => {
  try {
    const d = await api.getPrompts()
    items.value = d.items
    overriddenTotal.value = d.overridden
    if (d.items.length) selectedKey.value = d.items[0].key
    const first = firstTitledIdx()
    if (first >= 0) expandedSecs.value = new Set([first])
  } catch (e) {
    loadError.value = (e as Error).message
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="pl-shell" :class="{ 'has-detail': !!selected }">
    <!-- 左栏：搜索 + 分组列表 -->
    <aside class="pl-list-pane">
      <div class="pl-list-head">
        <div class="pl-brand">
          <span class="pl-title">提示词库</span>
          <span v-if="!loading" class="pl-total">{{ items.length }} 条<template v-if="overriddenTotal"> · {{ overriddenTotal }} 已自定义</template></span>
        </div>
        <div class="pl-search">
          <Search :size="13" :stroke-width="1.75" />
          <input v-model="keyword" placeholder="搜索提示词…" />
        </div>
      </div>
      <div class="pl-list-scroll">
        <div v-if="loading" class="pl-status">加载中…</div>
        <div v-else-if="loadError" class="pl-status pl-error">{{ loadError }}</div>
        <div v-else-if="!groupedFiltered.length" class="pl-status">没有匹配</div>
        <template v-else>
          <div v-for="g in groupedFiltered" :key="g.group" class="pl-group">
            <div class="pl-group-label">{{ g.group }}<span class="pl-group-count">{{ g.entries.length }}</span></div>
            <button
              v-for="e in g.entries"
              :key="e.key"
              class="pl-row"
              :class="{ active: e.key === selectedKey }"
              @click="select(e)"
            >
              <span v-if="e.overridden" class="pl-dot" title="已自定义"></span>
              <span class="pl-row-name">{{ e.name }}</span>
            </button>
          </div>
        </template>
      </div>
    </aside>

    <!-- 右栏：详情 -->
    <section v-if="selected" class="pl-detail">
      <button class="pl-back" aria-label="返回列表" @click="selectedKey = ''">
        <ArrowLeft :size="15" :stroke-width="1.75" /> 列表
      </button>

      <header class="pl-detail-head">
        <div class="pl-detail-title-row">
          <h2 class="pl-detail-name">{{ selected.name }}</h2>
          <span v-if="selected.overridden" class="pl-badge pl-badge-over">已自定义</span>
          <span v-else class="pl-badge">默认</span>
        </div>
        <div class="pl-detail-meta">
          <span class="pl-node-chip">{{ selected.group }} · {{ selected.node }}</span>
          <span class="pl-meta-item"><FileCode2 :size="12" :stroke-width="1.75" /> <code>{{ selected.source }}</code></span>
          <span class="pl-meta-item">{{ selected.chars }} 字</span>
          <span v-if="selected.edited_at" class="pl-meta-item">改于 {{ selected.edited_at.slice(5, 16) }}</span>
        </div>
        <p v-if="selected.note" class="pl-note">{{ selected.note }}</p>
        <div class="pl-actions">
          <div class="pl-seg" role="tablist" aria-label="查看方式">
            <button role="tab" :aria-selected="viewMode === 'render'" :class="{ on: viewMode === 'render' }" @click="viewMode = 'render'; editing = false">渲染</button>
            <button role="tab" :aria-selected="viewMode === 'raw'" :class="{ on: viewMode === 'raw' }" @click="viewMode = 'raw'; editing = false">原文</button>
          </div>
          <span class="pl-flex" />
          <button v-if="!editing" class="btn btn-sm" @click="copyText">
            <component :is="copied ? Check : Copy" :size="12" :stroke-width="1.75" />
            {{ copied ? '已复制' : '复制' }}
          </button>
          <button v-if="!editing && selected.editable" class="btn btn-sm btn-primary" @click="startEdit">
            <Pencil :size="12" :stroke-width="1.75" /> 编辑
          </button>
          <button v-if="!editing && selected.overridden" class="btn btn-sm" @click="resetOverride">
            <RotateCcw :size="12" :stroke-width="1.75" /> 恢复默认
          </button>
        </div>
      </header>

      <div class="pl-detail-body">
        <template v-if="editing">
          <textarea v-model="editText" class="pl-editor" spellcheck="false"></textarea>
          <div class="pl-editor-foot">
            <span class="pl-editor-hint">保存后立即生效（无需重启）。模板里的 {style_dna} / {name} 等占位符保持原样。</span>
            <span class="pl-flex" />
            <button class="btn btn-sm" :disabled="saving" @click="editing = false"><X :size="12" /> 取消</button>
            <button class="btn btn-sm btn-primary" :disabled="saving || !editText.trim()" @click="saveEdit">
              {{ saving ? '保存中…' : '保存' }}
            </button>
          </div>
        </template>
        <div v-else-if="viewMode === 'render'" class="pl-rendered">
          <template v-if="sections.filter(s => s.hasTitle).length > 1">
            <div class="pl-sec-toolbar">
              <span class="pl-sec-hint">按小节渐进展开</span>
              <span class="pl-flex" />
              <button class="btn btn-sm" @click="expandAll"><ChevronsDownUp :size="12" :stroke-width="1.75" /> 全部展开</button>
              <button class="btn btn-sm" @click="collapseAll"><ChevronsUpDown :size="12" :stroke-width="1.75" /> 全部收起</button>
            </div>
            <section
              v-for="(s, i) in sections"
              :key="i"
              class="pl-sec"
              :class="{ untitled: !s.hasTitle }"
            >
              <button v-if="s.hasTitle" class="pl-sec-head" @click="toggleSec(i)">
                <span class="pl-sec-caret" :class="{ open: expandedSecs.has(i) }">▸</span>
                <span class="pl-sec-title">{{ s.title }}</span>
                <span class="pl-sec-mark" v-if="expandedSecs.has(i)">收起</span>
              </button>
              <div v-if="!s.hasTitle || expandedSecs.has(i)" class="markdown-body pl-sec-body" v-html="s.html"></div>
              <button v-else-if="s.preview" class="pl-sec-preview" @click="toggleSec(i)" :title="s.preview">
                {{ s.preview }}…
                <span class="pl-sec-more">展开</span>
              </button>
            </section>
          </template>
          <div v-else class="markdown-body pl-sec-body" v-html="renderedHtml"></div>
        </div>
        <pre v-else class="pl-raw">{{ selected.text }}</pre>
      </div>
    </section>

    <!-- 未选中占位（桌面端初始） -->
    <section v-else class="pl-detail pl-empty-detail">
      <div class="pl-status">从左侧选择一条提示词</div>
    </section>
  </div>
</template>

<style scoped>
.pl-shell {
  height: 100%;
  display: flex;
  overflow: hidden;
}
.pl-list-pane {
  width: 300px;
  flex: none;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border-color);
  background: var(--bg-secondary);
}
.pl-list-head { padding: 18px 16px 10px; }
.pl-brand { display: flex; align-items: baseline; gap: 8px; margin-bottom: 10px; }
.pl-title {
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}
.pl-total { font-size: 11px; color: var(--text-tertiary); }
.pl-search {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 10px;
  border: 1px solid var(--border-color);
  border-radius: 9px;
  background: var(--bg-card);
  color: var(--text-tertiary);
}
.pl-search:focus-within { border-color: var(--accent); }
.pl-search input {
  flex: 1;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 12.5px;
  outline: none;
  font-family: inherit;
  min-width: 0;
}

.pl-list-scroll { flex: 1; overflow-y: auto; padding: 0 10px 24px; }
.pl-group { margin-top: 14px; }
.pl-group-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  padding: 0 8px 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.pl-group-count {
  font-weight: 400;
  opacity: 0.7;
}
.pl-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.12s, color 0.12s;
}
.pl-row:hover { background: var(--accent-lighter); color: var(--text-primary); }
.pl-row.active { background: var(--accent-light); color: var(--text-primary); font-weight: 600; }
.pl-row-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pl-dot {
  flex: none;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
}

/* ---- 右栏详情 ---- */
.pl-detail {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 24px 32px 40px;
}
.pl-back { display: none; }
.pl-detail-head { max-width: 860px; }
.pl-detail-title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.pl-detail-name {
  font-family: var(--font-serif);
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  margin: 0;
}
.pl-badge {
  font-size: 11px;
  padding: 2px 9px;
  border-radius: var(--radius-full);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-tertiary);
}
.pl-badge-over {
  background: var(--accent-light);
  border-color: var(--accent-border);
  color: var(--accent);
  font-weight: 600;
}
.pl-detail-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-tertiary);
}
.pl-node-chip {
  color: var(--accent);
  background: var(--accent-light);
  border-radius: var(--radius-full);
  padding: 2px 10px;
}
.pl-meta-item { display: inline-flex; align-items: center; gap: 4px; }
.pl-meta-item code { font-size: 11px; font-family: var(--font-mono, monospace); }
.pl-note {
  margin: 12px 0 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-secondary);
  max-width: 720px;
}
.pl-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 16px 0 0;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
}
.pl-flex { flex: 1; }
.pl-seg {
  display: inline-flex;
  border: 1px solid var(--border-color);
  border-radius: 9px;
  overflow: hidden;
  background: var(--bg-secondary);
}
.pl-seg button {
  border: 0;
  background: transparent;
  padding: 5px 14px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  font-family: inherit;
}
.pl-seg button.on {
  background: var(--accent);
  color: #fff;
  font-weight: 600;
}

.pl-detail-body { margin-top: 18px; max-width: 860px; }
.pl-rendered {
  font-size: 13.5px;
  line-height: 1.8;
  color: var(--text-primary);
}

/* ---- 渐进式披露：小节折叠 ---- */
.pl-sec-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.pl-sec-hint { font-size: 11.5px; color: var(--text-tertiary); }
.pl-sec {
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--bg-card);
  margin-bottom: 8px;
  overflow: hidden;
}
.pl-sec.untitled { border: 0; background: transparent; margin-bottom: 10px; }
.pl-sec-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 14px;
  border: 0;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
  text-align: left;
}
.pl-sec-head:hover { background: var(--accent-lighter); }
.pl-sec-caret {
  flex: none;
  font-size: 11px;
  color: var(--accent);
  transition: transform 0.15s;
}
.pl-sec-caret.open { transform: rotate(90deg); }
.pl-sec-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pl-sec-mark { margin-left: auto; flex: none; font-size: 11px; color: var(--text-tertiary); }
.pl-sec-preview {
  width: 100%;
  padding: 0 14px 10px 34px;
  border: 0;
  background: transparent;
  text-align: left;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-tertiary);
  cursor: pointer;
  font-family: inherit;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.pl-sec-preview:hover { color: var(--text-secondary); }
.pl-sec-more { color: var(--accent); margin-left: 4px; white-space: nowrap; }
.pl-sec-body { padding: 4px 16px 12px; }

/* ---- 缩进层级区分：每深一层，字号/颜色递减 + bullet 形状不同 ---- */
.pl-rendered :deep(li) { font-size: 13.5px; color: var(--text-primary); }
.pl-rendered :deep(li ul li),
.pl-rendered :deep(li ol li) {
  font-size: 12.75px;
  color: var(--text-secondary);
}
.pl-rendered :deep(li ul li ul li),
.pl-rendered :deep(li ol li ul li),
.pl-rendered :deep(li ul li ol li),
.pl-rendered :deep(li ol li ol li) {
  font-size: 12px;
  color: var(--text-tertiary);
}
.pl-rendered :deep(ul) { list-style-type: disc; }
.pl-rendered :deep(ul ul) { list-style-type: circle; }
.pl-rendered :deep(ul ul ul) { list-style-type: square; }
/* 深层嵌套的引导线弱化，靠字体差异和 bullet 区分层级 */
.pl-rendered :deep(ul ul),
.pl-rendered :deep(ol ol) { margin-top: 2px; }
.pl-raw {
  margin: 0;
  padding: 16px;
  border-radius: 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
.pl-editor {
  width: 100%;
  min-height: 380px;
  resize: vertical;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid var(--accent-border);
  background: var(--bg-card);
  font-family: var(--font-mono, monospace);
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-primary);
  outline: none;
  box-sizing: border-box;
}
.pl-editor:focus { border-color: var(--accent); }
.pl-editor-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}
.pl-editor-hint { font-size: 11.5px; color: var(--text-tertiary); }

.pl-status { padding: 40px; text-align: center; color: var(--text-tertiary); font-size: 13px; }
.pl-error { color: var(--danger, #d9534f); }
.pl-empty-detail { justify-content: center; }

/* 窄屏：列表/详情切换显示 */
@media (max-width: 900px) {
  .pl-list-pane { width: 100%; border-right: 0; }
  .pl-shell.has-detail .pl-list-pane { display: none; }
  .pl-shell:not(.has-detail) .pl-detail { display: none; }
  .pl-back {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    border: 0;
    background: transparent;
    color: var(--text-secondary);
    font-size: 12.5px;
    cursor: pointer;
    font-family: inherit;
    padding: 0 0 12px;
  }
  .pl-detail { padding: 16px 18px 32px; }
}
</style>
