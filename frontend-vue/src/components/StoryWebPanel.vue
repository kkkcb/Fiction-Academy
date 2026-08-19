<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'
import * as api from '../api'
import { Network, RefreshCw, User, BookMarked } from 'lucide-vue-next'

const store = useAppStore()
const { currentProjectId } = storeToRefs(store)

interface WebChapter { chapter: number; title: string; words: number; types: string[]; plot: string; emotion: string }
interface WebThread { kind: string; name: string; chapters: number[]; setup_ch?: number | null; payoff_chs?: number[] }

const chapters = ref<WebChapter[]>([])
const threads = ref<WebThread[]>([])
const missing = ref(0)
const loading = ref(false)
const backfilling = ref(false)

// ===== 力导向图（手写物理：斥力 + 弹簧 + 章节横向序约束） =====
interface GNode {
  id: string; kind: 'chapter' | 'character' | 'foreshadow'
  label: string; chapter?: number; words?: number; plot?: string; types?: string[]
  x: number; y: number; vx: number; vy: number; fx?: number | null
}
interface GLink { source: string; target: string; kind: string }
const nodes = ref<GNode[]>([])
const links = ref<GLink[]>([])
const W = 900, H = 640
const hoverNode = ref<GNode | null>(null)
const dragNode = ref<GNode | null>(null)
let raf = 0
let tick = 0

function buildGraph(cs: WebChapter[], ts: WebThread[]) {
  const ns: GNode[] = []
  const ls: GLink[] = []
  cs.forEach((c, i) => {
    ns.push({
      id: `c${c.chapter}`, kind: 'chapter', label: `${c.chapter}`, chapter: c.chapter,
      words: c.words, plot: c.plot, types: c.types,
      x: 80 + (i / Math.max(cs.length - 1, 1)) * (W - 160) + (Math.random() - 0.5) * 60,
      y: H / 2 + (Math.random() - 0.5) * 160, vx: 0, vy: 0, fx: null,
    })
  })
  ts.forEach(t => {
    if (t.chapters.length < 2 && t.kind === 'foreshadow' && !t.payoff_chs?.length) return
    const id = `${t.kind[0]}:${t.name}`
    ns.push({
      id, kind: t.kind as 'character' | 'foreshadow', label: t.name.slice(0, 8),
      x: W / 2 + (Math.random() - 0.5) * (W - 200), y: 80 + Math.random() * (H - 160),
      vx: 0, vy: 0, fx: null,
    })
    t.chapters.forEach(n => ls.push({ source: id, target: `c${n}`, kind: t.kind }))
    // 伏笔回收：实体→埋设章的强化边在 kind 里标记
  })
  // 去重边
  const seen = new Set<string>()
  const dedup = ls.filter(l => {
    const k = l.source + '>' + l.target
    if (seen.has(k)) return false
    seen.add(k); return true
  })
  nodes.value = ns
  links.value = dedup
  startSim()
}

function step() {
  const ns = nodes.value
  const byId = new Map(ns.map(n => [n.id, n]))
  // 斥力（O(n²)，节点数 <150 可接受）
  for (let i = 0; i < ns.length; i++) {
    for (let j = i + 1; j < ns.length; j++) {
      const a = ns[i], b = ns[j]
      let dx = b.x - a.x, dy = b.y - a.y
      let d2 = dx * dx + dy * dy || 1
      if (d2 > 160000) continue
      const f = 2600 / d2
      const d = Math.sqrt(d2)
      dx /= d; dy /= d
      a.vx -= dx * f; a.vy -= dy * f
      b.vx += dx * f; b.vy += dy * f
    }
  }
  // 弹簧
  for (const l of links.value) {
    const a = byId.get(l.source), b = byId.get(l.target)
    if (!a || !b) continue
    const dx = b.x - a.x, dy = b.y - a.y
    const d = Math.sqrt(dx * dx + dy * dy) || 1
    const rest = 150
    const f = (d - rest) * 0.012
    const ux = dx / d, uy = dy / d
    a.vx += ux * f * 10; a.vy += uy * f * 10
    b.vx -= ux * f * 10; b.vy -= uy * f * 10
  }
  // 章节节点：横向序约束 + 中线弱引力（神经网络的“层”感）
  const n = ns.filter(x => x.kind === 'chapter')
  n.forEach((c, i) => {
    const tx = 80 + (i / Math.max(n.length - 1, 1)) * (W - 160)
    c.vx += (tx - c.x) * 0.02
    c.vy += (H / 2 - c.y) * 0.008
  })
  // 实体节点：画布向心 + 阻尼
  for (const nd of ns) {
    if (nd.kind !== 'chapter') {
      nd.vx += (W / 2 - nd.x) * 0.002
      nd.vy += (H / 2 - nd.y) * 0.004
    }
    if (nd === dragNode.value) { nd.vx = 0; nd.vy = 0; continue }
    nd.vx *= 0.86; nd.vy *= 0.86
    nd.x += Math.max(-14, Math.min(14, nd.vx))
    nd.y += Math.max(-14, Math.min(14, nd.vy))
    nd.x = Math.max(40, Math.min(W - 40, nd.x))
    nd.y = Math.max(36, Math.min(H - 40, nd.y))
  }
}

