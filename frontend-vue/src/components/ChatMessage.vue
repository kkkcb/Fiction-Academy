<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import type { Message } from '../types'
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
const pinSaving = ref(false)
// 沉淀=全模块再分拣：深度思考比对 → 各模块融合建议 → 勾选确认写入
const pinSuggestions = ref<import('../api').PinModuleSuggestion[]>([])
const pinChosen = ref<Record<string, boolean>>({})
const pinExpanded = ref<Record<string, boolean>>({})
const pinNote = ref('')
const pinApplied = ref(0)
function onPin() {
  pinSuggestions.value = []
  pinApplied.value = 0
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
  if (!store.currentProjectId || pinSaving.value) return
  pinSaving.value = true
  try {
    const r = await api.pinRedistill(store.currentProjectId, m.value.content)
    pinSuggestions.value = r.modules
    pinNote.value = r.note
    pinChosen.value = Object.fromEntries(r.modules.map(x => [x.point, true]))
    pinExpanded.value = Object.fromEntries(r.modules.map(x => [x.point, false]))
  } catch (e) {
    alert(`再分拣失败：${(e as Error).message}`)
  } finally {
    pinSaving.value = false
  }
}
async function applyPin() {
  if (!store.currentProjectId) return
  const picked = pinSuggestions.value.filter(x => pinChosen.value[x.point])
  if (!picked.length) return
  pinSaving.value = true
  try {
    const r = await api.pinApply(store.currentProjectId, picked.map(x => ({ point: x.point, content: x.content })))
    pinApplied.value = r.applied.length
    store.fetchWorkspaceItems(store.currentProjectId)
  } catch (e) {
    alert(`写入失败：${(e as Error).message}`)
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

  <div v-else class="msg" :class="m.role" @contextmenu="onContextMenu">
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
      <div v-if="showPinModal" class="modal-overlay show" @click.self="closePin">
        <div class="modal-card pin-modal">
          <!-- 已采纳完成 -->
          <template v-if="pinApplied">
            <h3>沉淀完成</h3>
            <p class="pin-hint">已按你的确认更新 {{ pinApplied }} 个模块，右侧总览即时生效。</p>
            <div class="modal-actions">
              <button class="btn btn-primary" @click="closePin">好</button>
            </div>
          </template>

          <!-- 再分拣结果：逐模块确认 -->
          <template v-else-if="pinSuggestions.length">
            <h3>沉淀再分拣结果</h3>
            <p class="pin-hint">{{ pinNote }} 勾选要采纳的模块（点模块名展开看完整融合内容）。</p>
            <div class="pin-modules">
              <div v-for="x in pinSuggestions" :key="x.point" class="pin-module" :class="{ off: !pinChosen[x.point] }">
                <label class="pin-module-head">
                  <input
                    type="checkbox"
                    :checked="pinChosen[x.point]"
                    @change="pinChosen = { ...pinChosen, [x.point]: ($event.target as HTMLInputElement).checked }"
                  />
                  <span class="pin-module-label">{{ x.label }}</span>
                  <span v-if="x.is_new" class="pin-new-badge">新建</span>
                  <span v-else class="pin-old-chars">{{ x.old_chars }} 字 → {{ x.content.length }} 字</span>
                  <span class="pin-flex"></span>
                  <button class="btn-link" @click.prevent="pinExpanded = { ...pinExpanded, [x.point]: !pinExpanded[x.point] }">
                    {{ pinExpanded[x.point] ? '收起' : '展开' }}
                  </button>
                </label>
                <p v-if="x.note" class="pin-module-note">{{ x.note }}</p>
                <div v-if="pinExpanded[x.point]" class="markdown-body pin-module-content" v-html="formatReceiptMd(x.content)"></div>
              </div>
            </div>
            <div class="modal-actions">
              <button class="btn" :disabled="pinSaving" @click="closePin">取消（不写入）</button>
              <button class="btn btn-primary" :disabled="pinSaving || !pinSuggestions.some(x => pinChosen[x.point])" @click="applyPin">
                {{ pinSaving ? '写入中…' : `采纳所选（${pinSuggestions.filter(x => pinChosen[x.point]).length}）` }}
              </button>
            </div>
          </template>

          <!-- 初始：说明 + 开始 -->
          <template v-else-if="!pinSaving">
            <h3>沉淀到设定</h3>
            <div class="pin-hint">
              以这条消息为<b>新设定</b>、总览全部模块为<b>原设定</b>，深度思考全局比对后重新产出各模块的融合版，由你逐模块确认后写入。
            </div>
            <div class="modal-actions">
              <button class="btn" @click="closePin">取消</button>
              <button class="btn btn-primary" @click="doPin">开始再分拣（深度思考）</button>
            </div>
          </template>

          <!-- 深度思考中 -->
          <template v-else>
            <h3>深度思考中…</h3>
            <div class="pin-hint">正在把这条消息与总览全部模块做全局比对（思考强度最高，跨模块联动也会检查），稍等。</div>
          </template>
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
.pin-modal { max-width: min(680px, 92vw); max-height: 86vh; overflow-y: auto; }
.pin-modules { display: flex; flex-direction: column; gap: 8px; margin: 6px 0 12px; }
.pin-module {
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 8px 12px;
  transition: opacity 0.15s;
}
.pin-module.off { opacity: 0.45; }
.pin-module-head { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.pin-module-label { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.pin-new-badge {
  font-size: 10.5px; color: var(--accent); background: var(--accent-light);
  border-radius: var(--radius-full); padding: 1px 8px;
}
.pin-old-chars { font-size: 11px; color: var(--text-tertiary); }
.pin-flex { flex: 1; }
.pin-module-note { margin: 6px 0 0; font-size: 12px; color: var(--text-secondary); }
.pin-module-content {
  margin-top: 8px; padding: 10px; border-radius: 8px;
  background: var(--bg-secondary); font-size: 12px; line-height: 1.7;
  max-height: 320px; overflow-y: auto;
}
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
