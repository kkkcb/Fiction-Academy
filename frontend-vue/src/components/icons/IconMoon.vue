<script setup lang="ts">
import { Moon } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <Moon :size="size" :stroke-width="1.75" />
</template>
