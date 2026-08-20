<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import * as api from '../api'
import type { VolumeEntry } from '../api'
import { BookOpen, RefreshCw } from 'lucide-vue-next'

const store = useAppStore()
const { currentProjectId, chapters } = storeToRefs(store)

const volumes = ref<VolumeEntry[]>([])
const exists = ref(false)
const loading = ref(false)
const generating = ref(false)

async function load() {
  if (!currentProjectId.value) return
  loading.value = true
  try {
    const r = await api.getVolumeOutline(currentProjectId.value)
    volumes.value = r.volumes || []
    exists.value = r.exists
  } finally {
    loading.value = false
  }
}

async function generate() {
  if (!currentProjectId.value || generating.value) return
  generating.value = true
  try {
    const r = await api.generateVolumeOutline(currentProjectId.value)
    volumes.value = r.volumes || []
    exists.value = true
    store.notifySuccess('卷纲已生成')
  } catch (e) {
    store.error = (e as Error).message
  } finally {
    generating.value = false
  }
}

function volProgress(v: VolumeEntry): { done: number; total: number } {
  const m = v.chapters?.match(/(\d+)\s*-\s*(\d+)/)
  if (!m) return { done: 0, total: 0 }
  const lo = Number(m[1]), hi = Number(m[2])
  const done = chapters.value.filter(c => {
    const n = c.chapter_number || 0
    return n >= lo && n <= hi && c.status === 'finalized'
  }).length
  return { done, total: hi - lo + 1 }
}

const expandVol = ref<number | null>(1)

onMounted(load)
</script>

<template>
  <div class="vol-panel">
    <div class="vp-head">
      <div class="vp-title"><BookOpen :size="15" :stroke-width="1.75" /> 卷纲 · 每一卷写什么</div>
      <div class="vp-sub" v-if="exists">{{ volumes.length }} 卷规划 · 写章时自动注入本卷卷纲</div>
      <div class="vp-actions">
        <button v-if="!exists || volumes.length" class="btn btn-sm" :disabled="generating" @click="generate">
          <RefreshCw :size="12" :stroke-width="1.75" :class="{ spinning: generating }" />
          {{ generating ? '生成中…' : exists ? '重新生成' : '生成卷纲' }}
        </button>
        <button class="btn btn-sm" :disabled="loading" aria-label="刷新" @click="load">
          <RefreshCw :size="12" :stroke-width="1.75" :class="{ spinning: loading }" />
        </button>
      </div>
    </div>

    <div v-if="!exists && !loading && !generating" class="vp-empty">
      <BookOpen :size="34" :stroke-width="1.25" />
      <div>还没有卷纲</div>
      <div class="vp-hint">基于全书骨架生成分卷规划：每卷的主题、节点、高潮与悬念</div>
      <button class="btn btn-primary" @click="generate">
        <RefreshCw :size="13" :stroke-width="1.75" /> 生成卷纲
      </button>
    </div>

    <div v-else class="vp-body">
      <div v-for="v in volumes" :key="v.vol" class="vol-card" :class="{ open: expandVol === v.vol }">
        <div class="vc-head" @click="expandVol = expandVol === v.vol ? null : v.vol">
          <span class="vc-badge">第{{ v.vol }}卷</span>
          <span class="vc-name">《{{ v.name }}》</span>
          <span class="vc-range">{{ v.chapters }}章</span>
          <span class="vc-progress" :title="`${volProgress(v).done}/${volProgress(v).total} 章`">
            {{ volProgress(v).done }}/{{ volProgress(v).total }}
            <span class="vc-bar"><span class="vc-fill" :style="{ width: (volProgress(v).done / Math.max(volProgress(v).total, 1) * 100) + '%' }"></span></span>
          </span>
          <span class="vc-arrow" :class="{ folded: expandVol !== v.vol }">▾</span>
        </div>
        <div v-show="expandVol === v.vol" class="vc-body">
          <div class="vc-row"><span class="vc-k">主题</span><span>{{ v.premise }}</span></div>
          <div class="vc-row"><span class="vc-k">核心冲突</span><span>{{ v.core_conflict }}</span></div>
          <div class="vc-row"><span class="vc-k">关键节点</span><span>{{ (v.key_nodes || []).join(' → ') }}</span></div>
          <div class="vc-row"><span class="vc-k">本卷高潮</span><span>{{ v.climax }}</span></div>
          <div class="vc-row"><span class="vc-k">收束/悬念</span><span>{{ v.hook_to_next }}</span></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.vol-panel { display: flex; flex-direction: column; height: 100%; min-height: 0; overflow-y: auto; padding: 14px 18px; }
.vp-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.vp-title { display: flex; align-items: center; gap: 7px; font-family: var(--font-serif), serif; font-size: 14px; font-weight: 700; color: var(--text-primary); }
.vp-sub { font-size: 11px; color: var(--text-muted); }
.vp-actions { margin-left: auto; display: flex; gap: 6px; }
.vp-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 60px 0; color: var(--text-muted); font-size: 13px; }
.vp-hint { font-size: 11px; opacity: 0.75; margin-bottom: 6px; }
.vp-body { display: flex; flex-direction: column; gap: 10px; }
.vol-card { border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--bg-card); overflow: hidden; }
.vc-head { display: flex; align-items: center; gap: 10px; padding: 10px 14px; cursor: pointer; flex-wrap: wrap; }
.vc-head:hover { background: var(--bg-secondary); }
.vc-badge { font-size: 10px; font-weight: 700; color: var(--accent); background: var(--accent-lighter); border-radius: var(--radius-full); padding: 2px 9px; }
.vc-name { font-family: var(--font-serif), serif; font-size: 14px; font-weight: 700; color: var(--text-primary); }
.vc-range { font-size: 11px; color: var(--text-muted); font-family: var(--font-mono), monospace; }
.vc-progress { margin-left: auto; display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-secondary); font-family: var(--font-mono), monospace; }
.vc-bar { width: 64px; height: 5px; border-radius: var(--radius-full); background: var(--bg-secondary); overflow: hidden; display: inline-block; }
.vc-fill { display: block; height: 100%; background: var(--accent); border-radius: var(--radius-full); transition: width 0.4s; }
.vc-arrow { font-size: 11px; color: var(--text-muted); transition: transform 0.15s; }
.vc-arrow.folded { transform: rotate(-90deg); }
.vc-body { padding: 4px 16px 14px; border-top: 1px dashed var(--border-subtle); }
.vc-row { display: flex; gap: 10px; padding: 5px 0; font-size: 12px; color: var(--text-secondary); line-height: 1.6; }
.vc-k { flex-shrink: 0; width: 66px; color: var(--accent); font-weight: 600; }
.spinning { animation: vpSpin 0.9s linear infinite; }
@keyframes vpSpin { to { transform: rotate(360deg); } }
</style>
