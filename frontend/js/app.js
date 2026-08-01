import {
  getState, setState, subscribe, onError,
  fetchProjects, createProject, deleteProject,
  fetchConversations, createConversation, selectConversation, deleteConversation, renameConversation,
  sendMessage, regenerateMessage,
  fetchWorkspaceItems, createWorkspaceItem, updateItemStatus, deleteWorkspaceItem,
  fetchChronicle,
  navigateTo,
  fetchAssistants, selectAssistant, createAssistant, updateAssistant, deleteAssistant,
  fetchPoints, selectPoint, summarizeAndArchive, goalGenerate, expertConsult,
} from './store.js'
import { updateProject, updateWorkspaceItem } from './api.js'

const POINT_NAV = [
  { key: 'story_core', label: '故事核', desc: '一句话核心 · 书名' },
  { key: 'world_setting', label: '世界观', desc: '力量体系 · 金手指' },
  { key: 'character_setting', label: '核心人物', desc: '动机 · 红线' },
  { key: 'outline_reverse', label: '倒推大纲', desc: '终局 · 因果链' },
  { key: 'outline', label: '正向大纲', desc: '三幕 · 结局' },
]

const TYPE_LABELS = {
  story_core: '故事核', world_setting: '世界观', character_setting: '人物',
  outline_reverse: '倒推大纲', outline: '正向大纲', foreshadow: '伏笔',
  chapter_plan: '章纲', chapter: '章节', plot: '情节', theme: '主题',
  character: '角色', setting: '设定', summary: '摘要',
}

const STATUS_LABELS = { draft: '草稿', pending: '待审', finalized: '已定', locked: '已锁' }

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
const html = (strings, ...values) => strings.reduce((acc, str, i) => acc + str + (i < values.length ? values[i] : ''), '')

function showToast(message, type = 'info') {
  const toast = document.createElement('div')
  toast.className = `toast toast-${type}`
  toast.textContent = message
  document.body.appendChild(toast)
  requestAnimationFrame(() => toast.classList.add('show'))
  setTimeout(() => {
    toast.classList.remove('show')
    setTimeout(() => toast.remove(), 300)
  }, 3500)
}

function render() {
  const s = getState()
  const app = document.getElementById('app')
  if (!app) return
  if (s.route === 'workspace' && s.currentProjectId) {
    app.innerHTML = renderWorkspacePage(s)
    _postRenderSetup(s)
  } else {
    app.innerHTML = renderProjectsPage(s)
  }
}

function renderProjectsPage(s) {
  return html`
  <div class="projects-page">
    <div class="projects-header">
      <h1 class="projects-title">Fiction Academy</h1>
      <button class="btn btn-primary" data-action="new-project">+ 新建项目</button>
    </div>
    <div class="project-list">
      ${s.projects.length === 0 ? html`
        <div class="empty-state" style="padding:80px 20px;">
          <div class="empty-text">还没有项目</div>
          <div class="empty-hint">点击「新建项目」开始你的第一部小说</div>
        </div>
      ` : s.projects.map(p => html`
        <div class="project-card" data-action="select-project" data-id="${esc(p.id)}">
          <div class="project-card-name">${esc(p.name)}</div>
          <div class="project-card-meta">
            ${p.genre ? html`<span class="tag">${esc(p.genre)}</span>` : ''}
            <span>${formatTime(p.updated_at || p.created_at)}</span>
          </div>
          <button class="project-card-delete" data-action="delete-project" data-id="${esc(p.id)}" title="删除">
            <svg viewBox="0 0 16 16" fill="none" width="14" height="14"><path d="M5 5h6v8a1 1 0 01-1 1H6a1 1 0 01-1-1V5zM4 3h8M6.5 3h3M6.5 7v4M9.5 7v4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
          </button>
        </div>
      `).join('')}
    </div>
  </div>`
}

