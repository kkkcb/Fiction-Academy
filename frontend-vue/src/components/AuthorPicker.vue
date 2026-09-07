<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '../stores/app'
import { Feather } from 'lucide-vue-next'

const props = defineProps<{
  modelValue: string
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', key: string): void
}>()

const store = useAppStore()

const authors = computed(() => store.authors)

function pick(key: string) {
  emit('update:modelValue', key)
}
</script>

<template>
  <div class="author-picker" role="radiogroup" aria-label="选择作者人格（必选）">
    <button
      v-for="a in authors"
      :key="a.key"
      type="button"
      class="author-card"
      :class="{ active: modelValue === a.key }"
      role="radio"
      :aria-checked="modelValue === a.key"
      @click="pick(a.key)"
    >
      <div class="author-head">
        <Feather :size="14" :stroke-width="1.75" class="author-icon" />
        <span class="author-name">{{ a.name }}</span>
        <span class="author-label">{{ a.label }}</span>
      </div>
      <p class="author-blurb">{{ a.blurb }}</p>
    </button>
  </div>
</template>

<style scoped>
.author-picker {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px;
  margin: 6px 0 12px;
}
.author-card {
  text-align: left;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
  font-family: inherit;
}
.author-card:hover {
  border-color: var(--accent);
}
.author-card.active {
  border-color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent), 0 0 0 3px var(--accent-lighter);
  background: var(--accent-lighter);
}
.author-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.author-icon {
  color: var(--accent);
  flex: none;
}
.author-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.author-label {
  font-size: 11px;
  color: var(--accent);
  background: var(--accent-light);
  border-radius: var(--radius-full);
  padding: 1px 8px;
  white-space: nowrap;
}
.author-blurb {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
}
</style>
