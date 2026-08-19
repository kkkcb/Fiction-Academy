<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import * as api from '../api'
import { Network, RefreshCw, User, BookMarked } from 'lucide-vue-next'

const store = useAppStore()
const { currentProjectId } = storeToRefs(store)

interface WebChapter { chapter: number; title: string; words: number; types: string[]; plot: string; emotion: string }
interface WebThread { kind: string; name: string; chapters: number[]; setup_ch?: number | null; payoff_chs?: number[] }
const chapters = ref<WebChapter[]>([])
const threads = ref<WebThread[]>([])
const missing = ref(0)
const loading = ref(false)
const backfilling = ref(false)
const hoverChapter = ref<number | null>(null)
const focusThread = ref<string | null>(null)

const ROW_H = 56
const SPINE_X = 210
const THREAD_GAP = 46
const THREAD_X0 = 300
const width = computed(() => THREAD_X0 + Math.max(threads.value.length, 1) * THREAD_GAP + 30)
const height = computed(() => 70 + chapters.value.length * ROW_H)

async function load() {
  if (!currentProjectId.value) return
  loading.value = true
  try {
    const r = await api.getStoryWeb(currentProjectId.value)
    chapters.value = r.chapters
    threads.value = r.threads
    missing.value = r.missing_web
  } finally {
    loading.value = false
  }
}

async function backfill() {
  if (!currentProjectId.value || backfilling.value) return
  backfilling.value = true
  try {
    for (let i = 0; i < 60; i++) {
      const r = await api.backfillStoryWeb(currentProjectId.value, 3)
      if (!r.remaining) break
    }
    await load()
    store.notifySuccess('章节脉络已补全')
  } finally {
    backfilling.value = false
  }
}

const threadPath = (t: WebThread, idx: number) => {
  const x = THREAD_X0 + idx * THREAD_GAP
  const ys = t.chapters.map(n => {
    const i = chapters.value.findIndex(c => c.chapter === n)
    return 70 + i * ROW_H + ROW_H / 2
  })
  if (!ys.length) return ''
  return `M ${x} ${ys[0]} ` + ys.slice(1).map(y => `L ${x} ${y}`).join(' ')
}

const chY = (n: number) => 70 + chapters.value.findIndex(c => c.chapter === n) * ROW_H

const threadColor = (t: WebThread) => t.kind === 'character' ? '#0891b2' : '#d97706'
const threadDim = (t: WebThread) => focusThread.value && focusThread.value !== `${t.kind}:${t.name}` ? 0.15 : 0.9

const chaptersOfThread = (t: WebThread) => t.chapters.join('→')

onMounted(load)
</script>