function renderWorkspacePage(s) {
  const project = s.projects.find(p => p.id === s.currentProjectId)
  const pid = s.currentProjectId
  const pointInfo = POINT_NAV.find(p => p.key === s.currentPoint)
  const isPointMode = s.activeMode === 'point' && !!s.currentPoint
  const currentPointData = s.points.find(p => p.point === s.currentPoint)

  return html`
  <div class="workspace-layout">
    <div class="sidebar-left">
      <div class="glass-header">
        <button class="btn btn-sm" data-action="back-to-projects" title="返回">
          <svg viewBox="0 0 16 16" fill="none" width="14" height="14"><path d="M10 3L5 8l5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <span class="glass-title" data-action="rename-project" data-id="${esc(pid)}">${esc(project?.name || '未命名')}</span>
      </div>

      <div class="point-nav">
        <div class="point-nav-label">创作流程</div>
        ${POINT_NAV.map(p => {
          const data = s.points.find(d => d.point === p.key)
          const status = data?.status || 'pending'
          const isActive = s.currentPoint === p.key && isPointMode
          const dotClass = status === 'done' ? 'done' : status === 'active' ? 'active' : ''
          return html`
            <div class="point-nav-item ${isActive ? 'active' : ''}" data-action="select-point" data-point="${esc(p.key)}">
              <span class="point-nav-dot ${dotClass}">
                ${status === 'done'
                  ? html`<svg viewBox="0 0 16 16" fill="none" width="12" height="12"><path d="M3 8l3.5 3.5L13 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`
                  : status === 'active'
                  ? html`<span class="point-nav-pulse"></span>`
                  : ''
                }
              </span>
              <div class="point-nav-text">
                <span class="point-nav-name">${esc(p.label)}</span>
                <span class="point-nav-desc">${esc(p.desc)}</span>
              </div>
            </div>
          `
        }).join('')}
      </div>

      <div class="sidebar-divider"></div>

      <div class="conv-section">
        ${(s.conversations.filter(c => !c.point).length > 0 || true) ? html`
        <div class="conv-header">
          <span>自由对话</span>
          <button class="btn btn-sm" data-action="new-conv" title="新建">
            <svg viewBox="0 0 16 16" fill="none" width="12" height="12"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
          </button>
        </div>
        ` : ''}
        ${s.conversations.filter(c => !c.point).map(c => html`
          <div class="conv-item ${s.activeMode === 'free' && s.currentConversationId === c.id ? 'active' : ''}" data-action="select-conv" data-id="${esc(c.id)}">
            <span class="conv-title" data-action="rename-conv" data-id="${esc(c.id)}">${esc(c.title)}</span>
            <button class="conv-delete" data-action="delete-conv" data-id="${esc(c.id)}" title="删除">
              <svg viewBox="0 0 16 16" fill="none" width="11" height="11"><path d="M5 5h6v8a1 1 0 01-1 1H6a1 1 0 01-1-1V5zM4 3h8" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
            </button>
          </div>
        `).join('')}
        ${(() => {
          const pointConvs = s.conversations.filter(c => c.point)
          if (pointConvs.length === 0) return ''
          return html`
            <div class="conv-header" style="margin-top:12px;">
              <span>点位对话（旧）</span>
            </div>
            ${pointConvs.map(c => {
              const pointInfo = POINT_NAV.find(p => p.key === c.point)
              return html`
                <div class="conv-item ${s.currentConversationId === c.id ? 'active' : ''}" data-action="select-legacy-point" data-id="${esc(c.id)}" data-point="${esc(c.point)}">
                  <span class="conv-title">${esc(pointInfo?.label || c.title)}</span>
                  <span class="conv-tag">${esc(pointInfo?.desc || c.point)}</span>
                </div>
              `
            }).join('')}
          `
        })()}
      </div>
    </div>

    <div class="resize-handle" id="resize-left"></div>

    <div class="chat-area">
      <div class="chat-header">
        <div class="chat-header-title">
          ${isPointMode
            ? html`<span class="chat-header-point-badge">${esc(pointInfo?.label || '')}</span><span class="chat-header-subtitle">${esc(pointInfo?.desc || '')}</span>`
            : html`<span>自由对话</span>`
          }
        </div>
        ${isPointMode && currentPointData?.status !== 'done' ? html`
          <button class="btn btn-archive ${s.isArchiving ? 'loading' : ''}" data-action="summarize-point" data-point="${esc(s.currentPoint)}" ${s.isArchiving ? 'disabled' : ''}>
            <svg viewBox="0 0 16 16" fill="none" width="14" height="14"><path d="M3 2h7l3 3v9H3V2zM10 2v3h3M5.5 8h5M5.5 10.5h5M5.5 12.5h3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            ${s.isArchiving ? '存档中...' : '总结并存档'}
          </button>
        ` : ''}
        ${isPointMode && currentPointData?.status === 'done' ? html`
          <span class="badge-done">已存档</span>
        ` : ''}
      </div>
      <div id="chat-messages" class="chat-messages">${renderMessages(s)}</div>
      <div class="chat-input-area">
        ${s.assistants.length > 0 ? html`
          <select class="assistant-select" data-action="select-assistant">
            ${s.assistants.map(a => html`<option value="${esc(a.id)}" ${a.id === s.currentAssistantId ? 'selected' : ''}>${esc(a.name)}</option>`).join('')}
          </select>
        ` : ''}
        <textarea id="chat-input" class="chat-input" placeholder="${isPointMode ? '输入你的想法，和 AI 一起确定设定...（输入 / 召唤命令）' : '输入消息...（输入 / 召唤命令）'}" rows="1"></textarea>
        <div id="slash-popover" class="slash-popover" hidden></div>
        <button class="btn btn-send" data-action="send" ${s.isStreaming ? 'disabled' : ''}>
          <svg viewBox="0 0 16 16" fill="none" width="16" height="16"><path d="M2 8l12-5-5 12-2-5-5-2z" fill="currentColor"/></svg>
        </button>
      </div>
    </div>

    <div class="resize-handle" id="resize-right"></div>

    <div class="sidebar-right">
      ${renderOverviewPanel(s)}
    </div>
  </div>`
}

function renderMessages(s) {
  const parts = []
  if (s.messages.length === 0 && !s.isStreaming) {
    const isPoint = s.activeMode === 'point'
    parts.push(html`
      <div class="empty-state">
        <div class="empty-icon">${isPoint ? '✍️' : '💬'}</div>
        <div class="empty-text">${isPoint ? '开始设定' : '开始对话'}</div>
        <div class="empty-hint">${isPoint ? 'AI 会引导你逐步确定核心设定' : '自由讨论任何想法'}</div>
      </div>`)
  }
  for (let i = 0; i < s.messages.length; i++) {
    const m = s.messages[i]
    const isLastAssistant = m.role === 'assistant' && i === s.messages.length - 1
    const cmd = m.role === 'user' ? parseCommand(m.content) : null
    if (cmd) {
      parts.push(html`
        <div class="msg user msg-command" data-cmd="${cmd.type}">
          <div class="msg-role">你</div>
          <div class="command-card">
            <div class="command-header">
              <span class="command-icon">${cmd.icon}</span>
              <span class="command-label">${cmd.label}</span>
            </div>
            <div class="command-body">${formatContent(cmd.idea)}</div>
          </div>
        </div>`)
      continue
    }
    const record = m.role === 'assistant' ? parseConsultRecord(m.content) : null
    if (record) {
      parts.push(html`
        <div class="msg assistant msg-consult">
          <div class="msg-role">专家圆桌</div>
          <div class="msg-content consult-flow">${renderConsultFlow(record)}</div>
          ${!s.isStreaming ? html`
            <div class="msg-actions">
              <button class="btn btn-sm" data-action="copy-consult" data-index="${i}" title="复制裁决">复制裁决</button>
            </div>
          ` : ''}
        </div>`)
      continue
    }
    parts.push(html`
      <div class="msg ${m.role}">
        <div class="msg-role">${m.role === 'user' ? '你' : 'AI'}</div>
        <div class="msg-content markdown-body">${m.role === 'assistant' && m.thinking ? renderThinkingBlock(m.thinking, false) : ''}${m.role === 'user' ? formatContent(m.content) : formatMd(m.content)}</div>
        ${m.role === 'assistant' ? html`
          <div class="msg-actions">
            <button class="btn btn-sm" data-action="copy-msg" data-index="${i}" title="复制">复制</button>
            ${isLastAssistant && !s.isStreaming ? html`
              <button class="btn btn-sm" data-action="regenerate" title="重新生成">重新生成</button>
            ` : ''}
          </div>
        ` : ''}
      </div>`)
  }
  if (s.isStreaming) {
    if (s.consultFlow) {
      parts.push(html`
        <div class="msg assistant msg-consult" id="streaming-msg">
          <div class="msg-role">专家圆桌</div>
          <div class="msg-content consult-flow">${renderConsultFlow(s.consultFlow)}</div>
        </div>`)
    } else {
      const hasThinking = !!s.streamingThinking
      const isEmpty = !s.streamingContent && !hasThinking
      parts.push(html`
        <div class="msg assistant" id="streaming-msg">
          <div class="msg-role">AI</div>
          <div class="msg-content markdown-body">
            ${renderThinkingBlock(s.streamingThinking, true)}
            ${isEmpty ? html`<span class="thinking-hint">正在思考<span class="thinking-dots"></span></span>` : html`${formatMd(s.streamingContent)}${s.streamingContent ? '<span class="streaming-cursor"></span>' : ''}`}
          </div>
        </div>`)
    }
  }
  return parts.join('')
}

