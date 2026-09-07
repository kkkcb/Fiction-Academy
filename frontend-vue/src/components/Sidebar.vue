<script setup lang="ts">
import { ref, computed } from 'vue'
import { storeToRefs } from 'pinia'
import type { ID, Conversation } from '../types'
import { useAppStore } from '../stores/app'
import { POINT_NAV, relativeTime } from '../utils/format'
import IconTrash from './icons/IconTrash.vue'
import { ChevronLeft, BrainCircuit, PanelLeftClose, PanelLeftOpen, MessageSquareText, ChevronDown } from 'lucide-vue-next'

const store = useAppStore()
const {
  currentProjectId,
  projects,
  conversations,
  currentConversationId,
  points,
  assistants,
  currentAssistantId,
  centerView,
  chapters,
  sidebarCollapsed,
  outlineConvId,
} = storeToRefs(store)

const currentProject = computed(() =>
  projects.value.find(p => p.id === currentProjectId.value)
)

// 分区折叠（创作流程 / 对话历史）
const sectionCollapsed = ref({ points: false, convs: false })

// 对话历史：全部会话按更新时间倒序（创作对话/大纲语音/点位对话/自由对话）
const historyConversations = computed(() =>
  [...conversations.value]
    .sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''))
    .slice(0, 30)
)

function convLabel(c: Conversation): string {
  if (c.point === '__studio__') return '创作对话'
  if (c.point === '__outline__') return '🎙 大纲语音'
  if (c.point) return POINT_NAV.find(p => p.key === c.point)?.label || c.title || '对话'
  return c.title || '自由对话'
}

function openConv(c: Conversation) {
  if (c.point === '__outline__') {
    store.openOutlineConv(c.id)
  } else {
    store.selectConversation(c.id)
  }
}

function pointStatus(key: string) {
  const data = points.value.find(d => d.point === key)
  return data?.status || 'pending'
}

async function handleDeleteConv(id: ID) {
  if (confirm('确定删除这个对话？删除后不可恢复。')) {
    await store.deleteConversation(id)
    if (outlineConvId.value === id) store.openOutlineConv('') // 触发 OutlineStudio 重建新会话
  }
}

function goBack() {
  try {
    store.navigateTo('projects')
  } catch (e) {
    console.error('[goBack] navigateTo error:', e)
  }
}
</script>

