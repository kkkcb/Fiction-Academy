<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import { formatReceiptMd } from '../utils/format'
import { X, Loader2, Check, ChevronDown } from 'lucide-vue-next'
import ThinkingBlock from './ThinkingBlock.vue'

const store = useAppStore()
const {
  pinPanelOpen, pinStatus, pinThinking, pinSuggestions, pinNote,
  pinChosen, pinExpanded, pinAppliedCount, pinError, pinActivity,
} = storeToRefs(store)

const chosenCount = computed(() => pinSuggestions.value.filter(x => pinChosen.value[x.point]).length)

const statusText = computed(() => {
  switch (pinStatus.value) {
    case 'running': return '深度思考中'
    case 'result': return `待确认（${pinSuggestions.value.length} 个模块）`
    case 'applied': return `已写入 ${pinAppliedCount.value} 个模块`
    case 'error': return '出错'
    default: return '沉淀'
  }
})

function toggleExpand(point: string) {
  store.pinExpanded = { ...pinExpanded.value, [point]: !pinExpanded.value[point] }
}
</script>

<template>
  <!-- 关着但有进行中/待确认任务时：悬浮徽标随时唤回 -->
  <button
    v-if="!pinPanelOpen && pinActivity"
    class="pin-fab"
    :class="pinStatus"
    @click="store.togglePinPanel(true)"
  >
    <Loader2 v-if="pinStatus === 'running'" :size="13" class="spin" />
    <Check v-else :size="13" />
    沉淀{{ statusText }}
  </button>

  <Teleport to="body">
    <div v-if="pinPanelOpen" class="pin-panel">
      <header class="pin-panel-head">
        <span class="pin-panel-title">沉淀面板</span>
        <span class="pin-panel-status" :class="pinStatus">{{ statusText }}</span>
        <span class="pin-flex"></span>
        <button v-if="pinStatus === 'running'" class="btn btn-sm" @click="store.abortPin()">终止</button>
        <button class="panel-close" aria-label="收起面板（不打断任务）" title="收起（不打断任务）" @click="store.togglePinPanel(false)">
          <X :size="15" :stroke-width="1.75" />
        </button>
      </header>

      <div class="pin-panel-body">
        <!-- 进行中：思考流实时展示 -->
        <template v-if="pinStatus === 'running'">
          <p class="pin-tip">正在把选中的对话与总览全部模块做全局比对（思考强度最高）。收起面板不会打断，右下角徽标随时唤回。</p>
          <ThinkingBlock v-if="pinThinking" :text="pinThinking" :streaming="true" />
          <p v-else class="pin-tip">等待模型首批输出…</p>
        </template>

        <!-- 出错：已生成内容保留，可断点续传 -->
        <template v-else-if="pinStatus === 'error'">
          <p class="pin-error">{{ pinError }}</p>
          <p class="pin-tip">
            思考过程（{{ pinThinking.length }} 字）与已生成的结果内容都已保留——点「继续生成」让模型从中断处接着写，不会从头重来。
          </p>
          <details v-if="pinThinking" class="pin-think-back">
            <summary>回看已保留的思考过程</summary>
            <ThinkingBlock :text="pinThinking" :streaming="false" />
          </details>
          <div class="pin-panel-foot">
            <span class="pin-flex"></span>
            <button class="btn btn-sm" @click="store.retryPinFromScratch()">重新开始</button>
            <button class="btn btn-sm btn-primary" @click="store.resumePin()">
              <Loader2 :size="12" /> 继续生成（从断点）
            </button>
          </div>
        </template>

        <!-- 结果：逐模块确认 -->
        <template v-else-if="pinStatus === 'result'">
          <p class="pin-tip">{{ pinNote }} 勾选要采纳的模块。</p>
          <details v-if="pinThinking" class="pin-think-back">
            <summary>回看思考过程</summary>
            <ThinkingBlock :text="pinThinking" :streaming="false" />
          </details>
          <div class="pin-mods">
            <div v-for="x in pinSuggestions" :key="x.point" class="pin-mod" :class="{ off: !pinChosen[x.point] }">
              <label class="pin-mod-head">
                <input
                  type="checkbox"
                  :checked="pinChosen[x.point]"
                  @change="store.pinChosen = { ...pinChosen, [x.point]: ($event.target as HTMLInputElement).checked }"
                />
                <span class="pin-mod-label">{{ x.label }}</span>
                <span v-if="x.is_new" class="pin-mod-badge">新建</span>
                <span v-else class="pin-mod-chars">{{ x.old_chars }} → {{ x.content.length }} 字</span>
                <span class="pin-flex"></span>
                <button class="pin-mod-toggle" @click.prevent="toggleExpand(x.point)">
                  {{ pinExpanded[x.point] ? '收起' : '展开' }}
                  <ChevronDown :size="12" :class="{ flip: pinExpanded[x.point] }" />
                </button>
              </label>
              <p v-if="x.note" class="pin-mod-note">{{ x.note }}</p>
              <div v-if="pinExpanded[x.point]" class="markdown-body pin-mod-content" v-html="formatReceiptMd(x.content)"></div>
            </div>
          </div>
          <div class="pin-panel-foot">
            <span class="pin-tip">已选 {{ chosenCount }}/{{ pinSuggestions.length }}</span>
            <span class="pin-flex"></span>
            <button class="btn btn-sm" @click="store.abortPin()">放弃全部</button>
            <button class="btn btn-sm btn-primary" :disabled="!chosenCount" @click="store.applyPin()">
              <Check :size="12" /> 采纳所选（{{ chosenCount }}）
            </button>
          </div>
        </template>

        <!-- 完成 -->
        <template v-else-if="pinStatus === 'applied'">
          <p class="pin-tip">已按你的确认写入 {{ pinAppliedCount }} 个模块，右侧总览已更新。</p>
        </template>

        <template v-else>
          <p class="pin-tip">在对话里点某条 AI 回复的「沉淀」开始。</p>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.pin-fab {
  position: fixed;
  right: 18px;
  bottom: 18px;
  z-index: 60;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid var(--accent-border);
  background: var(--bg-card);
  color: var(--accent);
  font-size: 12.5px;
  font-family: inherit;
  cursor: pointer;
  box-shadow: var(--shadow-xl, 0 6px 24px rgba(0, 0, 0, 0.25));
}
.pin-fab.running .spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.pin-panel {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 61;
  width: min(560px, calc(100vw - 32px));
  max-height: min(72vh, 640px);
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border: 1px solid var(--accent-border);
  border-radius: 14px;
  box-shadow: var(--shadow-xl, 0 10px 40px rgba(0, 0, 0, 0.35));
  overflow: hidden;
}
.pin-panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-color);
}
.pin-panel-title { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.pin-panel-status { font-size: 11.5px; color: var(--text-tertiary); }
.pin-panel-status.running { color: var(--accent); }
.pin-flex { flex: 1; }
.panel-close {
  border: 0; background: transparent; color: var(--text-tertiary);
  cursor: pointer; padding: 2px; display: inline-flex;
}
.panel-close:hover { color: var(--text-primary); }
.pin-panel-body {
  flex: 1; overflow-y: auto; padding: 12px 14px;
}
.pin-tip { font-size: 12px; color: var(--text-tertiary); line-height: 1.6; margin: 0 0 8px; }
.pin-error { font-size: 12.5px; color: var(--danger, #d9534f); }
.pin-think-back { margin-bottom: 10px; }
.pin-think-back summary { font-size: 12px; color: var(--text-tertiary); cursor: pointer; }

.pin-mods { display: flex; flex-direction: column; gap: 8px; }
.pin-mod {
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 8px 12px;
  transition: opacity 0.15s;
}
.pin-mod.off { opacity: 0.45; }
.pin-mod-head { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.pin-mod-label { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.pin-mod-badge {
  font-size: 10.5px; color: var(--accent); background: var(--accent-light);
  border-radius: var(--radius-full); padding: 1px 8px;
}
.pin-mod-chars { font-size: 11px; color: var(--text-tertiary); }
.pin-mod-toggle {
  border: 0; background: transparent; color: var(--text-tertiary);
  font-size: 11.5px; cursor: pointer; display: inline-flex; align-items: center; gap: 3px;
  font-family: inherit; padding: 0;
}
.pin-mod-toggle svg { transition: transform 0.15s; }
.pin-mod-toggle svg.flip { transform: rotate(180deg); }
.pin-mod-note { margin: 6px 0 0; font-size: 12px; color: var(--text-secondary); }
.pin-mod-content {
  margin-top: 8px; padding: 10px; border-radius: 8px;
  background: var(--bg-secondary); font-size: 12px; line-height: 1.7;
  max-height: 300px; overflow-y: auto;
}
.pin-panel-foot {
  display: flex; align-items: center; gap: 8px;
  margin-top: 12px; padding-top: 10px;
  border-top: 1px dashed var(--border-color);
}
</style>
