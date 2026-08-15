<script setup lang="ts">
import { Target } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <Target :size="size" :stroke-width="1.75" />
</template>
