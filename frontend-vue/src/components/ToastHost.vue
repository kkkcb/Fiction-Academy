<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import { runtimeErrors } from '../utils/errorReport'

interface ToastItem {
  id: number
  type: string
  message: string
  detail?: string
}

const store = useAppStore()
const { error } = storeToRefs(store)

const toasts = ref<ToastItem[]>([])
let idCounter = 0

function push(type: string, message: string, detail?: string) {
  const id = ++idCounter
  toasts.value.push({ id, type, message, detail })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, 6000)
}

watch(error, (newError) => {
  if (newError) {
    push('error', newError)
    store.error = null
  }
})

watch(runtimeErrors, (errs) => {
  if (errs.length > 0) {
    const latest = errs[errs.length - 1]
    const short = latest.message.length > 80 ? latest.message.slice(0, 80) + '...' : latest.message
    push('error', '⚠️ 渲染错误: ' + short, latest.stack)
  }
}, { deep: true })
</script>

<template>
  <Teleport to="body">
    <div class="toast-host" aria-live="polite" aria-atomic="true">
      <Transition-group name="toast" tag="div">
        <div
          v-for="t in toasts"
          :key="t.id"
          class="toast"
          :class="'toast-' + t.type"
          role="alert"
          @click="t.detail && console.log(t.detail)"
        >
          <span class="toast-icon" v-if="t.type === 'error'"><IconAlert :size="16" /></span>
          <span class="toast-icon" v-else-if="t.type === 'success'"><IconCheck :size="16" /></span>
          <span class="toast-icon" v-else><IconInfo :size="16" /></span>
          <span class="toast-msg">{{ t.message }}</span>
          <span v-if="t.detail" class="toast-hint">点击查看详情</span>
        </div>
      </Transition-group>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-host {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10000;
  display: flex;
  flex-direction: column;
  gap: 6px;
  pointer-events: none;
}
.toast {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  box-shadow: 0 4px 12px rgba(0,0,0,0.12);
  pointer-events: auto;
}
.toast-error {
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
}
.toast-success {
  background: #f0fdf4;
  color: #15803d;
  border: 1px solid #bbf7d0;
}
.toast-info {
  background: #f8fafc;
  color: #334155;
  border: 1px solid #e2e8f0;
}
.toast-icon { flex-shrink: 0; }
.toast-msg { flex: 1; }
.toast-hint { font-size: 10px; color: rgba(0,0,0,0.4); flex-shrink: 0; }

.toast-enter-from {
  opacity: 0;
  transform: translateY(-12px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateY(-8px) scale(0.96);
}
.toast-enter-active {
  transition: all 0.25s cubic-bezier(0.22, 1, 0.36, 1);
}
.toast-leave-active {
  transition: all 0.15s ease-in;
}
</style>
