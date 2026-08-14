<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import type { KgEntity, KgRelation, KgEntityType, KgKnowledgeLayer, ID } from '../types'

const store = useAppStore()
const { currentProjectId, kgGraph, kgLoading } = storeToRefs(store)

const TYPE_COLORS: Record<KgEntityType, string> = {
  character: '#c55d3b',
  location: '#0891b2',
  faction: '#7c3aed',
  item: '#d97706',
  event: '#db2777',
}
const TYPE_LABELS: Record<KgEntityType, string> = {
  character: '角色', location: '地点', faction: '势力', item: '物品', event: '事件',
}
const LAYER_LABELS: Record<KgKnowledgeLayer, string> = {
  truth: '既定事实', revealed: '已揭示', foreshadow: '伏笔',
}
const LAYER_DASH: Record<KgKnowledgeLayer, string> = {
  truth: 'none', revealed: '6 4', foreshadow: '2 4',
}

const activeLayers = ref<KgKnowledgeLayer[]>(['truth', 'revealed', 'foreshadow'])
const currentChapter = ref<number | null>(null)
const maxChapter = ref<number>(0)
const selectedId = ref<ID | null>(null)

function toggleLayer(layer: KgKnowledgeLayer) {
  const idx = activeLayers.value.indexOf(layer)
  if (idx >= 0) {
    if (activeLayers.value.length > 1) activeLayers.value.splice(idx, 1)
  } else {
    activeLayers.value.push(layer)
  }
  reloadGraph()
}

async function reloadGraph() {
  if (!currentProjectId.value) return
  const projectId = currentProjectId.value
  await store.fetchWorkspaceItems(projectId)
  const items = store.workspaceItems
  const chapters = items.filter(i => i.item_type === 'chapter' && i.chapter_number)
  maxChapter.value = chapters.length > 0 ? Math.max(...chapters.map(c => c.chapter_number || 0)) : 0
  await store.fetchKgGraph(projectId, currentChapter.value ?? undefined, activeLayers.value)
}

function onChapterSlider() {
  reloadGraph()
}

function resetChapter() {
  currentChapter.value = null
  reloadGraph()
}

onMounted(() => { reloadGraph() })
watch(currentProjectId, () => { reloadGraph() })

interface SimNode { id: ID; x: number; y: number; vx: number; vy: number; entity: KgEntity }
interface SimEdge { source: ID; target: ID; relation: KgRelation }

const nodes = ref<SimNode[]>([])
const edges = ref<SimEdge[]>([])
const width = 520
const height = 520
const svgRef = ref<SVGSVGElement | null>(null)

const filteredEntities = computed(() => kgGraph.value.entities)
const filteredRelations = computed(() => kgGraph.value.relations)

watch([filteredEntities, filteredRelations], () => {
  buildSimulation()
}, { deep: true })

function buildSimulation() {
  const ents = filteredEntities.value
  const existing = new Map(nodes.value.map(n => [n.id, n]))
  const cx = width / 2, cy = height / 2
  nodes.value = ents.map((e, i) => {
    const old = existing.get(e.id)
    if (old) return { ...old, entity: e }
    const angle = (i / Math.max(ents.length, 1)) * Math.PI * 2
    const r = 140 + Math.random() * 40
    return { id: e.id, x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r, vx: 0, vy: 0, entity: e }
  })
  const nodeIds = new Set(ents.map(e => e.id))
  edges.value = filteredRelations.value
    .filter(r => nodeIds.has(r.subject_id) && nodeIds.has(r.object_id))
    .map(r => ({ source: r.subject_id, target: r.object_id, relation: r }))
  runSimulation()
}

