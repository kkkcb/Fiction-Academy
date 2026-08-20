<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import * as api from '../api'
import type { WritingTasks } from '../api'
import { ListTodo, Rocket, PenLine, Network, RefreshCw } from 'lucide-vue-next'

const store = useAppStore()
const { currentProjectId, isWritingChapter, batchWriting } = storeToRefs(store)

const tasks = ref<WritingTasks | null>(null)
const loading = ref(false)
const rewriting = ref<number | null>(null)
const weaving = ref(false)

async function load() {
  if (!currentProjectId.value) return
  loading.value = true
  try {
    tasks.value = await api.getWritingTasks(currentProjectId.value)
  } finally {
    loading.value = false
  }
}

function continueVolume() {
  if (!currentProjectId.value || !tasks.value) return
  const remain = Math.max(tasks.value.volume.target - tasks.value.volume.done, 1)
  store.startBatchWriting(currentProjectId.value, remain, '', true)
}

async function rewriteChapter(n: number) {
  if (!currentProjectId.value || isWritingChapter.value || batchWriting.value) return
  rewriting.value = n
  try {
    await store.writeNextChapter(currentProjectId.value, true, '', false, n)
  } finally {
    rewriting.value = null
  }
}

async function weaveWeb() {
  if (!currentProjectId.value || weaving.value) return
  weaving.value = true
  try {
    for (let i = 0; i < 60; i++) {
      const r = await api.backfillStoryWeb(currentProjectId.value, 3)
      if (!r.remaining) break
    }
    store.notifySuccess('章节脉络已补全')
    await load()
  } finally {
    weaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="task-panel">
    <div class="tp-head">
      <div class="tp-title"><ListTodo :size="15" :stroke-width="1.75" /> 写作任务</div>
      <button class="btn btn-sm" :disabled="loading" aria-label="刷新任务" @click="load">
        <RefreshCw :size="12" :stroke-width="1.75" :class="{ spinning: loading }" />
      </button>
    </div>

    <div v-if="tasks" class="tp-body">
      <!-- 卷进度 -->
      <div class="task-card">
        <div class="tc-head">
          <span class="tc-name">卷一进度</span>
          <span class="tc-meta">{{ tasks.volume.done }}/{{ tasks.volume.target }} 章 · {{ (tasks.volume.total_words / 10000).toFixed(1) }} 万字</span>
        </div>
        <div class="tc-progress"><div class="tc-fill" :style="{ width: Math.min(tasks.volume.done / tasks.volume.target * 100, 100) + '%' }"></div></div>
        <div class="tc-actions">
          <button class="btn btn-sm btn-primary" :disabled="isWritingChapter || batchWriting" @click="continueVolume">
            <Rocket :size="12" :stroke-width="1.75" /> {{ batchWriting ? '连续写作进行中' : '续写剩余章节' }}
          </button>
        </div>
      </div>

      <!-- 质量任务 -->
      <div class="task-card" :class="{ ok: !tasks.deficient.length }">
        <div class="tc-head">
          <span class="tc-name">质量修复</span>
          <span class="tc-meta">{{ tasks.deficient.length ? tasks.deficient.length + ' 章字数不达标' : '全部达标 ✓' }}</span>
        </div>
        <div v-for="d in tasks.deficient" :key="d.chapter" class="task-row">
          <span class="tr-name">第{{ d.chapter }}章《{{ d.title }}》</span>
          <span class="tr-meta">{{ d.words }}/{{ d.target * 85 / 100 | 0 }} 字下限</span>
          <button class="btn btn-sm" :disabled="isWritingChapter || batchWriting || rewriting !== null" @click="rewriteChapter(d.chapter)">
            <PenLine :size="12" :stroke-width="1.75" /> {{ rewriting === d.chapter ? '重写中…' : '重写' }}
          </button>
        </div>
      </div>

      <!-- 脉络任务 -->
      <div class="task-card" :class="{ ok: !tasks.missing_web }">
        <div class="tc-head">
          <span class="tc-name">脉络网编织</span>
          <span class="tc-meta">{{ tasks.missing_web ? tasks.missing_web + ' 章缺脉络' : '全部就绪 ✓' }}</span>
        </div>
        <div v-if="tasks.missing_web" class="tc-actions">
          <button class="btn btn-sm" :disabled="weaving" @click="weaveWeb">
            <Network :size="12" :stroke-width="1.75" /> {{ weaving ? '编织中…' : '补全脉络' }}
          </button>
        </div>
      </div>

      <!-- 空草稿 -->
      <div v-if="tasks.empty_draft_chapters.length" class="task-card">
        <div class="tc-head">
          <span class="tc-name">待续草稿</span>
          <span class="tc-meta">第 {{ tasks.empty_draft_chapters.join('、') }} 章（续写时自动接上）</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.task-panel { display: flex; flex-direction: column; height: 100%; overflow-y: auto; padding: 14px 18px; gap: 12px; }
.tp-head { display: flex; align-items: center; justify-content: space-between; }
.tp-title { display: flex; align-items: center; gap: 7px; font-family: var(--font-serif), serif; font-size: 14px; font-weight: 700; color: var(--text-primary); }
.tp-body { display: flex; flex-direction: column; gap: 10px; }
.task-card { border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 10px 14px; background: var(--bg-card); }
.task-card.ok { opacity: 0.7; }
.tc-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 6px; }
.tc-name { font-size: 12px; font-weight: 700; color: var(--text-primary); }
.tc-meta { font-size: 11px; color: var(--text-muted); }
.tc-progress { height: 6px; border-radius: var(--radius-full); background: var(--bg-secondary); overflow: hidden; margin-bottom: 8px; }
.tc-fill { height: 100%; background: var(--accent); border-radius: var(--radius-full); transition: width 0.4s; }
.tc-actions { display: flex; gap: 8px; }
.task-row { display: flex; align-items: center; gap: 10px; padding: 4px 0; }
.tr-name { font-size: 12px; color: var(--text-primary); flex: 1; }
.tr-meta { font-size: 10px; color: #d97706; font-family: var(--font-mono), monospace; }
.spinning { animation: tpSpin 0.9s linear infinite; }
@keyframes tpSpin { to { transform: rotate(360deg); } }
</style>