function renderOverviewPanel(s) {
  const archivedPoints = POINT_NAV.map(p => {
    const item = s.workspaceItems.find(w => w.item_type === p.key && (w.status === 'finalized' || w.status === 'locked'))
    return { nav: p, item }
  }).filter(x => x.item)

  const otherItems = s.workspaceItems.filter(w =>
    !POINT_NAV.some(p => p.key === w.item_type)
  )

  return html`
    <div class="overview-header">
      <span>总览</span>
      <button class="btn btn-sm" data-action="add-item" title="添加设定">
        <svg viewBox="0 0 16 16" fill="none" width="12" height="12"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      </button>
    </div>

    <div class="overview-body">
      ${archivedPoints.length > 0 ? html`
        <div class="overview-section">
          ${archivedPoints.map(({ nav, item }) => {
            const meta = _safeParseMeta(item.metadata)
            const fieldsText = meta ? Object.entries(meta).filter(([, v]) => v).slice(0, 4).map(([k, v]) => html`<div class="ov-field"><span class="ov-field-key">${esc(k)}</span><span class="ov-field-val">${esc(String(v).slice(0, 60))}</span></div>`).join('') : ''
            return html`
              <div class="ov-card ${item.status === 'locked' ? 'locked' : ''}">
                <div class="ov-card-header">
                  <span class="ov-card-title">${esc(nav.label)}</span>
                  <span class="ov-card-status ${item.status}">${STATUS_LABELS[item.status] || item.status}</span>
                </div>
                <div class="ov-card-content markdown-body">${formatMd(item.content || '')}</div>
                ${fieldsText ? html`<div class="ov-fields">${fieldsText}</div>` : ''}
                <div class="ov-card-actions">
                  ${item.status !== 'locked' ? html`<button class="btn-link" data-action="edit-item" data-id="${esc(item.id)}">编辑</button>` : ''}
                  ${item.status === 'draft' ? html`<button class="btn-link" data-action="approve-item" data-id="${esc(item.id)}">通过</button>` : ''}
                  ${item.status !== 'locked' ? html`<button class="btn-link danger" data-action="delete-item" data-id="${esc(item.id)}">删除</button>` : ''}
                </div>
              </div>
            `
          }).join('')}
        </div>
      ` : ''}

      ${otherItems.length > 0 ? html`
        <div class="overview-section">
          <div class="overview-section-label">其他设定</div>
          ${otherItems.map(item => html`
            <div class="ov-card-simple">
              <div class="ov-card-header">
                <span class="ov-type-badge">${TYPE_LABELS[item.item_type] || item.item_type}</span>
                <span class="ov-card-status ${item.status}">${STATUS_LABELS[item.status] || ''}</span>
              </div>
              <div class="ov-card-title">${esc(item.title || '无标题')}</div>
              <div class="ov-card-content markdown-body">${formatMd(item.content || '')}</div>
              <div class="ov-card-actions">
                ${item.status !== 'locked' ? html`<button class="btn-link" data-action="edit-item" data-id="${esc(item.id)}">编辑</button>` : ''}
                ${item.status !== 'locked' ? html`<button class="btn-link danger" data-action="delete-item" data-id="${esc(item.id)}">删除</button>` : ''}
              </div>
            </div>
          `).join('')}
        </div>
      ` : ''}

      ${archivedPoints.length === 0 && otherItems.length === 0 ? html`
        <div class="empty-state" style="padding:40px 16px;">
          <div class="empty-text">还没有存档的设定</div>
          <div class="empty-hint">完成点位对话后点击「总结并存档」</div>
        </div>
      ` : ''}

      ${s.chronicle ? html`
        <div class="overview-section">${renderChronicle(s.chronicle)}</div>
      ` : ''}
    </div>
  `
}

function _safeParseMeta(str) {
  if (!str) return null
  try { return typeof str === 'string' ? JSON.parse(str) : str } catch { return null }
}

function renderChronicle(chronicle) {
  if (!chronicle) return ''
  const hasData = (chronicle.timeline && chronicle.timeline.length > 0) ||
                  (chronicle.characters && chronicle.characters.length > 0) ||
                  (chronicle.key_events && chronicle.key_events.length > 0)
  if (!hasData) return ''
  return html`
    <div class="overview-section-label">编年录</div>
    ${chronicle.timeline && chronicle.timeline.length > 0 ? html`
      <div class="chron-section">
        ${chronicle.timeline.map(t => html`<div class="chron-item"><span class="chron-time">${esc(t.time)}</span><span class="chron-event">${esc(t.event)}</span></div>`).join('')}
      </div>
    ` : ''}
    ${chronicle.characters && chronicle.characters.length > 0 ? html`
      <div class="chron-section">
        ${chronicle.characters.map(c => html`<div class="chron-item"><span class="chron-char">${esc(c)}</span></div>`).join('')}
      </div>
    ` : ''}
    ${chronicle.key_events && chronicle.key_events.length > 0 ? html`
      <div class="chron-section">
        ${chronicle.key_events.map(e => html`<div class="chron-item"><span class="chron-event">${esc(e)}</span></div>`).join('')}
      </div>
    ` : ''}
  `
}

