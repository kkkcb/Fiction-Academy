<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import * as api from '../api'
import type { WorkspaceItem } from '../types'
import ThinkingBlock from './ThinkingBlock.vue'
import { POINT_NAV, STATUS_LABELS, relativeTime, formatMd } from '../utils/format'
import { BrainCircuit, ClipboardList, Search, BookOpen, CircleX, CircleAlert, CircleHelp, CircleCheck, Circle, Rocket, PenLine } from 'lucide-vue-next'

const store = useAppStore()
const {
  route,
  batchWriting,
  batchTarget,
  batchDone,
  batchPaused,
  batchHint,
  currentProjectId,
  currentProject,
  chapters,
  totalChapterWords,
  isWritingChapter,
  writingPhase,
  writingContent,
  writingThinking,
  writingChapterNumber,
  writingChapterTitle,
  workspaceItems,
} = storeToRefs(store)

const selectedId = ref<string | null>(null)

// ===== 实时写作进度（后台批量/他人会话写作时也可见） =====
const liveStatus = ref<api.WritingStatus | null>(null)
let statusTimer: ReturnType<typeof setInterval> | null = null

async function pollStatus() {
  if (!currentProjectId.value) return
  try {
    liveStatus.value = await api.getWritingStatus(currentProjectId.value)
  } catch { /* 忽略 */ }
}

onMounted(() => {
  pollStatus()
  statusTimer = setInterval(pollStatus, 5000)
})
onUnmounted(() => { if (statusTimer) clearInterval(statusTimer) })
const selected = computed<WorkspaceItem | null>(() =>
  chapters.value.find(c => c.id === selectedId.value) || null,
)

function planTypesOf(chapterNo: number | null | undefined): string[] {
  if (!chapterNo) return []
  const plan = workspaceItems.value.find(
    w => w.item_type === 'chapter_plan' && w.chapter_number === chapterNo,
  )
  if (!plan) return []
  try {
    const meta = JSON.parse(plan.metadata || '{}') as Record<string, unknown>
    const raw = meta.chapter_types ?? meta.chapter_type ?? []
    const list = Array.isArray(raw) ? raw : [raw]
    return list.map(String).filter(Boolean)
  } catch {
    return []
  }
}

const selectedPlan = computed<WorkspaceItem | null>(() => {
  if (!selected.value?.chapter_number) return null
  return workspaceItems.value.find(
    w => w.item_type === 'chapter_plan' && w.chapter_number === selected.value!.chapter_number,
  ) || null
})

const showPlan = ref(true)

watch(chapters, list => {
  if (list.length && !list.some(c => c.id === selectedId.value)) {
    selectedId.value = list[list.length - 1].id
  }
}, { immediate: true })

// 骨架就绪度（五个点位全部定稿）
const skeletonDone = computed(() => {
  const done = new Set(
    workspaceItems.value
      .filter(w => POINT_NAV.some(p => p.key === w.item_type) && (w.status === 'finalized' || w.status === 'locked'))
      .map(w => w.item_type),
  )
  return { done, ready: done.size >= POINT_NAV.length }
})

const nextNumber = computed(() =>
  chapters.value.length ? (chapters.value[chapters.value.length - 1].chapter_number || chapters.value.length) + 1 : 1,
)

// ===== 连续写作（Copilot 式目标） =====
const showBatch = ref(false)
const batchCount = ref(3)
const batchGoal = ref('')
const batchReview = ref(true)
const batchFast = ref(false)

function openBatch() {
  batchCount.value = 3
  batchGoal.value = ''
  batchReview.value = true
  showBatch.value = true
}

function startBatch() {
  if (!currentProjectId.value || batchCount.value < 1) return
  showBatch.value = false
  store.startBatchWriting(currentProjectId.value, batchCount.value, batchGoal.value.trim(), batchReview.value, batchFast.value)
}

// ===== 章节审阅：编辑正文 =====
const editingChapter = ref(false)
const editContent = ref('')
const editSaving = ref(false)

function startChapterEdit() {
  if (!selected.value) return
  editingChapter.value = true
  editContent.value = selected.value.content || ''
}

async function saveChapterEdit() {
  if (!selected.value || !currentProjectId.value) return
  editSaving.value = true
  try {
    await store.updateWorkspaceItem(selected.value.id, { content: editContent.value })
    editingChapter.value = false
    await store.fetchWorkspaceItems(currentProjectId.value)
    store.notifySuccess('章节修改已保存')
  } finally {
    editSaving.value = false
  }
}

