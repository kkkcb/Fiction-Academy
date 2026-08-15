<script setup lang="ts">
import { TriangleAlert } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <TriangleAlert :size="size" :stroke-width="1.75" />
</template>
