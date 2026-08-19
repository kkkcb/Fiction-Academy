<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import WritingPanel from './WritingPanel.vue'
import StoryWebPanel from './StoryWebPanel.vue'
import { Network, BookOpen } from 'lucide-vue-next'
import { ChevronLeft } from 'lucide-vue-next'

const store = useAppStore()
const view = ref<'chapters' | 'web'>('chapters')
const { currentProject, currentProjectId, chapters, totalChapterWords } = storeToRefs(store)

onMounted(() => {
  if (!currentProjectId.value) store.navigateTo('projects')
})
</script>

<template>
  <div class="writing-page">
    <header class="wp-topbar">
      <button class="btn btn-sm mode-pill" aria-label="切换到骨架工作台" title="骨架工作台（点位/对话/总览）" @click="store.navigateTo('workspace', { currentProjectId: currentProjectId! })">
        <ChevronLeft :size="14" :stroke-width="1.75" /> 骨架工作台
      </button>
      <div class="wp-title">
        <span class="wp-book">{{ currentProject?.name || '未命名' }}</span>
        <span class="wp-meta">
          <template v-if="chapters.length">已写 {{ chapters.length }} 章 · 共 {{ totalChapterWords.toLocaleString() }} 字</template>
          <template v-else>尚未开写</template>
        </span>
      </div>
    </header>
    <div class="wp-view-switch">
      <button class="wp-pill" :class="{ active: view === 'chapters' }" aria-label="章节视图" @click="view = 'chapters'">
        <BookOpen :size="13" :stroke-width="1.75" /> 章节
      </button>
      <button class="wp-pill" :class="{ active: view === 'web' }" aria-label="脉络网视图" @click="view = 'web'">
        <Network :size="13" :stroke-width="1.75" /> 脉络网
      </button>
    </div>
    <WritingPanel v-if="view === 'chapters'" class="wp-body" />
    <StoryWebPanel v-else class="wp-body" />
  </div>
</template>

<style scoped>
.writing-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}
.wp-topbar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-secondary);
  flex-shrink: 0;
}
.wp-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.wp-book {
  font-family: var(--font-serif), serif;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wp-meta { font-size: 11px; color: var(--text-muted); }
.wp-body { flex: 1; min-height: 0; }
</style>

<style scoped>
.wp-view-switch { display: flex; gap: 2px; margin-left: auto; }
.wp-pill {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 12px; border: none; border-radius: var(--radius-sm);
  background: transparent; color: var(--text-secondary);
  font-size: 12px; font-family: inherit; cursor: pointer;
}
.wp-pill:hover { background: var(--bg-hover); }
.wp-pill.active { background: var(--accent-lighter); color: var(--accent); font-weight: 600; }
</style>