// ===== 写作 =====
function writeNext() {
  if (!currentProjectId.value || !skeletonDone.value.ready) return
  store.writeNextChapter(currentProjectId.value, false, '')
}
function regenerateLatest() {
  if (!currentProjectId.value || !chapters.value.length) return
  if (!confirm(`重写第 ${nextNumber.value - 1} 章？旧稿将被替换。`)) return
  store.writeNextChapter(currentProjectId.value, true, '')
}

const readerEl = ref<HTMLElement | null>(null)
watch(() => writingContent.value, async () => {
  await nextTick()
  if (readerEl.value) readerEl.value.scrollTop = readerEl.value.scrollHeight
})

// ===== 审校 =====
const reviewing = ref(false)
const reviewResult = ref<null | {
  overall: string
  summary: string
  issues: { severity: string; description: string; suggestion?: string }[]
  needs_revision: boolean
}>(null)

async function runReview() {
  if (!currentProjectId.value || !selected.value?.chapter_number || !selected.value.content) return
  reviewing.value = true
  reviewResult.value = null
  try {
    const r = await api.reviewChapter(currentProjectId.value, selected.value.chapter_number, selected.value.content) as never
    reviewResult.value = r
  } catch (e) {
    store.error = `审校失败：${(e as Error).message}`
  } finally {
    reviewing.value = false
  }
}

// 正文渲染：每行视为一段（单换行转双换行交给 markdown），偶带 markdown 语法也能正确显示
function renderProse(text: string | null | undefined): string {
  return formatMd((text || '').split(/\n+/).join('\n\n'), { cache: false })
}
function wordCountOf(item: WorkspaceItem): number {
  return (item.content || '').length
}
const REVIEW_ICON: Record<string, unknown> = { error: CircleX, warning: CircleAlert, info: CircleHelp, pass: CircleCheck }
</script>