let _streamingStarted = false
let _autoScroll = false
let _savedScrollRatio = 1
let _savedScrollTop = 0
let _streamRAF = null
let _renderTimer = null
let _immediateRender = false
let _lastConvId = null
let _scrollMode = 'preserve'

function smartRender() {
  const s = getState()

  if (s.isStreaming) {
    if (_renderTimer) { clearTimeout(_renderTimer); _renderTimer = null }
    if (!_streamingStarted) {
      _streamingStarted = true
      _autoScroll = true
      const msgsEl = document.getElementById('chat-messages')
      if (msgsEl) {
        msgsEl.innerHTML = renderMessages(s)
        const btn = document.getElementById('chat-input')
        if (btn) btn.disabled = true
        msgsEl.scrollTop = msgsEl.scrollHeight
      }
      return
    }
    if (!_streamRAF) {
      _streamRAF = requestAnimationFrame(_updateStreamingContent)
    }
    return
  }

  if (_streamingStarted) {
    _streamingStarted = false
    _autoScroll = false
  }

  if (_immediateRender) {
    _immediateRender = false
    if (_renderTimer) { clearTimeout(_renderTimer); _renderTimer = null }
    _doRender(s)
    return
  }

  if (_renderTimer) clearTimeout(_renderTimer)
  _renderTimer = setTimeout(() => {
    _renderTimer = null
    _doRender(getState())
  }, 16)
}

function _doRender(s) {
  const app = document.getElementById('app')
  if (!app) return

  const convChanged = s.currentConversationId !== _lastConvId
  if (convChanged) {
    _lastConvId = s.currentConversationId
    _scrollMode = 'bottom'
  }

  const focusEl = document.activeElement
  let savedFocusId = null
  let savedInputValue = null
  let savedSelStart = null
  let savedSelEnd = null
  if (!convChanged && focusEl && (focusEl.tagName === 'TEXTAREA' || focusEl.tagName === 'INPUT') && focusEl.id) {
    savedFocusId = focusEl.id
    savedInputValue = focusEl.value
    savedSelStart = focusEl.selectionStart
    savedSelEnd = focusEl.selectionEnd
  }

  const msgsEl = document.getElementById('chat-messages')
  if (!convChanged && msgsEl && msgsEl.scrollHeight > 0) {
    _savedScrollTop = msgsEl.scrollTop
  }
  render()

  if (!convChanged && savedFocusId) {
    const restored = document.getElementById(savedFocusId)
    if (restored && (restored.tagName === 'TEXTAREA' || restored.tagName === 'INPUT')) {
      if (savedInputValue != null) restored.value = savedInputValue
      try { restored.setSelectionRange(savedSelStart, savedSelEnd) } catch {}
      restored.focus()
    }
  }

  const mode = _scrollMode
  _scrollMode = 'preserve'
  if (mode === 'top') {
    requestAnimationFrame(_scrollToTop)
  } else if (mode === 'bottom') {
    requestAnimationFrame(_scrollToBottom)
  } else if (_savedScrollRatio >= 0.99) {
    requestAnimationFrame(_scrollToBottom)
  } else {
    requestAnimationFrame(_restoreScrollTop)
  }
}

export function requestImmediateRender() {
  _immediateRender = true
  smartRender()
}

function _updateStreamingContent() {
  _streamRAF = null
  const s = getState()
  const streamMsg = document.getElementById('streaming-msg')
  if (streamMsg) {
    const msgsEl = document.getElementById('chat-messages')
    const nearBottom = msgsEl
      ? (msgsEl.scrollHeight - msgsEl.scrollTop - msgsEl.clientHeight) < 120
      : false
    if (s.consultFlow) {
      const flowEl = streamMsg.querySelector('.consult-flow')
      if (flowEl) {
        flowEl.innerHTML = renderConsultFlow(s.consultFlow)
      }
    } else {
      const contentEl = streamMsg.querySelector('.msg-content')
      if (contentEl) {
        const thinkingHtml = renderThinkingBlock(s.streamingThinking, true)
        const bodyHtml = s.streamingContent
          ? formatMd(s.streamingContent) + '<span class="streaming-cursor"></span>'
          : '<span class="thinking-hint">正在思考<span class="thinking-dots"></span></span>'
        contentEl.innerHTML = thinkingHtml + bodyHtml
      }
    }
    if (nearBottom) {
      if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight
    }
  }
}

function _scrollToBottom() {
  const msgsEl = document.getElementById('chat-messages')
  if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight
}

function _scrollToTop() {
  const msgsEl = document.getElementById('chat-messages')
  if (msgsEl) msgsEl.scrollTop = 0
}

function _restoreScrollTop() {
  const msgsEl = document.getElementById('chat-messages')
  if (msgsEl) {
    const maxTop = msgsEl.scrollHeight - msgsEl.clientHeight
    msgsEl.scrollTop = Math.min(_savedScrollTop, Math.max(0, maxTop))
  }
}

