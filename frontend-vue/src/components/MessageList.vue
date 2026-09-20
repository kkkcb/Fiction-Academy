<script setup lang="ts">
import { computed, watch, onMounted, nextTick, ref } from 'vue'
import { storeToRefs } from 'pinia'
import ChatMessage from './ChatMessage.vue'
import ConsultFlow from './ConsultFlow.vue'
import ThinkingBlock from './ThinkingBlock.vue'
import { formatMd, pointPersonaName } from '../utils/format'
import { PenLine, MessageSquare } from 'lucide-vue-next'
import { useAutoScroll } from '../composables/useAutoScroll'
import { useAppStore } from '../stores/app'
import IconWrite from './icons/IconWrite.vue'
import IconChat from './icons/IconChat.vue'

const store = useAppStore()
const {
  messages,
  messagesLoading,
  streamingContent,
  streamingThinking,
  consultFlow,
  isStreaming,
} = storeToRefs(store)

const { el, onScroll, scrollToBottom, reset } = useAutoScroll()

const isPoint = computed(() => store.activeMode === 'point')
const streamingRole = computed(() =>
  isPoint.value ? (pointPersonaName(store.currentPoint) || 'AI') : 'AI'
)
const isEmpty = computed(() => messages.value.length === 0 && !isStreaming.value)
const hasThinking = computed(() => !!streamingThinking.value)
const isStreamingEmpty = computed(() => !streamingContent.value && !hasThinking.value)
const streamingHtml = computed(() => formatMd(streamingContent.value, { cache: false }))
const showStreamingCursor = computed(() => !!streamingContent.value)
const lastIndex = computed(() => messages.value.length - 1)

function isLastAssistant(i: number) {
  return i === lastIndex.value && messages.value[i]?.role === 'assistant'
}

function msgKey(m: { id?: string | number }, i: number): string | number {
  return m.id ?? `local-${i}`
}

function handleRegenerate() {
  if (!store.currentConversationId) return
  store.regenerateMessage(store.currentConversationId)
}

// 消息条数变化要等 DOM 渲染完再滚（watch 默认 pre-flush，滚的是旧高度，会停在半路）
watch(() => messages.value.length, async () => {
  await nextTick()
  scrollToBottom()
})

// 进入/切换对话：历史渲染期间抑制入场动画（否则整屏消息逐个淡入像"刷新"），
// 布局稳定（双 rAF + 延迟复滚兜底字体/代码高亮等晚到的布局变化）后瞬时置底
const suppressAnim = ref(true)
let settleTimer: ReturnType<typeof setTimeout> | null = null

function settleToBottom() {
  suppressAnim.value = true
  reset()
  scrollToBottom(true)
  requestAnimationFrame(() => requestAnimationFrame(() => scrollToBottom(true)))
  if (settleTimer) clearTimeout(settleTimer)
  settleTimer = setTimeout(() => {
    scrollToBottom(true)
    suppressAnim.value = false
  }, 220)
}

watch(messagesLoading, (v) => {
  if (!v && messages.value.length) settleToBottom()
})
watch(() => store.currentConversationId, () => {
  if (messages.value.length) settleToBottom()
  else suppressAnim.value = false
})
onMounted(() => settleToBottom())

watch(() => streamingContent.value, () => scrollToBottom())
watch(() => streamingThinking.value, () => scrollToBottom())
watch(() => consultFlow.value, () => scrollToBottom(), { deep: true })
watch(() => isStreaming.value, (v) => {
  if (v) { reset(); scrollToBottom(true) }
})
</script>

<template>
  <div ref="el" class="chat-messages" :class="{ 'suppress-anim': suppressAnim }" @scroll="onScroll">
    <div v-if="isEmpty" class="empty-state">
      <PenLine v-if="isPoint" class="empty-icon" :size="30" :stroke-width="1.5" />
      <MessageSquare v-else class="empty-icon" :size="30" :stroke-width="1.5" />
      <div class="empty-text">{{ isPoint ? '开始设定' : '开始对话' }}</div>
      <div class="empty-hint">{{ isPoint ? 'AI 会引导你逐步确定核心设定' : '自由讨论任何想法' }}</div>
    </div>

    <div v-if="messagesLoading && !isStreaming" class="msg-skeleton-group" aria-label="消息加载中">
      <div v-for="n in 2" :key="n" class="msg" :class="n % 2 ? 'assistant' : 'user'">
        <div class="msg-role">{{ n % 2 ? 'AI' : '你' }}</div>
        <div class="msg-content">
          <div class="skeleton-line" :style="{ width: (70 + n * 10) + '%' }"></div>
          <div class="skeleton-line" style="width: 45%"></div>
        </div>
      </div>
    </div>

    <ChatMessage
      v-for="(m, i) in messages"
      :key="msgKey(m, i)"
      :message="m"
      :index="i"
      :is-last-assistant="isLastAssistant(i)"
      :is-streaming="isStreaming"
      @regenerate="handleRegenerate"
    />

    <div v-if="isStreaming && consultFlow" id="streaming-msg" class="msg assistant msg-consult">
      <div class="msg-role">专家圆桌</div>
      <div class="msg-content consult-flow">
        <ConsultFlow :record="consultFlow" />
      </div>
    </div>

    <div v-else-if="isStreaming" id="streaming-msg" class="msg assistant">
      <div class="msg-role">{{ streamingRole }}</div>
      <div class="msg-content markdown-body">
        <ThinkingBlock :text="streamingThinking" :streaming="true" />
        <span v-if="isStreamingEmpty" class="thinking-hint">正在思考<span class="thinking-dots"></span></span>
        <template v-else>
          <div v-html="streamingHtml"></div>
          <span v-if="showStreamingCursor" class="streaming-cursor"></span>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 历史消息初次渲染不做入场动画：几十条一起淡入像整屏刷新，且动画期间布局在变 */
.suppress-anim :deep(.msg),
.suppress-anim :deep(.empty-state) {
  animation: none;
}
</style>
