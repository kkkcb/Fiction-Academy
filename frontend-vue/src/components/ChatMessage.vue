<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import type { Message, MessageRequestPayload } from '../types'
import * as api from '../api'
import { formatReceiptMd, formatContent, parseCommand, parseConsultRecord, parseDistillReview, splitMessageWithChoices, formatTime, charCount, pointPersonaName } from '../utils/format'
import { useAppStore } from '../stores/app'
import { Trash2 } from 'lucide-vue-next'
import ThinkingBlock from './ThinkingBlock.vue'
import ConsultFlow from './ConsultFlow.vue'
import DistillReviewCard from './DistillReviewCard.vue'

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
const review = computed(() => m.value.role === 'assistant' ? parseDistillReview(m.value.content) : null)
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

// 可点击选项：按问题分组挂在各自段落下；点选/填写→确认→一次发送（Trae 式两段交互）
const choicesPicked = ref(false)
const selected = ref<Record<number, string>>({}) // qno → 选项 value
const openDrafts = ref<Record<number, string>>({}) // qno → 开放问题的输入草稿

const segments = computed(() => {
  if (isUser.value || !props.isLastAssistant || props.isStreaming) return []
  return splitMessageWithChoices(m.value.content)
})
const answerableSegs = computed(() => segments.value.filter(s => s.choices || s.open))
const answered = computed(() =>
  answerableSegs.value.filter(s => selected.value[s.qno] || (openDrafts.value[s.qno] || '').trim()).length,
)
const showChoices = computed(() => !choicesPicked.value && answerableSegs.value.length > 0)

function toggleChoice(qno: number, value: string) {
  if (selected.value[qno] === value) delete selected.value[qno]
  else selected.value[qno] = value
  // 触发响应式替换
  selected.value = { ...selected.value }
}

function resetChoices() {
  selected.value = {}
  openDrafts.value = {}
}

function confirmChoices() {
  if (!store.currentConversationId || answered.value === 0) return
  // 不带问题序号：序号是 UI 内部对位用的，发给模型反而容易和它自己的行文编号对不上；
  // 选项原文本身（含 A./是X还是Y 的措辞）已足够模型分辨对应哪个问题
  const lines = answerableSegs.value
    .filter(s => selected.value[s.qno] || (openDrafts.value[s.qno] || '').trim())
    .map(s => (openDrafts.value[s.qno] || '').trim() || selected.value[s.qno])
  choicesPicked.value = true
  store.sendMessage(store.currentConversationId, lines.join('\n'))
}

const copied = ref(false)
let copyTimer: ReturnType<typeof setTimeout> | null = null

// 双击 AI 回复：查看本次请求发给模型的完整输入（系统提示词含上下文 + 消息列表）
const showRequestModal = ref(false)
const requestPayload = ref<MessageRequestPayload | null>(null)

function showRequest() {
  if (isUser.value || props.isStreaming) return
  if (!m.value.request_json) {
    requestPayload.value = null
  } else {
    try {
      requestPayload.value = JSON.parse(m.value.request_json) as MessageRequestPayload
    } catch {
      requestPayload.value = null
    }
  }
  showRequestModal.value = true
}

function closeRequest() {
  showRequestModal.value = false
}

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