function _postRenderSetup(s) {
  const msgsEl = document.getElementById('chat-messages')
  if (msgsEl && !msgsEl._faScrollInit) {
    msgsEl._faScrollInit = true
    msgsEl.addEventListener('scroll', () => {
      const distFromBottom = msgsEl.scrollHeight - msgsEl.scrollTop - msgsEl.clientHeight
      if (distFromBottom > 120) {
        _autoScroll = false
      } else if (distFromBottom < 40) {
        _autoScroll = true
      }
    }, { passive: true })
  }
  const input = document.getElementById('chat-input')
  if (input && !input._faInit) {
    input._faInit = true
    const popover = document.getElementById('slash-popover')
    let slashState = { open: false, items: [], active: 0 }

    const closeSlash = () => {
      if (!slashState.open) return
      slashState.open = false
      slashState.items = []
      if (popover) { popover.hidden = true; popover.innerHTML = '' }
    }

    const renderSlash = () => {
      if (!popover) return
      if (!slashState.open || slashState.items.length === 0) {
        popover.hidden = true; popover.innerHTML = ''; return
      }
      popover.hidden = false
      popover.innerHTML = slashState.items.map((it, i) => html`
        <div class="slash-item${i === slashState.active ? ' active' : ''}" data-idx="${i}">
          <span class="slash-icon">${it.icon}</span>
          <div class="slash-text">
            <div class="slash-cmd">${esc(it.cmd)} <span class="slash-title">${esc(it.title)}</span></div>
            <div class="slash-desc">${esc(it.desc)}</div>
          </div>
        </div>`).join('')
      popover.querySelectorAll('.slash-item').forEach(el => {
        el.addEventListener('mousedown', e => {
          e.preventDefault()
          const idx = parseInt(el.dataset.idx)
          if (slashState.items[idx]) applySlash(slashState.items[idx])
        })
      })
    }

    const applySlash = (item) => {
      input.value = item.cmd + ' '
      input.focus()
      const v = input.value.length
      input.setSelectionRange(v, v)
      input.style.height = 'auto'
      input.style.height = Math.min(input.scrollHeight, 160) + 'px'
      closeSlash()
    }

    const updateSlash = () => {
      const val = input.value
      const isPoint = !!getState().currentPoint
      if (!val.startsWith('/') || /\s/.test(val.slice(1))) { closeSlash(); return }
      const q = val.toLowerCase()
      const items = SLASH_COMMANDS.filter(c => (!c.pointOnly || isPoint) && c.cmd.toLowerCase().startsWith(q))
      slashState.items = items
      slashState.active = 0
      slashState.open = items.length > 0
      renderSlash()
    }

    input.addEventListener('input', () => {
      input.style.height = 'auto'
      input.style.height = Math.min(input.scrollHeight, 160) + 'px'
      updateSlash()
    })
    input.addEventListener('keydown', e => {
      if (slashState.open) {
        if (e.key === 'ArrowDown') {
          e.preventDefault()
          slashState.active = (slashState.active + 1) % slashState.items.length
          renderSlash(); return
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault()
          slashState.active = (slashState.active - 1 + slashState.items.length) % slashState.items.length
          renderSlash(); return
        }
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault()
          if (slashState.items[slashState.active]) { applySlash(slashState.items[slashState.active]); return }
        }
        if (e.key === 'Escape') { e.preventDefault(); closeSlash(); return }
        if (e.key === 'Tab') {
          if (slashState.items[slashState.active]) { e.preventDefault(); applySlash(slashState.items[slashState.active]); return }
        }
      } else {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault()
          handleSend()
        }
      }
    })
    input.addEventListener('blur', () => { setTimeout(closeSlash, 150) })
  }
}

function showModal(htmlContent) {
  const overlay = document.createElement('div')
  overlay.className = 'modal-overlay'
  overlay.id = 'modal-overlay'
  overlay.innerHTML = htmlContent
  document.body.appendChild(overlay)
  requestAnimationFrame(() => overlay.classList.add('show'))
  const firstInput = overlay.querySelector('input, textarea, select')
  if (firstInput) firstInput.focus()
}

function closeModal() {
  const overlay = document.getElementById('modal-overlay')
  if (overlay) {
    overlay.classList.remove('show')
    setTimeout(() => overlay.remove(), 200)
  }
}

function showCreateProject() {
  showModal(html`
    <div class="modal-card">
      <div class="modal-header"><h3>新建项目</h3></div>
      <div class="modal-body">
        <input class="modal-input" id="modal-name" placeholder="小说名称" />
        <input class="modal-input" id="modal-genre" placeholder="类型（可选，如：玄幻、都市、科幻）" />
      </div>
      <div class="modal-footer">
        <button class="btn" data-action="close-modal">取消</button>
        <button class="btn btn-primary" data-action="modal-confirm" data-modal="create-project">创建</button>
      </div>
    </div>
  `)
}

function showConfirmDeleteProject(id) {
  showModal(html`
    <div class="modal-card">
      <div class="modal-header"><h3>删除项目？</h3></div>
      <div class="modal-body"><p>此操作不可恢复，所有对话和设定都将丢失。</p></div>
      <div class="modal-footer">
        <button class="btn" data-action="close-modal">取消</button>
        <button class="btn btn-danger" data-action="modal-confirm" data-modal="delete-project" data-id="${esc(id)}">确认删除</button>
      </div>
    </div>
  `)
}

function showConfirmDeleteConv(id) {
  showModal(html`
    <div class="modal-card">
      <div class="modal-header"><h3>删除对话？</h3></div>
      <div class="modal-footer">
        <button class="btn" data-action="close-modal">取消</button>
        <button class="btn btn-danger" data-action="modal-confirm" data-modal="delete-conv" data-id="${esc(id)}">确认删除</button>
      </div>
    </div>
  `)
}

function showAddItem() {
  const types = Object.keys(TYPE_LABELS)
  showModal(html`
    <div class="modal-card">
      <div class="modal-header"><h3>添加设定</h3></div>
      <div class="modal-body">
        <select class="modal-input" id="modal-type">
          ${types.map(t => html`<option value="${esc(t)}">${TYPE_LABELS[t]}</option>`).join('')}
        </select>
        <input class="modal-input" id="modal-title" placeholder="标题" />
        <textarea class="modal-input" id="modal-content" placeholder="内容（支持 Markdown）" rows="6"></textarea>
      </div>
      <div class="modal-footer">
        <button class="btn" data-action="close-modal">取消</button>
        <button class="btn btn-primary" data-action="modal-confirm" data-modal="add-item">添加</button>
      </div>
    </div>
  `)
}

function showEditItem(id) {
  const s = getState()
  const item = s.workspaceItems.find(i => i.id === id)
  if (!item) return
  showModal(html`
    <div class="modal-card">
      <div class="modal-header"><h3>编辑设定</h3></div>
      <div class="modal-body">
        <input class="modal-input" id="modal-title" value="${esc(item.title || '')}" placeholder="标题" />
        <textarea class="modal-input" id="modal-content" rows="8">${esc(item.content || '')}</textarea>
      </div>
      <div class="modal-footer">
        <button class="btn" data-action="close-modal">取消</button>
        <button class="btn btn-primary" data-action="modal-confirm" data-modal="edit-item" data-id="${esc(id)}">保存</button>
      </div>
    </div>
  `)
}