let rafId = 0
let alpha = 1
function runSimulation() {
  cancelAnimationFrame(rafId)
  alpha = 1
  const step = () => {
    alpha *= 0.97
    if (alpha < 0.02 || nodes.value.length === 0) return
    const ns = nodes.value
    const cx = width / 2, cy = height / 2
    const kRepel = 6000 * alpha
    const kSpring = 0.04
    const restLen = 110
    const kCenter = 0.008 * alpha

    for (let i = 0; i < ns.length; i++) {
      for (let j = i + 1; j < ns.length; j++) {
        let dx = ns[i].x - ns[j].x, dy = ns[i].y - ns[j].y
        let d2 = dx * dx + dy * dy || 0.01
        let d = Math.sqrt(d2)
        const f = kRepel / d2
        const fx = (dx / d) * f, fy = (dy / d) * f
        ns[i].vx += fx; ns[i].vy += fy
        ns[j].vx -= fx; ns[j].vy -= fy
      }
    }
    for (const e of edges.value) {
      const s = ns.find(n => n.id === e.source), t = ns.find(n => n.id === e.target)
      if (!s || !t) continue
      const dx = t.x - s.x, dy = t.y - s.y
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01
      const f = (d - restLen) * kSpring
      const fx = (dx / d) * f, fy = (dy / d) * f
      s.vx += fx; s.vy += fy
      t.vx -= fx; t.vy -= fy
    }
    for (const n of ns) {
      if (draggingId.value === n.id) continue
      n.vx += (cx - n.x) * kCenter
      n.vy += (cy - n.y) * kCenter
      n.vx *= 0.82; n.vy *= 0.82
      n.x += n.vx; n.y += n.vy
      n.x = Math.max(30, Math.min(width - 30, n.x))
      n.y = Math.max(30, Math.min(height - 30, n.y))
    }
    rafId = requestAnimationFrame(step)
  }
  rafId = requestAnimationFrame(step)
}
onUnmounted(() => cancelAnimationFrame(rafId))

const draggingId = ref<ID | null>(null)
function onNodeDown(e: MouseEvent, node: SimNode) {
  e.preventDefault()
  draggingId.value = node.id
  selectedId.value = node.id
}
function onSvgMove(e: MouseEvent) {
  if (!draggingId.value || !svgRef.value) return
  const rect = svgRef.value.getBoundingClientRect()
  const scaleX = width / rect.width
  const scaleY = height / rect.height
  const x = (e.clientX - rect.left) * scaleX
  const y = (e.clientY - rect.top) * scaleY
  const n = nodes.value.find(n => n.id === draggingId.value)
  if (n) { n.x = x; n.y = y; n.vx = 0; n.vy = 0 }
}
function onSvgUp() { draggingId.value = null }

const selectedEntity = computed<KgEntity | null>(() =>
  nodes.value.find(n => n.id === selectedId.value)?.entity ?? null
)
const selectedRelations = computed(() => {
  if (!selectedId.value) return []
  return edges.value
    .filter(e => e.source === selectedId.value || e.target === selectedId.value)
    .map(e => {
      const isSubject = e.source === selectedId.value
      const otherId = isSubject ? e.target : e.source
      const other = nodes.value.find(n => n.id === otherId)
      return {
        predicate: e.relation.predicate,
        direction: e.relation.direction,
        layer: e.relation.knowledge_layer,
        otherName: other?.entity.name ?? '?',
        otherType: other?.entity.entity_type,
        isSubject,
      }
    })
})

function propsList(entity: KgEntity): [string, string][] {
  const p = entity.properties ?? {}
  return Object.entries(p).filter(([, v]) => v != null && v !== '').map(([k, v]) => [k, String(v)])
}

function onExtractFromChat() {
  if (!currentProjectId.value) return
  store.extractKg(currentProjectId.value, { message_limit: 20 })
}

function exportGraph(format: 'json' | 'markdown' | 'mermaid') {
  if (!currentProjectId.value) return
  window.open(`/api/projects/${currentProjectId.value}/kg/export?format=${format}`, '_blank')
}

async function onDeleteEntity() {
  if (!selectedId.value || !currentProjectId.value) return
  if (!confirm('确定删除该实体及其关联关系？')) return
  await store.deleteKgEntity(currentProjectId.value, selectedId.value)
  selectedId.value = null
}

const showAdd = ref(false)
const newType = ref<KgEntityType>('character')
const newName = ref('')
const newLayer = ref<KgKnowledgeLayer>('truth')
async function onAddEntity() {
  if (!newName.value.trim() || !currentProjectId.value) return
  await store.createKgEntity(currentProjectId.value, {
    entity_type: newType.value, name: newName.value.trim(), knowledge_layer: newLayer.value,
  })
  newName.value = ''
  showAdd.value = false
}

const entityStats = computed(() => {
  const by: Record<string, number> = {}
  for (const e of filteredEntities.value) by[e.entity_type] = (by[e.entity_type] || 0) + 1
  return by
})
</script>

