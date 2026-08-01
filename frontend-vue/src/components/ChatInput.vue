<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import { useSlashCommands } from '../composables/useSlashCommands'
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
  if (popoverOpen.value) {
    if (handleKeydown(e)) return
  } else if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    doSend()
  }
}

function doSend() {
  const content = text.value.trim()
  if (!content || isStreaming.value) return

  const consultMatch = content.match(/^\/consult\s+([\s\S]+)/i)
  const goalMatch = content.match(/^\/goal\s+([\s\S]+)/i)

  if (consultMatch) {
    if (!currentPoint.value || activeMode.value !== 'point') return
    store.expertConsult(currentProjectId.value!, currentPoint.value, consultMatch[1].trim())
  } else if (goalMatch) {
    if (!currentPoint.value || activeMode.value !== 'point') return
    store.goalGenerate(currentProjectId.value!, currentPoint.value, goalMatch[1].trim())
  } else if (currentConversationId.value) {
    store.sendMessage(currentConversationId.value, content)
  }

  text.value = ''
  closePopover()
  nextTick(autoResize)
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
    <select
      v-if="assistants.length > 0"
      class="assistant-select"
      :value="currentAssistantId"
      @change="onSelectAssistant"
    >
      <option v-for="a in assistants" :key="a.id" :value="a.id">{{ a.name }}</option>
    </select>

    <textarea
      ref="inputEl"
      v-model="text"
      class="chat-input"
      :placeholder="placeholder"
      rows="1"
      :disabled="isStreaming"
      @input="onInput"
      @keydown="onKeydown"
      @blur="onBlur"
    ></textarea>

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

    <button
      class="btn btn-send"
      :class="{ 'is-loading': isStreaming }"
      :disabled="isStreaming"
      :aria-label="isStreaming ? '正在生成' : '发送消息'"
      @click="doSend"
    >
      <span v-if="isStreaming" class="btn-spinner" aria-hidden="true"></span>
      <svg v-else viewBox="0 0 16 16" fill="none" width="16" height="16" aria-hidden="true"><path d="M2 8l12-5-5 12-2-5-5-2z" fill="currentColor"/></svg>
    </button>
  </div>
</template>
