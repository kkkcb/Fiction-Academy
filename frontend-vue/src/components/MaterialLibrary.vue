<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import * as api from '../api'
import type { HotItem, Material } from '../api'
import { relativeTime } from '../utils/format'
import { Flame, Bookmark, BookmarkCheck, Trash2, RefreshCw, ExternalLink, PenLine, X } from 'lucide-vue-next'

const props = withDefaults(defineProps<{ variant?: 'modal' | 'page' }>(), { variant: 'modal' })
const emit = defineEmits<{ (e: 'close'): void }>()
const store = useAppStore()
const isPage = computed(() => props.variant === 'page')

const tab = ref<'hot' | 'saved'>('hot')
const SOURCES = [
  { key: 'douyin', label: '抖音热点' },
  { key: 'weibo', label: '微博热搜' },
  { key: 'zhihu', label: '知乎热榜' },
]
const activeSource = ref('douyin')
const hotLoading = ref(false)
const hotLabel = ref('')
const hotItems = ref<HotItem[]>([])
const savedIds = ref<Set<string>>(new Set())

const materials = ref<Material[]>([])
const savedLoading = ref(false)
const creatingId = ref<string | null>(null)

const savedKey = (title: string, source: string) => `${source}::${title}`

async function loadHot() {
  hotLoading.value = true
  try {
    const r = await api.getHotList(activeSource.value)
    hotLabel.value = r.label
    hotItems.value = r.items
    if (r.stale) store.error = '热榜刷新失败，以下为缓存数据'
  } catch (e) {
    store.error = `热榜获取失败：${(e as Error).message}`
  } finally {
    hotLoading.value = false
  }
}

async function loadMaterials() {
  savedLoading.value = true
  try {
    materials.value = await api.listMaterials()
    savedIds.value = new Set(materials.value.map(m => savedKey(m.title || '', m.source || '')))
  } finally {
    savedLoading.value = false
  }
}

function switchSource(key: string) {
  if (activeSource.value === key) return
  activeSource.value = key
  loadHot()
}

async function collect(item: HotItem) {
  try {
    await api.createMaterial({
      title: item.title, source: activeSource.value, url: item.url, hot: item.hot,
    })
    savedIds.value.add(savedKey(item.title, activeSource.value))
    store.notifySuccess('已收藏到素材库')
  } catch (e) {
    store.error = (e as Error).message
  }
}

async function removeMaterial(id: string) {
  if (!confirm('删除这条素材？')) return
  await api.deleteMaterial(id)
  await loadMaterials()
}

async function createFromMaterial(m: Material) {
  creatingId.value = m.id
  try {
    const p = await store.createProject(m.title.slice(0, 20), '')
    if (p) {
      emit('close')
      store.navigateTo('workspace', { currentProjectId: p.id })
    }
  } finally {
    creatingId.value = null
  }
}

function onEsc(e: KeyboardEvent) {
  if (e.key === 'Escape' && !isPage.value) emit('close')
}
onMounted(() => {
  window.addEventListener('keydown', onEsc)
  loadHot()
  loadMaterials()
})
onUnmounted(() => window.removeEventListener('keydown', onEsc))
</script>

