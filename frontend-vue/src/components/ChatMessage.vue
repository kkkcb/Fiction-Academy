<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import type { Message, WorkspaceItemType } from '../types'
import { formatReceiptMd, formatContent, parseCommand, parseConsultRecord, splitMessageWithChoices, formatTime, charCount, pointPersonaName } from '../utils/format'
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
const assistantHtml = computed(() => formatReceiptMd(m.value.content))
const timeText = computed(() => formatTime(m.value.created_at))
const countText = computed(() => charCount(m.value.content))
const showCount = computed(() => !isUser.value && m.value.content.length > 50)

// 可点击选项：按问题分组挂在各自段落下；点选→确认→一次发送（Trae 式两段交互）
const choicesPicked = ref(false)
const selected = ref<Record<number, string>>({}) // qno → 选项 value

const segments = computed(() => {
  if (isUser.value || !props.isLastAssistant || props.isStreaming) return []
  return splitMessageWithChoices(m.value.content)
})
const choiceSegs = computed(() => segments.value.filter(s => s.choices))
const answered = computed(() => Object.keys(selected.value).length)
const showChoices = computed(() => !choicesPicked.value && choiceSegs.value.length > 0)

function toggleChoice(qno: number, value: string) {
  if (selected.value[qno] === value) delete selected.value[qno]
  else selected.value[qno] = value
  // 触发响应式替换
  selected.value = { ...selected.value }
}

function resetChoices() {
  selected.value = {}
}

function confirmChoices() {
  if (!store.currentConversationId || answered.value === 0) return
  const lines = choiceSegs.value
    .filter(s => selected.value[s.qno])
    .map(s => `${s.qno}. ${selected.value[s.qno]}`)
  choicesPicked.value = true
  store.sendMessage(store.currentConversationId, lines.join('\n'))
}

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
      <template v-else>
        <!-- 按段落渲染，有选项的问题段落后面紧跟自己的选项组 -->
        <template v-for="(seg, i) in segments" :key="i">
          <div v-html="formatReceiptMd(seg.md)"></div>
          <div v-if="seg.choices && showChoices" class="msg-choices" role="group" :aria-label="`问题${seg.qno}选项`">
            <span class="choice-qno">{{ seg.qno }}</span>
            <button
              v-for="opt in seg.choices"
              :key="opt.value"
              class="choice-chip"
              :class="{ selected: selected[seg.qno] === opt.value }"
              :title="opt.value"
              @click="toggleChoice(seg.qno, opt.value)"
            >{{ opt.label }}</button>
          </div>
        </template>
        <div v-if="showChoices && choiceSegs.length" class="msg-choices-bar">
          <span class="choices-progress">已选 {{ answered }}/{{ choiceSegs.length }}</span>
          <span class="choices-flex"></span>
          <button v-if="answered" class="btn btn-sm" @click="resetChoices">重置</button>
          <button class="btn btn-sm btn-primary" :disabled="!answered" @click="confirmChoices">
            {{ answered ? `发送所选（${answered}）` : '点上方选项作答' }}
          </button>
        </div>
        <div v-if="!segments.length" v-html="assistantHtml"></div>
      </template>
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

<style scoped>
/* 可点击选项（Trae 式）：点选 → 确认 → 一次发送 */
.msg-choices {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}
.choice-qno {
  flex: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--accent-light);
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.choice-chip {
  padding: 7px 14px;
  border-radius: 999px;
  border: 1px solid var(--accent-border);
  background: var(--accent-lighter);
  color: var(--text-primary);
  font-size: 12.5px;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
  text-align: left;
  max-width: 100%;
}
.choice-chip:hover {
  border-color: var(--accent);
}
.choice-chip.selected {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
  font-weight: 600;
  box-shadow: 0 0 0 3px var(--accent-light);
}
.msg-choices-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-color);
}
.choices-progress { font-size: 12px; color: var(--text-tertiary); }
.choices-flex { flex: 1; }
</style>
