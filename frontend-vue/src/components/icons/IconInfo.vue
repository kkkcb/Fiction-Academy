<script setup lang="ts">
import { Info } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <Info :size="size" :stroke-width="1.75" />
</template>
