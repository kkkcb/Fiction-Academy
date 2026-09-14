<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import * as api from '../api'
import type { PromptEntry } from '../types'
import { formatMd } from '../utils/format'
import { Search, Copy, Check, FileCode2, Pencil, RotateCcw, X, ArrowLeft } from 'lucide-vue-next'

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

function select(e: PromptEntry) {
  selectedKey.value = e.key
  viewMode.value = 'render'
  editing.value = false
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
        <div v-else-if="viewMode === 'render'" class="markdown-body pl-rendered" v-html="renderedHtml"></div>
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
