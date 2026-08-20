<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import * as api from '../api'
import type { WritingTasks } from '../api'
import { ListTodo, Rocket, PenLine, Network, RefreshCw } from 'lucide-vue-next'

const store = useAppStore()
const { currentProjectId, isWritingChapter, batchWriting } = storeToRefs(store)

const tasks = ref<WritingTasks | null>(null)
const dispatchTarget = ref(3)
const dispatchHint = ref('')
const dispatchFast = ref(false)
const dispatchReview = ref(false)
const dispatching = ref(false)
const loading = ref(false)
const rewriting = ref<number | null>(null)
const weaving = ref(false)

import type { WritingStatus } from '../api'

const live = ref<WritingStatus | null>(null)
let liveTimer: ReturnType<typeof setInterval> | null = null

async function pollLive() {
  if (!currentProjectId.value) return
  try {
    live.value = await api.getWritingStatus(currentProjectId.value)
  } catch { /* 忽略 */ }
}

const batch = computed(() => live.value?.batch || null)

async function dispatch() {
  if (!currentProjectId.value || dispatching.value) return
  dispatching.value = true
  try {
    await api.startWritingBatch(currentProjectId.value, {
      target: dispatchTarget.value, hint: dispatchHint.value.trim(),
      fast: dispatchFast.value, pause_each: dispatchReview.value,
    })
    dispatchHint.value = ''
    store.notifySuccess('任务已派发')
    pollLive()
  } catch (e) {
    store.error = (e as Error).message
  } finally {
    dispatching.value = false
  }
}

async function control(action: 'pause' | 'resume' | 'stop') {
  if (!currentProjectId.value) return
  try {
    await api.controlWritingBatch(currentProjectId.value, action)
    pollLive()
  } catch (e) {
    store.error = (e as Error).message
  }
}

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

onMounted(() => {
  load()
  pollLive()
  liveTimer = setInterval(pollLive, 4000)
})
onUnmounted(() => { if (liveTimer) clearInterval(liveTimer) })
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
      <!-- 正在写 -->
      <div v-if="live?.in_progress" class="task-card live-card">
        <span class="dot-pulse"></span>
        <span class="live-text">
          正在写第 {{ live.current_chapter }} 章《{{ live.current_title }}》
          <span v-if="live.fast">（快速）</span>
          · 本书已 {{ live.chapters }} 章
        </span>
      </div>

      <!-- 批量任务控制 -->
      <div v-if="batch?.active" class="task-card batch-card">
        <div class="tc-head">
          <span class="tc-name">连续任务 {{ batch.done }}/{{ batch.target }}</span>
          <span class="tc-meta">
            {{ batch.awaiting_review ? '第' + batch.done + ' 章完成，待审阅' : batch.paused ? '已暂停' : batch.fast ? '快速模式' : '精细模式' }}
          </span>
        </div>
        <div class="tc-progress"><div class="tc-fill" :style="{ width: Math.min(batch.done / batch.target * 100, 100) + '%' }"></div></div>
        <div v-if="batch.last_error" class="batch-err">{{ batch.last_error }}</div>
        <div class="tc-actions">
          <button v-if="batch.paused" class="btn btn-sm btn-primary" @click="control('resume')">继续</button>
          <button v-else class="btn btn-sm" :disabled="!live?.in_progress" @click="control('pause')">写完本章后暂停</button>
          <button class="btn btn-sm" @click="control('stop')">停止</button>
        </div>
      </div>

      <!-- 派发新任务 -->
      <div class="task-card">
        <div class="tc-head">
          <span class="tc-name">派发写作任务</span>
          <span class="tc-meta" v-if="batch?.active">进行中，停止后可派发</span>
        </div>
        <div class="dispatch-form">
          <label class="df-row">写几章 <input v-model.number="dispatchTarget" type="number" min="1" max="40" class="df-num" /></label>
          <textarea v-model="dispatchHint" class="df-hint" rows="2" placeholder="要求（可选）：如 接下来重点写血神教冲突，节奏加快"></textarea>
          <label class="df-check"><input v-model="dispatchReview" type="checkbox" /> 每章完成后暂停等我审阅</label>
          <label class="df-check"><input v-model="dispatchFast" type="checkbox" /> 快速模式（约1分钟/章）</label>
          <button class="btn btn-sm btn-primary" :disabled="!!batch?.active || dispatching" @click="dispatch">
            <Rocket :size="12" :stroke-width="1.75" /> {{ dispatching ? '派发中…' : '派发' }}
          </button>
        </div>
      </div>

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

<style scoped>
.live-card {
  display: flex;
  align-items: center;
  gap: 10px;
  border-left: 3px solid var(--accent);
  background: var(--accent-lighter);
}
.live-text { font-size: 12px; color: var(--text-primary); font-weight: 600; }
.dot-pulse {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  animation: livePulse 1.2s ease-in-out infinite;
}
@keyframes livePulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }
</style>

<style scoped>
.batch-card { border-left: 3px solid var(--accent); }
.batch-err { font-size: 11px; color: #dc2626; margin: 4px 0; }
.dispatch-form { display: flex; flex-direction: column; gap: 8px; }
.df-row { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-secondary); }
.df-num { width: 64px; padding: 4px 8px; border: 1px solid var(--border-color); border-radius: var(--radius-sm); background: var(--bg-secondary); color: var(--text-primary); font-size: 12px; }
.df-hint { padding: 6px 10px; border: 1px solid var(--border-color); border-radius: var(--radius-sm); background: var(--bg-secondary); color: var(--text-primary); font-size: 12px; resize: vertical; font-family: inherit; }
.df-check { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-secondary); }
</style>
