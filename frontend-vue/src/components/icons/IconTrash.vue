<script setup lang="ts">
import { Trash2 } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <Trash2 :size="size" :stroke-width="1.75" />
</template>
