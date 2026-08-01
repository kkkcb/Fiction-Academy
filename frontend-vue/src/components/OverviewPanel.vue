<script setup lang="ts">
import { ref, computed } from 'vue'
import { storeToRefs } from 'pinia'
import type { WorkspaceItem, WorkspaceItemType, ID } from '../types'
import { useAppStore } from '../stores/app'
import { POINT_NAV, TYPE_LABELS, STATUS_LABELS, type PointNavEntry } from '../utils/format'

const store = useAppStore()
const { currentProjectId, workspaceItems, chronicle } = storeToRefs(store)

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
}

const chronicleHasData = computed(() => {
  const c = chronicle.value
  if (!c) return false
  return !!(c.timeline?.length || c.characters?.length || c.key_events?.length)
})
</script>

<template>
  <aside class="sidebar-right">
    <div class="overview-header">
      <span>总览</span>
      <button class="btn btn-sm" title="添加设定" aria-label="添加设定" @click="showCreate = true">
        <svg aria-hidden="true" viewBox="0 0 16 16" fill="none" width="12" height="12"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      </button>
    </div>

    <div class="overview-body">
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
            <div class="ov-card-content markdown-body">{{ item.content }}</div>
            <div v-if="metaFields(item).length > 0" class="ov-fields">
              <div v-for="[k, v] in metaFields(item)" :key="k" class="ov-field">
                <span class="ov-field-key">{{ k }}</span>
                <span class="ov-field-val">{{ String(v).slice(0, 60) }}</span>
              </div>
            </div>
            <div class="ov-card-actions">
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
            <div class="ov-card-content markdown-body">{{ item.content }}</div>
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
  white-space: pre-wrap;
  word-break: break-word;
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
</style>
