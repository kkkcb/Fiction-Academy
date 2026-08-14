<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import type { GoalStep, GoalDimension } from '../types'

const store = useAppStore()
const { currentProjectId, goalState, goalLoading } = storeToRefs(store)

const DIM_STATUS_ICON: Record<string, string> = { complete: '✅', partial: '⚠️', missing: '❌' }
const STEP_ICON: Record<string, string> = { pending: '⬜', executing: '▶️', completed: '✅', skipped: '⏭️' }

const hasGoal = computed(() => goalState.value !== null)
const isPlanning = computed(() => goalState.value?.status === 'planning')
const isExecuting = computed(() => goalState.value?.status === 'executing')
const isCompleted = computed(() => goalState.value?.status === 'completed')

const dimensions = computed<GoalDimension[]>(() => goalState.value?.analysis?.dimensions ?? [])
const completionRate = computed(() => {
  const r = goalState.value?.analysis?.completion_rate ?? 0
  return Math.round(r * 100)
})
const progressPercent = computed(() => {
  if (!goalState.value) return 0
  const steps = goalState.value.steps
  const done = steps.filter(s => s.status === 'completed' || s.status === 'skipped').length
  return Math.round((done / Math.max(steps.length, 1)) * 100)
})
const currentStepIndex = computed(() => goalState.value?.current_step ?? 0)

const editingSteps = ref<GoalStep[]>([])
const showEdit = ref(false)

watch(() => goalState.value?.steps, (steps) => {
  if (steps) editingSteps.value = JSON.parse(JSON.stringify(steps))
}, { immediate: true })

function startEdit() {
  editingSteps.value = JSON.parse(JSON.stringify(goalState.value?.steps ?? []))
  showEdit.value = true
}

async function saveEdit() {
  if (!goalState.value || !currentProjectId.value) return
  await store.confirmGoalPlan(currentProjectId.value, goalState.value.goal_id, editingSteps.value)
  showEdit.value = false
}

async function confirmPlan() {
  if (!goalState.value || !currentProjectId.value) return
  await store.confirmGoalPlan(currentProjectId.value, goalState.value.goal_id)
}

const stepInput = ref('')
async function executeStep(idx: number) {
  if (!goalState.value || !currentProjectId.value) return
  const input = stepInput.value.trim()
  stepInput.value = ''
  await store.executeGoalStep(currentProjectId.value, goalState.value.goal_id, idx, input)
}

async function skipStep(idx: number) {
  if (!goalState.value || !currentProjectId.value) return
  await store.skipGoalStep(currentProjectId.value, goalState.value.goal_id, idx)
}

async function cancel() {
  if (!goalState.value || !currentProjectId.value) return
  await store.cancelGoal(currentProjectId.value, goalState.value.goal_id)
}

function close() {
  store.clearGoal()
}

function removeStep(idx: number) {
  editingSteps.value.splice(idx, 1)
  editingSteps.value.forEach((s, i) => { s.index = i })
}
function addStep() {
  editingSteps.value.push({
    index: editingSteps.value.length, title: '新步骤', dimension: '', description: '',
    step_type: 'generate', questions: [], status: 'pending', result: '', saved_item_id: null,
  })
}
</script>