<template>
  <aside class="sidebar-left" :class="{ collapsed: sidebarCollapsed }">

    <!-- 折叠态：图标栏（悬浮显示提示） -->
    <div v-if="sidebarCollapsed" class="sidebar-rail">
      <button class="rail-btn" data-tip="返回项目列表" aria-label="返回项目列表" @click="goBack">
        <ChevronLeft :size="16" :stroke-width="1.75" />
      </button>
      <div class="rail-avatar" data-tip="展开侧栏">{{ (currentProject?.name || '未').slice(0, 1) }}</div>
      <div class="rail-sep"></div>
      <button
        class="rail-btn"
        data-tip="创作对话 · 与作者讨论"
        aria-label="创作对话"
        @click="store.openStudio(currentProjectId!)"
      >
        <MessageSquareText :size="16" :stroke-width="1.75" />
      </button>
      <button class="rail-btn" :class="{ active: centerView === 'writing' }" data-tip="小说写作" aria-label="进入小说写作" @click="store.openWriting()">
        <BrainCircuit :size="16" :stroke-width="1.75" />
      </button>
      <div class="rail-sep"></div>
      <button class="rail-btn" data-tip="创作对话" aria-label="创作对话" @click="store.openStudio(currentProjectId!)">
        <MessageSquareText :size="16" :stroke-width="1.75" />
      </button>
      <button class="rail-btn rail-expand" data-tip="展开侧栏（Ctrl+\）" aria-label="展开侧栏" @click="store.toggleSidebar()">
        <PanelLeftOpen :size="16" :stroke-width="1.75" />
      </button>
    </div>

    <template v-else>
    <div class="glass-header">
      <button class="btn btn-sm" title="返回项目列表" aria-label="返回项目列表" @click="goBack">
        <ChevronLeft :size="14" :stroke-width="1.75" />
      </button>
      <span class="glass-title">{{ currentProject?.name || '未命名' }}</span>
      <button class="btn btn-sm sidebar-collapse-btn" title="收起侧栏（Ctrl+\）" aria-label="收起侧栏" @click="store.toggleSidebar()">
        <PanelLeftClose :size="14" :stroke-width="1.75" />
      </button>
    </div>

    <div class="point-nav">
      <div class="point-nav-label section-head" @click="sectionCollapsed.points = !sectionCollapsed.points">
        <ChevronDown :size="12" :stroke-width="1.75" class="section-arrow" :class="{ folded: sectionCollapsed.points }" />
        创作流程
      </div>
      <button
        v-show="!sectionCollapsed.points"
        class="mode-nav-item"
        :class="{ active: centerView !== 'writing' }"
        @click="store.openStudio(currentProjectId!)"
      >
        <span class="mode-nav-icon"><MessageSquareText :size="15" :stroke-width="1.75" /></span>
        <div class="point-nav-text">
          <span class="point-nav-name">创作对话</span>
          <span class="point-nav-desc">与作者讨论 · 补全骨架</span>
        </div>
      </button>

      <button
        v-show="!sectionCollapsed.points"
        class="mode-nav-item"
        :class="{ active: centerView === 'writing' }"
        aria-label="进入小说写作"
        @click="store.openWriting()"
      >
        <span class="mode-nav-icon"><BrainCircuit :size="15" :stroke-width="1.75" /></span>
        <div class="point-nav-text">
          <span class="point-nav-name">小说写作</span>
          <span class="point-nav-desc">{{ chapters.length ? `已写 ${chapters.length} 章` : '骨架就绪后开写' }}</span>
        </div>
      </button>
    </div>

    <!-- 对话历史：可打开续聊、可删除 -->
    <div class="conv-section">
      <div class="conv-header section-head">
        <span class="section-head-inner" @click="sectionCollapsed.convs = !sectionCollapsed.convs">
          <ChevronDown :size="12" :stroke-width="1.75" class="section-arrow" :class="{ folded: sectionCollapsed.convs }" />
          对话历史
        </span>
      </div>

      <div
        v-for="c in historyConversations"
        v-show="!sectionCollapsed.convs"
        :key="c.id"
        class="conv-item"
        :class="{ active: currentConversationId === c.id || (c.point === '__outline__' && centerView === 'outline' && outlineConvId === c.id) }"
        @click="openConv(c)"
      >
        <div class="conv-main">
          <span class="conv-title">{{ convLabel(c) }}</span>
          <span v-if="c.updated_at" class="conv-time">{{ relativeTime(c.updated_at) }}</span>
        </div>
        <button class="conv-delete" title="删除对话" :aria-label="`删除对话 ${convLabel(c)}`" @click.stop="handleDeleteConv(c.id)">
          <IconTrash :size="12" />
        </button>
      </div>

      <div v-if="historyConversations.length === 0 && !sectionCollapsed.convs" class="conv-empty">
        还没有对话记录
      </div>
    </div>
      </template>
  </aside>
</template>

<style scoped>
.conv-rename-input {
  flex: 1;
  min-width: 0;
  background: var(--bg-tertiary);
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  padding: 2px 6px;
  font-family: inherit;
  outline: none;
}
.conv-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.conv-time {
  font-size: 10px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conv-empty {
  padding: 10px 14px;
  font-size: 11px;
  line-height: 1.7;
  color: var(--text-muted);
  text-align: center;
}
.legacy-header {
  margin-top: 12px;
}
.assistant-section {
  padding: 8px 12px;
  border-top: 1px solid var(--border-color);
  flex-shrink: 0;
}
</style>
