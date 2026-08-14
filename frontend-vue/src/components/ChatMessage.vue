<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Message, WorkspaceItemType } from '../types'
import { formatMd, formatContent, parseCommand, parseConsultRecord } from '../utils/format'
import { useAppStore } from '../stores/app'
import ThinkingBlock from './ThinkingBlock.vue'
import ConsultFlow from './ConsultFlow.vue'
import IconTarget from './icons/IconTarget.vue'
import IconBolt from './icons/IconBolt.vue'

const props = withDefaults(defineProps<{ message: Message; index: number; isLastAssistant?: boolean; isStreaming?: boolean }>(), {
  isLastAssistant: false,
  isStreaming: false,
})
const emit = defineEmits<{
  (e: 'copy-msg', index: number): void
  (e: 'regenerate', index: number): void
}>()

const store = useAppStore()

const m = computed(() => props.message)
const cmd = computed(() => m.value.role === 'user' ? parseCommand(m.value.content) : null)
const record = computed(() => m.value.role === 'assistant' ? parseConsultRecord(m.value.content) : null)
const isUser = computed(() => m.value.role === 'user')
const showRegenerate = computed(() => props.isLastAssistant && !props.isStreaming)

const userHtml = computed(() => formatContent(m.value.content))
const assistantHtml = computed(() => formatMd(m.value.content))

function onCopy() { emit('copy-msg', props.index) }
function onRegenerate() { emit('regenerate', props.index) }

const showPinModal = ref(false)
const pinType = ref<WorkspaceItemType>('story_core')
const pinTitle = ref('')
const pinSaving = ref(false)
const pinTypes: { value: WorkspaceItemType; label: string }[] = [
  { value: 'story_core', label: '核心设定' },
  { value: 'world_setting', label: '世界观' },
  { value: 'character_setting', label: '角色设定' },
  { value: 'outline', label: '大纲' },
  { value: 'foreshadow', label: '伏笔' },
]
function onPin() {
  pinTitle.value = ''
  pinType.value = 'story_core'
  showPinModal.value = true
}
async function doPin() {
  if (!store.currentProjectId) return
  pinSaving.value = true
  try {
    await store.createWorkspaceItem(store.currentProjectId, {
      item_type: pinType.value,
      title: pinTitle.value.trim() || m.value.content.slice(0, 16),
      content: m.value.content,
      status: 'draft',
    })
    showPinModal.value = false
  } finally {
    pinSaving.value = false
  }
}
</script>

<template>
  <div v-if="cmd" class="msg user msg-command" :data-cmd="cmd.type">
    <div class="msg-role">你</div>
    <div class="command-card">
      <div class="command-header">
        <span class="command-icon">{{ cmd.icon }}</span>
        <span class="command-label">{{ cmd.label }}</span>
      </div>
      <div class="command-body" v-html="formatContent(cmd.idea)"></div>
    </div>
  </div>

  <div v-else-if="record" class="msg assistant msg-consult">
    <div class="msg-role">专家圆桌</div>
    <div class="msg-content consult-flow">
      <ConsultFlow :record="record" />
    </div>
    <div v-if="!isStreaming" class="msg-actions">
      <button class="btn btn-sm" title="复制裁决" @click="onCopy">复制裁决</button>
    </div>
  </div>

  <div v-else class="msg" :class="m.role">
    <div class="msg-role">{{ isUser ? '你' : 'AI' }}</div>
    <div class="msg-content markdown-body">
      <ThinkingBlock v-if="!isUser && m.thinking" :text="m.thinking" :streaming="false" />
      <div v-if="isUser" v-html="userHtml"></div>
      <div v-else v-html="assistantHtml"></div>
    </div>
    <div v-if="!isUser" class="msg-actions">
      <button class="btn btn-sm" title="复制" aria-label="复制消息" @click="onCopy">复制</button>
      <button class="btn btn-sm" title="沉淀到工作台" aria-label="将此回复沉淀到工作台" @click="onPin">沉淀</button>
      <button v-if="showRegenerate" class="btn btn-sm" title="重新生成" aria-label="重新生成回复" @click="onRegenerate">重新生成</button>
    </div>
    <Teleport to="body">
      <div v-if="showPinModal" class="modal-overlay show" @click.self="showPinModal = false">
        <div class="modal-card">
          <h3>沉淀到工作台</h3>
          <label class="pin-label">类型</label>
          <select v-model="pinType" class="modal-input">
            <option v-for="t in pinTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
          <label class="pin-label">标题（可选）</label>
          <input v-model="pinTitle" class="modal-input" placeholder="留空则取内容前16字" @keydown.enter="doPin" />
          <div class="modal-actions">
            <button class="btn" :disabled="pinSaving" @click="showPinModal = false">取消</button>
            <button class="btn btn-primary" :disabled="pinSaving" @click="doPin">{{ pinSaving ? '保存中…' : '沉淀' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
