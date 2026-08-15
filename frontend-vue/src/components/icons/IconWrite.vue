<script setup lang="ts">
import { Feather } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <Feather :size="size" :stroke-width="1.75" />
</template>
