<script setup lang="ts">
import { Menu } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <Menu :size="size" :stroke-width="1.75" />
</template>