function showCreateAssistant() {
  showModal(html`
    <div class="modal-card">
      <div class="modal-header"><h3>创建助理</h3></div>
      <div class="modal-body">
        <input class="modal-input" id="modal-name" placeholder="助理名称" />
        <textarea class="modal-input" id="modal-prompt" placeholder="系统提示词（定义助理的角色和风格）" rows="5"></textarea>
      </div>
      <div class="modal-footer">
        <button class="btn" data-action="close-modal">取消</button>
        <button class="btn btn-primary" data-action="modal-confirm" data-modal="create-assistant">创建</button>
      </div>
    </div>
  `)
}

function showEditAssistant(id) {
  const s = getState()
  const a = s.assistants.find(x => x.id === id)
  if (!a) return
  showModal(html`
    <div class="modal-card">
      <div class="modal-header"><h3>编辑助理</h3></div>
      <div class="modal-body">
        <input class="modal-input" id="modal-name" value="${esc(a.name || '')}" />
        <textarea class="modal-input" id="modal-prompt" rows="5">${esc(a.system_prompt || '')}</textarea>
      </div>
      <div class="modal-footer">
        <button class="btn" data-action="close-modal">取消</button>
        <button class="btn btn-primary" data-action="modal-confirm" data-modal="edit-assistant" data-id="${esc(id)}">保存</button>
      </div>
    </div>
  `)
}

function showConfirmDeleteAssistant(id) {
  showModal(html`
    <div class="modal-card">
      <div class="modal-header"><h3>删除助理？</h3></div>
      <div class="modal-footer">
        <button class="btn" data-action="close-modal">取消</button>
        <button class="btn btn-danger" data-action="modal-confirm" data-modal="delete-assistant" data-id="${esc(id)}">确认删除</button>
      </div>
    </div>
  `)
}

function showInlineRename(titleEl, type) {
  const id = titleEl.dataset.id
  const oldName = titleEl.textContent
  const input = document.createElement('input')
  input.className = 'inline-rename-input'
  input.style.cssText = 'font-size:13px;font-weight:600;padding:2px 8px;border-radius:4px;flex:1;min-width:0;'
  input.value = oldName
  titleEl.replaceWith(input)
  input.focus()
  input.select()
  const finish = async () => {
    const newName = input.value.trim() || oldName
    if (newName !== oldName) {
      if (type === 'project') {
        await updateProject(id, { name: newName })
        await fetchProjects()
      } else {
        await renameConversation(id, newName)
      }
    }
    render()
  }
  input.addEventListener('blur', finish)
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); input.blur() }
    if (e.key === 'Escape') { input.value = oldName; input.blur() }
  })
}

function handleSend() {
  const input = document.getElementById('chat-input')
  if (!input) return
  const content = input.value.trim()
  if (!content) return
  const s = getState()
  if (!s.currentConversationId) return
  if (s.isStreaming) return
  _autoScroll = true
  _scrollMode = 'bottom'
  input.value = ''
  input.style.height = 'auto'

  const goalMatch = content.match(/^\/goal\s+(.+)/i)
  if (goalMatch) {
    const idea = goalMatch[1].trim()
    if (s.currentPoint && s.currentProjectId) {
      goalGenerate(s.currentProjectId, s.currentPoint, idea)
      requestImmediateRender()
      return
    }
    showToast('请在点位对话中使用 /goal', 'info')
    return
  }

  const consultMatch = content.match(/^\/consult\s+(.+)/i)
  if (consultMatch) {
    const idea = consultMatch[1].trim()
    if (s.currentPoint && s.currentProjectId) {
      expertConsult(s.currentProjectId, s.currentPoint, idea)
      requestImmediateRender()
      return
    }
    showToast('请在点位对话中使用 /consult', 'info')
    return
  }

  sendMessage(s.currentConversationId, content)
  requestImmediateRender()
}

function formatContent(text) {
  if (!text) return ''
  return esc(text).replace(/\n/g, '<br>')
}

function parseCommand(content) {
  if (typeof content !== 'string') return null
  const consult = content.match(/^\/consult\s+([\s\S]+)/i)
  if (consult) return { type: 'consult', icon: '🎯', label: '专家会诊', idea: consult[1].trim() }
  const goal = content.match(/^\/goal\s+([\s\S]+)/i)
  if (goal) return { type: 'goal', icon: '⚡', label: '快速生成', idea: goal[1].trim() }
  return null
}

function renderThinkingBlock(text, streaming) {
  if (!text || !text.trim()) return ''
  return html`
    <details class="thinking-block${streaming ? ' is-streaming' : ''}" ${streaming ? 'open' : ''}>
      <summary class="thinking-summary">
        <span class="thinking-icon">💭</span>
        <span class="thinking-title">${streaming ? '思考中' : '思考过程'}</span>
      </summary>
      <div class="thinking-content">${formatMd(text)}</div>
    </details>`
}

const EXPERT_ICONS = { '主线策划': '🎯', '世界观架构师': '🌍', '人物塑造师': '👤', '逆向架构师': '🔁', '节奏导演': '🎬' }
const EXPERT_COLORS = { '主线策划': '#d97757', '世界观架构师': '#7c3aed', '人物塑造师': '#0891b2', '逆向架构师': '#059669', '节奏导演': '#db2777' }
function expertIcon(name) { return EXPERT_ICONS[name] || '💬' }
function expertColor(name) { return EXPERT_COLORS[name] || '#78716c' }
function expertKey(name) { return ({ '主线策划': 'leader', '世界观架构师': 'world', '人物塑造师': 'character', '逆向架构师': 'reverse', '节奏导演': 'pacing' })[name] || 'other' }

const SLASH_COMMANDS = [
  { cmd: '/consult', icon: '🎯', title: '专家会诊', desc: '召集五位创作专家圆桌讨论，主线策划统率全局后给出裁决', pointOnly: true },
  { cmd: '/goal', icon: '⚡', title: '快速生成', desc: '根据一句话想法，AI 直接生成完整的点位设定', pointOnly: true },
]

function parseConsultRecord(content) {
  if (typeof content !== 'string' || !content) return null
  const t = content.trim()
  if (t.charAt(0) !== '{') return null
  try {
    const obj = JSON.parse(t)
    if (obj && obj.kind === 'consult_record') return obj
  } catch {}
  return null
}