// 沉淀走全局面板（store.startPinRedistill）：思考流/结果/确认都在面板里，关面板不打断
function onPin() {
  store.startPinRedistill(m.value.content)
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

  <div v-else-if="review" class="msg assistant msg-consult" @contextmenu="onContextMenu">
    <div class="msg-role">设定分拣</div>
    <div class="msg-content consult-flow">
      <DistillReviewCard :record="review" :project-id="store.currentProjectId!" />
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

  <div v-else class="msg" :class="m.role" @contextmenu="onContextMenu"
    :title="isUser ? undefined : '双击查看本次请求的输入'"
    @dblclick="showRequest">
    <div v-if="!isUser" class="msg-role">
      {{ assistantRole }}
      <span v-if="timeText" class="msg-time">{{ timeText }}</span>
    </div>
    <div class="msg-content markdown-body">
      <ThinkingBlock v-if="!isUser && m.thinking" :text="m.thinking" :streaming="false" />
      <div v-if="isUser" v-html="userHtml"></div>
      <template v-else>
        <!-- 按段落渲染：前文 → 选项行/输入框 → 后文（选项文本不再在正文里重复） -->
        <template v-for="(seg, i) in segments" :key="i">
          <div v-if="seg.pre.trim()" v-html="formatReceiptMd(seg.pre)"></div>
          <div v-if="seg.choices && seg.choices.length && showChoices" class="msg-choices" role="group" :aria-label="`问题${seg.qno}选项`">
            <button
              v-for="(opt, oi) in seg.choices"
              :key="oi"
              class="choice-row"
              :class="{ selected: selected[seg.qno] === opt.value }"
              @click="toggleChoice(seg.qno, opt.value)"
            >
              <span class="choice-radio" aria-hidden="true"></span>
              <span class="choice-text">{{ opt.value }}</span>
            </button>
          </div>
          <!-- 每个问题都可以不选选项、直接输入自定义答案 -->
          <div v-if="(seg.choices || seg.open) && showChoices" class="msg-open-answer">
            <input
              class="open-input"
              :value="openDrafts[seg.qno] || ''"
              :placeholder="seg.choices ? '其他（不选上面的，直接输入你的答案）' : '直接回答这个问题（回车即连同其他所选一起发送）'"
              @input="openDrafts = { ...openDrafts, [seg.qno]: ($event.target as HTMLInputElement).value }"
              @keydown.enter="confirmChoices"
            />
          </div>
          <div v-if="seg.post.trim()" v-html="formatReceiptMd(seg.post)"></div>
        </template>
        <div v-if="showChoices && answerableSegs.length" class="msg-choices-bar">
          <span class="choices-progress">已答 {{ answered }}/{{ answerableSegs.length }}</span>
          <span class="choices-flex"></span>
          <button v-if="answered" class="btn btn-sm" @click="resetChoices">重置</button>
          <button class="btn btn-sm btn-primary" :disabled="!answered" @click="confirmChoices">
            {{ answered ? `发送所选（${answered}）` : '点选项或在输入框作答' }}
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
      <div v-if="showRequestModal" class="modal-overlay show" @click.self="closeRequest">
        <div class="modal-card request-modal">
          <h3>本次请求的输入</h3>
          <template v-if="requestPayload">
            <div class="req-meta">
              <span class="req-chip">模型：{{ requestPayload.model || '默认' }}</span>
              <span class="req-chip">消息 {{ requestPayload.messages.length }} 条</span>
              <span class="req-chip">系统提示词 {{ requestPayload.system_prompt.length }} 字</span>
            </div>
            <details open class="req-section">
              <summary>系统提示词（含人格与上下文）</summary>
              <pre class="req-pre">{{ requestPayload.system_prompt }}</pre>
            </details>
            <details class="req-section">
              <summary>消息列表</summary>
              <div v-for="(msg, i) in requestPayload.messages" :key="i" class="req-msg">
                <span class="req-role" :class="msg.role">{{ msg.role === 'user' ? '用户' : 'AI' }}</span>
                <pre class="req-pre">{{ msg.content }}</pre>
              </div>
            </details>
          </template>
          <p v-else class="pin-hint">这条消息没有留存请求输入（旧版本数据，或非对话生成的消息）。</p>
          <div class="modal-actions">
            <button class="btn btn-primary" @click="closeRequest">关闭</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.pin-hint {
  margin-bottom: 10px;
  color: var(--text-tertiary);
  font-weight: 400;
  line-height: 1.6;
}

/* 请求输入查看弹窗 */
.request-modal { max-width: min(760px, 92vw); max-height: 86vh; overflow-y: auto; }
.req-meta { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.req-chip {
  font-size: 11.5px; color: var(--text-secondary);
  background: var(--bg-secondary); border: 1px solid var(--border-color);
  border-radius: var(--radius-full); padding: 2px 10px;
}
.req-section { margin-bottom: 10px; }
.req-section summary {
  font-size: 12.5px; font-weight: 600; color: var(--text-primary);
  cursor: pointer; user-select: none; margin-bottom: 6px;
}
.req-pre {
  margin: 0; padding: 10px 12px; border-radius: 8px;
  background: var(--bg-secondary); border: 1px solid var(--border-color);
  font-family: var(--font-mono, monospace); font-size: 11.5px; line-height: 1.65;
  color: var(--text-primary); white-space: pre-wrap; word-break: break-word;
  max-height: 340px; overflow-y: auto;
}
.req-msg { margin-bottom: 8px; }
.req-role {
  display: inline-block; font-size: 11px; margin-bottom: 4px;
  border-radius: var(--radius-full); padding: 1px 9px;
}
.req-role.user { color: var(--accent); background: var(--accent-light); }
.req-role.assistant { color: var(--text-secondary); background: var(--bg-secondary); }
/* 可点选项：整行可选卡（完整文本 + 单选圆点），点选 → 确认 → 一次发送 */
.msg-choices {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 8px 0 6px;
}
.choice-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  text-align: left;
  padding: 9px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 12.5px;
  line-height: 1.6;
  cursor: pointer;
  font-family: inherit;
  transition: border-color 0.15s, background 0.15s;
}
.choice-row:hover { border-color: var(--accent); }
.choice-row.selected {
  border-color: var(--accent);
  background: var(--accent-lighter);
  box-shadow: inset 0 0 0 1px var(--accent);
}
.choice-radio {
  flex: none;
  width: 14px;
  height: 14px;
  margin-top: 4px;
  border-radius: 50%;
  border: 1.5px solid var(--border-color);
  transition: all 0.15s;
}
.choice-row.selected .choice-radio {
  border-color: var(--accent);
  background: var(--accent);
  box-shadow: inset 0 0 0 3px var(--bg-card);
}
.choice-text {
  flex: 1;
  word-break: break-word;
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

/* 开放问题的行内作答输入框 */
.msg-open-answer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.open-input {
  flex: 1;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 12.5px;
  outline: none;
  font-family: inherit;
  min-width: 0;
}
.open-input:focus { border-color: var(--accent); }
.open-input::placeholder { color: var(--text-tertiary); }
</style>
