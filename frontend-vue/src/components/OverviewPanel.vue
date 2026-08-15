<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import type { WorkspaceItem, WorkspaceItemType, ID } from '../types'
import { useAppStore } from '../stores/app'
import { POINT_NAV, TYPE_LABELS, STATUS_LABELS, formatMd, charCount, propertyLabel, type PointNavEntry } from '../utils/format'
import { Plus } from 'lucide-vue-next'
import KgGraphPanel from './KgGraphPanel.vue'
import GoalPanel from './GoalPanel.vue'

const store = useAppStore()
const { currentProjectId, currentProject, workspaceItems, chronicle, goalState, lintResult, lintLoading } = storeToRefs(store)

const viewMode = ref<'overview' | 'graph' | 'goal'>('overview')

watch(goalState, (g) => {
  if (g && g.status !== 'cancelled') viewMode.value = 'goal'
})

const archivedPoints = computed(() =>
  POINT_NAV.map(nav => {
    const item = workspaceItems.value.find(
      w => w.item_type === nav.key && (w.status === 'finalized' || w.status === 'locked')
    )
    return { nav, item }
  }).filter((x): x is { nav: PointNavEntry; item: WorkspaceItem } => !!x.item)
)

const otherItems = computed(() =>
  workspaceItems.value.filter(w => !POINT_NAV.some(p => p.key === w.item_type))
)

const hasContent = computed(() => archivedPoints.value.length > 0 || otherItems.value.length > 0)

function safeParseMeta(str: string | null | undefined): Record<string, unknown> | null {
  if (!str) return null
  try { return typeof str === 'string' ? JSON.parse(str) as Record<string, unknown> : null } catch { return null }
}

function metaFields(item: WorkspaceItem): [string, unknown][] {
  const meta = safeParseMeta(item.metadata)
  if (!meta) return []
  return Object.entries(meta).filter(([, v]) => v).slice(0, 4)
}

function shortVal(v: unknown): string {
  const s = String(v)
  return s.length > 80 ? s.slice(0, 80) + '…' : s
}

/** 正文分层：自带换行/标题/列表的按原结构分段；纯文本长段落按句读拆条（收尾引号/括号跟随前句） */
function contentSegments(text: string | null | undefined): string[] {
  const t = (text || '').trim()
  if (!t) return []
  if (/\n/.test(t)) return t.split(/\n{2,}/).map(s => s.trim()).filter(Boolean)
  return t.split(/(?<=[。！？；])(?!["”』」）)］】])|(?<=[。！？；]["”』」）)］】])/).map(s => s.trim()).filter(Boolean)
}

const editingId = ref<ID | null>(null)
const editingContent = ref<string>('')

function startEdit(item: WorkspaceItem) {
  editingId.value = item.id
  editingContent.value = item.content || ''
}

function cancelEdit() {
  editingId.value = null
  editingContent.value = ''
}

async function saveEdit(item: WorkspaceItem) {
  await store.updateWorkspaceItem(item.id, { content: editingContent.value })
  editingId.value = null
  editingContent.value = ''
}

async function approve(item: WorkspaceItem) {
  await store.updateItemStatus(item.id, 'finalized', currentProjectId.value!)
}

async function lock(item: WorkspaceItem) {
  await store.updateItemStatus(item.id, 'locked', currentProjectId.value!)
}

async function remove(item: WorkspaceItem) {
  if (confirm('确定删除这条设定？')) {
    await store.deleteWorkspaceItem(item.id, currentProjectId.value!)
  }
}

const showCreate = ref<boolean>(false)
const newItemType = ref<string>('setting')
const newItemTitle = ref<string>('')

async function handleCreate() {
  if (!newItemTitle.value.trim()) return
  await store.createWorkspaceItem(currentProjectId.value!, {
    item_type: newItemType.value as WorkspaceItemType,
    title: newItemTitle.value.trim(),
    content: '',
    status: 'draft',
  })
  newItemTitle.value = ''
  showCreate.value = false
  store.notifySuccess('设定已创建（草稿）')
}

