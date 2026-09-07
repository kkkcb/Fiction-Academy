<script setup lang="ts">
/**
 * 大纲语音对话：浏览器原生语音识别（Chrome/Edge），说完自动发送，
 * 访谈主持人一次一问把大纲聊定，一键生成倒推+正向大纲草稿。
 */
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import * as api from '../api'
import { useVoiceInput, isVoiceInputSupported } from '../composables/useVoiceInput'
import { formatMd } from '../utils/format'
import { Mic, MicOff, Send, ClipboardCheck, ArrowLeft, CircleCheck, Circle } from 'lucide-vue-next'

const store = useAppStore()
const { currentProjectId } = storeToRefs(store)

interface LocalMsg { role: 'user' | 'assistant'; content: string }

const messages = ref<LocalMsg[]>([])
const input = ref('')
const sending = ref(false)
const distilling = ref(false)
const convId = ref('')
const listEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLTextAreaElement | null>(null)
const voiceSupported = isVoiceInputSupported()
const autoSend = ref(localStorage.getItem('outlineAutoSend') !== '0')  // 默认开：说完自动发

// 访谈清单（与后端访谈主持人的八问一致，仅作导览）
const CHECKLIST = [
  '① 终局画面', '② 真相底牌', '③ 中段低谷', '④ 身份揭穿',
  '⑤ 日常起点', '⑥ 三幕划分', '⑦ 卷设计', '⑧ 结局落点',
]

const voice = useVoiceInput({
  onFinalText: text => {
    input.value += (input.value ? ' ' : '') + text
    scheduleAutoSend()
  },
  onError: msg => { store.error = msg },
})
const recording = voice.recording
const interim = voice.interim

// 覆盖度仅按用户已答轮次估算（vs 八问），给清单一个轻量进度感
const coveredCount = computed(() => Math.min(messages.value.filter(m => m.role === 'user').length, 8))

let autoSendTimer: ReturnType<typeof setTimeout> | null = null
function scheduleAutoSend() {
  if (autoSendTimer) clearTimeout(autoSendTimer)
  if (!autoSend.value || sending.value) return
  // 停顿 1.5s 没有新语句 → 自动发送，接近自然对话节奏
  autoSendTimer = setTimeout(() => {
    if (input.value.trim() && !sending.value && !recording.value) send()
  }, 1500)
}

function toggleAutoSend() {
  autoSend.value = !autoSend.value
  localStorage.setItem('outlineAutoSend', autoSend.value ? '1' : '0')
}

async function scrollBottom() {
  await nextTick()
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
}

async function load() {
  if (!currentProjectId.value) return
  try {
    const ensured = await api.ensurePointConversation(currentProjectId.value, '__outline__')
    convId.value = ensured.conversation_id
    const msgs = await api.getMessages(convId.value)
    messages.value = msgs.map(m => ({ role: m.role === 'assistant' ? 'assistant' : 'user', content: m.content || '' }))
    await scrollBottom()
  } catch (e) {
    store.error = `加载大纲对话失败：${(e as Error).message}`
  }
}
onMounted(load)
onUnmounted(() => { if (autoSendTimer) clearTimeout(autoSendTimer) })

function send() {
  const text = input.value.trim()
  if (!text || sending.value || !convId.value) return
  if (autoSendTimer) clearTimeout(autoSendTimer)
  input.value = ''
  messages.value.push({ role: 'user', content: text })
  sending.value = true
  let reply = ''
  messages.value.push({ role: 'assistant', content: '' })
  scrollBottom()
  api.streamChat(
    convId.value,
    text,
    chunk => {
      reply += chunk
      messages.value[messages.value.length - 1].content = reply
      scrollBottom()
    },
    () => {
      sending.value = false
      scheduleAutoSend()
    },
    (err, partial) => {
      sending.value = false
      if (partial) messages.value[messages.value.length - 1].content = partial
      else messages.value.pop()
      store.error = `发送失败：${err.message}`
    },
    '',
  )
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
  if (e.key === 'Escape' && recording.value) voice.stop()
}

