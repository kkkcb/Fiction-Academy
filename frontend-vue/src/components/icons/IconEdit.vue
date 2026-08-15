<script setup lang="ts">
import { PenLine } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <PenLine :size="size" :stroke-width="1.75" />
</template>