function onEsc(e: KeyboardEvent) {
  if (e.key === 'Escape' && showCreate.value) showCreate.value = false
}
onMounted(() => window.addEventListener('keydown', onEsc))
onUnmounted(() => window.removeEventListener('keydown', onEsc))

const chronicleHasData = computed(() => {
  const c = chronicle.value
  if (!c) return false
  return !!(c.timeline?.length || c.characters?.length || c.key_events?.length)
})

const projectRules = computed(() => currentProject.value?.rules_text ?? '')
const hasRules = computed(() => projectRules.value.trim().length > 0)

const editingRules = ref<boolean>(false)
const rulesText = ref<string>('')
const savingRules = ref<boolean>(false)

watch(currentProject, (p) => {
  editingRules.value = false
  rulesText.value = p?.rules_text ?? ''
}, { immediate: true })

function startEditRules() {
  rulesText.value = projectRules.value
  editingRules.value = true
}

function cancelEditRules() {
  editingRules.value = false
  rulesText.value = projectRules.value
}

async function saveRules() {
  savingRules.value = true
  try {
    await store.updateProjectRules(rulesText.value)
    editingRules.value = false
  } finally {
    savingRules.value = false
  }
}

function runConsistencyLint() {
  if (!currentProjectId.value) return
  store.runLint(currentProjectId.value)
}

const LINT_ICON: Record<string, string> = { error: '🔴', warning: '🟡', info: '🔵' }
const lintScore = computed(() => {
  const s = lintResult.value?.consistency_score ?? 0
  return Math.round(s * 100)
})
</script>

