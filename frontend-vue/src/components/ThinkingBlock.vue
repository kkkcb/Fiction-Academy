<script setup lang="ts">
import { computed } from 'vue'
import { formatMd } from '../utils/format'

const props = withDefaults(defineProps<{ text?: string; streaming?: boolean }>(), {
  text: '',
  streaming: false,
})

const visible = computed(() => !!(props.text && props.text.trim()))
const html = computed(() => formatMd(props.text))
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
