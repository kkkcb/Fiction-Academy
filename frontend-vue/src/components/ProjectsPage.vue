<script setup lang="ts">
import { ref, computed } from 'vue'
import { storeToRefs } from 'pinia'
import type { ID, Project } from '../types'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const { projects, currentProjectId } = storeToRefs(store)

const showCreate = ref(false)
const newName = ref('')
const newGenre = ref('玄幻')

const genres = ['玄幻', '都市', '科幻', '悬疑', '历史', '言情', '其他']

function openProject(p: Project) {
  store.navigateTo('workspace', { currentProjectId: p.id })
}

async function handleCreate() {
  if (!newName.value.trim()) return
  await store.createProject(newName.value.trim(), newGenre.value)
  newName.value = ''
  showCreate.value = false
}

async function handleDelete(id: ID) {
  if (confirm('确定删除这个项目？所有对话和设定将永久丢失。')) {
    await store.deleteProject(id)
  }
}
</script>

<template>
  <div class="projects-page">
    <div class="projects-header">
      <h1 class="projects-title">Fiction Academy</h1>
      <p class="projects-subtitle">沉浸式 AI 小说创作平台</p>
      <button class="btn btn-primary" aria-label="新建项目" @click="showCreate = true">+ 新建项目</button>
    </div>

    <div class="projects-grid">
      <div v-for="p in projects" :key="p.id" class="project-card" role="button" tabindex="0" :aria-label="`打开项目 ${p.name}`" @click="openProject(p)" @keydown.enter="openProject(p)" @keydown.space.prevent="openProject(p)">
        <div class="project-card-header">
          <span class="project-genre">{{ p.genre || '其他' }}</span>
        </div>
        <h3 class="project-name">{{ p.name }}</h3>
        <button class="btn btn-sm project-delete" :aria-label="`删除项目 ${p.name}`" @click.stop="handleDelete(p.id)">删除</button>
      </div>
    </div>

    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal-card">
        <h3>新建项目</h3>
        <input v-model="newName" class="modal-input" placeholder="项目名称" @keydown.enter="handleCreate" />
        <select v-model="newGenre" class="modal-input">
          <option v-for="g in genres" :key="g" :value="g">{{ g }}</option>
        </select>
        <div class="modal-actions">
          <button class="btn" aria-label="取消" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" aria-label="创建项目" @click="handleCreate">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>