<template>
  <div class="writing-panel">
    <header class="writing-header" :class="{ standalone: route === 'writing' }">
      <div v-if="route !== 'writing'" class="wh-left">
        <div class="wh-title">小说写作</div>
        <div class="wh-sub">
          {{ currentProject?.name }} ·
          <template v-if="chapters.length">已写 {{ chapters.length }} 章 · 共 {{ totalChapterWords.toLocaleString() }} 字</template>
          <template v-else>尚未开写</template>
        </div>
      </div>
      <div class="wh-actions">
        <template v-if="skeletonDone.ready">
          <button v-if="!isWritingChapter && !batchWriting" class="btn" aria-label="连续写作" title="设定目标，AI 连续写多章" @click="openBatch">
            <Rocket :size="14" :stroke-width="1.75" /> 连续写作
          </button>
          <button v-if="!isWritingChapter && !batchWriting" class="btn btn-primary" aria-label="写下一章" @click="writeNext">
            <BrainCircuit :size="14" :stroke-width="1.75" style="vertical-align:-2px" /> 写第 {{ nextNumber }} 章
          </button>
          <button v-else class="btn" aria-label="停止写作" @click="store.stopWritingChapter()">■ 停止</button>
          <button
            v-if="!isWritingChapter && chapters.length"
            class="btn"
            aria-label="重写最新一章"
            @click="regenerateLatest"
          >重写最新章</button>
        </template>
        <span v-else class="wh-not-ready">骨架未完成，先去创作流程把五个点位定稿</span>
      </div>
    </header>

    <!-- 后台写作实时进度 -->
    <div v-if="liveStatus?.in_progress && !batchWriting" class="batch-bar live-bar">
      <span class="dot-pulse"></span>
      <span class="batch-text">
        正在写第 {{ liveStatus.current_chapter }}章《{{ liveStatus.current_title }}》
        <span v-if="liveStatus.fast">（快速模式）</span> · 本书已 {{ liveStatus.chapters }} 章 / {{ (liveStatus.total_words / 10000).toFixed(1) }} 万字
      </span>
      <button class="btn btn-sm" aria-label="立即刷新章节列表" @click="currentProjectId && store.fetchWorkspaceItems(currentProjectId)">刷新列表</button>
    </div>

    <!-- 连续写作：进度/审阅横幅 -->
    <div v-if="batchWriting" class="batch-bar">
      <template v-if="batchPaused">
        <span class="batch-text">
          第 {{ batchDone }}/{{ batchTarget }} 章完成——请审阅下方内容（可编辑），满意后继续
        </span>
        <button class="btn btn-primary btn-sm" aria-label="继续写下一章" @click="store.resumeBatch()">继续下一章</button>
        <button class="btn btn-sm" aria-label="中止连续写作" @click="store.stopBatchWriting()">中止</button>
      </template>
      <template v-else>
        <span class="batch-text">连续写作 {{ batchDone }}/{{ batchTarget }} · {{ isWritingChapter ? '正在写下一章…' : '准备中…' }}<span v-if="batchHint">（目标：{{ batchHint.slice(0, 24) }}）</span></span>
        <button class="btn btn-sm" aria-label="停止连续写作" @click="store.stopBatchWriting()">停止</button>
      </template>
      <div class="batch-progress"><div class="batch-fill" :style="{ width: (batchDone / Math.max(batchTarget, 1) * 100) + '%' }"></div></div>
    </div>

    <div class="writing-body">
      <aside class="chapter-list">
        <div v-if="chapters.length" class="ch-scroll">
          <button
            v-for="c in chapters"
            :key="c.id"
            class="ch-item"
            :class="{ active: c.id === selectedId && !isWritingChapter }"
            @click="selectedId = c.id"
          >
            <span class="ch-num">第{{ c.chapter_number }}章</span>
            <span v-for="t in planTypesOf(c.chapter_number)" :key="t" class="ch-type">{{ t }}</span>
            <span class="ch-title">{{ c.title || '未命名' }}</span>
            <span class="ch-words">{{ wordCountOf(c).toLocaleString() }}字</span>
            <span v-if="c.status === 'draft'" class="ch-status">草稿</span>
          </button>
        </div>
        <div v-else class="ch-empty">
          <div class="ch-empty-title">开写前的准备清单</div>
          <div v-for="p in POINT_NAV" :key="p.key" class="ch-check" :class="{ ok: skeletonDone.done.has(p.key) }">
            <CircleCheck v-if="skeletonDone.done.has(p.key)" :size="13" :stroke-width="1.75" class="ch-check-ok" />
            <Circle v-else :size="13" :stroke-width="1.75" class="ch-check-todo" />
            <span>{{ p.label }}</span>
            <span class="ch-check-desc">{{ p.desc }}</span>
          </div>
          <button v-if="skeletonDone.ready" class="btn btn-primary ch-cta" @click="writeNext"><BrainCircuit :size="14" :stroke-width="1.75" style="vertical-align:-2px" /> 开始写第 1 章</button>
        </div>
      </aside>

      <main ref="readerEl" class="chapter-reader">
        <!-- 写作中 / 写作完成预览 -->
        <template v-if="isWritingChapter || writingContent">
          <div class="reader-head">
            <div class="reader-title">
              第{{ writingChapterNumber || '?' }}章<template v-if="writingChapterTitle"> · {{ writingChapterTitle }}</template>
            </div>
            <div v-if="isWritingChapter" class="reader-phase">
              <span class="dot-pulse"></span>{{ writingPhase || '正在执笔…' }}
            </div>
            <div v-else class="reader-meta">已存档</div>
          </div>
          <div v-if="isWritingChapter && !writingContent && !writingThinking" class="reader-waiting">{{ writingPhase || '正在准备…' }}</div>
          <ThinkingBlock v-if="isWritingChapter && writingThinking && !writingContent" :text="writingThinking" :streaming="true" class="writing-thinking" />
          <article class="reader-content">
            <div v-html="renderProse(writingContent)"></div>
            <span v-if="isWritingChapter" class="writing-cursor"></span>
          </article>
        </template>

        <!-- 已选章节阅读 -->
        <template v-else-if="selected">
          <div class="reader-head">
            <div class="reader-title">第{{ selected.chapter_number }}章 · {{ selected.title || '未命名' }}</div>
            <div class="reader-meta">
              <span>{{ wordCountOf(selected).toLocaleString() }} 字</span>
              <span v-if="selected.created_at">{{ relativeTime(selected.created_at) }}</span>
              <span class="reader-status" :class="selected.status">{{ STATUS_LABELS[selected.status] || selected.status }}</span>
            </div>
          </div>

          <div v-if="selectedPlan" class="plan-card">
            <button class="plan-toggle" @click="showPlan = !showPlan">
              <ClipboardList :size="13" :stroke-width="1.75" style="vertical-align:-2px" /> 本章章纲 <span class="plan-arrow" :class="{ open: showPlan }">▾</span>
            </button>
            <div v-show="showPlan" class="plan-body markdown-body" v-html="formatMd(selectedPlan.content || '')"></div>
          </div>

          <template v-if="editingChapter">
            <textarea v-model="editContent" class="chapter-edit-area" rows="18" aria-label="编辑章节内容"></textarea>
            <div class="reader-actions">
              <button class="btn btn-primary" :disabled="editSaving" @click="saveChapterEdit">{{ editSaving ? '保存中…' : '保存修改' }}</button>
              <button class="btn" :disabled="editSaving" @click="editingChapter = false">取消</button>
            </div>
          </template>
          <article v-else class="reader-content">
            <div v-html="renderProse(selected.content)"></div>
          </article>

          <div class="reader-actions">
            <button v-if="!editingChapter" class="btn" aria-label="编辑本章" title="逐段审阅/修改本章内容" @click="startChapterEdit">
              <PenLine :size="13" :stroke-width="1.75" /> 编辑
            </button>
            <button class="btn" :disabled="reviewing" @click="runReview">
              <Search v-if="!reviewing" :size="13" :stroke-width="1.75" />
              {{ reviewing ? '审校中…' : '一致性审校' }}
            </button>
          </div>

          <div v-if="reviewResult" class="review-card">
            <div class="review-head">
              <span class="review-overall" :class="reviewResult.overall"><component :is="REVIEW_ICON[reviewResult.overall] || CircleHelp" :size="13" :stroke-width="1.75" /> {{ reviewResult.overall }}</span>
              <span class="review-summary">{{ reviewResult.summary }}</span>
            </div>
            <div v-if="reviewResult.issues?.length" class="review-issues">
              <div v-for="(iss, i) in reviewResult.issues" :key="i" class="review-issue" :class="iss.severity">
                <component :is="REVIEW_ICON[iss.severity] || CircleHelp" :size="12" :stroke-width="1.75" />
                <div>
                  <div class="ri-desc">{{ iss.description }}</div>
                  <div v-if="iss.suggestion" class="ri-sug">建议：{{ iss.suggestion }}</div>
                </div>
              </div>
            </div>
            <div v-else class="review-clean"><CircleCheck :size="12" :stroke-width="1.75" style="vertical-align:-2px" /> 未发现设定一致性问题</div>
          </div>
        </template>

        <div v-else class="reader-empty">
          <BookOpen class="reader-empty-icon" :size="34" :stroke-width="1.5" />
          <div v-if="skeletonDone.ready">点上方「写第 {{ nextNumber }} 章」开始，或从左侧选择章节阅读</div>
          <div v-else>完成骨架后即可开始正文创作</div>
        </div>
      </main>
    </div>
  </div>

    <!-- 连续写作目标对话框 -->
    <div v-if="showBatch" class="modal-overlay show" @click.self="showBatch = false">
      <div class="modal-card">
        <h3>连续写作目标</h3>
        <label class="pin-label">连续写几章</label>
        <input v-model.number="batchCount" type="number" min="1" max="20" class="modal-input" />
        <label class="pin-label">目标 / 要求（自然语言，会作为每章的写作要求）</label>
        <textarea v-model="batchGoal" class="modal-input batch-goal" rows="4"
          placeholder="例：接下来重点写血神教与青石镇的正面冲突，节奏加快，每章结尾留强钩子"></textarea>
        <label class="batch-check">
          <input v-model="batchReview" type="checkbox" />
          每章完成后暂停，等我审阅再继续（取消则一口气写完）
        </label>
        <label class="batch-check">
          <input v-model="batchFast" type="checkbox" />
          快速模式（关思考，约1分钟/章；默认精细模式约4-5分钟/章，质量更佳）
        </label>
        <div class="modal-actions">
          <button class="btn" @click="showBatch = false">取消</button>
          <button class="btn btn-primary" :disabled="!batchCount || batchCount < 1" @click="startBatch">
            <Rocket :size="13" :stroke-width="1.75" /> 开始
          </button>
        </div>
      </div>
    </div>
