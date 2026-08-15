<script setup lang="ts">
import { Brain } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <Brain :size="size" :stroke-width="1.75" />
</template>
