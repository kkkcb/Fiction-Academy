<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import { useSlashCommands } from '../composables/useSlashCommands'
import { useVoiceInput, isVoiceInputSupported } from '../composables/useVoiceInput'
import IconTarget from './icons/IconTarget.vue'
import IconBolt from './icons/IconBolt.vue'

const emit = defineEmits<{ (e: 'send'): void }>()

const store = useAppStore()
const { isStreaming, assistants, currentAssistantId, currentPoint, activeMode, currentProjectId, currentConversationId } = storeToRefs(store)

const text = ref<string>('')
const inputEl = ref<HTMLTextAreaElement | null>(null)

const isPointMode = computed(() => activeMode.value === 'point')
const placeholder = computed(() => isPointMode.value
  ? '输入你的想法，和 AI 一起确定设定...（输入 / 召唤命令）'
  : '输入消息...（输入 / 召唤命令）')

const { popoverOpen, matchedCommands, activeIndex, handleInput, handleKeydown, closePopover } = useSlashCommands(text, currentPoint)

/* ---- 语音输入（浏览器原生，免费） ---- */
const voiceSupported = isVoiceInputSupported()
const voice = useVoiceInput({
  onFinalText: (chunk) => {
    const prev = text.value
    const glue = prev && !/[\u4e00-\u9fa5，。！？、；：）]$/u.test(prev) ? ' ' : ''
    text.value = prev + glue + chunk
    nextTick(autoResize)
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

function onSelectAssistant(e: Event) {
  store.selectAssistant((e.target as HTMLSelectElement).value)
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
            <template v-if="voiceRecording">
              <span class="voice-status" :title="voiceInterim">
                <span class="voice-dot"></span>
                <span class="voice-status-text">正在聆听<template v-if="voiceInterim">：{{ voiceInterim }}</template></span>
              </span>
            </template>
            <select
              v-else-if="assistants.length > 0"
              class="assistant-select toolbar-select"
              :value="currentAssistantId"
              @change="onSelectAssistant"
            >
              <option value="">默认 · 跟随点位</option>
              <option v-for="a in assistants" :key="a.id" :value="a.id">{{ a.name }}</option>
            </select>
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
              <svg viewBox="0 0 16 16" fill="none" width="15" height="15" aria-hidden="true">
                <rect x="6" y="1.5" width="4" height="8" rx="2" stroke="currentColor" stroke-width="1.4"/>
                <path d="M3.5 7.5a4.5 4.5 0 009 0M8 12v2.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
              </svg>
            </button>

            <button
              v-if="isStreaming"
              class="toolbar-btn btn-send toolbar-send"
              title="停止生成（保留已生成内容）"
              aria-label="停止生成"
              @click="store.stopStreaming()"
            >
              <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"><rect x="3.5" y="3.5" width="9" height="9" rx="1.5" fill="currentColor"/></svg>
            </button>
            <button
              v-else
              class="toolbar-btn btn-send toolbar-send"
              :disabled="!text.trim()"
              aria-label="发送消息"
              @click="doSend"
            >
              <svg viewBox="0 0 16 16" fill="none" width="15" height="15" aria-hidden="true"><path d="M2 8l12-5-5 12-2-5-5-2z" fill="currentColor"/></svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
