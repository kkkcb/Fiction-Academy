<script setup lang="ts">
import { User } from 'lucide-vue-next'
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <User :size="size" :stroke-width="1.75" />
</template>
