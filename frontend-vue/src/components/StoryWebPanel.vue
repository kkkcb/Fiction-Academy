<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
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

// ===== 力导向（持续低频运行 + 有机漂浮） =====
interface GNode {
  id: string; kind: 'chapter' | 'character' | 'foreshadow'
  label: string; chapter?: number; words?: number; plot?: string; types?: string[]; emotion?: string
  x: number; y: number; vx: number; vy: number
  phase: number
  born: number
}
interface GLink { source: string; target: string; kind: string }
const nodes = ref<GNode[]>([])
const links = ref<GLink[]>([])
const W = 960, H = 700
const hoverNode = ref<GNode | null>(null)
const dragNode = ref<GNode | null>(null)
let raf = 0
let clock = 0

const TYPE_RING: Record<string, string> = {
  '埋伏笔': '#f59e0b', '推剧情': '#22d3ee', '爽点爆发': '#fb7185',
  '高潮': '#fbbf24', '过渡铺垫': '#94a3b8', '人物塑造': '#a78bfa',
}

function buildGraph(cs: WebChapter[], ts: WebThread[]) {
  const ns: GNode[] = []
  const ls: GLink[] = []
  cs.forEach((c, i) => {
    ns.push({
      id: 'c' + c.chapter, kind: 'chapter', label: String(c.chapter), chapter: c.chapter,
      words: c.words, plot: c.plot, types: c.types, emotion: c.emotion,
      x: 90 + (i / Math.max(cs.length - 1, 1)) * (W - 180) + (Math.random() - 0.5) * 60,
      y: H / 2 + (Math.random() - 0.5) * 170,
      vx: 0, vy: 0, phase: Math.random() * Math.PI * 2, born: i,
    })
  })
  ts.forEach((t, idx) => {
    if (t.chapters.length < 2 && t.kind === 'foreshadow' && !t.payoff_chs?.length) return
    ns.push({
      id: t.kind[0] + ':' + t.name, kind: t.kind as 'character' | 'foreshadow', label: t.name.slice(0, 8),
      x: W / 2 + (Math.random() - 0.5) * (W - 220), y: 90 + Math.random() * (H - 180),
      vx: 0, vy: 0, phase: Math.random() * Math.PI * 2, born: cs.length + idx,
    })
    t.chapters.forEach(n => ls.push({ source: t.kind[0] + ':' + t.name, target: 'c' + n, kind: t.kind }))
  })
  const seen = new Set<string>()
  links.value = ls.filter(l => {
    const k = l.source + '>' + l.target
    if (seen.has(k)) return false
    seen.add(k); return true
  })
  nodes.value = ns
}

function step() {
  const ns = nodes.value
  const byId = new Map(ns.map(n => [n.id, n]))
  for (let i = 0; i < ns.length; i++) {
    for (let j = i + 1; j < ns.length; j++) {
      const a = ns[i], b = ns[j]
      let dx = b.x - a.x, dy = b.y - a.y
      let d2 = dx * dx + dy * dy || 1
      if (d2 > 150000) continue
      const d = Math.sqrt(d2)
      const f = 3200 / d2
      dx /= d; dy /= d
      a.vx -= dx * f; a.vy -= dy * f
      b.vx += dx * f; b.vy += dy * f
    }
  }
  for (const l of links.value) {
    const a = byId.get(l.source), b = byId.get(l.target)
    if (!a || !b) continue
    const dx = b.x - a.x, dy = b.y - a.y
    const d = Math.sqrt(dx * dx + dy * dy) || 1
    const f = (d - 160) * 0.014
    const ux = dx / d, uy = dy / d
    a.vx += ux * f * 10; a.vy += uy * f * 10
    b.vx -= ux * f * 10; b.vy -= uy * f * 10
  }
  const chs = ns.filter(x => x.kind === 'chapter')
  chs.forEach((c, i) => {
    const tx = 90 + (i / Math.max(chs.length - 1, 1)) * (W - 180)
    c.vx += (tx - c.x) * 0.02
    c.vy += (H / 2 - c.y) * 0.008
  })
  clock += 0.016
  for (const nd of ns) {
    if (nd.kind !== 'chapter') {
      nd.vx += (W / 2 - nd.x) * 0.002
      nd.vy += (H / 2 - nd.y) * 0.004
    }
    if (nd === dragNode.value) { nd.vx = 0; nd.vy = 0; continue }
    nd.vx = nd.vx * 0.85 + Math.sin(clock * 0.7 + nd.phase) * 0.05
    nd.vy = nd.vy * 0.85 + Math.cos(clock * 0.55 + nd.phase * 1.3) * 0.05
    nd.x += Math.max(-14, Math.min(14, nd.vx))
    nd.y += Math.max(-14, Math.min(14, nd.vy))
    nd.x = Math.max(46, Math.min(W - 46, nd.x))
    nd.y = Math.max(42, Math.min(H - 46, nd.y))
  }
}

