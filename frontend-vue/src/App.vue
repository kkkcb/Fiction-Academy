<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from './stores/app'
import ProjectsPage from './components/ProjectsPage.vue'
import WorkspacePage from './components/WorkspacePage.vue'
import WritingPage from './components/WritingPage.vue'
import ToastHost from './components/ToastHost.vue'
import PinPanel from './components/PinPanel.vue'

const store = useAppStore()
const { route } = storeToRefs(store)

onMounted(() => {
  store.fetchProjects()
})
</script>

<template>
  <!-- 不加路由过渡动画：页面处于后台/被遮挡时 Vue 过渡的 rAF 会停转，
       leave 阶段永久卡住，表现为「点了没反应」。瞬时切换最稳。 -->
  <ProjectsPage v-if="route === 'projects'" />
  <WritingPage v-else-if="route === 'writing'" />
  <WorkspacePage v-else />
  <ToastHost />
  <PinPanel />
</template>
