<script setup lang="ts">
import { computed } from 'vue'
import IconTarget from './IconTarget.vue'
import IconGlobe from './IconGlobe.vue'
import IconUser from './IconUser.vue'
import IconRefresh from './IconRefresh.vue'
import IconClapper from './IconClapper.vue'
import IconScale from './IconScale.vue'

const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 28 })

const colorMap: Record<string, string> = {
  '主线策划': '#c55d3b',
  '世界观架构师': '#7c3aed',
  '人物塑造师': '#0891b2',
  '逆向架构师': '#059669',
  '节奏导演': '#db2777',
  '终局裁决': '#c55d3b',
}

const color = computed(() => colorMap[props.name] || '#78716c')
const bg = computed(() => color.value + '14')

const iconComp = computed(() => {
  switch (props.name) {
    case '主线策划': return IconTarget
    case '世界观架构师': return IconGlobe
    case '人物塑造师': return IconUser
    case '逆向架构师': return IconRefresh
    case '节奏导演': return IconClapper
    case '终局裁决': return IconScale
    default: return IconUser
  }
})
</script>

<template>
  <span
    class="expert-avatar"
    :style="{ background: bg, color: color, width: size + 'px', height: size + 'px' }"
  >
    <component :is="iconComp" :size="size * 0.62" />
  </span>
</template>

<style scoped>
.expert-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  flex-shrink: 0;
  flex: none;
}
</style>