function loop() {
  step()
  raf = requestAnimationFrame(loop)
}

const nodeById = (id: string) => nodes.value.find(n => n.id === id)

function linkPath(l: GLink): string {
  const a = nodeById(l.source), b = nodeById(l.target)
  if (!a || !b) return ''
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2
  let nx = -(b.y - a.y), ny = b.x - a.x
  const len = Math.hypot(nx, ny) || 1
  const off = Math.min(46, len * 0.16) * (l.kind === 'character' ? 1 : -1)
  return 'M ' + a.x + ' ' + a.y + ' Q ' + (mx + nx / len * off) + ' ' + (my + ny / len * off) + ' ' + b.x + ' ' + b.y
}

const linkColor = (k: string) => k === 'character' ? '#22d3ee' : '#f59e0b'
const nodeRadius = (n: GNode) =>
  n.kind === 'chapter' ? Math.max(11, Math.min(21, Math.sqrt((n.words || 3200) / 20)))
  : n.kind === 'character' ? 10 : 8
const ringColor = (n: GNode) => (n.types && n.types.length && TYPE_RING[n.types[0]]) || '#c55d3b'
const dimmed = (id: string) => hoverNode.value && hoverNode.value.id !== id && !links.value.some(l =>
  (l.source === hoverNode.value!.id && l.target === id) || (l.target === hoverNode.value!.id && l.source === id))
const nodeTransform = (n: GNode) => 'translate(' + n.x + ' ' + n.y + ')'
const nodeDelay = (n: GNode) => (n.born * 40) + 'ms'
const haloDelay = (n: GNode) => (n.phase * 0.4) + 's'
const pulseDur = (i: number) => (2.2 + (i % 6) * 0.55).toFixed(1) + 's'
const pulseBegin = (i: number) => ((i * 0.17) % 2.4).toFixed(2) + 's'

function chaptersOfHover(): string {
  if (!hoverNode.value || hoverNode.value.kind === 'chapter') return ''
  const t = threads.value.find(x => x.kind[0] + ':' + x.name.slice(0, 8) === hoverNode.value!.id)
  return (t?.chapters || []).join('、')
}

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

onMounted(() => {
  load()
  raf = requestAnimationFrame(loop)
})
onUnmounted(() => cancelAnimationFrame(raf))
</script>

