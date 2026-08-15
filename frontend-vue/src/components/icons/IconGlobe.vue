<script setup lang="ts">
import { Globe } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <Globe :size="size" :stroke-width="1.75" />
</template>