async function distill() {
  if (!currentProjectId.value || distilling.value) return
  distilling.value = true
  try {
    const r = await api.outlineDistill(currentProjectId.value)
    const parts: string[] = []
    if (r.generated?.length) parts.push('已生成：' + r.generated.map(g => `${g.label}（${g.chars}字）`).join('、'))
    if (r.skipped?.length) parts.push('已定稿跳过：' + r.skipped.join('、'))
    if (r.errors?.length) parts.push('失败：' + r.errors.join('；'))
    if (parts.length) messages.value.push({ role: 'assistant', content: parts.join('\n\n') })
    store.notifySuccess(r.generated?.length ? '大纲草稿已生成，去工作区「大纲」点位查看' : '没有新草稿（可能已定稿）')
    await store.fetchWorkspaceItems(currentProjectId.value)
    await scrollBottom()
  } catch (e) {
    store.error = `生成大纲失败：${(e as Error).message}`
  } finally {
    distilling.value = false
  }
}
</script>

<template>
  <div class="outline-studio">
    <header class="os-header">
      <div class="os-title-wrap">
        <button class="btn btn-sm" title="返回自由对话" @click="store.centerView = 'chat'">
          <ArrowLeft :size="13" :stroke-width="1.75" /> 返回
        </button>
        <span class="os-title">大纲语音对话</span>
        <span class="os-sub">对着麦克风聊，主持人一问一答帮你把大纲定下来</span>
      </div>
      <button class="btn btn-primary" :disabled="distilling" @click="distill">
        <ClipboardCheck :size="14" :stroke-width="1.75" />
        {{ distilling ? '生成中…' : '生成大纲草稿' }}
      </button>
    </header>

    <div class="os-checklist">
      <span v-for="(c, i) in CHECKLIST" :key="i" class="os-chip">
        <CircleCheck v-if="i < coveredCount" :size="11" :stroke-width="2" class="os-chip-ok" />
        <Circle v-else :size="11" :stroke-width="1.75" class="os-chip-todo" />
        {{ c }}
      </span>
    </div>

    <div ref="listEl" class="os-messages">
      <div v-if="!messages.length" class="os-empty">
        <Mic :size="30" :stroke-width="1.5" class="os-empty-icon" />
        <div class="os-empty-title">按住话题，开口聊</div>
        <div class="os-empty-sub">比如：「我想写个修仙的，主角是个守着茶园的懒郎中，结局是他送走所有人」<br />主持人会顺着终局往回帮你倒推整条大纲</div>
      </div>
      <div v-for="(m, i) in messages" :key="i" class="os-msg" :class="m.role">
        <div v-if="m.role === 'assistant'" class="os-bubble markdown-body" v-html="formatMd(m.content)"></div>
        <div v-else class="os-bubble">{{ m.content }}</div>
      </div>
      <div v-if="sending && !messages[messages.length - 1]?.content" class="os-typing">主持人在想…</div>
    </div>

    <footer class="os-inputbar" :class="{ recording }">
      <div v-if="interim" class="os-interim">{{ interim }}</div>
      <div class="os-row">
        <button
          class="os-mic"
          :class="{ on: recording, disabled: !voiceSupported }"
          :title="!voiceSupported ? '当前浏览器不支持语音，请用 Chrome/Edge' : (recording ? '停止录音（Esc）' : '开始录音')"
          :disabled="!voiceSupported"
          @click="voice.toggle()"
        >
          <MicOff v-if="recording" :size="18" :stroke-width="1.75" />
          <Mic v-else :size="18" :stroke-width="1.75" />
        </button>
        <textarea
          ref="inputEl"
          v-model="input"
          class="os-textarea"
          rows="1"
          placeholder="说话或打字，Enter 发送"
          @keydown="onKeydown"
          @input="scheduleAutoSend"
        ></textarea>
        <button class="os-send" :disabled="!input.trim() || sending" title="发送" @click="send">
          <Send :size="15" :stroke-width="1.75" />
        </button>
      </div>
      <label class="os-autosend" title="停顿1.5秒自动发送，像打电话一样聊">
        <input type="checkbox" :checked="autoSend" @change="toggleAutoSend" />
        说完自动发送
        <span v-if="!voiceSupported" class="os-unsupported">（当前浏览器不支持语音输入，请用 Chrome / Edge）</span>
      </label>
    </footer>
  </div>
