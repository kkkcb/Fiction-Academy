<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, type ComponentPublicInstance } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import { POINT_NAV } from '../utils/format'
import { toggleTheme as toggleThemeUtil } from '../utils/theme'
import Sidebar from './Sidebar.vue'
import OverviewPanel from './OverviewPanel.vue'
import WritingPanel from './WritingPanel.vue'
import MessageList from './MessageList.vue'
import ChatInput from './ChatInput.vue'
import IconMoon from './icons/IconMoon.vue'
import IconSun from './icons/IconSun.vue'
import { Archive, PanelRight } from 'lucide-vue-next'

const store = useAppStore()
const {
  currentProjectId,
  projects,
  currentPoint,
  activeMode,
  centerView,
  points,
  isArchiving,
  sidebarCollapsed,
} = storeToRefs(store)

const currentProject = computed(() =>
  projects.value.find(p => p.id === currentProjectId.value)
)

const isPointMode = computed(() => activeMode.value === 'point' && !!currentPoint.value)
const pointInfo = computed(() => POINT_NAV.find(p => p.key === currentPoint.value))
const currentPointData = computed(() =>
  points.value.find(p => p.point === currentPoint.value)
)

const leftRef = ref<ComponentPublicInstance | null>(null)
const rightRef = ref<ComponentPublicInstance | null>(null)
const leftWidth = ref<number>(260)
const rightWidth = ref<number>(400)
const draggingSide = ref<'left' | 'right' | null>(null)

// 小屏默认折叠右面板（专注写作）；用户可手动展开
const showRightPanel = ref(true)

const isDark = ref(false)

function toggleTheme() {
  const next = toggleThemeUtil()
  isDark.value = next === 'dark'
}

interface DragState {
  side: 'left' | 'right'
  startX: number
  startWidth: number
  min: number
  max: number
}
let dragState: DragState | null = null

function getPanelEl(side: 'left' | 'right') {
  const r = side === 'left' ? leftRef.value : rightRef.value
  return r?.$el || r
}

function startResize(side: 'left' | 'right', e: MouseEvent) {
  e.preventDefault()
  const el = getPanelEl(side)
  if (!el) return
  dragState = {
    side,
    startX: e.clientX,
    startWidth: el.offsetWidth || (side === 'left' ? leftWidth.value : rightWidth.value),
    min: parseInt(getComputedStyle(el).minWidth) || 180,
    max: parseInt(getComputedStyle(el).maxWidth) || 600,
  }
  draggingSide.value = side
  document.addEventListener('mousemove', onResizing)
  document.addEventListener('mouseup', stopResize)
}

function onResizing(e: MouseEvent) {
  if (!dragState) return
  const dx = e.clientX - dragState.startX
  const raw = dragState.side === 'left' ? dragState.startWidth + dx : dragState.startWidth - dx
  const w = Math.max(dragState.min, Math.min(dragState.max, raw))
  if (dragState.side === 'left') leftWidth.value = w
  else rightWidth.value = w
}

function stopResize() {
  dragState = null
  draggingSide.value = null
  document.removeEventListener('mousemove', onResizing)
  document.removeEventListener('mouseup', stopResize)
}

onMounted(() => {
  isDark.value = document.documentElement.dataset.theme === 'dark'
  if (window.innerWidth < 1180) showRightPanel.value = false
  if (currentProjectId.value && points.value.length === 0) {
    store.navigateTo('workspace', { currentProjectId: currentProjectId.value })
  }
})

function onSidebarShortcut(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === '\\') {
    e.preventDefault()
    store.toggleSidebar()
  }
}
onMounted(() => document.addEventListener('keydown', onSidebarShortcut))
onUnmounted(() => document.removeEventListener('keydown', onSidebarShortcut))

onUnmounted(() => {
  document.removeEventListener('mousemove', onResizing)
  document.removeEventListener('mouseup', stopResize)
})

async function handleArchive() {
  if (!currentProjectId.value || !currentPoint.value) return
  await store.summarizeAndArchive(currentProjectId.value, currentPoint.value)
}
</script>

<template>
  <div class="workspace-page workspace-layout">
    <Sidebar ref="leftRef" :style="{ width: (sidebarCollapsed ? 56 : leftWidth) + 'px' }" />

    <div
      v-if="!sidebarCollapsed"
      class="resize-handle"
      :class="{ active: draggingSide === 'left' }"
      @mousedown="startResize('left', $event)"
    ></div>

    <div class="workspace-center chat-area">
      <WritingPanel v-if="centerView === 'writing'" class="writing-host" />

      <template v-else>
      <div class="chat-header">
        <div class="chat-header-title">
          <span class="chat-header-project">{{ currentProject?.name }}</span>
          <template v-if="isPointMode">
            <span class="chat-header-point-badge">{{ pointInfo?.label }}</span>
            <span class="chat-header-subtitle">{{ pointInfo?.desc }}</span>
          </template>
          <span v-else class="chat-header-subtitle">自由对话</span>
        </div>
        <button
          v-if="isPointMode && currentPointData?.status !== 'done'"
          class="btn btn-archive"
          :class="{ loading: isArchiving }"
          :disabled="isArchiving"
          aria-label="总结并存档"
          @click="handleArchive"
        >
          <Archive :size="14" :stroke-width="1.75" />
          {{ isArchiving ? '存档中...' : '总结并存档' }}
        </button>
        <span v-else-if="isPointMode && currentPointData?.status === 'done'" class="badge-done">已存档</span>
        <button
          class="theme-toggle"
          :class="{ active: !showRightPanel }"
          @click="showRightPanel = !showRightPanel"
          :title="showRightPanel ? '收起设定面板（专注模式）' : '展开设定面板'"
          :aria-label="showRightPanel ? '收起设定面板' : '展开设定面板'"
        >
          <PanelRight :size="16" :stroke-width="1.75" />
        </button>
        <button
          class="theme-toggle"
          @click="toggleTheme"
          :title="isDark ? '切换到浅色' : '切换到深色'"
          :aria-label="isDark ? '切换到浅色' : '切换到深色'"
        >
          <IconMoon v-if="isDark" :size="18" />
          <IconSun v-else :size="18" />
        </button>
      </div>

      <MessageList />

      <ChatInput />
      </template>
    </div>

    <div
      v-if="showRightPanel"
      class="resize-handle"
      :class="{ active: draggingSide === 'right' }"
      @mousedown="startResize('right', $event)"
    ></div>

    <OverviewPanel v-if="showRightPanel" ref="rightRef" :style="{ width: rightWidth + 'px' }" />
  </div>
</template>
