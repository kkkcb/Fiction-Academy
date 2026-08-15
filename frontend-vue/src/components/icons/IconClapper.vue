<script setup lang="ts">
import { Clapperboard } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <Clapperboard :size="size" :stroke-width="1.75" />
</template>