</template>

<style scoped>
.outline-studio {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bg-primary);
}
.os-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-color);
}
.os-title-wrap { display: flex; align-items: center; gap: 10px; min-width: 0; }
.os-title {
  font-family: var(--font-serif), serif;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
}
.os-sub {
  font-size: 11px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.os-checklist {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 8px 16px;
  border-bottom: 1px dashed var(--border-subtle);
  background: var(--bg-secondary);
}
.os-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-full);
  padding: 2px 8px;
  white-space: nowrap;
}
.os-chip-ok { color: #059669; }
.os-chip-todo { color: var(--text-muted); }
.os-messages {
  flex: 1;
  overflow-y: auto;
  padding: 18px 20px 28px;
}
.os-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-muted);
  text-align: center;
}
.os-empty-icon { font-size: 30px; opacity: 0.45; }
.os-empty-title { font-size: 14px; font-weight: 600; color: var(--text-secondary); }
.os-empty-sub { font-size: 12px; line-height: 1.9; }
.os-msg { display: flex; margin-bottom: 12px; }
.os-msg.user { justify-content: flex-end; }
.os-bubble {
  max-width: 78%;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  font-size: 13px;
  line-height: 1.8;
  word-break: break-word;
}
.os-msg.assistant .os-bubble {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  color: var(--text-primary);
}
.os-msg.user .os-bubble {
  background: var(--accent-lighter);
  border: 1px solid var(--accent-border);
  color: var(--text-primary);
}
.os-msg :deep(p) { margin: 4px 0; }
.os-typing { font-size: 12px; color: var(--text-muted); padding: 4px 8px; }
.os-inputbar {
  border-top: 1px solid var(--border-color);
  padding: 10px 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--bg-primary);
}
.os-inputbar.recording { box-shadow: inset 0 2px 0 0 #ef4444; }
.os-interim {
  font-size: 12px;
  color: var(--text-tertiary);
  font-style: italic;
  padding: 2px 6px;
  min-height: 18px;
}
.os-row { display: flex; align-items: flex-end; gap: 8px; }
.os-mic {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid var(--border-color);
  background: var(--bg-card);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.os-mic.on {
  background: #ef4444;
  border-color: #ef4444;
  color: #fff;
  animation: osPulse 1.2s ease-in-out infinite;
}
.os-mic.disabled { opacity: 0.4; cursor: not-allowed; }
@keyframes osPulse { 0%, 100% { box-shadow: 0 0 0 0 #ef444455; } 50% { box-shadow: 0 0 0 8px #ef444400; } }
.os-textarea {
  flex: 1;
  resize: none;
  max-height: 120px;
  padding: 9px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  color: var(--text-primary);
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
  outline: none;
}
.os-textarea:focus { border-color: var(--accent); }
.os-send {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  border: none;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.os-send:disabled { opacity: 0.4; cursor: not-allowed; }
.os-autosend {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-tertiary);
  cursor: pointer;
  user-select: none;
}
.os-unsupported { color: #d97706; }

@media (max-width: 768px) {
  .os-header { flex-wrap: wrap; padding: 8px 10px; }
  .os-title-wrap { flex: 1 1 100%; }
  .os-sub { display: none; }
  .os-header > .btn { flex: 1 1 100%; justify-content: center; }
  .os-checklist {
    flex-wrap: nowrap;
    overflow-x: auto;
    padding: 6px 10px;
    -webkit-overflow-scrolling: touch;
  }
  .os-chip { flex: 0 0 auto; }
  .os-messages { padding: 12px 10px 20px; }
  .os-bubble { max-width: 92%; }
  .os-inputbar { padding: 8px 10px 10px; }
  .os-row { gap: 6px; }
  .os-mic, .os-send { width: 46px; height: 46px; }
  .os-textarea { font-size: 16px; padding: 10px 10px; }
  .os-empty-sub br { display: none; }
}
</style>
