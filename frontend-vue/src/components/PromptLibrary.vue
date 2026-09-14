<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import * as api from '../api'
import type { PromptEntry } from '../types'
import { Search, Copy, Check, ChevronDown, FileCode2 } from 'lucide-vue-next'

const loading = ref(true)
const loadError = ref('')
const total = ref(0)
const groups = ref<{ group: string; count: number }[]>([])
const items = ref<PromptEntry[]>([])

const keyword = ref('')
const activeGroup = ref('')

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  return items.value.filter(e => {
    if (activeGroup.value && e.group !== activeGroup.value) return false
    if (!k) return true
    return (
      e.name.toLowerCase().includes(k) ||
      e.node.toLowerCase().includes(k) ||
      e.group.toLowerCase().includes(k) ||
      e.note.toLowerCase().includes(k) ||
      e.text.toLowerCase().includes(k)
    )
  })
})

const expanded = ref<Set<number>>(new Set())

function toggle(i: number) {
  const s = new Set(expanded.value)
  s.has(i) ? s.delete(i) : s.add(i)
  expanded.value = s
}

const copied = ref<number | null>(null)

async function copyText(e: PromptEntry, i: number) {
  try {
    await navigator.clipboard.writeText(e.text)
    copied.value = i
    setTimeout(() => { if (copied.value === i) copied.value = null }, 1500)
  } catch { /* 剪贴板不可用（http 环境）时静默 */ }
}

onMounted(async () => {
  try {
    const d = await api.getPrompts()
    total.value = d.total
    groups.value = d.groups
    items.value = d.items
  } catch (e) {
    loadError.value = (e as Error).message
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="prompt-library">
    <div class="pl-header">
      <div class="pl-title-row">
        <h1 class="pl-title">提示词库</h1>
        <span v-if="!loading" class="pl-total">共 {{ total }} 条 · 覆盖 9 大环节</span>
      </div>
      <p class="pl-desc">
        全应用每个环节的 LLM 提示词都在这里（含系统提示词、作者文风 DNA、各节点人格），与代码实时同步。
        复制出来改好后告诉 AI 改哪条，或按代码位置直接改文件。
      </p>
      <div class="pl-search">
        <Search :size="14" :stroke-width="1.75" />
        <input v-model="keyword" class="pl-search-input" placeholder="搜索名称 / 节点 / 提示词内容…" />
      </div>
      <div class="pl-group-nav">
        <button
          class="pl-chip"
          :class="{ active: activeGroup === '' }"
          @click="activeGroup = ''"
        >全部 {{ total }}</button>
        <button
          v-for="g in groups"
          :key="g.group"
          class="pl-chip"
          :class="{ active: activeGroup === g.group }"
          @click="activeGroup = g.group"
        >{{ g.group }} {{ g.count }}</button>
      </div>
    </div>

    <div v-if="loading" class="pl-status">加载中…</div>
    <div v-else-if="loadError" class="pl-status pl-error">{{ loadError }}</div>
    <div v-else-if="filtered.length === 0" class="pl-status">没有匹配的提示词</div>

    <div v-else class="pl-list">
      <div v-for="(e, i) in filtered" :key="`${e.group}-${e.name}-${i}`" class="pl-card" :class="{ open: expanded.has(i) }">
        <button class="pl-card-head" @click="toggle(i)">
          <ChevronDown :size="14" :stroke-width="1.75" class="pl-caret" :class="{ flip: expanded.has(i) }" />
          <span class="pl-node">{{ e.node }}</span>
          <span class="pl-name">{{ e.name }}</span>
          <span class="pl-chars">{{ e.chars }} 字</span>
        </button>
        <div class="pl-card-body">
          <p v-if="e.note" class="pl-note">{{ e.note }}</p>
          <div class="pl-meta">
            <FileCode2 :size="12" :stroke-width="1.75" />
            <code>{{ e.source }}</code>
            <span class="pl-flex" />
            <button class="btn btn-sm" @click="copyText(e, i)">
              <component :is="copied === i ? Check : Copy" :size="12" :stroke-width="1.75" />
              {{ copied === i ? '已复制' : '复制全文' }}
            </button>
          </div>
          <pre class="pl-text">{{ e.text }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.prompt-library {
  height: 100%;
  overflow-y: auto;
  padding: 28px 32px;
}
.pl-header { max-width: 980px; margin: 0 auto 16px; }
.pl-title-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.pl-title {
  font-family: var(--font-serif);
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  margin: 0;
}
.pl-total { font-size: 12px; color: var(--text-tertiary); }
.pl-desc {
  margin: 6px 0 14px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}
.pl-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--bg-secondary);
  color: var(--text-tertiary);
  margin-bottom: 10px;
}
.pl-search:focus-within { border-color: var(--accent); }
.pl-search-input {
  flex: 1;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  font-family: inherit;
}
.pl-group-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.pl-chip {
  padding: 4px 12px;
  border-radius: var(--radius-full);
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.pl-chip:hover { border-color: var(--accent); color: var(--accent); }
.pl-chip.active { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 500; }

.pl-status { padding: 40px; text-align: center; color: var(--text-tertiary); font-size: 13px; }
.pl-error { color: var(--danger, #d9534f); }

.pl-list {
  max-width: 980px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-bottom: 40px;
}
.pl-card {
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--bg-card);
  overflow: hidden;
}
.pl-card-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: transparent;
  border: 0;
  cursor: pointer;
  font-family: inherit;
  text-align: left;
}
.pl-card-head:hover { background: var(--accent-lighter); }
.pl-caret { color: var(--text-tertiary); flex: none; transition: transform 0.15s; }
.pl-caret.flip { transform: rotate(-90deg); }
.pl-node {
  flex: none;
  font-size: 11px;
  color: var(--accent);
  background: var(--accent-light);
  border-radius: var(--radius-full);
  padding: 1px 8px;
  white-space: nowrap;
}
.pl-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pl-chars { margin-left: auto; flex: none; font-size: 11px; color: var(--text-tertiary); }

.pl-card-body { display: none; padding: 0 14px 12px; }
.pl-card.open .pl-card-body { display: block; }
.pl-note {
  margin: 0 0 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
}
.pl-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}
.pl-meta code { font-size: 11px; font-family: var(--font-mono, monospace); }
.pl-flex { flex: 1; }
.pl-text {
  margin: 0;
  padding: 12px;
  border-radius: 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  line-height: 1.65;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 480px;
  overflow-y: auto;
}
</style>
