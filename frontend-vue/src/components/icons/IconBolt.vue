<script setup lang="ts">
import { Zap } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <Zap :size="size" :stroke-width="1.75" />
</template>
