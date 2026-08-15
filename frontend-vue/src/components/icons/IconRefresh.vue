<script setup lang="ts">
import { RefreshCw } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <RefreshCw :size="size" :stroke-width="1.75" />
</template>
