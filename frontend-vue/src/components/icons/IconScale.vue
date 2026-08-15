<script setup lang="ts">
import { Scale } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <Scale :size="size" :stroke-width="1.75" />
</template>
