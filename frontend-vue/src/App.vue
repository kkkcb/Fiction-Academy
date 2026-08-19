<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from './stores/app'
import ProjectsPage from './components/ProjectsPage.vue'
import WorkspacePage from './components/WorkspacePage.vue'
import WritingPage from './components/WritingPage.vue'
import ToastHost from './components/ToastHost.vue'

const store = useAppStore()
const { route } = storeToRefs(store)

onMounted(() => {
  store.fetchProjects()
})
</script>

<template>
  <Transition name="page" mode="out-in">
    <ProjectsPage v-if="route === 'projects'" key="projects" />
    <WritingPage v-else-if="route === 'writing'" key="writing" />
    <WorkspacePage v-else key="workspace" />
  </Transition>
  <ToastHost />
</template>