<template>
  <div class="story-web">
    <div class="sw-head">
      <div class="sw-title"><Network :size="15" :stroke-width="1.75" /> 章节脉络网</div>
      <div class="sw-sub">章节为轴 · 人物线（青）/ 伏笔线（琥珀）交织，悬停章节看概要</div>
      <div class="sw-actions">
        <span v-if="missing > 0" class="sw-missing">{{ missing }} 章待补脉络</span>
        <button v-if="missing > 0" class="btn btn-sm btn-primary" :disabled="backfilling" @click="backfill">
          <RefreshCw :size="12" :stroke-width="1.75" :class="{ spinning: backfilling }" />
          {{ backfilling ? '补全中…' : '补全脉络' }}
        </button>
        <button class="btn btn-sm" :disabled="loading" aria-label="刷新脉络网" @click="load">
          <RefreshCw :size="12" :stroke-width="1.75" :class="{ spinning: loading }" />
        </button>
      </div>
    </div>

    <div v-if="!chapters.length && !loading" class="sw-empty">还没有已定稿的章节</div>

    <div v-else class="sw-scroll">
      <svg :width="width" :height="height" class="sw-svg">
        <!-- 章节轴 -->
        <line :x1="SPINE_X" :x2="SPINE_X" y1="50" :y2="height - 20" class="spine" />
        <!-- 线程 -->
        <g v-for="(t, idx) in threads" :key="t.kind + t.name"
           :opacity="threadDim(t)" class="thread" @click="focusThread = focusThread === `${t.kind}:${t.name}` ? null : `${t.kind}:${t.name}`">
          <path :d="threadPath(t, idx)" :stroke="threadColor(t)" fill="none" stroke-width="2.5" />
          <circle v-for="n in t.chapters" :key="n" :cx="THREAD_X0 + idx * THREAD_GAP" :cy="chY(n) + ROW_H / 2" r="4" :fill="threadColor(t)" />
          <text :x="THREAD_X0 + idx * THREAD_GAP" y="42" class="thread-label" text-anchor="middle">{{ t.name.slice(0, 6) }}</text>
        </g>
        <!-- 章节节点 -->
        <g v-for="c in chapters" :key="c.chapter" class="chapter-node"
           @mouseenter="hoverChapter = c.chapter" @mouseleave="hoverChapter = null">
          <rect x="14" :y="chY(c.chapter)" :width="SPINE_X - 34" :height="ROW_H - 8" rx="8"
                :class="{ hover: hoverChapter === c.chapter }" />
          <circle :cx="SPINE_X" :cy="chY(c.chapter) + ROW_H / 2 - 4" r="6" class="ch-dot" />
          <text x="30" :y="chY(c.chapter) + 20" class="ch-num">第{{ c.chapter }}章</text>
          <text x="86" :y="chY(c.chapter) + 20" class="ch-title">{{ c.title }}</text>
          <text x="30" :y="chY(c.chapter) + 38" class="ch-plot">{{ (hoverChapter === c.chapter ? c.plot : (c.types.join('·') || c.emotion)).slice(0, 30) }}</text>
        </g>
      </svg>
    </div>

    <!-- 线程图例 -->
    <div v-if="threads.length" class="sw-legend">
      <div v-for="t in threads" :key="'l' + t.kind + t.name" class="legend-item"
           :class="{ dim: focusThread && focusThread !== `${t.kind}:${t.name}` }"
           @click="focusThread = focusThread === `${t.kind}:${t.name}` ? null : `${t.kind}:${t.name}`">
        <component :is="t.kind === 'character' ? User : BookMarked" :size="12" :stroke-width="1.75" :color="threadColor(t)" />
        <span class="lg-name">{{ t.name }}</span>
        <span class="lg-chs">{{ chaptersOfThread(t) }}</span>
        <span v-if="t.payoff_chs?.length" class="lg-payoff">已收 {{ t.payoff_chs.length }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.story-web { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.sw-head { display: flex; align-items: center; gap: 12px; padding: 10px 16px; border-bottom: 1px solid var(--border-subtle); flex-wrap: wrap; }
.sw-title { display: flex; align-items: center; gap: 7px; font-family: var(--font-serif), serif; font-size: 14px; font-weight: 700; color: var(--text-primary); }
.sw-sub { font-size: 11px; color: var(--text-muted); }
.sw-actions { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.sw-missing { font-size: 11px; color: #d97706; }
.sw-empty { padding: 60px 0; text-align: center; color: var(--text-muted); font-size: 13px; }
.sw-scroll { flex: 1; overflow: auto; padding: 8px 12px; }
.spine { stroke: var(--border-color); stroke-width: 3; }
.thread { cursor: pointer; }
.thread path { opacity: 0.55; }
.thread:hover path { opacity: 1; }
.thread-label { font-size: 10px; fill: var(--text-secondary); }
.chapter-node rect { fill: var(--bg-card); stroke: var(--border-subtle); cursor: default; }
.chapter-node rect.hover { stroke: var(--accent); }
.ch-dot { fill: var(--accent); }
.ch-num { font-size: 11px; fill: var(--accent); font-weight: 600; }
.ch-title { font-size: 12px; fill: var(--text-primary); }
.ch-plot { font-size: 10px; fill: var(--text-muted); }
.spinning { animation: swSpin 0.9s linear infinite; }
@keyframes swSpin { to { transform: rotate(360deg); } }
.sw-legend {
  display: flex; flex-wrap: wrap; gap: 6px 14px;
  padding: 8px 16px; border-top: 1px solid var(--border-subtle);
  max-height: 140px; overflow-y: auto;
}
.legend-item { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-secondary); cursor: pointer; }
.legend-item.dim { opacity: 0.35; }
.lg-name { color: var(--text-primary); }
.lg-chs { font-family: var(--font-mono), monospace; font-size: 10px; color: var(--text-muted); }
.lg-payoff { font-size: 9px; color: #059669; }
</style>