</template>

<style scoped>
.writing-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.writing-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-color);
}
.wh-title {
  font-family: var(--font-serif), serif;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}
.wh-sub {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
}
.wh-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.wh-not-ready {
  font-size: 11px;
  color: var(--text-muted);
}

.writing-body {
  flex: 1;
  display: flex;
  min-height: 0;
}
.chapter-list {
  width: 210px;
  flex-shrink: 0;
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.ch-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.ch-item {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 6px;
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--text-secondary);
  transition: background 0.15s;
  font-family: inherit;
}
.ch-item:hover { background: var(--bg-secondary); }
.ch-item.active { background: var(--accent-lighter); color: var(--text-primary); }
.ch-num {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  white-space: nowrap;
}
.ch-title {
  flex: 1;
  min-width: 60px;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ch-words {
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono), monospace;
}
.ch-status {
  font-size: 9px;
  color: #d97706;
  border: 1px solid #d9770655;
  border-radius: var(--radius-full);
  padding: 0 6px;
}
.ch-empty {
  padding: 16px 12px;
}
.ch-empty-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 10px;
}
.ch-check {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  padding: 5px 0;
}
.ch-check.ok { color: var(--text-primary); }
.ch-check-desc {
  font-size: 10px;
  color: var(--text-muted);
  margin-left: auto;
}
.ch-cta { width: 100%; margin-top: 12px; justify-content: center; }

