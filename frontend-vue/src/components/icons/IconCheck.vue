<script setup lang="ts">
import { Check } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <Check :size="size" :stroke-width="1.75" />
</template>