<template>
  <div class="kg-panel">
    <div class="kg-toolbar">
      <div class="kg-layer-toggles">
        <button
          v-for="layer in (['truth','revealed','foreshadow'] as KgKnowledgeLayer[])"
          :key="layer"
          class="kg-layer-chip"
          :class="{ active: activeLayers.includes(layer), [layer]: activeLayers.includes(layer) }"
          @click="toggleLayer(layer)"
        >{{ LAYER_LABELS[layer] }}</button>
      </div>
      <div class="kg-toolbar-right">
        <span class="kg-stats">{{ filteredEntities.length }}节点 · {{ filteredRelations.length }}关系</span>
        <div class="kg-export-group">
          <button class="btn btn-sm" :disabled="filteredEntities.length === 0" title="导出JSON" @click="exportGraph('json')">JSON</button>
          <button class="btn btn-sm" :disabled="filteredEntities.length === 0" title="导出Markdown" @click="exportGraph('markdown')">MD</button>
          <button class="btn btn-sm" :disabled="filteredEntities.length === 0" title="导出Mermaid" @click="exportGraph('mermaid')">Mermaid</button>
        </div>
        <button class="btn btn-sm" :disabled="kgLoading" @click="onExtractFromChat">
          {{ kgLoading ? '提取中…' : 'AI提取' }}
        </button>
        <button class="btn btn-sm btn-primary" @click="showAdd = true">+ 添加</button>
      </div>
    </div>

    <div v-if="maxChapter > 0" class="kg-chapter-slider">
      <span class="slider-label">时序</span>
      <button class="slider-btn" :class="{ active: currentChapter === null }" @click="resetChapter">全部</button>
      <input
        type="range"
        class="chapter-range"
        min="1"
        :max="maxChapter"
        :value="currentChapter || 1"
        @input="currentChapter = Number(($event.target as HTMLInputElement).value); onChapterSlider()"
      />
      <span class="slider-chapter">第{{ currentChapter || '∞' }}章</span>
    </div>

    <div class="kg-canvas-wrap">
      <svg
        ref="svgRef"
        class="kg-svg"
        :viewBox="`0 0 ${width} ${height}`"
        @mousemove="onSvgMove"
        @mouseup="onSvgUp"
        @mouseleave="onSvgUp"
      >
        <defs>
          <marker id="kg-arrow" markerWidth="8" markerHeight="8" refX="20" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="var(--text-muted, #999)" />
          </marker>
        </defs>

        <g v-for="e in edges" :key="e.relation.id">
          <line
            :x1="nodes.find(n => n.id === e.source)?.x"
            :y1="nodes.find(n => n.id === e.source)?.y"
            :x2="nodes.find(n => n.id === e.target)?.x"
            :y2="nodes.find(n => n.id === e.target)?.y"
            :stroke="e.relation.knowledge_layer === 'foreshadow' ? 'var(--accent)' : 'var(--text-muted, #999)'"
            :stroke-dasharray="LAYER_DASH[e.relation.knowledge_layer]"
            :stroke-width="selectedId && (e.source === selectedId || e.target === selectedId) ? 2 : 1.2"
            :marker-end="e.relation.direction === 'directed' ? 'url(#kg-arrow)' : ''"
            :opacity="selectedId && (e.source !== selectedId && e.target !== selectedId) ? 0.25 : 0.7"
          />
          <text
            class="kg-edge-label"
            :x="((nodes.find(n => n.id === e.source)?.x || 0) + (nodes.find(n => n.id === e.target)?.x || 0)) / 2"
            :y="((nodes.find(n => n.id === e.source)?.y || 0) + (nodes.find(n => n.id === e.target)?.y || 0)) / 2 - 4"
            text-anchor="middle"
          >{{ e.relation.predicate }}</text>
        </g>

        <g
          v-for="n in nodes"
          :key="n.id"
          class="kg-node-g"
          :class="{ selected: n.id === selectedId }"
          @mousedown="onNodeDown($event, n)"
          @click.stop="selectedId = n.id"
        >
          <circle
            :cx="n.x" :cy="n.y" r="16"
            :fill="TYPE_COLORS[n.entity.entity_type]"
            :stroke="n.id === selectedId ? 'var(--bg-card)' : 'none'"
            stroke-width="3"
          />
          <text :x="n.x" :y="n.y + 34" text-anchor="middle" class="kg-node-label">{{ n.entity.name }}</text>
        </g>

        <g v-if="nodes.length === 0 && !kgLoading" class="kg-empty">
          <text :x="width / 2" :y="height / 2 - 10" text-anchor="middle" class="kg-empty-title">知识图谱为空</text>
          <text :x="width / 2" :y="height / 2 + 16" text-anchor="middle" class="kg-empty-hint">点击「AI提取」从对话中生成，或「+ 添加」手动创建</text>
        </g>
      </svg>

      <div class="kg-legend">
        <div v-for="(color, type) in TYPE_COLORS" :key="type" class="kg-legend-item">
          <span class="kg-legend-dot" :style="{ background: color }"></span>
          <span>{{ TYPE_LABELS[type as KgEntityType] }}<sup v-if="entityStats[type]">{{ entityStats[type] }}</sup></span>
        </div>
      </div>
    </div>

    <div v-if="selectedEntity" class="kg-detail">
      <div class="kg-detail-header">
        <span class="kg-detail-name">{{ selectedEntity.name }}</span>
        <span class="kg-detail-type" :style="{ background: TYPE_COLORS[selectedEntity.entity_type] }">{{ TYPE_LABELS[selectedEntity.entity_type] }}</span>
        <span class="kg-detail-layer" :class="selectedEntity.knowledge_layer">{{ LAYER_LABELS[selectedEntity.knowledge_layer] }}</span>
      </div>
      <div v-if="selectedEntity.aliases?.length" class="kg-detail-row">
        <span class="kg-detail-key">别名</span>
        <span class="kg-detail-val">{{ selectedEntity.aliases.join('、') }}</span>
      </div>
      <div v-if="selectedEntity.summary" class="kg-detail-row">
        <span class="kg-detail-key">概述</span>
        <span class="kg-detail-val">{{ selectedEntity.summary }}</span>
      </div>
      <div v-for="[k, v] in propsList(selectedEntity)" :key="k" class="kg-detail-row">
        <span class="kg-detail-key">{{ k }}</span>
        <span class="kg-detail-val">{{ v }}</span>
      </div>
      <div v-if="selectedRelations.length" class="kg-detail-relations">
        <div class="kg-detail-section">关系网络</div>
        <div v-for="(r, i) in selectedRelations" :key="i" class="kg-rel-item">
          <span class="kg-rel-arrow">{{ r.isSubject ? '→' : '←' }}</span>
          <span class="kg-rel-pred">{{ r.predicate }}</span>
          <span class="kg-rel-name">{{ r.otherName }}</span>
          <span class="kg-rel-layer" :class="r.layer">{{ LAYER_LABELS[r.layer] }}</span>
        </div>
      </div>
      <div class="kg-detail-actions">
        <button class="btn-link danger" @click="onDeleteEntity">删除</button>
      </div>
    </div>

    <div v-if="showAdd" class="modal-overlay show" @click.self="showAdd = false">
      <div class="modal-card">
        <h3>添加实体</h3>
        <select v-model="newType" class="modal-input">
          <option v-for="(label, type) in TYPE_LABELS" :key="type" :value="type">{{ label }}</option>
        </select>
        <input v-model="newName" class="modal-input" placeholder="实体名称" @keydown.enter="onAddEntity" />
        <select v-model="newLayer" class="modal-input">
          <option v-for="(label, layer) in LAYER_LABELS" :key="layer" :value="layer">{{ label }}</option>
        </select>
        <div class="modal-actions">
          <button class="btn" @click="showAdd = false">取消</button>
          <button class="btn btn-primary" @click="onAddEntity">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kg-panel { display: flex; flex-direction: column; height: 100%; gap: 8px; }
