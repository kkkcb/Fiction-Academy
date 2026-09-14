<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import type { ID, Project } from '../types'
import { useAppStore } from '../stores/app'
import { relativeTime } from '../utils/format'
import MaterialLibrary from './MaterialLibrary.vue'
import AuthorPicker from './AuthorPicker.vue'
import PromptLibrary from './PromptLibrary.vue'
import { Flame, BookOpen, PenLine, BrainCircuit, ScrollText } from 'lucide-vue-next'

const store = useAppStore()
const { projects } = storeToRefs(store)

const showCreate = ref(false)
const mainView = ref<'novel' | 'materials' | 'prompts'>('novel')
const matRef = ref<InstanceType<typeof MaterialLibrary> | null>(null)

// 切回素材库时：超过 5 分钟静默刷新热榜（平时秒切，无感）
watch(mainView, v => {
  if (v === 'materials') matRef.value?.refreshIfStale?.()
})
const creating = ref(false)
const newName = ref('')
const newGenre = ref('')
const newAuthorKey = ref('')
const nameInputEl = ref<HTMLInputElement | null>(null)

const genres = ['玄幻', '都市', '科幻', '悬疑', '历史', '言情', '其他']

// 题材 → 作者人格 的联动预选（仅建议，用户可改选任何作者）
const GENRE_AUTHOR: Record<string, string> = {
  '玄幻': 'fanren',
  '都市': 'dushi',
  '科幻': 'kehuan',
  '悬疑': 'xuanyi',
}

const isEmpty = computed(() => projects.value.length === 0)

// 弹窗打开时自动聚焦名称输入框——否则用户的击键会丢失
watch(showCreate, async (v) => {
  if (v) {
    await nextTick()
    nameInputEl.value?.focus()
    store.fetchAuthors()
  }
})

// 选题材时联动预选对应作者（没映射的题材不预选，用户自己挑）
function pickGenre(g: string) {
  newGenre.value = g
  const suggested = GENRE_AUTHOR[g]
  if (suggested && !newAuthorKey.value) newAuthorKey.value = suggested
}

function timeText(p: Project) {
  return relativeTime(p.updated_at)
}

function openProject(p: Project) {
  // 记住每本书上次的模式（骨架工作台 / 小说创作），进入零选择成本
  store.openProject(p.id)
}

function openProjectAt(p: Project, mode: 'workspace' | 'writing') {
  store.navigateTo(mode, { currentProjectId: p.id })
}

function closeCreate() {
  showCreate.value = false
}

async function handleCreate() {
  if (creating.value) return
  if (!newAuthorKey.value) return // 作者必选：没有文风不让建项目
  creating.value = true
  try {
    // 名称可留空：后端默认「未命名作品」，确定故事核后 AI 自动命名
    const p = await store.createProject(newName.value.trim(), newGenre.value || '', undefined, newAuthorKey.value)
    if (p) {
      newName.value = ''
      newGenre.value = ''
      newAuthorKey.value = ''
      showCreate.value = false
    }
  } finally {
    creating.value = false
  }
}

// ---- 重命名 ----
const renamingProject = ref<Project | null>(null)
const renameName = ref('')
const renameSaving = ref(false)
const renameInputEl = ref<HTMLInputElement | null>(null)

watch(renamingProject, async (p) => {
  if (p) {
    await nextTick()
    renameInputEl.value?.focus()
    renameInputEl.value?.select()
  }
})

function startRename(p: Project) {
  renamingProject.value = p
  renameName.value = p.name === '未命名作品' ? '' : p.name
}

async function doRename() {
  const p = renamingProject.value
  const name = renameName.value.trim()
  if (!p || !name || renameSaving.value || name === p.name) {
    if (p && name === p.name) renamingProject.value = null
    return
  }
  renameSaving.value = true
  try {
    await store.renameProject(p.id, name)
    renamingProject.value = null
  } finally {
    renameSaving.value = false
  }
}

async function handleDelete(id: ID) {
  if (confirm('确定删除这个项目？所有对话和设定将永久丢失。')) {
    await store.deleteProject(id)
  }
}

function onEsc(e: KeyboardEvent) {
  if (e.key !== 'Escape') return
  if (showCreate.value) closeCreate()
  else if (renamingProject.value) renamingProject.value = null
}
onMounted(() => window.addEventListener('keydown', onEsc))
onUnmounted(() => window.removeEventListener('keydown', onEsc))
</script>

