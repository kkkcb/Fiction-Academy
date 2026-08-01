<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from './stores/app'
import ProjectsPage from './components/ProjectsPage.vue'
import WorkspacePage from './components/WorkspacePage.vue'
import ToastHost from './components/ToastHost.vue'

const store = useAppStore()
const { route } = storeToRefs(store)

const toastHost = ref<InstanceType<typeof ToastHost> | null>(null)

onMounted(() => {
  store.fetchProjects()
})
</script>

<template>
  <Transition name="page" mode="out-in">
    <ProjectsPage v-if="route === 'projects'" key="projects" />
    <WorkspacePage v-else key="workspace" />
  </Transition>
  <ToastHost ref="toastHost" />
</template>
