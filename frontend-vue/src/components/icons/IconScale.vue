<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>
<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M6 3h12v4a6 6 0 0 1-12 0V3z" />
    <path d="M6 7H4a2 2 0 0 0 0 4h2" />
    <path d="M18 7h2a2 2 0 0 1 0 4h-2" />
    <path d="M9 17h6" />
    <path d="M12 13v4" />
    <path d="M8 21h8" />
  </svg>
</template>