<template>
  <div :class="isPage ? 'mat-page' : 'modal-overlay show'" @click.self="!isPage && emit('close')">
    <div class="mat-library" :class="{ 'mat-page-card': isPage }">
      <div class="mat-head">
        <div class="mat-title"><Flame :size="16" :stroke-width="1.75" /> 热点素材库</div>
        <button v-if="!isPage" class="btn btn-sm" aria-label="关闭素材库" @click="emit('close')">
          <X :size="14" :stroke-width="1.75" />
        </button>
      </div>

      <div class="mat-tabs">
        <button class="mat-tab" :class="{ active: tab === 'hot' }" @click="tab = 'hot'">
          <Flame :size="13" :stroke-width="1.75" /> 实时热榜
        </button>
        <button class="mat-tab" :class="{ active: tab === 'saved' }" @click="tab = 'saved'">
          <Bookmark :size="13" :stroke-width="1.75" /> 我的收藏（{{ materials.length }}）
        </button>
      </div>

      <div v-if="tab === 'hot'" class="mat-body">
        <div class="mat-source-row">
          <button
            v-for="s in SOURCES"
            :key="s.key"
            class="mat-source"
            :class="{ active: activeSource === s.key }"
            @click="switchSource(s.key)"
          >{{ s.label }}</button>
          <button class="btn btn-sm mat-refresh" :disabled="hotLoading" aria-label="刷新热榜" @click="loadHot">
            <RefreshCw :size="12" :stroke-width="1.75" :class="{ spinning: hotLoading }" />
          </button>
        </div>
        <div v-if="hotLoading && !hotItems.length" class="mat-loading">热榜加载中…</div>
        <div v-else class="mat-list">
          <div v-for="(item, i) in hotItems" :key="i" class="mat-item">
            <span class="mat-rank" :class="{ top: i < 3 }">{{ i + 1 }}</span>
            <div class="mat-item-main">
              <a v-if="item.url" :href="item.url" target="_blank" class="mat-item-title" rel="noopener noreferrer">
                {{ item.title }} <ExternalLink :size="10" :stroke-width="1.75" class="mat-ext" />
              </a>
              <span v-else class="mat-item-title">{{ item.title }}</span>
              <span v-if="item.hot" class="mat-hot">{{ item.hot }}</span>
            </div>
            <button
              class="btn btn-sm mat-collect"
              :class="{ done: savedIds.has(activeSource + '::' + item.title) }"
              :aria-label="`收藏 ${item.title}`"
              @click="collect(item)"
            >
              <BookmarkCheck v-if="savedIds.has(activeSource + '::' + item.title)" :size="13" :stroke-width="1.75" />
              <Bookmark v-else :size="13" :stroke-width="1.75" />
            </button>
          </div>
        </div>
      </div>

      <!-- 收藏 -->
      <div v-else class="mat-body">
        <div v-if="savedLoading" class="mat-loading">加载中…</div>
        <div v-else-if="!materials.length" class="mat-empty">
          <Bookmark :size="28" :stroke-width="1.5" />
          <div>还没有收藏的素材</div>
          <div class="mat-empty-hint">去「实时热榜」把感兴趣的事件收藏进来</div>
        </div>
        <div v-else class="mat-list">
          <div v-for="m in materials" :key="m.id" class="mat-item">
            <span class="mat-rank">{{ (SOURCES.find(s => s.key === m.source)?.label || m.source || '热点').slice(0, 2) }}</span>
            <div class="mat-item-main">
              <a v-if="m.url" :href="m.url" target="_blank" class="mat-item-title" rel="noopener noreferrer">{{ m.title }}</a>
              <span v-else class="mat-item-title">{{ m.title }}</span>
              <span class="mat-meta">
                <span v-if="m.hot">{{ m.hot }}</span>
                <span v-if="m.created_at">{{ relativeTime(m.created_at) }}</span>
              </span>
            </div>
            <button
              class="btn btn-sm mat-create"
              :disabled="creatingId === m.id"
              :aria-label="`以 ${m.title} 为题创作`"
              title="以此为题创建新书"
              @click="createFromMaterial(m)"
            >
              <PenLine :size="13" :stroke-width="1.75" />
              {{ creatingId === m.id ? '创建中…' : '创作' }}
            </button>
            <button class="btn btn-sm mat-del" aria-label="删除素材" @click="removeMaterial(m.id)">
              <Trash2 :size="13" :stroke-width="1.75" />
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mat-library {
  width: min(560px, 92vw);
  max-height: 82vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.28);
  overflow: hidden;
}
.mat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-subtle);
}
.mat-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-serif), serif;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}
.mat-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 16px 0;
}
.mat-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
}
.mat-tab.active {
  background: var(--accent-lighter);
  color: var(--accent);
  font-weight: 600;
}
.mat-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 10px 16px 16px;
}
.mat-source-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}
.mat-source {
  padding: 4px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  font-family: inherit;
  cursor: pointer;
}
.mat-source.active {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-lighter);
}
.mat-refresh { margin-left: auto; }
.spinning { animation: matSpin 0.9s linear infinite; }
@keyframes matSpin { to { transform: rotate(360deg); } }
.mat-loading, .mat-empty {
  padding: 40px 0;
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.mat-empty-hint { font-size: 11px; opacity: 0.7; }
.mat-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.mat-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
}
.mat-item:hover { background: var(--bg-secondary); }
.mat-rank {
  flex-shrink: 0;
  width: 22px;
  text-align: center;
  font-family: var(--font-mono), monospace;
  font-size: 11px;
  color: var(--text-muted);
}
.mat-rank.top { color: var(--accent); font-weight: 700; }
.mat-item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.mat-item-title {
  font-size: 13px;
  color: var(--text-primary);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
a.mat-item-title:hover { color: var(--accent); }
.mat-ext { opacity: 0.4; vertical-align: baseline; }
.mat-hot, .mat-meta {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--text-muted);
  display: inline-flex;
  gap: 8px;
}
.mat-collect.done { color: var(--accent); }
.mat-create { flex-shrink: 0; display: inline-flex; align-items: center; gap: 4px; }
.mat-del { flex-shrink: 0; color: #dc2626; }

/* ===== 页面模式（首页左栏内容区） ===== */
.mat-page {
  display: flex;
  width: 100%;
  height: 100%;
}
.mat-page-card {
  flex: 1;
  width: auto;
  max-height: none;
  box-shadow: none;
}
</style>
