<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import type { ID, Conversation } from '../types'
import { useAppStore } from '../stores/app'
import { POINT_NAV } from '../utils/format'
import IconCheck from './icons/IconCheck.vue'
import IconTrash from './icons/IconTrash.vue'

const store = useAppStore()
const {
  currentProjectId,
  projects,
  conversations,
  currentConversationId,
  points,
  currentPoint,
  activeMode,
  assistants,
  currentAssistantId,
} = storeToRefs(store)

const currentProject = computed(() =>
  projects.value.find(p => p.id === currentProjectId.value)
)

const isPointMode = computed(() => activeMode.value === 'point' && !!currentPoint.value)

const freeConversations = computed(() => conversations.value.filter(c => !c.point))
const legacyPointConversations = computed(() => conversations.value.filter(c => c.point))

function pointStatus(key: string) {
  const data = points.value.find(d => d.point === key)
  return data?.status || 'pending'
}

function pointLabel(key: string | null | undefined) {
  return POINT_NAV.find(p => p.key === key)
}

const editingConvId = ref<ID | null>(null)
const editingTitle = ref<string>('')
const editInputEl = ref<HTMLInputElement | null>(null)

function setEditInput(el: unknown) {
  if (el instanceof HTMLInputElement) editInputEl.value = el
}

async function startRename(conv: Conversation) {
  editingConvId.value = conv.id
  editingTitle.value = conv.title
  await nextTick()
  editInputEl.value?.focus()
  editInputEl.value?.select()
}

async function commitRename() {
  const id = editingConvId.value
  const title = editingTitle.value.trim()
  editingConvId.value = null
  if (id && title) {
    await store.renameConversation(id, title)
  }
}

function cancelRename() {
  editingConvId.value = null
}

async function handleDeleteConv(id: ID) {
  if (confirm('确定删除这个对话？')) {
    await store.deleteConversation(id)
  }
}

async function handleNewConv() {
  if (!currentProjectId.value) return
  await store.createConversation(currentProjectId.value, '新对话')
}

function goBack() {
  console.log('[goBack] clicked, route before:', store.route)
  try {
    store.navigateTo('projects')
    console.log('[goBack] navigateTo called, route after:', store.route)
  } catch (e) {
    console.error('[goBack] navigateTo error:', e)
  }
}

function onSelectAssistant(e: Event) {
  store.selectAssistant((e.target as HTMLSelectElement).value)
}
</script>

<template>
  <aside class="sidebar-left">
    <div class="glass-header">
      <button class="btn btn-sm" title="返回项目列表" aria-label="返回项目列表" @click="goBack">
        <svg aria-hidden="true" viewBox="0 0 16 16" fill="none" width="14" height="14"><path d="M10 3L5 8l5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
      <span class="glass-title">{{ currentProject?.name || '未命名' }}</span>
    </div>

    <div class="point-nav">
      <div class="point-nav-label">创作流程</div>
      <div
        v-for="p in POINT_NAV"
        :key="p.key"
        class="point-nav-item"
        :class="{ active: currentPoint === p.key && isPointMode }"
        @click="store.selectPoint(currentProjectId!, p.key)"
      >
        <span class="point-nav-dot" :class="pointStatus(p.key)">
          <IconCheck v-if="pointStatus(p.key) === 'done'" :size="10" />
          <span v-else-if="pointStatus(p.key) === 'active'" class="point-nav-pulse"></span>
        </span>
        <div class="point-nav-text">
          <span class="point-nav-name">{{ p.label }}</span>
          <span class="point-nav-desc">{{ p.desc }}</span>
        </div>
      </div>
    </div>

    <div class="sidebar-divider"></div>

    <div class="conv-section">
      <div class="conv-header">
        <span>自由对话</span>
        <button class="btn btn-sm" title="新建对话" aria-label="新建对话" @click="handleNewConv">
          <svg aria-hidden="true" viewBox="0 0 16 16" fill="none" width="12" height="12"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
        </button>
      </div>

      <div
        v-for="c in freeConversations"
        :key="c.id"
        class="conv-item"
        :class="{ active: activeMode === 'free' && currentConversationId === c.id }"
        @click="store.selectConversation(c.id)"
      >
        <input
          v-if="editingConvId === c.id"
          :ref="setEditInput"
          v-model="editingTitle"
          class="conv-rename-input"
          @click.stop
          @keydown.enter="commitRename"
          @keydown.esc="cancelRename"
          @blur="commitRename"
        />
        <template v-else>
          <span class="conv-title" @click.stop="startRename(c)" title="点击重命名">{{ c.title }}</span>
          <button class="conv-delete" title="删除" :aria-label="`删除对话${c.title}`" @click.stop="handleDeleteConv(c.id)">
            <IconTrash :size="12" />
          </button>
        </template>
      </div>

      <template v-if="legacyPointConversations.length > 0">
        <div class="conv-header legacy-header">
          <span>点位对话（旧）</span>
        </div>
        <div
          v-for="c in legacyPointConversations"
          :key="c.id"
          class="conv-item"
          :class="{ active: currentConversationId === c.id }"
          @click="store.selectConversation(c.id)"
        >
          <span class="conv-title">{{ pointLabel(c.point)?.label || c.title }}</span>
          <span class="conv-tag">{{ pointLabel(c.point)?.desc || c.point }}</span>
        </div>
      </template>
    </div>

    <div v-if="assistants.length > 0" class="assistant-section">
      <select class="assistant-select" aria-label="选择助理" :value="currentAssistantId" @change="onSelectAssistant">
        <option v-for="a in assistants" :key="a.id" :value="a.id">{{ a.name }}</option>
      </select>
    </div>
  </aside>
</template>

<style scoped>
.conv-rename-input {
  flex: 1;
  min-width: 0;
  background: var(--bg-tertiary);
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  padding: 2px 6px;
  font-family: inherit;
  outline: none;
}
.legacy-header {
  margin-top: 12px;
}
.assistant-section {
  padding: 8px 12px;
  border-top: 1px solid var(--border-color);
  flex-shrink: 0;
}
</style>
