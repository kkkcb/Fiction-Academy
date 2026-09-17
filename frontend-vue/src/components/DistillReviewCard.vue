<script setup lang="ts">
import { ref, computed } from 'vue'
import * as api from '../api'
import type { DistillReviewRecord, ID } from '../types'
import { useAppStore } from '../stores/app'
import { GitCompareArrows, Check } from 'lucide-vue-next'

const props = defineProps<{ record: DistillReviewRecord; projectId: ID }>()
const store = useAppStore()

type Decision = 'old' | 'new' | 'custom'
const decisions = ref<Record<number, Decision>>({})
const customs = ref<Record<number, string>>({})
const submitting = ref(false)
const doneCount = ref(0)
const error = ref('')

const allDecided = computed(() =>
  props.record.conflicts.every(c => decisions.value[c.id]))

async function submit() {
  if (!allDecided.value || submitting.value) return
  submitting.value = true
  error.value = ''
  try {
    const choices = props.record.conflicts
      .filter(c => decisions.value[c.id])
      .map(c => ({
        id: c.id,
        decision: decisions.value[c.id],
        custom_text: decisions.value[c.id] === 'custom' ? (customs.value[c.id] || '').trim() : undefined,
      }))
    const r = await api.resolveDistillConflicts(props.projectId, choices)
    doneCount.value = r.resolved
    // 刷新对话（总结消息）+ 工作区点位 + 总览摘要
    if (store.currentConversationId) await store.fetchMessages(store.currentConversationId)
    if (store.currentProjectId) {
      await store.fetchWorkspaceItems(store.currentProjectId)
      await store.fetchDistillDigest?.(store.currentProjectId)
    }
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="dr-card">
    <div class="dr-head">
      <GitCompareArrows :size="15" :stroke-width="1.75" class="dr-icon" />
      <span class="dr-title">设定冲突核对</span>
      <span class="dr-sub">新讨论与现有设定有 {{ record.conflicts.length }} 处分歧，取舍后写入点位</span>
    </div>

    <template v-if="!doneCount">
      <div v-for="c in record.conflicts" :key="c.id" class="dr-conflict">
        <div class="dr-point-chip">{{ c.label }}</div>
        <div class="dr-compare">
          <div class="dr-side dr-old">
            <span class="dr-side-tag">现有设定</span>
            <p>{{ c.old_summary }}</p>
          </div>
          <div class="dr-side dr-new">
            <span class="dr-side-tag">本轮新说法</span>
            <p>{{ c.new_summary }}</p>
          </div>
        </div>
        <p v-if="c.suggestion" class="dr-suggestion">融合建议：{{ c.suggestion }}</p>
        <div class="dr-decide" role="group" :aria-label="`${c.label}取舍`">
          <button
            class="dr-btn" :class="{ on: decisions[c.id] === 'old' }"
            @click="decisions = { ...decisions, [c.id]: 'old' }"
          >保留旧的</button>
          <button
            class="dr-btn" :class="{ on: decisions[c.id] === 'new' }"
            @click="decisions = { ...decisions, [c.id]: 'new' }"
          >用新的</button>
          <button
            class="dr-btn" :class="{ on: decisions[c.id] === 'custom' }"
            @click="decisions = { ...decisions, [c.id]: 'custom' }"
          >手动融合</button>
        </div>
        <textarea
          v-if="decisions[c.id] === 'custom'"
          v-model="customs[c.id]"
          class="dr-custom"
          rows="3"
          placeholder="写下这一条的最终版本（融合旧新、或另起炉灶）"
        ></textarea>
      </div>

      <div class="dr-foot">
        <span v-if="error" class="dr-error">{{ error }}</span>
        <span class="dr-flex"></span>
        <button class="btn btn-sm btn-primary" :disabled="!allDecided || submitting" @click="submit">
          <Check :size="12" :stroke-width="1.75" />
          {{ submitting ? '提交中…' : allDecided ? `确认取舍（${record.conflicts.length} 处）` : '每处先选一个' }}
        </button>
      </div>
    </template>

    <div v-else class="dr-done">
      ✅ 已按你的取舍更新 {{ doneCount }} 处设定，总结已并入对话与右侧总览。
    </div>
  </div>
</template>

<style scoped>
.dr-card {
  border: 1px solid var(--accent-border);
  border-radius: 12px;
  background: var(--bg-card);
  padding: 14px 16px;
}
.dr-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.dr-icon { color: var(--accent); }
.dr-title { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.dr-sub { font-size: 12px; color: var(--text-tertiary); }
.dr-conflict {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-color);
}
.dr-point-chip {
  display: inline-block;
  font-size: 11px;
  color: var(--accent);
  background: var(--accent-light);
  border-radius: var(--radius-full);
  padding: 2px 10px;
  margin-bottom: 8px;
}
.dr-compare { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.dr-side {
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.6;
}
.dr-side p { margin: 4px 0 0; color: var(--text-primary); word-break: break-word; }
.dr-old { background: var(--bg-secondary); border: 1px solid var(--border-color); }
.dr-new { background: var(--accent-lighter); border: 1px solid var(--accent-border); }
.dr-side-tag { font-size: 10.5px; color: var(--text-tertiary); }
.dr-suggestion { margin: 8px 0 0; font-size: 12px; color: var(--text-secondary); }
.dr-decide { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
.dr-btn {
  padding: 5px 12px;
  border-radius: var(--radius-full);
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}
.dr-btn:hover { border-color: var(--accent); color: var(--accent); }
.dr-btn.on { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
.dr-custom {
  width: 100%;
  box-sizing: border-box;
  margin-top: 8px;
  border-radius: 8px;
  border: 1px solid var(--accent-border);
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 12.5px;
  line-height: 1.6;
  padding: 8px 10px;
  outline: none;
  font-family: inherit;
  resize: vertical;
}
.dr-foot { display: flex; align-items: center; gap: 8px; margin-top: 14px; }
.dr-flex { flex: 1; }
.dr-error { font-size: 12px; color: var(--danger, #d9534f); }
.dr-done { margin-top: 10px; font-size: 12.5px; color: var(--text-secondary); }

@media (max-width: 640px) {
  .dr-compare { grid-template-columns: 1fr; }
}
</style>
