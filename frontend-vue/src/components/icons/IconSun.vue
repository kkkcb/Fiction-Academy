<script setup lang="ts">
import { Sun } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <Sun :size="size" :stroke-width="1.75" />
</template>
