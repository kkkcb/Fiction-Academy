<script setup lang="ts">
import { computed } from 'vue'
import type { Message } from '../types'
import { formatMd, formatContent, parseCommand, parseConsultRecord } from '../utils/format'
import ThinkingBlock from './ThinkingBlock.vue'
import ConsultFlow from './ConsultFlow.vue'
import IconTarget from './icons/IconTarget.vue'
import IconBolt from './icons/IconBolt.vue'

const props = withDefaults(defineProps<{ message: Message; index: number; isLastAssistant?: boolean; isStreaming?: boolean }>(), {
  isLastAssistant: false,
  isStreaming: false,
})
const emit = defineEmits<{
  (e: 'copy-msg', index: number): void
  (e: 'regenerate', index: number): void
}>()

const m = computed(() => props.message)
const cmd = computed(() => m.value.role === 'user' ? parseCommand(m.value.content) : null)
const record = computed(() => m.value.role === 'assistant' ? parseConsultRecord(m.value.content) : null)
const isUser = computed(() => m.value.role === 'user')
const showRegenerate = computed(() => props.isLastAssistant && !props.isStreaming)

const userHtml = computed(() => formatContent(m.value.content))
const assistantHtml = computed(() => formatMd(m.value.content))

function onCopy() { emit('copy-msg', props.index) }
function onRegenerate() { emit('regenerate', props.index) }
</script>

<template>
  <div v-if="cmd" class="msg user msg-command" :data-cmd="cmd.type">
    <div class="msg-role">你</div>
    <div class="command-card">
      <div class="command-header">
        <span class="command-icon">{{ cmd.icon }}</span>
        <span class="command-label">{{ cmd.label }}</span>
      </div>
      <div class="command-body" v-html="formatContent(cmd.idea)"></div>
    </div>
  </div>

  <div v-else-if="record" class="msg assistant msg-consult">
    <div class="msg-role">专家圆桌</div>
    <div class="msg-content consult-flow">
      <ConsultFlow :record="record" />
    </div>
    <div v-if="!isStreaming" class="msg-actions">
      <button class="btn btn-sm" title="复制裁决" @click="onCopy">复制裁决</button>
    </div>
  </div>

  <div v-else class="msg" :class="m.role">
    <div class="msg-role">{{ isUser ? '你' : 'AI' }}</div>
    <div class="msg-content markdown-body">
      <ThinkingBlock v-if="!isUser && m.thinking" :text="m.thinking" :streaming="false" />
      <div v-if="isUser" v-html="userHtml"></div>
      <div v-else v-html="assistantHtml"></div>
    </div>
    <div v-if="!isUser" class="msg-actions">
      <button class="btn btn-sm" title="复制" aria-label="复制消息" @click="onCopy">复制</button>
      <button v-if="showRegenerate" class="btn btn-sm" title="重新生成" aria-label="重新生成回复" @click="onRegenerate">重新生成</button>
    </div>
  </div>
</template>