function loop() {
  step()
  tick++
  // 冷却：无拖拽且已稳定后降频（保持脉冲动画由 SVG 承担，物理可歇）
  if (tick < 400 || dragNode.value) raf = requestAnimationFrame(loop)
  else raf = requestAnimationFrame(() => setTimeout(loop, 120))
}

function startSim() {
  cancelAnimationFrame(raf)
  tick = 0
  loop()
}

const nodeById = (id: string) => nodes.value.find(n => n.id === id)

function linkPath(l: GLink): string {
  const a = nodeById(l.source), b = nodeById(l.target)
  if (!a || !b) return ''
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2
  const nx = -(b.y - a.y), ny = b.x - a.x
  const len = Math.hypot(nx, ny) || 1
  const bend = 0.14
  return `M ${a.x} ${a.y} Q ${mx + nx / len * len * bend / len * 40} ${my + ny / len * len * bend / len * 40} ${b.x} ${b.y}`
}

function nodeTransform(n: GNode): string {
  return 'translate(' + n.x + ' ' + n.y + ')'
}

function chaptersOfHover(): string {
  if (!hoverNode.value || hoverNode.value.kind === 'chapter') return ''
  const t = threads.value.find(x => x.kind[0] + ':' + x.name.slice(0, 8) === hoverNode.value!.id)
  return (t?.chapters || []).join('、')
}

const linkColor = (k: string) => k === 'character' ? '#22d3ee' : '#f59e0b'
const nodeRadius = (n: GNode) =>
  n.kind === 'chapter' ? Math.max(10, Math.min(20, Math.sqrt((n.words || 3000) / 22)))
  : n.kind === 'character' ? 9 : 7

// 拖拽
function onPointerDown(n: GNode, e: PointerEvent) {
  dragNode.value = n
  ;(e.target as SVGElement).setPointerCapture(e.pointerId)
}
function onPointerMove(e: PointerEvent) {
  if (!dragNode.value) return
  const svg = e.currentTarget as SVGElement
  const r = svg.getBoundingClientRect()
  dragNode.value.x = (e.clientX - r.left) * (W / r.width)
  dragNode.value.y = (e.clientY - r.top) * (H / r.height)
}
function onPointerUp() { dragNode.value = null }

async function load() {
  if (!currentProjectId.value) return
  loading.value = true
  try {
    const r = await api.getStoryWeb(currentProjectId.value)
    chapters.value = r.chapters
    threads.value = r.threads
    missing.value = r.missing_web
    buildGraph(r.chapters, r.threads)
  } finally {
    loading.value = false
  }
}

async function backfill() {
  if (!currentProjectId.value || backfilling.value) return
  backfilling.value = true
  try {
    for (let i = 0; i < 60; i++) {
      const r = await api.backfillStoryWeb(currentProjectId.value, 3)
      if (!r.remaining) break
    }
    await load()
    store.notifySuccess('章节脉络已补全')
  } finally {
    backfilling.value = false
  }
}

onMounted(load)
onUnmounted(() => cancelAnimationFrame(raf))
</script>