function renderConsultFlow(record) {
  const parts = []
  if (record.leader && (record.leader.content || record.leader.thinking)) {
    const ld = record.leader
    const color = expertColor(ld.name)
    parts.push(html`
      <div class="cf-msg cf-leader">
        <span class="cf-avatar" style="background:${color}1a">${expertIcon(ld.name)}</span>
        <div class="cf-bubble-wrap">
          <div class="cf-name" style="color:${color}">${esc(ld.name)} <span class="cf-role">统率者定调</span></div>
          ${renderThinkingBlock(ld.thinking, !ld.content)}
          <div class="cf-bubble">${ld.content ? html`<div class="cf-text markdown-body">${formatMd(ld.content)}</div>` : ''}</div>
        </div>
      </div>`)
  }
  for (const r of (record.rounds || [])) {
    parts.push(html`<div class="cf-divider">第${r.round}轮 · ${esc(r.label || '讨论')}${r.round > 1 ? '（含统率者）' : ''}</div>`)
    for (const e of (r.entries || [])) {
      const color = expertColor(e.name)
      parts.push(html`
        <div class="cf-msg${e.is_leader ? ' is-leader' : ''}">
          <span class="cf-avatar" style="background:${color}1a">${expertIcon(e.name)}</span>
          <div class="cf-bubble-wrap">
            <div class="cf-name" style="color:${color}">${esc(e.name)} <span class="cf-role">${esc(e.perspective || '')}</span></div>
            ${renderThinkingBlock(e.thinking, !e.content)}
            <div class="cf-bubble">${e.content ? html`<div class="cf-text markdown-body">${formatMd(e.content)}</div>` : ''}</div>
          </div>
        </div>`)
    }
  }
  if (record.summary || record.summaryThinking) {
    const color = '#d97757'
    parts.push(html`
      <div class="cf-msg cf-verdict">
        <span class="cf-avatar" style="background:${color}1a">⚖️</span>
        <div class="cf-bubble-wrap">
          <div class="cf-name" style="color:${color}">终局裁决 <span class="cf-role">主线策划</span></div>
          ${renderThinkingBlock(record.summaryThinking, !record.summary)}
          <div class="cf-bubble">${record.summary ? html`<div class="cf-text markdown-body">${formatMd(record.summary)}</div>` : ''}</div>
        </div>
      </div>`)
  }
  if (record.error) {
    parts.push(html`<div class="cf-error">⚠️ ${esc(record.error)}</div>`)
  }
  if (record.pending) {
    parts.push(html`<div class="cf-pending">${esc(record.pending)}<span class="thinking-dots"></span></div>`)
  }
  return parts.join('')
}

const _mdCache = new Map()
const _MD_CACHE_MAX = 100
let _markedReady = false
function _getMarked() {
  if (_markedReady) return window.marked
  if (window.marked) {
    window.marked.setOptions({ breaks: false, gfm: true })
    _markedReady = true
    return window.marked
  }
  return null
}

function formatMd(text) {
  if (!text) return ''
  if (_mdCache.has(text)) return _mdCache.get(text)
  const md = _getMarked()
  let h
  if (md) {
    const normalized = _normalizeMd(text)
    try { h = md.parse(normalized) } catch { h = _fallbackMd(text) }
  } else {
    h = _fallbackMd(text)
  }
  if (text.length < 8000) {
    if (_mdCache.size >= _MD_CACHE_MAX) {
      const firstKey = _mdCache.keys().next().value
      _mdCache.delete(firstKey)
    }
    _mdCache.set(text, h)
  }
  return h
}

function _normalizeMd(text) {
  let t = text.replace(/\r\n/g, '\n')
  t = t.replace(/\n{3,}/g, '\n\n')
  return t
}

function _fallbackMd(text) {
  let h = esc(text)
  h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  h = h.replace(/^# (.+)$/gm, '<h2>$1</h2>')
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  h = h.replace(/\*(.+?)\*/g, '<em>$1</em>')
  h = h.replace(/`(.+?)`/g, '<code>$1</code>')
  h = h.replace(/^[-*] (.+)$/gm, '<li>$1</li>')
  h = h.replace(/\n\n/g, '<br><br>')
  h = h.replace(/\n/g, '<br>')
  return h
}

function formatTime(ts) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
  } catch { return ts }
}