<template>
  <aside class="sidebar-right">
    <div class="overview-header">
      <div class="overview-tabs">
        <button class="ov-tab" :class="{ active: viewMode === 'overview' }" @click="viewMode = 'overview'">总览</button>
        <button class="ov-tab" :class="{ active: viewMode === 'graph' }" @click="viewMode = 'graph'">知识图谱</button>
        <button class="ov-tab" :class="{ active: viewMode === 'goal' }" @click="viewMode = 'goal'">
          目标<span v-if="goalState" class="goal-tab-dot"></span>
        </button>
      </div>
      <button v-if="viewMode === 'overview'" class="btn btn-sm" title="添加设定" aria-label="添加设定" @click="showCreate = true">
        <Plus :size="12" :stroke-width="2" />
      </button>
    </div>

    <KgGraphPanel v-if="viewMode === 'graph'" class="overview-graph-host" />

    <GoalPanel v-else-if="viewMode === 'goal'" class="overview-graph-host" />

    <div v-else class="overview-body">
      <div class="rules-card">
        <div class="rules-card-header">
          <span class="rules-card-title">创作守则</span>
          <span class="rules-priority-badge">最高优先级</span>
        </div>

        <template v-if="editingRules">
          <div class="rules-hint">本项目的红线、风格、偏好。AI 在任何创作中都会严格遵守，不得违反。</div>
          <textarea
            v-model="rulesText"
            class="rules-textarea"
            rows="8"
            placeholder="例如：&#10;- 禁止出现真实地名、人名&#10;- 保持克制冷静的叙事语调&#10;- 每章 3000 字左右&#10;- 对话占比不低于 40%"
            :disabled="savingRules"
          ></textarea>
          <div class="rules-actions">
            <button class="btn btn-sm" :disabled="savingRules" @click="cancelEditRules">取消</button>
            <button class="btn btn-sm btn-primary" :disabled="savingRules" @click="saveRules">
              {{ savingRules ? '保存中…' : '保存' }}
            </button>
          </div>
        </template>

        <template v-else-if="hasRules">
          <div class="rules-view markdown-body" v-html="formatMd(projectRules)"></div>
          <div class="rules-actions">
            <button class="btn-link" aria-label="编辑创作守则" @click="startEditRules">编辑</button>
          </div>
        </template>

        <template v-else>
          <div class="rules-empty">尚未设置创作守则</div>
          <div class="rules-actions">
            <button class="btn-link" @click="startEditRules">+ 添加守则</button>
          </div>
        </template>
      </div>

      <div class="lint-card">
        <div class="lint-card-header">
          <span class="lint-card-title">一致性检测</span>
          <button class="btn btn-sm" :disabled="lintLoading" @click="runConsistencyLint">
            {{ lintLoading ? '检测中…' : lintResult ? '重新检测' : '开始检测' }}
          </button>
        </div>
        <template v-if="lintResult">
          <div class="lint-rate-bar">
            <div class="lint-rate-fill" :style="{ width: lintScore + '%', background: lintScore >= 70 ? '#059669' : lintScore >= 40 ? '#d97706' : '#dc2626' }"></div>
            <span class="lint-rate-text">一致性 {{ lintScore }}%</span>
          </div>
          <div class="lint-summary">{{ lintResult.summary }}</div>
          <div v-if="lintResult.issues.length" class="lint-issues">
            <div v-for="(issue, i) in lintResult.issues" :key="i" class="lint-issue" :class="issue.severity">
              <span class="lint-issue-icon">{{ LINT_ICON[issue.severity] || '❓' }}</span>
              <div class="lint-issue-body">
                <div class="lint-issue-desc">{{ issue.description }}</div>
                <div class="lint-issue-meta">
                  <span class="lint-issue-cat">{{ issue.category }}</span>
                  <span v-if="issue.location" class="lint-issue-loc">📍 {{ issue.location }}</span>
                </div>
                <div v-if="issue.suggestion" class="lint-issue-sug">{{ issue.suggestion }}</div>
              </div>
            </div>
          </div>
          <div v-else class="lint-no-issues">✅ 未发现一致性问题</div>
        </template>
        <div v-else-if="!lintLoading" class="lint-hint">扫描工作台和知识图谱，自动检测矛盾、冲突和缺漏</div>
      </div>

      <div v-if="archivedPoints.length >= POINT_NAV.length" class="write-cta-card">
        <div class="write-cta-text">
          <div class="write-cta-title">骨架已就绪 ✨</div>
          <div class="write-cta-sub">五个点位全部定稿，可以开始正文创作了</div>
        </div>
        <button class="btn btn-primary" aria-label="进入小说写作" @click="store.openWriting()">✍️ 去写作</button>
      </div>

      <div v-if="archivedPoints.length > 0" class="overview-section">
        <div
          v-for="{ nav, item } in archivedPoints"
          :key="item.id"
          class="ov-card"
          :class="{ locked: item.status === 'locked' }"
        >
          <div class="ov-card-header">
            <span class="ov-card-title">{{ nav.label }}</span>
            <span class="ov-card-status" :class="item.status">{{ STATUS_LABELS[item.status] || item.status }}</span>
          </div>

          <template v-if="editingId === item.id">
            <textarea v-model="editingContent" class="ov-edit-area" rows="6"></textarea>
            <div class="ov-card-actions">
              <button class="btn-link" @click="saveEdit(item)">保存</button>
              <button class="btn-link" @click="cancelEdit">取消</button>
            </div>
          </template>
          <template v-else>
            <div class="ov-card-content">
              <div
                v-for="(seg, i) in contentSegments(item.content)"
                :key="i"
                class="ov-seg markdown-body"
                v-html="formatMd(seg, { cache: false })"
              ></div>
            </div>
            <div v-if="metaFields(item).length > 0" class="ov-fields">
              <div v-for="[k, v] in metaFields(item)" :key="k" class="ov-field">
                <span class="ov-field-key">{{ propertyLabel(k) }}</span>
                <span class="ov-field-val">{{ shortVal(v) }}</span>
              </div>
            </div>
            <div class="ov-card-actions">
              <span class="ov-card-count">{{ charCount(item.content) }}</span>
              <button v-if="item.status !== 'locked'" class="btn-link" :aria-label="`编辑${item.title}`" @click="startEdit(item)">编辑</button>
              <button v-if="item.status === 'draft'" class="btn-link" :aria-label="`审批${item.title}`" @click="approve(item)">通过</button>
              <button v-if="item.status !== 'locked'" class="btn-link" :aria-label="`锁定${item.title}`" @click="lock(item)">锁定</button>
              <button v-if="item.status !== 'locked'" class="btn-link danger" :aria-label="`删除${item.title}`" @click="remove(item)">删除</button>
            </div>
          </template>
        </div>
      </div>

      <div v-if="otherItems.length > 0" class="overview-section">
        <div class="overview-section-label">其他设定</div>
        <div v-for="item in otherItems" :key="item.id" class="ov-card-simple">
          <div class="ov-card-header">
            <span class="ov-type-badge">{{ TYPE_LABELS[item.item_type] || item.item_type }}</span>
            <span class="ov-card-status" :class="item.status">{{ STATUS_LABELS[item.status] || '' }}</span>
          </div>
          <div class="ov-card-title">{{ item.title || '无标题' }}</div>
          <template v-if="editingId === item.id">
            <textarea v-model="editingContent" class="ov-edit-area" rows="4"></textarea>
            <div class="ov-card-actions">
              <button class="btn-link" @click="saveEdit(item)">保存</button>
              <button class="btn-link" @click="cancelEdit">取消</button>
            </div>
          </template>
          <template v-else>
            <div class="ov-card-content markdown-body" v-html="formatMd(item.content)"></div>
            <div class="ov-card-actions">
              <button v-if="item.status !== 'locked'" class="btn-link" :aria-label="`编辑${item.title}`" @click="startEdit(item)">编辑</button>
              <button v-if="item.status !== 'locked'" class="btn-link" :aria-label="`锁定${item.title}`" @click="lock(item)">锁定</button>
              <button v-if="item.status !== 'locked'" class="btn-link danger" :aria-label="`删除${item.title}`" @click="remove(item)">删除</button>
            </div>
          </template>
        </div>
      </div>

      <div v-if="!hasContent" class="empty-state overview-empty">
        <div class="empty-text">还没有存档的设定</div>
        <div class="empty-hint">完成点位对话后点击「总结并存档」</div>
      </div>

      <div v-if="chronicle && chronicleHasData" class="overview-section chronicle">
        <div class="overview-section-label">编年录</div>
        <div v-if="chronicle.timeline?.length" class="chron-section">
          <div v-for="(t, i) in chronicle.timeline" :key="'t' + i" class="chron-item">
            <span class="chron-time">{{ t.time }}</span>
            <span class="chron-event">{{ t.event }}</span>
          </div>
        </div>
        <div v-if="chronicle.characters?.length" class="chron-section">
          <div v-for="(c, i) in chronicle.characters" :key="'c' + i" class="chron-item">
            <span class="chron-char">{{ c }}</span>
          </div>
        </div>
        <div v-if="chronicle.key_events?.length" class="chron-section">
          <div v-for="(e, i) in chronicle.key_events" :key="'e' + i" class="chron-item">
            <span class="chron-event">{{ e }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal-card">
        <h3>添加设定</h3>
        <select v-model="newItemType" class="modal-input">
          <option v-for="(label, key) in TYPE_LABELS" :key="key" :value="key">{{ label }}</option>
        </select>
        <input v-model="newItemTitle" class="modal-input" placeholder="设定标题" @keydown.enter="handleCreate" />
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="handleCreate">创建</button>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.ov-card-content {
  word-break: break-word;
  font-size: 12px;
  line-height: 1.7;
}
.write-cta-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 16px;
  padding: 12px 14px;
  border: 1px solid var(--accent-border);
  border-radius: var(--radius-md);
  background: var(--accent-lighter);
}
.write-cta-title {
  font-family: var(--font-serif), serif;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}
