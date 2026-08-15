<script setup lang="ts">
import { Lock } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <Lock :size="size" :stroke-width="1.75" />
</template>