.kg-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; flex-wrap: wrap; padding: 4px 0;
}
.kg-layer-toggles { display: flex; gap: 4px; }
.kg-layer-chip {
  font-size: 11px; padding: 3px 10px; border-radius: var(--radius-full);
  border: 1px solid var(--border-color); background: var(--bg-secondary);
  color: var(--text-secondary); cursor: pointer; transition: all 0.15s;
}
.kg-layer-chip.active.truth { background: var(--accent); color: #fff; border-color: var(--accent); }
.kg-layer-chip.active.revealed { background: #0891b2; color: #fff; border-color: #0891b2; }
.kg-layer-chip.active.foreshadow { background: #7c3aed; color: #fff; border-color: #7c3aed; }
.kg-toolbar-right { display: flex; align-items: center; gap: 8px; }
.kg-export-group { display: flex; gap: 2px; }
.kg-export-group .btn { font-size: 10px; padding: 2px 6px; min-width: auto; opacity: 0.7; }
.kg-export-group .btn:hover { opacity: 1; }
.kg-stats { font-size: 11px; color: var(--text-muted); font-family: var(--font-mono), monospace; }
.kg-chapter-slider {
  display: flex; align-items: center; gap: 8px; padding: 4px 0;
}
.slider-label { font-size: 10px; color: var(--text-muted); font-weight: 600; letter-spacing: 0.05em; }
.slider-btn {
  font-size: 10px; padding: 2px 8px; border-radius: var(--radius-full);
  border: 1px solid var(--border-color); background: var(--bg-secondary);
  color: var(--text-secondary); cursor: pointer;
}
.slider-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.chapter-range {
  flex: 1; height: 4px; -webkit-appearance: none; appearance: none;
  background: var(--bg-secondary); border-radius: var(--radius-full); outline: none;
  cursor: pointer;
}
.chapter-range::-webkit-slider-thumb {
  -webkit-appearance: none; width: 14px; height: 14px; border-radius: 50%;
  background: var(--accent); cursor: pointer; border: 2px solid var(--bg-card);
}
.chapter-range::-moz-range-thumb {
  width: 14px; height: 14px; border-radius: 50%;
  background: var(--accent); cursor: pointer; border: 2px solid var(--bg-card);
}
.slider-chapter {
  font-size: 10px; color: var(--text-primary); font-family: var(--font-mono), monospace;
  min-width: 50px; text-align: right;
}
.kg-canvas-wrap {
  position: relative; flex: 1; min-height: 320px;
  border: 1px solid var(--border-color); border-radius: var(--radius-md);
  background: var(--bg-secondary); overflow: hidden;
}
.kg-svg { width: 100%; height: 100%; cursor: grab; user-select: none; }
.kg-svg:active { cursor: grabbing; }
.kg-node-g { cursor: pointer; }
.kg-node-g:hover circle { filter: brightness(1.15); }
.kg-node-label {
  font-size: 11px; fill: var(--text-primary); font-family: var(--font-sans);
  pointer-events: none; paint-order: stroke; stroke: var(--bg-secondary); stroke-width: 3px;
}
.kg-edge-label {
  font-size: 9px; fill: var(--text-muted); font-family: var(--font-sans);
  pointer-events: none; paint-order: stroke; stroke: var(--bg-secondary); stroke-width: 3px;
}
.kg-empty-title { font-size: 14px; fill: var(--text-secondary); font-family: var(--font-serif), serif; }
.kg-empty-hint { font-size: 11px; fill: var(--text-muted); }
.kg-legend {
  position: absolute; bottom: 8px; left: 8px; display: flex; flex-wrap: wrap; gap: 8px;
  padding: 6px 10px; border-radius: var(--radius-sm);
  background: var(--bg-card); border: 1px solid var(--border-color);
}
.kg-legend-item { display: flex; align-items: center; gap: 4px; font-size: 10px; color: var(--text-secondary); }
.kg-legend-dot { width: 9px; height: 9px; border-radius: 50%; }
.kg-legend-item sup { color: var(--text-muted); font-size: 9px; }
.kg-detail {
  border: 1px solid var(--border-color); border-radius: var(--radius-md);
  background: var(--bg-card); padding: 12px 14px; max-height: 200px; overflow-y: auto;
}
.kg-detail-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.kg-detail-name { font-family: var(--font-serif), serif; font-size: 14px; font-weight: 600; color: var(--text-primary); }
.kg-detail-type { font-size: 10px; color: #fff; padding: 1px 7px; border-radius: var(--radius-full); }
.kg-detail-layer { font-size: 10px; padding: 1px 7px; border-radius: var(--radius-full); border: 1px solid var(--border-color); color: var(--text-secondary); }
.kg-detail-layer.foreshadow { color: #7c3aed; border-color: #7c3aed; }
.kg-detail-layer.revealed { color: #0891b2; border-color: #0891b2; }
.kg-detail-row { display: flex; gap: 8px; font-size: 12px; line-height: 1.7; padding: 1px 0; }
.kg-detail-key { color: var(--text-muted); min-width: 48px; flex-shrink: 0; }
.kg-detail-val { color: var(--text-primary); word-break: break-word; }
.kg-detail-section { font-size: 11px; color: var(--text-muted); margin: 8px 0 4px; letter-spacing: 0.05em; }
.kg-rel-item { display: flex; align-items: center; gap: 6px; font-size: 11px; padding: 2px 0; color: var(--text-secondary); }
.kg-rel-arrow { color: var(--text-muted); }
.kg-rel-pred { color: var(--accent); font-weight: 500; }
.kg-rel-name { color: var(--text-primary); }
.kg-rel-layer { font-size: 9px; padding: 0 5px; border-radius: var(--radius-full); border: 1px solid var(--border-color); color: var(--text-muted); }
.kg-detail-actions { margin-top: 8px; text-align: right; }
</style>