<template>
  <div class="story-web">
    <div class="sw-head">
      <div class="sw-title"><Network :size="15" :stroke-width="1.75" /> 章节脉络网</div>
      <div class="sw-sub">拖拽节点 · 悬停聚焦 · 流光即人物/伏笔线</div>
      <div class="sw-actions">
        <span v-if="missing > 0" class="sw-missing">{{ missing }} 章待补脉络</span>
        <button v-if="missing > 0" class="btn btn-sm btn-primary" :disabled="backfilling" @click="backfill">
          <RefreshCw :size="12" :stroke-width="1.75" :class="{ spinning: backfilling }" />
          {{ backfilling ? '补全中…' : '补全脉络' }}
        </button>
        <button class="btn btn-sm" :disabled="loading" aria-label="重新布局" title="重新布局" @click="load">
          <RefreshCw :size="12" :stroke-width="1.75" :class="{ spinning: loading }" />
        </button>
      </div>
    </div>

    <div v-if="!chapters.length && !loading" class="sw-empty">还没有已定稿的章节</div>

    <div v-else class="sw-canvas" @pointermove="onPointerMove" @pointerup="onPointerUp" @pointerleave="onPointerUp">
      <svg :viewBox="'0 0 ' + W + ' ' + H" class="sw-svg">
        <defs>
          <filter id="glow2" x="-120%" y="-120%" width="340%" height="340%">
            <feGaussianBlur stdDeviation="5" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <radialGradient id="chGrad" cx="35%" cy="30%">
            <stop offset="0%" stop-color="#ffe9d6" />
            <stop offset="55%" stop-color="#e8966a" />
            <stop offset="100%" stop-color="#c55d3b" />
          </radialGradient>
          <radialGradient id="chGradFg" cx="35%" cy="30%">
            <stop offset="0%" stop-color="#d6f7ff" />
            <stop offset="60%" stop-color="#4fd0e4" />
            <stop offset="100%" stop-color="#0e9ab8" />
          </radialGradient>
        </defs>

        <!-- 连线：流光虚线 -->
        <path v-for="(l, i) in links" :key="'e' + i" :d="linkPath(l)" class="edge"
              :stroke="linkColor(l.kind)"
              :class="{ lit: hoverNode && (l.source === hoverNode.id || l.target === hoverNode.id), dim: !!hoverNode && !(l.source === hoverNode.id || l.target === hoverNode.id) }" />
        <!-- 彗星脉冲 -->
        <g v-for="(l, i) in links" :key="'p' + i">
          <path :id="'lp' + i" :d="linkPath(l)" fill="none" stroke="none" />
          <circle r="3.2" class="comet" :fill="linkColor(l.kind)" filter="url(#glow2)">
            <animateMotion :dur="pulseDur(i)" repeatCount="indefinite" :begin="pulseBegin(i)">
              <mpath :href="'#lp' + i" />
            </animateMotion>
            <animate attributeName="opacity" values="0;1;1;0" :dur="pulseDur(i)" repeatCount="indefinite" :begin="pulseBegin(i)" />
          </circle>
        </g>

        <!-- 节点 -->
        <g v-for="n in nodes" :key="n.id" class="gnode" :transform="nodeTransform(n)"
           :style="{ animationDelay: nodeDelay(n) }"
           @pointerdown="onPointerDown(n, $event)" @mouseenter="hoverNode = n" @mouseleave="hoverNode = null">
          <circle :r="nodeRadius(n) * 2.1" class="halo" :class="{ dim: dimmed(n.id) }"
                  :style="{ animationDelay: haloDelay(n) }" />
          <g v-if="n.kind === 'chapter'" filter="url(#glow2)">
            <circle :r="nodeRadius(n) + 5" fill="none" :stroke="ringColor(n)" stroke-width="1.6" opacity="0.85" />
            <circle :r="nodeRadius(n)" :fill="(n.types || []).includes('爽点爆发') || n.emotion === '燃' ? 'url(#chGradFg)' : 'url(#chGrad)'" />
            <text text-anchor="middle" dy="4" class="nnum">{{ n.label }}</text>
          </g>
          <g v-else-if="n.kind === 'character'" filter="url(#glow2)">
            <rect x="-10" y="-10" width="20" height="20" rx="6" fill="#0e7490" stroke="#67e8f9" stroke-width="1.4" />
            <text text-anchor="middle" dy="4" class="nicon">{{ n.label.slice(0, 1) }}</text>
          </g>
          <g v-else filter="url(#glow2)">
            <rect x="-7" y="-7" width="14" height="14" rx="2.5" fill="#b45309" stroke="#fcd34d" stroke-width="1.3"
                  transform="rotate(45)" />
          </g>
          <text v-if="n.kind !== 'chapter'" text-anchor="middle" :dy="nodeRadius(n) + 17" class="nlabel"
                :class="{ dim: dimmed(n.id) }">{{ n.label }}</text>
        </g>
      </svg>

      <div v-if="hoverNode" class="hover-card" :style="{
        left: Math.min((hoverNode.x / W) * 100, 70) + '%',
        top: Math.min((hoverNode.y / H) * 100, 76) + '%',
      }">
        <div v-if="hoverNode.kind === 'chapter'" class="hc-title">
          第{{ hoverNode.chapter }}章 · {{ chapters.find(c => c.chapter === hoverNode?.chapter)?.title }}
        </div>
        <div v-else class="hc-title">
          <component :is="hoverNode.kind === 'character' ? User : BookMarked" :size="12" /> {{ hoverNode.label }}
        </div>
        <div v-if="hoverNode.kind === 'chapter'" class="hc-body">
          <div class="hc-meta">{{ (hoverNode.types || []).join(' · ') }} | {{ hoverNode.words }} 字 | {{ hoverNode.emotion }}</div>
          <div class="hc-plot">{{ hoverNode.plot }}</div>
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

