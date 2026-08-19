<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import type { ID, Conversation } from '../types'
import { useAppStore } from '../stores/app'
import { POINT_NAV, relativeTime } from '../utils/format'
import IconCheck from './icons/IconCheck.vue'
import IconTrash from './icons/IconTrash.vue'
import { ChevronLeft, Plus, BrainCircuit, PanelLeftClose, PanelLeftOpen, MessageSquareText, ChevronDown } from 'lucide-vue-next'

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
  centerView,
  chapters,
  sidebarCollapsed,
} = storeToRefs(store)

const currentProject = computed(() =>
  projects.value.find(p => p.id === currentProjectId.value)
)

const isPointMode = computed(() => activeMode.value === 'point' && !!currentPoint.value)

// 分区折叠（创作流程 / 自由对话）
const sectionCollapsed = ref({ points: false, convs: false })

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
  try {
    store.navigateTo('projects')
  } catch (e) {
    console.error('[goBack] navigateTo error:', e)
  }
}

function onSelectAssistant(e: Event) {
  store.selectAssistant((e.target as HTMLSelectElement).value)
}
</script>

<template>
  <aside class="sidebar-left" :class="{ collapsed: sidebarCollapsed }">

    <!-- 折叠态：图标栏（悬浮显示提示） -->
    <div v-if="sidebarCollapsed" class="sidebar-rail">
      <button class="rail-btn" data-tip="返回项目列表" aria-label="返回项目列表" @click="goBack">
        <ChevronLeft :size="16" :stroke-width="1.75" />
      </button>
      <div class="rail-avatar" data-tip="展开侧栏">{{ (currentProject?.name || '未').slice(0, 1) }}</div>
      <div class="rail-sep"></div>
      <button
        v-for="p in POINT_NAV"
        :key="p.key"
        class="rail-btn rail-dot"
        :class="[pointStatus(p.key), { active: currentPoint === p.key && isPointMode }]"
        :data-tip="`${p.label} · ${pointStatus(p.key) === 'done' ? '已完成' : pointStatus(p.key) === 'active' ? '进行中' : '未开始'}`"
        :aria-label="p.label"
        @click="store.selectPoint(currentProjectId!, p.key)"
      >
        <IconCheck v-if="pointStatus(p.key) === 'done'" :size="14" :stroke-width="2" />
        <span v-else class="rail-dot-empty"></span>
      </button>
      <button class="rail-btn" :class="{ active: centerView === 'writing' }" data-tip="小说写作" aria-label="进入小说写作" @click="store.openWriting()">
        <BrainCircuit :size="16" :stroke-width="1.75" />
      </button>
      <div class="rail-sep"></div>
      <button class="rail-btn" data-tip="自由对话（展开侧栏查看）" aria-label="展开侧栏查看对话" @click="store.toggleSidebar()">
        <MessageSquareText :size="16" :stroke-width="1.75" />
      </button>
      <button class="rail-btn rail-expand" data-tip="展开侧栏（Ctrl+\）" aria-label="展开侧栏" @click="store.toggleSidebar()">
        <PanelLeftOpen :size="16" :stroke-width="1.75" />
      </button>
    </div>

    <template v-else>
    <div class="glass-header">
      <button class="btn btn-sm" title="返回项目列表" aria-label="返回项目列表" @click="goBack">
        <ChevronLeft :size="14" :stroke-width="1.75" />
      </button>
      <span class="glass-title">{{ currentProject?.name || '未命名' }}</span>
      <button class="btn btn-sm sidebar-collapse-btn" title="收起侧栏（Ctrl+\）" aria-label="收起侧栏" @click="store.toggleSidebar()">
        <PanelLeftClose :size="14" :stroke-width="1.75" />
      </button>
    </div>

    <div class="point-nav">
      <div class="point-nav-label section-head" @click="sectionCollapsed.points = !sectionCollapsed.points">
        <ChevronDown :size="12" :stroke-width="1.75" class="section-arrow" :class="{ folded: sectionCollapsed.points }" />
        创作流程
      </div>
      <div
        v-for="p in POINT_NAV"
        v-show="!sectionCollapsed.points"
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

      <button
        v-show="!sectionCollapsed.points"
        class="write-nav-item"
        :class="{ active: centerView === 'writing' }"
        aria-label="进入小说写作"
        @click="store.openWriting()"
      >
        <BrainCircuit class="write-nav-icon" :size="16" :stroke-width="1.75" />
        <div class="point-nav-text">
          <span class="point-nav-name">小说写作</span>
          <span class="point-nav-desc">{{ chapters.length ? `已写 ${chapters.length} 章` : '骨架就绪后开写' }}</span>
        </div>
      </button>
    </div>

    <div class="sidebar-divider"></div>

    <div class="conv-section">
      <div class="conv-header section-head" @click.self="sectionCollapsed.convs = !sectionCollapsed.convs">
        <span class="section-head-inner" @click="sectionCollapsed.convs = !sectionCollapsed.convs">
          <ChevronDown :size="12" :stroke-width="1.75" class="section-arrow" :class="{ folded: sectionCollapsed.convs }" />
          自由对话
        </span>
        <button class="btn btn-sm" title="新建对话" aria-label="新建对话" @click="handleNewConv">
          <Plus :size="12" :stroke-width="2" />
        </button>
      </div>

      <div
        v-for="c in freeConversations"
        v-show="!sectionCollapsed.convs"
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
          <div class="conv-main">
            <span class="conv-title" @click.stop="startRename(c)" title="点击重命名">{{ c.title }}</span>
            <span v-if="c.updated_at" class="conv-time">{{ relativeTime(c.updated_at) }}</span>
          </div>
          <button class="conv-delete" title="删除" :aria-label="`删除对话${c.title}`" @click.stop="handleDeleteConv(c.id)">
            <IconTrash :size="12" />
          </button>
        </template>
      </div>

      <div v-if="freeConversations.length === 0 && !sectionCollapsed.convs" class="conv-empty">
        暂无自由对话<br />点击右上角 + 随时开聊
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
        <option value="">默认 · 跟随点位</option>
        <option v-for="a in assistants" :key="a.id" :value="a.id">{{ a.name }}</option>
      </select>
    </div>
      </template>
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
.conv-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.conv-time {
  font-size: 10px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conv-empty {
  padding: 10px 14px;
  font-size: 11px;
  line-height: 1.7;
  color: var(--text-muted);
  text-align: center;
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
