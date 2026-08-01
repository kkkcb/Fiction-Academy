<script setup lang="ts">
import { computed } from 'vue'
import type { ConsultRecord, ConsultRound } from '../types'
import { formatMd, expertColor } from '../utils/format'
import ThinkingBlock from './ThinkingBlock.vue'
import ExpertAvatar from './icons/ExpertAvatar.vue'
import IconAlert from './icons/IconAlert.vue'

const props = defineProps<{ record: ConsultRecord }>()

const leader = computed(() => props.record.leader)
const rounds = computed(() => props.record.rounds || [])
const showVerdict = computed(() => props.record.summary || props.record.summaryThinking)
const verdictColor = '#d97757'

function dividerText(r: ConsultRound) {
  return `第${r.round}轮 · ${r.label || '讨论'}${r.round > 1 ? '（含统率者）' : ''}`
}
</script>

<template>
  <div class="consult-flow-inner">
    <div v-if="leader && (leader.content || leader.thinking)" class="cf-msg cf-leader">
      <ExpertAvatar :name="leader.name" :size="28" />
      <div class="cf-bubble-wrap">
        <div class="cf-name" :style="{ color: expertColor(leader.name) }">{{ leader.name }} <span class="cf-role">统率者定调</span></div>
        <ThinkingBlock :text="leader.thinking" :streaming="!leader.content" />
        <div class="cf-bubble">
          <div v-if="leader.content" class="cf-text markdown-body" v-html="formatMd(leader.content)"></div>
        </div>
      </div>
    </div>

    <template v-for="r in rounds" :key="r.round">
      <div class="cf-divider">{{ dividerText(r) }}</div>
      <div
        v-for="(e, i) in (r.entries || [])"
        :key="r.round + '-' + i"
        class="cf-msg"
        :class="{ 'is-leader': e.is_leader }"
      >
        <ExpertAvatar :name="e.name" :size="28" />
        <div class="cf-bubble-wrap">
          <div class="cf-name" :style="{ color: expertColor(e.name) }">{{ e.name }} <span class="cf-role">{{ e.perspective || '' }}</span></div>
          <ThinkingBlock :text="e.thinking" :streaming="!e.content" />
          <div class="cf-bubble">
            <div v-if="e.content" class="cf-text markdown-body" v-html="formatMd(e.content)"></div>
          </div>
        </div>
      </div>
    </template>

    <div v-if="showVerdict" class="cf-msg cf-verdict">
      <ExpertAvatar name="终局裁决" :size="28" />
      <div class="cf-bubble-wrap">
        <div class="cf-name" :style="{ color: verdictColor }">终局裁决 <span class="cf-role">主线策划</span></div>
        <ThinkingBlock :text="record.summaryThinking" :streaming="!record.summary" />
        <div class="cf-bubble">
          <div v-if="record.summary" class="cf-text markdown-body" v-html="formatMd(record.summary)"></div>
        </div>
      </div>
    </div>

    <div v-if="record.error" class="cf-error"><IconAlert :size="14" /> {{ record.error }}</div>
    <div v-if="record.pending" class="cf-pending">{{ record.pending }}<span class="thinking-dots"></span></div>
  </div>
</template>
