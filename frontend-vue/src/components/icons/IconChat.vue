<script setup lang="ts">
import { MessageSquare } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <MessageSquare :size="size" :stroke-width="1.75" />
</template>