<template>
  <div class="story-web">
    <div class="sw-head">
      <div class="sw-title"><Network :size="15" :stroke-width="1.75" /> 章节脉络网</div>
      <div class="sw-sub">章节神经元 × 人物/伏笔神经元 · 青色人物线 · 琥珀伏笔线 · 可拖拽</div>
      <div class="sw-actions">
        <span v-if="missing > 0" class="sw-missing">{{ missing }} 章待补脉络</span>
        <button v-if="missing > 0" class="btn btn-sm btn-primary" :disabled="backfilling" @click="backfill">
          <RefreshCw :size="12" :stroke-width="1.75" :class="{ spinning: backfilling }" />
          {{ backfilling ? '补全中…' : '补全脉络' }}
        </button>
        <button class="btn btn-sm" :disabled="loading" aria-label="重新生成布局" title="重新生成布局" @click="load">
          <RefreshCw :size="12" :stroke-width="1.75" :class="{ spinning: loading }" />
        </button>
      </div>
    </div>

    <div v-if="!chapters.length && !loading" class="sw-empty">还没有已定稿的章节</div>

    <div v-else class="sw-canvas" @pointermove="onPointerMove" @pointerup="onPointerUp" @pointerleave="onPointerUp">
      <svg :viewBox="`0 0 ${W} ${H}`" class="sw-svg">
        <defs>
          <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="3.4" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <!-- 连线 -->
        <path v-for="(l, i) in links" :key="i" :d="linkPath(l)" class="edge" :stroke="linkColor(l.kind)"
              :class="{ dim: !!hoverNode && hoverNode.id !== l.source && hoverNode.id !== l.target }" />
        <!-- 能量脉冲（沿线流动的光点） -->
        <circle v-for="(l, i) in links.slice(0, 46)" :key="'p' + i" r="2.6" class="pulse" :fill="linkColor(l.kind)">
          <animateMotion :dur="(2.6 + (i % 5) * 0.7).toFixed(1) + 's'" repeatCount="indefinite" :begin="(i * 0.21 % 3).toFixed(2) + 's'">
            <mpath :href="'#lp' + i" />
          </animateMotion>
        </circle>
        <path v-for="(l, i) in links.slice(0, 46)" :key="'lp' + i" :id="'lp' + i" :d="linkPath(l)" fill="none" stroke="none" />
        <!-- 节点 -->
        <g v-for="n in nodes" :key="n.id" class="gnode" :transform="nodeTransform(n)"
           @pointerdown="onPointerDown(n, $event)" @mouseenter="hoverNode = n" @mouseleave="hoverNode = null">
          <circle :r="nodeRadius(n) + 8" class="halo" :class="{ dim: !!hoverNode && hoverNode.id !== n.id }" />
          <circle v-if="n.kind === 'chapter'" :r="nodeRadius(n)" class="node-ch" filter="url(#glow)"
                  :class="{ dim: !!hoverNode && hoverNode.id !== n.id }" />
          <rect v-else-if="n.kind === 'character'" x="-8" y="-8" width="16" height="16" rx="4"
                class="node-char" filter="url(#glow)" :class="{ dim: !!hoverNode && hoverNode.id !== n.id }" />
          <circle v-else :r="nodeRadius(n)" class="node-fs" filter="url(#glow)"
                  :class="{ dim: !!hoverNode && hoverNode.id !== n.id }" />
          <text v-if="n.kind === 'chapter'" text-anchor="middle" dy="4" class="nlabel-ch">{{ n.label }}</text>
          <text v-else text-anchor="middle" :dy="nodeRadius(n) + 14" class="nlabel">{{ n.label }}</text>
        </g>
      </svg>
      <!-- 悬停信息卡 -->
      <div v-if="hoverNode" class="hover-card" :style="{
        left: Math.min((hoverNode.x / W) * 100, 72) + '%',
        top: Math.min((hoverNode.y / H) * 100, 78) + '%',
      }">
        <div v-if="hoverNode.kind === 'chapter'" class="hc-title">第{{ hoverNode!.chapter }}章 · {{ chapters.find(c => c.chapter === hoverNode?.chapter)?.title }}</div>
        <div v-else class="hc-title"><component :is="hoverNode.kind === 'character' ? User : BookMarked" :size="12" /> {{ hoverNode.label }}</div>
        <div v-if="hoverNode.kind === 'chapter'" class="hc-body">
          <div class="hc-meta">{{ (hoverNode?.types || []).join(' · ') }} | {{ hoverNode?.words }} 字</div>
          <div class="hc-plot">{{ hoverNode?.plot }}</div>
        </div>
        <div v-else class="hc-body hc-meta">出现于 第 {{ chaptersOfHover() }} 章</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.story-web { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.sw-head { display: flex; align-items: center; gap: 12px; padding: 10px 16px; border-bottom: 1px solid var(--border-subtle); flex-wrap: wrap; }
.sw-title { display: flex; align-items: center; gap: 7px; font-family: var(--font-serif), serif; font-size: 14px; font-weight: 700; color: var(--text-primary); }
.sw-sub { font-size: 11px; color: var(--text-muted); }
.sw-actions { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.sw-missing { font-size: 11px; color: #d97706; }
.sw-empty { padding: 60px 0; text-align: center; color: var(--text-muted); font-size: 13px; }
.sw-canvas { flex: 1; min-height: 0; position: relative; background: radial-gradient(ellipse at 50% 40%, rgba(197, 93, 59, 0.05), transparent 65%); overflow: hidden; }
.sw-svg { width: 100%; height: 100%; cursor: grab; }
.sw-svg:active { cursor: grabbing; }
.edge { fill: none; stroke-width: 1.4; opacity: 0.4; transition: opacity 0.15s; }
.edge.dim { opacity: 0.07; }
.pulse { opacity: 0.95; }
.halo { fill: currentColor; opacity: 0.06; }
.gnode { cursor: pointer; }
.gnode .halo { color: var(--accent); }
.node-ch { fill: var(--accent); }
.node-char { fill: #22d3ee; }
.node-fs { fill: #f59e0b; }
.dim { opacity: 0.25; }
.nlabel-ch { fill: #fff; font-size: 11px; font-weight: 700; pointer-events: none; }
.nlabel { fill: var(--text-secondary); font-size: 10px; pointer-events: none; }
.hover-card {
  position: absolute; max-width: 260px; padding: 10px 12px;
  background: var(--bg-card); border: 1px solid var(--border-color);
  border-radius: var(--radius-md); box-shadow: 0 10px 30px rgba(0,0,0,0.22);
  pointer-events: none; z-index: 5; transform: translateY(-100%);
}
.hc-title { display: flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.hc-meta { font-size: 10px; color: var(--accent); margin-bottom: 4px; }
.hc-plot { font-size: 11px; line-height: 1.6; color: var(--text-secondary); max-height: 110px; overflow-y: auto; }
.spinning { animation: swSpin 0.9s linear infinite; }
@keyframes swSpin { to { transform: rotate(360deg); } }
</style>