.sw-canvas {
  flex: 1; min-height: 0; position: relative; overflow: hidden;
  background:
    radial-gradient(ellipse 70% 55% at 50% 42%, rgba(197, 93, 59, 0.10), transparent 70%),
    radial-gradient(ellipse 40% 30% at 18% 75%, rgba(34, 211, 238, 0.06), transparent 70%),
    radial-gradient(ellipse 40% 30% at 82% 25%, rgba(245, 158, 11, 0.05), transparent 70%),
    #14110d;
}
.sw-svg { width: 100%; height: 100%; cursor: grab; }
.sw-svg:active { cursor: grabbing; }

.edge {
  fill: none; stroke-width: 1.5; opacity: 0.5;
  stroke-dasharray: 5 12;
  animation: flow 1.4s linear infinite;
  transition: opacity 0.18s, stroke-width 0.18s;
}
.edge.dim { opacity: 0.06; animation-duration: 3s; }
.edge.lit { opacity: 0.95; stroke-width: 2.4; animation-duration: 0.55s; }
@keyframes flow { to { stroke-dashoffset: -17; } }

.comet { mix-blend-mode: screen; }

.gnode { cursor: pointer; animation: pop-in 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both; }
@keyframes pop-in {
  from { opacity: 0; transform: scale(0.2); }
  to { opacity: 1; }
}
.halo {
  fill: currentColor; opacity: 0.10; color: var(--accent);
  animation: breathe 3.2s ease-in-out infinite;
}
@keyframes breathe {
  0%, 100% { opacity: 0.05; transform: scale(0.9); }
  50% { opacity: 0.16; transform: scale(1.12); }
}
.halo.dim { opacity: 0.02; animation: none; }
.nnum { fill: #fff; font-size: 11px; font-weight: 800; pointer-events: none; }
.nicon { fill: #e0feff; font-size: 10px; font-weight: 700; pointer-events: none; }
.nlabel { fill: #c7bfb4; font-size: 10px; pointer-events: none; transition: opacity 0.15s; }
.nlabel.dim { opacity: 0.2; }

.hover-card {
  position: absolute; max-width: 270px; padding: 10px 12px;
  background: rgba(24, 20, 16, 0.96); border: 1px solid rgba(197, 93, 59, 0.35);
  border-radius: var(--radius-md); box-shadow: 0 14px 44px rgba(0, 0, 0, 0.5);
  pointer-events: none; z-index: 5; transform: translateY(-104%);
}
.hc-title { display: flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 700; color: #f3ece3; margin-bottom: 4px; }
.hc-meta { font-size: 10px; color: #e8966a; margin-bottom: 4px; }
.hc-plot { font-size: 11px; line-height: 1.65; color: #bfb6aa; max-height: 116px; overflow-y: auto; }
.spinning { animation: swSpin 0.9s linear infinite; }
@keyframes swSpin { to { transform: rotate(360deg); } }
</style>
