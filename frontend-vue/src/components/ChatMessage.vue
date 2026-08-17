<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import type { Message, WorkspaceItemType } from '../types'
import { formatMd, formatContent, parseCommand, parseConsultRecord, formatTime, charCount, pointPersonaName } from '../utils/format'
import { useAppStore } from '../stores/app'
import { Trash2 } from 'lucide-vue-next'
import ThinkingBlock from './ThinkingBlock.vue'
import ConsultFlow from './ConsultFlow.vue'

const props = withDefaults(defineProps<{ message: Message; index: number; isLastAssistant?: boolean; isStreaming?: boolean }>(), {
  isLastAssistant: false,
  isStreaming: false,
})
const emit = defineEmits<{
  (e: 'regenerate', index: number): void
}>()

const store = useAppStore()

const m = computed(() => props.message)
const cmd = computed(() => m.value.role === 'user' ? parseCommand(m.value.content) : null)
const record = computed(() => m.value.role === 'assistant' ? parseConsultRecord(m.value.content) : null)
const isUser = computed(() => m.value.role === 'user')
const showRegenerate = computed(() => props.isLastAssistant && !props.isStreaming)

// 点位有主导角色时以角色名示人，否则显示 AI
const assistantRole = computed(() =>
  store.activeMode === 'point' ? (pointPersonaName(store.currentPoint) || 'AI') : 'AI'
)

const userHtml = computed(() => formatContent(m.value.content))
const assistantHtml = computed(() => formatMd(m.value.content))
const timeText = computed(() => formatTime(m.value.created_at))
const countText = computed(() => charCount(m.value.content))
const showCount = computed(() => !isUser.value && m.value.content.length > 50)

const copied = ref(false)
let copyTimer: ReturnType<typeof setTimeout> | null = null

async function onCopy() {
  if (!m.value.content) return
  try {
    await navigator.clipboard.writeText(m.value.content)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = m.value.content
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    ta.remove()
  }
  copied.value = true
  if (copyTimer) clearTimeout(copyTimer)
  copyTimer = setTimeout(() => { copied.value = false }, 1500)
}

onUnmounted(() => {
  if (copyTimer) clearTimeout(copyTimer)
})

function onRegenerate() { emit('regenerate', props.index) }

// ===== 右键菜单：删除消息 =====
const ctxMenu = ref<{ x: number; y: number } | null>(null)
const ctxStyle = computed(() => {
  const x = Math.min(ctxMenu.value?.x ?? 0, window.innerWidth - 150)
  const y = Math.min(ctxMenu.value?.y ?? 0, window.innerHeight - 70)
  return { left: x + 'px', top: y + 'px' }
})
function onContextMenu(e: MouseEvent) {
  if (props.isStreaming || !m.value.id) return
  e.preventDefault()
  ctxMenu.value = { x: e.clientX, y: e.clientY }
}
function closeCtx() { ctxMenu.value = null }
async function onDeleteMessage() {
  closeCtx()
  const id = m.value.id
  if (!id) return
  if (!confirm('删除这条消息？删除后不可恢复。')) return
  await store.deleteMessage(id)
}
function onCtxEsc(e: KeyboardEvent) {
  if (e.key === 'Escape' && ctxMenu.value) closeCtx()
}
onMounted(() => {
  window.addEventListener('click', closeCtx)
  window.addEventListener('keydown', onCtxEsc)
})
onUnmounted(() => {
  window.removeEventListener('click', closeCtx)
  window.removeEventListener('keydown', onCtxEsc)
})