.chapter-reader {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 20px 28px 40px;
}
.reader-head {
  margin-bottom: 14px;
}
.reader-title {
  font-family: var(--font-serif), serif;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}
.reader-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}
.reader-status {
  padding: 0 8px;
  border-radius: var(--radius-full);
  font-size: 10px;
}
.reader-status.finalized { color: #059669; border: 1px solid #05966944; }
.reader-status.draft { color: #d97706; border: 1px solid #d9770655; }
.reader-status.locked { color: var(--text-tertiary); border: 1px solid var(--border-color); }
.reader-phase {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--accent);
  margin-top: 6px;
}
.dot-pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
  animation: chPulse 1.2s ease-in-out infinite;
}
@keyframes chPulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }
.reader-waiting {
  color: var(--text-muted);
  font-size: 13px;
  padding: 60px 0;
  text-align: center;
}
.reader-content {
  max-width: 720px;
}
.reader-content :deep(p) {
  font-family: var(--font-serif), serif;
  font-size: 14.5px;
  line-height: 2;
  color: var(--text-primary);
  margin: 0 0 14px;
  text-indent: 2em;
}
.writing-cursor {
  display: inline-block;
  width: 2px;
  height: 16px;
  background: var(--accent);
  animation: chPulse 0.8s step-end infinite;
  vertical-align: middle;
}
.plan-card {
  max-width: 720px;
  margin-bottom: 18px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
}
.plan-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
}
.plan-arrow { transition: transform 0.2s; font-size: 10px; }
.plan-arrow.open { transform: rotate(0deg); }
.plan-body {
  padding: 4px 14px 12px;
  max-height: 220px;
  overflow-y: auto;
  border-top: 1px dashed var(--border-subtle);
}
.plan-body :deep(p) {
  font-size: 12px;
  line-height: 1.8;
  color: var(--text-secondary);
  margin: 6px 0;
}
.reader-actions {
  margin-top: 18px;
  display: flex;
  gap: 8px;
}
.review-card {
  max-width: 720px;
  margin-top: 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  background: var(--bg-card);
}
.review-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
}
.review-overall {
  font-size: 12px;
  font-weight: 600;
}
.review-overall.pass, .review-overall.ok { color: #059669; }
.review-overall.warn { color: #d97706; }
.review-overall.error, .review-overall.fail { color: #dc2626; }
.review-summary {
  font-size: 11px;
  color: var(--text-secondary);
}
.review-issues { display: flex; flex-direction: column; gap: 6px; }
.review-issue {
  display: flex;
  gap: 6px;
  font-size: 11px;
  padding: 6px 8px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
}
.ri-desc { color: var(--text-primary); line-height: 1.5; }
.ri-sug { color: var(--text-tertiary); margin-top: 2px; font-style: italic; }
.review-clean { font-size: 12px; color: #059669; }
.reader-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-muted);
  font-size: 12px;
}
.reader-empty-icon { font-size: 32px; opacity: 0.5; }
</style>

<style scoped>
.batch-bar {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 8px 16px 14px;
  border-bottom: 1px dashed var(--border-subtle);
  background: var(--accent-lighter);
}
.batch-text { font-size: 12px; color: var(--text-primary); }
.batch-progress {
  position: absolute;
  left: 16px;
  right: 16px;
  bottom: 6px;
  height: 3px;
  border-radius: var(--radius-full);
  background: var(--border-subtle);
  overflow: hidden;
}
.batch-fill {
  height: 100%;
  background: var(--accent);
  border-radius: var(--radius-full);
  transition: width 0.4s var(--ease-out);
}
.batch-goal { min-height: 90px; resize: vertical; }
.batch-check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  margin: 8px 0 4px;
}
.chapter-edit-area {
  width: 100%;
  min-height: 320px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-family: var(--font-serif), serif;
  font-size: 14px;
  line-height: 2;
  padding: 14px 16px;
  resize: vertical;
  outline: none;
}
.chapter-edit-area:focus { border-color: var(--accent); }
</style>

<style scoped>
.writing-header.standalone { justify-content: flex-end; }
</style>

<style scoped>
.ch-type {
  flex-shrink: 0;
  font-size: 9px;
  color: var(--accent);
  border: 1px solid var(--accent-border);
  background: var(--accent-lighter);
  border-radius: var(--radius-full);
  padding: 0 6px;
  line-height: 16px;
}
</style>

<style scoped>
.live-bar { background: var(--accent-lighter); }
</style>