<template>
  <div class="projects-shell">
    <!-- 左侧工具栏：小说创作 / 素材库 / 提示词库 -->
    <nav class="app-rail" aria-label="主导航">
      <div class="app-rail-brand">
        <BrainCircuit :size="20" :stroke-width="1.75" />
      </div>
      <button
        class="rail-item"
        :class="{ active: mainView === 'novel' }"
        aria-label="小说创作"
        title="小说创作"
        @click="mainView = 'novel'"
      >
        <PenLine :size="18" :stroke-width="1.75" />
        <span class="rail-label">小说创作</span>
      </button>
      <button
        class="rail-item"
        :class="{ active: mainView === 'materials' }"
        aria-label="素材库"
        title="热点素材库"
        @click="mainView = 'materials'"
      >
        <Flame :size="18" :stroke-width="1.75" />
        <span class="rail-label">素材库</span>
      </button>
      <button
        class="rail-item"
        :class="{ active: mainView === 'prompts' }"
        aria-label="提示词库"
        title="提示词库（全环节系统提示词统一管理）"
        @click="mainView = 'prompts'"
      >
        <ScrollText :size="18" :stroke-width="1.75" />
        <span class="rail-label">提示词库</span>
      </button>
    </nav>

    <!-- 素材库页面（常驻不卸载，切换即时渲染） -->
    <MaterialLibrary v-show="mainView === 'materials'" ref="matRef" variant="page" class="rail-content mat-host" />

    <!-- 提示词库：全环节提示词统一查看/复制/优化 -->
    <PromptLibrary v-if="mainView === 'prompts'" class="rail-content" />

    <!-- 小说创作（项目列表） -->
    <div v-if="mainView === 'novel'" class="projects-page rail-content">
    <div class="projects-header">
      <h1 class="projects-title">Fiction Academy</h1>
      <p class="projects-subtitle">沉浸式 AI 小说创作平台</p>
      <!-- 空列表时由空状态的 CTA 作为唯一入口，避免出现两个创建按钮 -->
      <div class="projects-header-actions">
        <button v-if="!isEmpty" class="btn btn-primary" aria-label="新建项目" @click="showCreate = true">+ 新建项目</button>
      </div>
    </div>

    <div v-if="isEmpty" class="projects-empty">
      <BookOpen class="projects-empty-icon" :size="40" :stroke-width="1.25" />
      <div class="projects-empty-title">开始你的第一部作品</div>
      <div class="projects-empty-desc">创建项目后，AI 策划会通过五个点位引导你搭出完整故事骨架，再进入章节创作。</div>
      <button class="btn btn-primary" aria-label="新建项目" @click="showCreate = true">创建第一个项目</button>
    </div>

    <div v-else class="projects-grid">
      <div v-for="p in projects" :key="p.id" class="project-card" role="button" tabindex="0" :aria-label="`打开项目 ${p.name}`" @click="openProject(p)" @keydown.enter="openProject(p)" @keydown.space.prevent="openProject(p)">
        <div class="project-card-header">
          <span class="project-genre">{{ p.genre || '其他' }}</span>
        </div>
        <h3 class="project-name">{{ p.name }}</h3>
        <div class="project-card-footer">
          <span class="project-time">{{ timeText(p) }}</span>
          <div class="project-card-ops">
            <button class="btn btn-sm project-quick" :aria-label="`进入${p.name}骨架工作台`" title="骨架工作台（点位/设定/图谱）" @click.stop="openProjectAt(p, 'workspace')">骨架</button>
            <button class="btn btn-sm project-quick" :aria-label="`进入${p.name}小说创作`" title="小说创作（章节写作）" @click.stop="openProjectAt(p, 'writing')">写作</button>
            <button class="btn btn-sm" :aria-label="`重命名项目 ${p.name}`" @click.stop="startRename(p)">重命名</button>
            <button class="btn btn-sm project-delete" :aria-label="`删除项目 ${p.name}`" @click.stop="handleDelete(p.id)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showCreate" class="modal-overlay" @click.self="closeCreate">
      <div class="modal-card">
        <h3>新建项目</h3>
        <input
          ref="nameInputEl"
          v-model="newName"
          class="modal-input"
          placeholder="书名（可留空，AI 会在确定故事核时起名）"
          @keydown.enter="handleCreate"
        />
        <div class="genre-pills" role="radiogroup" aria-label="选择类型（可跳过，后续对话确认）">
          <button
            v-for="g in genres"
            :key="g"
            class="genre-pill"
            :class="{ active: newGenre === g }"
            role="radio"
            :aria-checked="newGenre === g"
            @click="pickGenre(g)"
          >{{ g }}</button>
        </div>
        <div class="create-author-section">
          <div class="create-author-title">选择作者人格 <span class="req-star">*</span>——决定对话与执笔的文风</div>
          <AuthorPicker v-model="newAuthorKey" />
        </div>
        <div class="modal-actions">
          <button class="btn" aria-label="取消" @click="closeCreate">取消</button>
          <button class="btn btn-primary" :disabled="creating || !newAuthorKey" @click="handleCreate">{{ creating ? '创建中…' : '创建' }}</button>
        </div>
      </div>
    </div>

    <div v-if="renamingProject" class="modal-overlay" @click.self="renamingProject = null">
      <div class="modal-card">
        <h3>重命名项目</h3>
        <input
          ref="renameInputEl"
          v-model="renameName"
          class="modal-input"
          placeholder="新的书名"
          maxlength="40"
          @keydown.enter="doRename"
        />
        <div class="modal-actions">
          <button class="btn" :disabled="renameSaving" @click="renamingProject = null">取消</button>
          <button class="btn btn-primary" :disabled="renameSaving || !renameName.trim()" @click="doRename">{{ renameSaving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

<style scoped>
.create-author-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}
.req-star {
  color: var(--accent);
}
/* 创建弹窗装下 6 张作者卡片：限宽 + 内部滚动 */
.modal-card {
  max-height: 86vh;
  overflow-y: auto;
  max-width: 640px;
}
</style>