const showPinModal = ref(false)
const pinType = ref<WorkspaceItemType>('story_core')
const pinTitle = ref('')
const pinSaving = ref(false)
const pinTypes: { value: WorkspaceItemType; label: string }[] = [
  { value: 'story_core', label: '核心设定' },
  { value: 'world_setting', label: '世界观' },
  { value: 'character_setting', label: '角色设定' },
  { value: 'outline', label: '大纲' },
  { value: 'foreshadow', label: '伏笔' },
]
function onPin() {
  pinTitle.value = ''
  pinType.value = 'story_core'
  showPinModal.value = true
}
function closePin() {
  showPinModal.value = false
}
function onEsc(e: KeyboardEvent) {
  if (e.key === 'Escape' && showPinModal.value) closePin()
}
onMounted(() => window.addEventListener('keydown', onEsc))
onUnmounted(() => window.removeEventListener('keydown', onEsc))
async function doPin() {
  if (!store.currentProjectId) return
  pinSaving.value = true
  try {
    await store.createWorkspaceItem(store.currentProjectId, {
      item_type: pinType.value,
      title: pinTitle.value.trim() || m.value.content.slice(0, 16),
      content: m.value.content,
      status: 'draft',
    })
    showPinModal.value = false
    store.notifySuccess('已沉淀到工作台（草稿）')
  } finally {
    pinSaving.value = false
  }
}
</script>

<template>
  <div v-if="cmd" class="msg user msg-command" :data-cmd="cmd.type" @contextmenu="onContextMenu">
    <div class="command-card">
      <div class="command-header">
        <span class="command-icon">{{ cmd.icon }}</span>
        <span class="command-label">{{ cmd.label }}</span>
      </div>
      <div class="command-body" v-html="formatContent(cmd.idea)"></div>
    </div>
  </div>

  <div v-else-if="record" class="msg assistant msg-consult" @contextmenu="onContextMenu">
    <div class="msg-role">专家圆桌</div>
    <div class="msg-content consult-flow">
      <ConsultFlow :record="record" />
    </div>
    <div v-if="!isStreaming" class="msg-actions">
      <button class="btn btn-sm" title="复制裁决" @click="onCopy">{{ copied ? '已复制' : '复制裁决' }}</button>
    </div>
  </div>

  <div v-else class="msg" :class="m.role" @contextmenu="onContextMenu">
    <div v-if="!isUser" class="msg-role">
      {{ assistantRole }}
      <span v-if="timeText" class="msg-time">{{ timeText }}</span>
    </div>
    <div class="msg-content markdown-body">
      <ThinkingBlock v-if="!isUser && m.thinking" :text="m.thinking" :streaming="false" />
      <div v-if="isUser" v-html="userHtml"></div>
      <div v-else v-html="assistantHtml"></div>
      <span v-if="isUser && timeText" class="msg-time msg-time-user">{{ timeText }}</span>
    </div>
    <div v-if="!isUser" class="msg-actions">
      <span v-if="showCount" class="msg-count">{{ countText }}</span>
      <button class="btn btn-sm" title="复制" aria-label="复制消息" @click="onCopy">{{ copied ? '已复制' : '复制' }}</button>
      <button class="btn btn-sm" title="沉淀到工作台" aria-label="将此回复沉淀到工作台" @click="onPin">沉淀</button>
      <button v-if="showRegenerate" class="btn btn-sm" title="重新生成" aria-label="重新生成回复" @click="onRegenerate">重新生成</button>
    </div>
    <Teleport to="body">
      <div v-if="ctxMenu" class="ctx-menu" :style="ctxStyle" @click.stop>
        <button class="ctx-item ctx-danger" @click="onDeleteMessage">
          <Trash2 :size="13" :stroke-width="1.75" />
          删除消息
        </button>
      </div>
    </Teleport>
    <Teleport to="body">
      <div v-if="showPinModal" class="modal-overlay show" @click.self="closePin">
        <div class="modal-card">
          <h3>沉淀到工作台</h3>
          <label class="pin-label">类型</label>
          <select v-model="pinType" class="modal-input">
            <option v-for="t in pinTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
          <label class="pin-label">标题（可选）</label>
          <input v-model="pinTitle" class="modal-input" placeholder="留空则取内容前16字" @keydown.enter="doPin" />
          <div class="modal-actions">
            <button class="btn" :disabled="pinSaving" @click="closePin">取消</button>
            <button class="btn btn-primary" :disabled="pinSaving" @click="doPin">{{ pinSaving ? '保存中…' : '沉淀' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