.write-cta-sub {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
}
.ov-seg {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.8;
  padding-left: 10px;
  border-left: 2px solid var(--border-subtle);
}
.ov-seg :deep(p) {
  margin: 0;
}
.ov-seg + .ov-seg {
  margin-top: 6px;
}
.ov-seg:first-child {
  color: var(--text-primary);
  border-left-color: var(--accent);
}
.ov-card-count {
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono), monospace;
  margin-right: auto;
}
.ov-edit-area {
  width: 100%;
  min-height: 80px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.5;
  padding: 6px 8px;
  resize: vertical;
  margin-bottom: 6px;
  font-family: inherit;
  outline: none;
}
.ov-edit-area:focus {
  border-color: var(--accent);
}
.overview-empty {
  padding: 40px 16px;
}

.rules-card {
  margin-bottom: 16px;
  padding: 12px 14px;
  border: 1px solid var(--accent-border);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius-md);
  background: var(--accent-lighter);
}
.rules-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.rules-card-title {
  font-family: var(--font-serif), serif;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.02em;
}
.rules-priority-badge {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  color: #fff;
  background: var(--accent);
  white-space: nowrap;
}
.rules-hint {
  font-size: 11px;
  line-height: 1.6;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.rules-view {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-primary);
  max-height: 240px;
  overflow-y: auto;
  padding: 2px 0 4px;
}
.rules-empty {
  font-size: 12px;
  color: var(--text-secondary);
  padding: 4px 0;
  font-style: italic;
}
.rules-textarea {
  width: 100%;
  min-height: 160px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.7;
  padding: 8px 10px;
  resize: vertical;
  margin-bottom: 8px;
  font-family: var(--font-serif), serif;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.rules-textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-lighter);
}
.rules-textarea::placeholder {
  color: var(--text-muted, #999);
  font-style: italic;
}
.rules-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.overview-tabs { display: flex; gap: 2px; }
.ov-tab {
  font-size: 12px; padding: 4px 12px; border: none; background: transparent;
  color: var(--text-secondary); cursor: pointer; border-radius: var(--radius-sm);
  font-family: var(--font-serif), serif; transition: all 0.15s;
}
.ov-tab:hover { background: var(--bg-secondary); color: var(--text-primary); }
.ov-tab.active { color: var(--accent); background: var(--accent-lighter); font-weight: 600; }
.goal-tab-dot {
  display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent); margin-left: 4px; vertical-align: middle;
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.overview-graph-host {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  padding: 0 12px 12px; min-height: 0;
}

.lint-card {
  margin-bottom: 16px; padding: 12px 14px;
  border: 1px solid var(--border-color); border-radius: var(--radius-md);
  background: var(--bg-card);
}
.lint-card-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;
}
.lint-card-title {
  font-family: var(--font-serif), serif; font-size: 13px; font-weight: 600;
  color: var(--text-primary); letter-spacing: 0.02em;
}
.lint-rate-bar {
  position: relative; height: 18px; background: var(--bg-secondary);
  border-radius: var(--radius-full); overflow: hidden; margin-bottom: 8px;
}
.lint-rate-fill { height: 100%; border-radius: var(--radius-full); transition: width 0.5s var(--ease-out); }
.lint-rate-text {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  font-size: 10px; font-weight: 600; color: var(--text-primary); font-family: var(--font-mono), monospace;
  white-space: nowrap;
}
.lint-summary { font-size: 11px; color: var(--text-secondary); margin-bottom: 6px; line-height: 1.5; }
.lint-issues { display: flex; flex-direction: column; gap: 4px; max-height: 300px; overflow-y: auto; }
.lint-issue {
  display: flex; gap: 6px; padding: 6px 8px; border-radius: var(--radius-sm);
  background: var(--bg-secondary); border-left: 3px solid var(--border-color);
}
.lint-issue.error { border-left-color: #dc2626; }
.lint-issue.warning { border-left-color: #d97706; }
.lint-issue.info { border-left-color: #0891b2; }
.lint-issue-icon { flex-shrink: 0; font-size: 11px; }
.lint-issue-body { flex: 1; min-width: 0; }
.lint-issue-desc { font-size: 11px; color: var(--text-primary); line-height: 1.5; }
.lint-issue-meta { display: flex; gap: 8px; margin-top: 2px; flex-wrap: wrap; }
.lint-issue-cat { font-size: 9px; color: var(--accent); font-weight: 500; }
.lint-issue-loc { font-size: 9px; color: var(--text-muted); }
.lint-issue-sug { font-size: 10px; color: var(--text-secondary); margin-top: 3px; font-style: italic; }
.lint-no-issues { font-size: 12px; color: #059669; padding: 4px 0; }
.lint-hint { font-size: 11px; color: var(--text-muted); padding: 4px 0; line-height: 1.5; }
</style>
