<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import * as api from '../api'
import { useSlashCommands } from '../composables/useSlashCommands'
import { useVoiceInput, isVoiceInputSupported } from '../composables/useVoiceInput'
import { Mic, Square, ArrowUp } from 'lucide-vue-next'
import IconTarget from './icons/IconTarget.vue'
import IconBolt from './icons/IconBolt.vue'

const emit = defineEmits<{ (e: 'send'): void }>()

const store = useAppStore()
const { isStreaming, currentPoint, activeMode, currentProjectId, currentConversationId } = storeToRefs(store)

const text = ref<string>('')
const inputEl = ref<HTMLTextAreaElement | null>(null)

const isPointMode = computed(() => activeMode.value === 'point')
const placeholder = computed(() => isPointMode.value
  ? '输入你的想法，和 AI 一起确定设定...（输入 / 召唤命令）'
  : '输入消息...（输入 / 召唤命令）')

const { popoverOpen, matchedCommands, activeIndex, handleInput, handleKeydown, closePopover } = useSlashCommands(text, currentPoint)

/* ---- 语音输入（浏览器原生，免费） ---- */
const voiceSupported = isVoiceInputSupported()

// 语音转写自动加标点：停顿 600ms 后把整段送后端补标点（只加标点不改字），
// 期间用户手动改过输入框就放弃替换，避免覆盖手打内容
let punctTimer: ReturnType<typeof setTimeout> | null = null
let punctToken = 0
let punctuating = ref(false)
function schedulePunctuate() {
  if (punctTimer) clearTimeout(punctTimer)
  punctTimer = setTimeout(async () => {
    const src = text.value
    if (!src.trim() || src.length > 2000) return
    const tk = ++punctToken
    punctuating.value = true
    try {
      const r = await api.punctuate(src)
      if (tk === punctToken && r.text && r.text !== src && text.value === src) {
        text.value = r.text
        nextTick(autoResize)
      }
    } catch { /* 标点失败静默：原文照样能发 */ }
    finally {
      if (tk === punctToken) punctuating.value = false
    }
  }, 600)
}

const voice = useVoiceInput({
  onFinalText: (chunk) => {
    const prev = text.value
    const glue = prev && !/[\u4e00-\u9fa5，。！？、；：）]$/u.test(prev) ? ' ' : ''
    text.value = prev + glue + chunk
    nextTick(autoResize)
    schedulePunctuate()
  },
  onError: (msg) => { store.error = msg },
})
const voiceRecording = voice.recording
const voiceInterim = voice.interim
function toggleVoice() {
  if (!voiceSupported) {
    store.error = '当前浏览器不支持语音输入，请使用 Chrome 或 Edge'
    return
  }
  voice.toggle()
}

function autoResize() {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

function onInput() {
  autoResize()
  handleInput()
}

function focusEnd() {
  nextTick(() => {
    autoResize()
    inputEl.value?.focus()
    const len = text.value.length
    inputEl.value?.setSelectionRange(len, len)
  })
}

function fillCommand(cmd: string) {
  text.value = cmd + ' '
  closePopover()
  focusEnd()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && voiceRecording.value) {
    voice.stop()
    return
  }
  if (popoverOpen.value) {
    if (handleKeydown(e)) return
  } else if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    doSend()
  }
}