<template>
  <div class="goal-panel">
    <div v-if="!hasGoal" class="goal-empty">
      <div class="goal-empty-icon">🎯</div>
      <p class="goal-empty-title">目标模式</p>
      <p class="goal-empty-hint">在输入框使用 <code>/goal 目标描述</code> 启动</p>
      <p class="goal-empty-hint">AI 将自主拆解任务、逐步执行、保存到工作台</p>
    </div>

    <template v-else>
      <div class="goal-header">
        <span class="goal-badge">{{ goalState!.goal_type }}</span>
        <span class="goal-desc">{{ goalState!.description }}</span>
        <button v-if="!isCompleted" class="btn btn-sm" title="取消" @click="cancel">取消</button>
        <button v-else class="btn btn-sm" title="关闭" @click="close">关闭</button>
      </div>

      <div v-if="isPlanning" class="goal-section">
        <div class="goal-section-title">📊 完整性分析</div>
        <div class="goal-rate-bar">
          <div class="goal-rate-fill" :style="{ width: completionRate + '%' }"></div>
          <span class="goal-rate-text">{{ completionRate }}%</span>
        </div>
        <div class="goal-dims">
          <div v-for="dim in dimensions" :key="dim.name" class="goal-dim" :class="dim.status">
            <span class="goal-dim-icon">{{ DIM_STATUS_ICON[dim.status] || '❓' }}</span>
            <span class="goal-dim-name">{{ dim.name }}</span>
            <span class="goal-dim-detail">{{ dim.detail }}</span>
          </div>
        </div>
      </div>

      <div v-if="isPlanning" class="goal-section">
        <div class="goal-section-title">
          📋 执行计划（{{ goalState!.steps.length }}步）
          <button class="btn-link" @click="startEdit">编辑</button>
        </div>
        <div class="goal-steps">
          <div v-for="(step, idx) in goalState!.steps" :key="idx" class="goal-step-item planning">
            <span class="goal-step-num">{{ idx + 1 }}</span>
            <div class="goal-step-body">
              <div class="goal-step-title">{{ step.title }}</div>
              <div class="goal-step-desc">{{ step.description }}</div>
            </div>
          </div>
        </div>
        <div class="goal-plan-actions">
          <button class="btn btn-primary" :disabled="goalLoading" @click="confirmPlan">
            {{ goalLoading ? '准备中…' : '开始执行' }}
          </button>
        </div>
      </div>

      <div v-if="isExecuting" class="goal-section">
        <div class="goal-section-title">📊 执行进度</div>
        <div class="goal-rate-bar">
          <div class="goal-rate-fill executing" :style="{ width: progressPercent + '%' }"></div>
          <span class="goal-rate-text">{{ progressPercent }}%</span>
        </div>
        <div class="goal-steps">
          <div
            v-for="(step, idx) in goalState!.steps"
            :key="idx"
            class="goal-step-item"
            :class="step.status"
          >
            <span class="goal-step-icon">{{ STEP_ICON[step.status] }}</span>
            <div class="goal-step-body">
              <div class="goal-step-title">{{ step.title }}</div>
              <div v-if="step.status === 'completed' && step.result" class="goal-step-result markdown-body">
                {{ step.result.slice(0, 200) }}{{ step.result.length > 200 ? '…' : '' }}
              </div>
              <div v-if="step.status === 'completed' && step.saved_item_id" class="goal-step-saved">
                已保存到工作台
              </div>
            </div>
            <div v-if="step.status === 'pending' && idx === currentStepIndex" class="goal-step-actions">
              <textarea
                v-model="stepInput"
                class="goal-step-input"
                placeholder="补充信息（可选，留空则AI自主生成）"
                rows="2"
              ></textarea>
              <div class="goal-step-buttons">
                <button class="btn btn-sm" :disabled="goalLoading" @click="skipStep(idx)">跳过</button>
                <button class="btn btn-sm btn-primary" :disabled="goalLoading" @click="executeStep(idx)">
                  {{ goalLoading ? '执行中…' : '执行' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="isCompleted" class="goal-section">
        <div class="goal-section-title">🎉 目标完成</div>
        <div class="goal-summary markdown-body">{{ goalState!.summary }}</div>
        <div class="goal-plan-actions">
          <button class="btn btn-primary" @click="close">完成</button>
        </div>
      </div>

      <Teleport to="body">
        <div v-if="showEdit" class="modal-overlay show" @click.self="showEdit = false">
          <div class="modal-card modal-wide">
            <h3>编辑执行计划</h3>
            <div class="edit-steps">
              <div v-for="(step, idx) in editingSteps" :key="idx" class="edit-step">
                <input v-model="step.title" class="modal-input" placeholder="步骤标题" />
                <input v-model="step.description" class="modal-input" placeholder="步骤说明" />
                <button class="btn btn-sm btn-danger" @click="removeStep(idx)">删除</button>
              </div>
            </div>
            <button class="btn btn-sm" @click="addStep">+ 添加步骤</button>
            <div class="modal-actions">
              <button class="btn" @click="showEdit = false">取消</button>
              <button class="btn btn-primary" @click="saveEdit">保存计划</button>
            </div>
          </div>
        </div>
      </Teleport>
    </template>
  </div>
</template>

<style scoped>
.goal-panel { display: flex; flex-direction: column; height: 100%; gap: 8px; overflow-y: auto; padding: 0 12px 12px; }
.goal-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  flex: 1; text-align: center; gap: 4px; padding: 40px 20px;
}
.goal-empty-icon { font-size: 36px; opacity: 0.6; }
.goal-empty-title { font-family: var(--font-serif), serif; font-size: 15px; color: var(--text-primary); margin: 8px 0 4px; }
.goal-empty-hint { font-size: 11px; color: var(--text-muted); line-height: 1.6; }
.goal-empty-hint code { background: var(--bg-secondary); padding: 1px 6px; border-radius: var(--radius-sm); font-size: 10px; }
.goal-header {
  display: flex; align-items: center; gap: 8px; padding: 8px 0;
  border-bottom: 1px solid var(--border-color);
}
.goal-badge {
  font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: var(--radius-full);
  background: var(--accent-lighter); color: var(--accent); white-space: nowrap;
}
.goal-desc { font-size: 13px; color: var(--text-primary); flex: 1; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.goal-section { padding: 8px 0; }
.goal-section-title {
  font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px;
  display: flex; align-items: center; justify-content: space-between;
}
.goal-rate-bar {
  position: relative; height: 20px; background: var(--bg-secondary); border-radius: var(--radius-full);
  overflow: hidden; margin-bottom: 10px;
}
.goal-rate-fill {
  height: 100%; background: var(--accent); border-radius: var(--radius-full);
  transition: width 0.5s var(--ease-out);
}
.goal-rate-fill.executing { background: linear-gradient(90deg, var(--accent), #d97706); }
.goal-rate-text {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  font-size: 10px; font-weight: 600; color: var(--text-primary); font-family: var(--font-mono), monospace;
}
.goal-dims { display: flex; flex-direction: column; gap: 3px; }
.goal-dim {
  display: flex; align-items: flex-start; gap: 6px; font-size: 11px; line-height: 1.5;
  padding: 3px 0;
}
.goal-dim-icon { flex-shrink: 0; }
.goal-dim-name { font-weight: 500; color: var(--text-primary); flex-shrink: 0; min-width: 70px; }
.goal-dim-detail { color: var(--text-muted); }
.goal-dim.missing .goal-dim-detail { color: #dc2626; }
.goal-steps { display: flex; flex-direction: column; gap: 6px; }
.goal-step-item {
  display: flex; gap: 8px; padding: 8px 10px; border-radius: var(--radius-sm);
  background: var(--bg-secondary); transition: all 0.2s;
}
.goal-step-item.completed { background: rgba(5, 150, 105, 0.08); }
.goal-step-item.executing { background: var(--accent-lighter); }
.goal-step-item.planning { background: transparent; border: 1px solid var(--border-color); }
.goal-step-num {
  flex-shrink: 0; width: 22px; height: 22px; border-radius: 50%;
  background: var(--accent); color: #fff; font-size: 10px; font-weight: 600;
  display: flex; align-items: center; justify-content: center;
}
.goal-step-icon { flex-shrink: 0; font-size: 14px; line-height: 22px; }
.goal-step-body { flex: 1; min-width: 0; }
.goal-step-title { font-size: 12px; font-weight: 500; color: var(--text-primary); }
.goal-step-desc { font-size: 10px; color: var(--text-muted); line-height: 1.5; margin-top: 2px; }
.goal-step-result {
  font-size: 10px; color: var(--text-secondary); line-height: 1.6; margin-top: 4px;
  padding: 4px 6px; background: var(--bg-card); border-radius: var(--radius-sm);
  white-space: pre-wrap; word-break: break-word; max-height: 80px; overflow-y: auto;
}
.goal-step-saved { font-size: 9px; color: #059669; margin-top: 3px; font-weight: 500; }
.goal-step-actions { margin-top: 6px; width: 100%; }
.goal-step-input {
  width: 100%; background: var(--bg-card); border: 1px solid var(--border-color);
  border-radius: var(--radius-sm); color: var(--text-primary); font-size: 11px;
  padding: 5px 8px; resize: vertical; outline: none; margin-bottom: 4px;
  font-family: var(--font-sans);
}
.goal-step-input:focus { border-color: var(--accent); }
.goal-step-buttons { display: flex; justify-content: flex-end; gap: 6px; }
.goal-plan-actions { margin-top: 10px; display: flex; justify-content: center; }
.goal-summary {
  font-size: 11px; line-height: 1.8; color: var(--text-primary);
  white-space: pre-wrap; padding: 8px 10px; background: var(--bg-secondary);
  border-radius: var(--radius-sm);
}
.modal-wide { width: 500px; max-width: 90vw; }
.edit-steps { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; max-height: 300px; overflow-y: auto; }
.edit-step { display: flex; gap: 6px; align-items: center; }
.edit-step .modal-input { flex: 1; }
.edit-step .modal-input:first-child { max-width: 160px; }
</style>
