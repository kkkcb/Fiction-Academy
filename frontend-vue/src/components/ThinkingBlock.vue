<script setup lang="ts">
import { computed } from 'vue'
import { formatMd } from '../utils/format'
import IconThinking from './icons/IconThinking.vue'

const props = withDefaults(defineProps<{ text?: string; streaming?: boolean }>(), {
  text: '',
  streaming: false,
})

const visible = computed(() => !!(props.text && props.text.trim()))
// 流式中间态不进缓存（每个 chunk 都是不同 key，会冲掉历史消息的缓存）
const html = computed(() => formatMd(props.text, { cache: !props.streaming }))
const title = computed(() => (props.streaming ? '思考中' : '思考过程'))
</script>

<template>
  <details
    v-if="visible"
    class="thinking-block"
    :class="{ 'is-streaming': streaming }"
    :open="streaming"
  >
    <summary class="thinking-summary">
      <span class="thinking-icon"><IconThinking :size="14" /></span>
      <span class="thinking-title">{{ title }}</span>
    </summary>
    <div class="thinking-content" v-html="html"></div>
  </details>
</template>