function doSend() {
  const content = text.value.trim()
  if (!content) return

  const consultMatch = content.match(/^\/consult\s+([\s\S]+)/i)
  const genMatch = content.match(/^\/gen\s+([\s\S]+)/i)
  const missionMatch = content.match(/^\/goal\s+([\s\S]+)/i)

  let handled = false
  if (consultMatch) {
    if (!currentPoint.value || activeMode.value !== 'point') {
      store.error = '「/consult 专家会诊」仅在点位对话中使用'
      return // 输入保留，用户可修改后重发
    }
    if (isStreaming.value) return
    store.expertConsult(currentProjectId.value!, currentPoint.value, consultMatch[1].trim())
    handled = true
  } else if (genMatch) {
    if (!currentPoint.value || activeMode.value !== 'point') {
      store.error = '「/gen 快速生成」仅在点位对话中使用'
      return
    }
    if (isStreaming.value) return
    store.goalGenerate(currentProjectId.value!, currentPoint.value, genMatch[1].trim())
    handled = true
  } else if (missionMatch) {
    if (!currentProjectId.value) return
    if (isStreaming.value) return
    store.startGoal(currentProjectId.value, missionMatch[1].trim())
    handled = true
  } else if (content === '/distill' || content === '/build') {
    if (!currentProjectId.value || !currentConversationId.value) return
    if (isStreaming.value) return
    if (content === '/distill') {
      store.studioDistill(currentProjectId.value)
    } else {
      store.studioBuild(currentProjectId.value)
    }
    handled = true
  } else if (currentConversationId.value && !isStreaming.value) {
    store.sendMessage(currentConversationId.value, content)
    handled = true
  }

  if (handled) {
    text.value = ''
    closePopover()
    nextTick(() => {
      autoResize()
      inputEl.value?.focus()
    })
  }
}

function onBlur() {
  setTimeout(closePopover, 150)
}
</script>

<template>
  <div class="chat-input-area">
    <div class="slash-popover-anchor">
      <div v-if="popoverOpen" class="slash-popover">
        <div
          v-for="(it, i) in matchedCommands"
          :key="it.cmd"
          class="slash-item"
          :class="{ active: i === activeIndex }"
          @mousedown.prevent="fillCommand(it.cmd)"
        >
          <span class="slash-icon">{{ it.icon }}</span>
          <div class="slash-text">
            <div class="slash-cmd">{{ it.cmd }} <span class="slash-title">{{ it.title }}</span></div>
            <div class="slash-desc">{{ it.desc }}</div>
          </div>
        </div>
      </div>

      <div class="chat-input-shell" :class="{ 'voice-active': voiceRecording }">
        <textarea
          ref="inputEl"
          v-model="text"
          class="chat-input"
          :placeholder="placeholder"
          rows="1"
          @input="onInput"
          @keydown="onKeydown"
          @blur="onBlur"
        ></textarea>

        <div class="input-toolbar">
          <div class="toolbar-left">
            <span v-if="voiceRecording" class="voice-status" :title="voiceInterim">
              <span class="voice-dot"></span>
              <span class="voice-status-text">正在聆听<template v-if="voiceInterim">：{{ voiceInterim }}</template></span>
            </span>
          </div>

          <div class="toolbar-right">
            <span v-if="text.length > 0 && !voiceRecording" class="input-count" :class="{ warn: text.length > 4000 }">
              {{ text.length.toLocaleString('zh-CN') }} 字
            </span>

            <button
              class="toolbar-btn btn-mic"
              :class="{ recording: voiceRecording, unsupported: !voiceSupported }"
              :disabled="isStreaming || !voiceSupported"
              :title="!voiceSupported ? '当前浏览器不支持语音输入（建议 Chrome/Edge）' : voiceRecording ? '停止语音输入（Esc）' : '语音输入'"
              :aria-label="voiceRecording ? '停止语音输入' : '语音输入'"
              :aria-pressed="voiceRecording"
              @click="toggleVoice"
            >
              <Mic :size="15" :stroke-width="1.75" aria-hidden="true" />
            </button>

            <button
              v-if="isStreaming"
              class="toolbar-btn btn-send toolbar-send"
              title="停止生成（保留已生成内容）"
              aria-label="停止生成"
              @click="store.stopStreaming()"
            >
              <Square :size="11" :stroke-width="0" fill="currentColor" aria-hidden="true" />
            </button>
            <button
              v-else
              class="toolbar-btn btn-send toolbar-send"
              :disabled="!text.trim()"
              aria-label="发送消息"
              @click="doSend"
            >
              <ArrowUp :size="16" :stroke-width="2" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
