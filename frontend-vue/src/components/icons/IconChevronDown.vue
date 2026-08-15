<script setup lang="ts">
import { ChevronDown } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <ChevronDown :size="size" :stroke-width="1.75" />
</template>