document.addEventListener('click', async (e) => {
  if (e.target.closest('.modal-overlay') && !e.target.closest('.modal-card')) {
    closeModal()
    return
  }
  const target = e.target.closest('[data-action]')
  if (!target) return
  const action = target.dataset.action
  const s = getState()
  const pid = s.currentProjectId

  switch (action) {
    case 'back-to-projects':
      navigateTo('projects')
      break
    case 'select-project':
      navigateTo('workspace', { currentProjectId: target.dataset.id })
      break
    case 'rename-project':
    case 'rename-conv':
      if (e.target === target) showInlineRename(target, action === 'rename-project' ? 'project' : 'conv')
      break
    case 'new-project':
      showCreateProject()
      break
    case 'delete-project':
      showConfirmDeleteProject(target.dataset.id)
      break

    case 'select-point': {
      if (pid) selectPoint(pid, target.dataset.point)
      break
    }
    case 'summarize-point': {
      if (pid && s.currentPoint) {
        const r = await summarizeAndArchive(pid, s.currentPoint)
        if (r) {
          const label = POINT_NAV.find(p => p.key === s.currentPoint)?.label || s.currentPoint
          showToast(`${label} 已存档`, 'success')
          const nextPoint = POINT_NAV.find((p, i) => i > POINT_NAV.findIndex(x => x.key === s.currentPoint))
          if (nextPoint) {
            selectPoint(pid, nextPoint.key)
          }
        }
      }
      break
    }

    case 'new-conv':
      if (pid) {
        const c = await createConversation(pid, '新对话')
        if (c) showToast('新对话已创建', 'success')
      }
      break
    case 'select-conv':
      selectConversation(target.dataset.id)
      break
    case 'select-legacy-point': {
      const convId = target.dataset.id
      const point = target.dataset.point
      setState({ currentPoint: point, activeMode: 'point', currentConversationId: convId, messages: [], isStreaming: false, streamingContent: '' })
      try {
        const apiMod = await import('./api.js')
        const msgs = await apiMod.getMessages(convId)
        if (getState().currentConversationId === convId) {
          setState({ messages: msgs, error: null })
        }
      } catch (err) { setState({ error: err.message }) }
      break
    }
    case 'delete-conv':
      showConfirmDeleteConv(target.dataset.id)
      break

    case 'send':
      handleSend()
      break
    case 'regenerate':
      if (s.currentConversationId) regenerateMessage(s.currentConversationId)
      break
    case 'copy-msg': {
      const idx = parseInt(target.dataset.index)
      const msg = s.messages[idx]
      if (msg) {
        try { await navigator.clipboard.writeText(msg.content); showToast('已复制', 'success') }
        catch { showToast('复制失败', 'error') }
      }
      break
    }
    case 'copy-consult': {
      const idx = parseInt(target.dataset.index)
      const msg = s.messages[idx]
      const rec = msg ? parseConsultRecord(msg.content) : null
      if (rec && rec.summary) {
        try { await navigator.clipboard.writeText(rec.summary); showToast('已复制裁决', 'success') }
        catch { showToast('复制失败', 'error') }
      }
      break
    }

    case 'add-item':
      showAddItem()
      break
    case 'edit-item':
      showEditItem(target.dataset.id)
      break
    case 'delete-item':
      if (pid) {
        await deleteWorkspaceItem(target.dataset.id, pid)
        showToast('已删除', 'success')
      }
      break
    case 'approve-item':
      if (pid) {
        await updateItemStatus(target.dataset.id, 'finalized', pid)
        showToast('已通过', 'success')
      }
      break
    case 'lock-item':
      if (pid) {
        await updateItemStatus(target.dataset.id, 'locked', pid)
        showToast('已锁定', 'success')
      }
      break
    case 'unlock-item':
      if (pid) {
        await updateItemStatus(target.dataset.id, 'finalized', pid)
        showToast('已解锁', 'success')
      }
      break

    case 'new-assistant':
      showCreateAssistant()
      break
    case 'edit-assistant':
      showEditAssistant(target.dataset.id)
      break
    case 'delete-assistant':
      showConfirmDeleteAssistant(target.dataset.id)
      break

    case 'close-modal':
      closeModal()
      break
    case 'modal-confirm':
      await _handleModalConfirm(target)
      break
  }
})

async function _handleModalConfirm(target) {
  const modal = target.dataset.modal
  const id = target.dataset.id
  const s = getState()
  const pid = s.currentProjectId

  switch (modal) {
    case 'create-project': {
      const name = document.getElementById('modal-name')?.value.trim()
      const genre = document.getElementById('modal-genre')?.value.trim()
      if (!name) { showToast('请输入名称', 'error'); return }
      closeModal()
      const p = await createProject(name, genre)
      if (p) {
        showToast('项目已创建', 'success')
        navigateTo('workspace', { currentProjectId: p.id })
      }
      break
    }
    case 'delete-project':
      closeModal()
      await deleteProject(id)
      break
    case 'delete-conv':
      closeModal()
      await deleteConversation(id)
      break
    case 'add-item': {
      const type = document.getElementById('modal-type')?.value
      const title = document.getElementById('modal-title')?.value.trim()
      const content = document.getElementById('modal-content')?.value.trim()
      if (!pid || !type) return
      closeModal()
      await createWorkspaceItem(pid, { item_type: type, title: title || TYPE_LABELS[type], content: content || '' })
      showToast('已添加', 'success')
      break
    }
    case 'edit-item': {
      const title = document.getElementById('modal-title')?.value.trim()
      const content = document.getElementById('modal-content')?.value.trim()
      if (!pid) return
      closeModal()
      try {
        await updateWorkspaceItem(id, { title, content })
        await fetchWorkspaceItems(pid)
        showToast('已保存', 'success')
      } catch (err) { setState({ error: err.message }) }
      break
    }
    case 'create-assistant': {
      const name = document.getElementById('modal-name')?.value.trim()
      const prompt = document.getElementById('modal-prompt')?.value.trim()
      if (!name) { showToast('请输入名称', 'error'); return }
      closeModal()
      await createAssistant({ name, system_prompt: prompt })
      break
    }
    case 'edit-assistant': {
      const name = document.getElementById('modal-name')?.value.trim()
      const prompt = document.getElementById('modal-prompt')?.value.trim()
      if (!name) { showToast('请输入名称', 'error'); return }
      closeModal()
      await updateAssistant(id, { name, system_prompt: prompt })
      break
    }
    case 'delete-assistant':
      closeModal()
      await deleteAssistant(id)
      break
  }
}

document.addEventListener('change', (e) => {
  const target = e.target.closest('[data-action]')
  if (!target) return
  const action = target.dataset.action
  if (action === 'select-assistant') {
    selectAssistant(target.value)
  }
})

function initResizeHandles() {
  let activeHandle = null
  let startX = 0
  let startWidth = 0
  let targetPanel = null

  const onMouseDown = (e) => {
    const handle = e.target.closest('.resize-handle')
    if (!handle) return
    e.preventDefault()
    activeHandle = handle
    startX = e.clientX
    handle.classList.add('active')

    if (handle.id === 'resize-left') {
      targetPanel = handle.previousElementSibling
    } else {
      targetPanel = handle.nextElementSibling
    }
    if (targetPanel) startWidth = targetPanel.offsetWidth

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }

  const onMouseMove = (e) => {
    if (!activeHandle || !targetPanel) return
    const dx = e.clientX - startX
    let newWidth
    if (activeHandle.id === 'resize-left') {
      newWidth = startWidth + dx
    } else {
      newWidth = startWidth - dx
    }
    const min = parseInt(getComputedStyle(targetPanel).minWidth) || 180
    const max = parseInt(getComputedStyle(targetPanel).maxWidth) || 600
    targetPanel.style.width = Math.max(min, Math.min(max, newWidth)) + 'px'
  }

  const onMouseUp = () => {
    if (activeHandle) activeHandle.classList.remove('active')
    activeHandle = null
    targetPanel = null
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  document.addEventListener('mousedown', onMouseDown)
}

initResizeHandles()
subscribe(() => smartRender())
onError(msg => showToast(msg, 'error'))
;(async () => { await fetchProjects(); render() })()
