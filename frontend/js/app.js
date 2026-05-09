import {
  getState, setState, subscribe,
  fetchProjects, createProject, deleteProject,
  fetchConversations, createConversation, selectConversation, deleteConversation, renameConversation,
  sendMessage, regenerateMessage,
  fetchWorkspaceItems, createWorkspaceItem, updateItemStatus, deleteWorkspaceItem,
  fetchChronicle,
  navigateTo,
  fetchAssistants, selectAssistant, createAssistant, updateAssistant, deleteAssistant,
} from './store.js'
import { updateProject } from './api.js'

const html = (strings, ...values) => strings.reduce((acc, s, i) => acc + s + (values[i] ?? ''), '')
const esc = s => s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''

const TYPE_LABELS = { world_setting: '世界观', character_setting: '角色', outline: '大纲', chapter: '章节' }
const STATUS_LABELS = { draft: '草稿', finalized: '正文', locked: '锁定' }

let _marked = null
async function md(text) {
  if (!text) return ''
  if (!_marked) {
    _marked = await import('https://cdn.jsdelivr.net/npm/marked/marked.min.js')
  }
  try {
    return _marked.marked.parse(text)
  } catch {
    return esc(text).replace(/\n/g, '<br>')
  }
}

function render() {
  const app = document.getElementById('app')
  if (!app) return
  const s = getState()
  if (s.route === 'workspace' && s.currentProjectId) {
    renderWorkspacePage(app, s)
  } else {
    renderProjectsPage(app, s)
  }
}

function renderProjectsPage(app, s) {
  app.innerHTML = html`
  <div class="app-workspace">
    <div class="sidebar-left">
      <div style="padding:20px 16px;border-bottom:1px solid var(--border-color);">
        <div style="font-size:16px;font-weight:700;color:var(--text-primary);margin-bottom:2px;">Fiction Academy</div>
        <div style="font-size:12px;color:var(--text-tertiary);">AI 小说创作平台</div>
      </div>
      <button class="btn-new-conv" data-action="create-project">+ 新建项目</button>
      <div class="conv-list">
        ${s.projects.map(p => html`
          <div class="conv-item" data-action="open-project" data-id="${esc(p.id)}">
            <div style="display:flex;align-items:center;justify-content:space-between;">
              <div class="conv-title" style="cursor:pointer;" data-action="rename-project" data-id="${esc(p.id)}" title="点击重命名">${esc(p.name)}</div>
              <button class="btn-delete-sm" data-action="delete-project" data-id="${esc(p.id)}" title="删除项目">✕</button>
            </div>
            <div class="conv-time">${p.stats?.workspace_item_count ?? 0} 条目 · ${p.stats?.conversation_count ?? 0} 对话${p.stats?.has_world_setting ? ' · ✓ 世界观' : ''}</div>
          </div>
        `).join('')}
      </div>
    </div>
    <div class="chat-area" style="display:flex;align-items:center;justify-content:center;">
      <div class="empty-state">
        <div class="empty-icon">${s.projects.length === 0 ? '📖' : '✍️'}</div>
        <div class="empty-text">${s.projects.length === 0 ? '开始你的创作之旅' : '选择一个项目开始创作'}</div>
        <div class="empty-hint">${s.projects.length === 0 ? '点击左侧「+ 新建项目」创建你的第一部小说' : '从左侧选择项目，或创建新项目'}</div>
      </div>
    </div>
  </div>`
}

function renderWorkspacePage(app, s) {
  app.innerHTML = html`
  <div class="app-workspace">
    <div class="sidebar-left">
      <div style="padding:16px;border-bottom:1px solid var(--border-color);display:flex;align-items:center;gap:8px;">
        <button class="btn" data-action="go-home" style="padding:6px 10px;font-size:12px;">← 返回</button>
        <span style="font-size:14px;font-weight:700;color:var(--text-primary);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;" data-action="edit-project-name" title="点击修改项目名称">${esc(s.projects.find(p => p.id === s.currentProjectId)?.name || '')}</span>
      </div>
      <button class="btn-new-conv" data-action="new-conv">+ 新对话</button>
      <div class="conv-list">
        ${s.conversations.map(c => html`
          <div class="conv-item ${c.id === s.currentConversationId ? 'active' : ''}" data-action="select-conv" data-id="${esc(c.id)}">
            <div style="display:flex;align-items:center;justify-content:space-between;">
              <div class="conv-title" style="cursor:pointer;" data-action="rename-conv" data-id="${esc(c.id)}" title="点击重命名">${esc(c.title)}</div>
              <button class="btn-delete-sm" data-action="delete-conv" data-id="${esc(c.id)}" title="删除对话">✕</button>
            </div>
            <div class="conv-time">${formatTime(c.created_at)}</div>
          </div>
        `).join('')}
      </div>
    </div>
    <div class="chat-area">
      <div class="chat-messages" id="chat-messages">
        ${renderMessages(s)}
      </div>
      <div class="chat-input-area">
        <div class="assistant-selector">
          <select id="assistant-select" data-action="change-assistant">
            ${s.assistants.map(a => html`
              <option value="${esc(a.id)}" ${a.id === s.currentAssistantId ? 'selected' : ''}>${esc(a.name)}</option>
            `).join('')}
          </select>
          <button class="btn btn-sm" data-action="new-assistant" title="新建助理">+</button>
          ${s.currentAssistantId && !s.assistants.find(a => a.id === s.currentAssistantId)?.is_builtin ? html`
            <button class="btn btn-sm" data-action="edit-assistant" data-id="${esc(s.currentAssistantId)}" title="编辑助理">✎</button>
            <button class="btn btn-sm btn-delete-sm" data-action="delete-assistant" data-id="${esc(s.currentAssistantId)}" title="删除助理">✕</button>
          ` : s.currentAssistantId ? html`
            <button class="btn btn-sm" data-action="edit-assistant" data-id="${esc(s.currentAssistantId)}" title="编辑助理">✎</button>
          ` : ''}
        </div>
        <div style="display:flex;gap:8px;align-items:flex-end;">
          <textarea class="chat-input" id="chat-input" placeholder="输入消息... (Enter 发送, Shift+Enter 换行)" rows="1"></textarea>
          <button class="btn-send" id="btn-send" data-action="send" ${s.isStreaming ? 'disabled' : ''}>➤</button>
        </div>
      </div>
    </div>
    <div class="sidebar-right">
      <div style="padding:16px;border-bottom:1px solid var(--border-color);display:flex;align-items:center;justify-content:space-between;">
        <span style="font-size:14px;font-weight:700;color:var(--text-primary);">工作台</span>
        <button class="btn" data-action="add-item" style="padding:4px 10px;font-size:12px;">+ 添加</button>
      </div>
      <div class="workspace-panel">
        ${renderWorkspaceItems(s)}
        ${renderChronicle(s.chronicle)}
      </div>
    </div>
  </div>`
  setTimeout(() => {
    const msgs = document.getElementById('chat-messages')
    if (msgs) msgs.scrollTop = msgs.scrollHeight
  }, 0)
}

function renderMessages(s) {
  const parts = []
  if (s.messages.length === 0 && !s.isStreaming) {
    parts.push(html`
      <div class="empty-state">
        <div class="empty-icon">✍️</div>
        <div class="empty-text">开始创作</div>
        <div class="empty-hint">${s.workspaceItems.some(i => i.item_type === 'world_setting' && i.status === 'locked') ? '世界观已就绪，可以开始写章节了' : '先和 AI 一起构建你的世界观吧'}</div>
      </div>`)
  }
  for (let i = 0; i < s.messages.length; i++) {
    const m = s.messages[i]
    const isLastAssistant = m.role === 'assistant' && i === s.messages.length - 1
    parts.push(html`
      <div class="msg ${m.role}">
        <div class="msg-role">${m.role === 'user' ? '你' : 'AI'}</div>
        <div class="msg-content markdown-body">${m.role === 'user' ? formatContent(m.content) : formatMd(m.content)}</div>
        ${isLastAssistant && !s.isStreaming ? html`
          <div class="msg-actions">
            <button class="btn btn-sm" data-action="regenerate" title="重新生成">🔄 重新生成</button>
          </div>
        ` : ''}
      </div>`)
  }
  if (s.isStreaming) {
    parts.push(html`
      <div class="msg assistant" id="streaming-msg">
        <div class="msg-role">AI</div>
        <div class="msg-content markdown-body">${formatMd(s.streamingContent)}<span class="streaming-cursor"></span></div>
      </div>`)
  }
  return parts.join('')
}

function renderWorkspaceItems(s) {
  if (s.workspaceItems.length === 0) {
    return html`
      <div class="empty-state" style="padding:40px 16px;">
        <div class="empty-icon">📋</div>
        <div class="empty-text">工作台空空如也</div>
        <div class="empty-hint">在对话中创作的内容可以保存到这里</div>
      </div>`
  }
  return s.workspaceItems.map(item => html`
    <div class="ws-item ${item.status === 'locked' ? 'locked' : ''}">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
        <span class="ws-type-badge ${item.item_type === 'chapter' ? 'plot' : item.item_type === 'character_setting' ? 'character' : item.item_type === 'world_setting' ? 'setting' : 'theme'}">${TYPE_LABELS[item.item_type] || item.item_type}</span>
        <span class="ws-status ${item.status}">${STATUS_LABELS[item.status]}</span>
        ${item.chapter_number != null ? html`<span style="font-size:11px;color:var(--text-secondary);font-family:var(--font-mono);">#${item.chapter_number}</span>` : ''}
      </div>
      <div class="ws-title">${esc(item.title || '无标题')}</div>
      <div style="font-size:12px;color:var(--text-secondary);max-height:60px;overflow:hidden;line-height:1.5;">${esc((item.content || '').slice(0, 120))}${(item.content || '').length > 120 ? '...' : ''}</div>
      <div class="ws-actions">
        ${item.status === 'draft' ? html`<button class="btn-approve" data-action="approve-item" data-id="${esc(item.id)}">通过</button>` : ''}
        ${item.status === 'draft' ? html`<button class="btn-approve" data-action="lock-item" data-id="${esc(item.id)}" style="color:var(--accent);background:rgba(240,165,0,0.15);border-color:rgba(240,165,0,0.3);">锁定</button>` : ''}
        ${item.status !== 'locked' ? html`<button class="btn-edit" data-action="edit-item" data-id="${esc(item.id)}">编辑</button>` : ''}
        ${item.status !== 'locked' ? html`<button class="btn-delete" data-action="delete-item" data-id="${esc(item.id)}">删除</button>` : ''}
      </div>
    </div>
  `).join('')
}

function renderChronicle(chronicle) {
  if (!chronicle) return ''
  const hasData = (chronicle.timeline && chronicle.timeline.length > 0) ||
                  (chronicle.characters && chronicle.characters.length > 0) ||
                  (chronicle.key_events && chronicle.key_events.length > 0)
  if (!hasData) return ''
  let out = '<div class="chronicle-section"><div class="section-title">📜 编年记录</div>'
  if (chronicle.timeline && chronicle.timeline.length > 0) {
    out += '<div class="chronicle-timeline" style="margin-bottom:16px;">'
    for (const t of chronicle.timeline) {
      out += html`<div class="timeline-item"><span style="font-size:13px;">${esc(typeof t === 'string' ? t : JSON.stringify(t))}</span></div>`
    }
    out += '</div>'
  }
  if (chronicle.characters && chronicle.characters.length > 0) {
    out += '<div style="margin-bottom:12px;">'
    for (const c of chronicle.characters) {
      out += html`<div class="chronicle-char"><div class="char-name">${esc(c.name)}</div>`
      if (c.periods && c.periods.length > 0) {
        out += html`<div class="char-event">${esc(c.periods[c.periods.length - 1].status || '')}</div>`
      }
      out += '</div>'
    }
    out += '</div>'
  }
  if (chronicle.unresolved_threads && chronicle.unresolved_threads.length > 0) {
    out += '<div style="font-size:12px;color:var(--text-secondary);"><div style="font-weight:700;margin-bottom:6px;">🔍 未解决伏笔</div>'
    for (const t of chronicle.unresolved_threads) {
      out += html`<div style="margin-bottom:4px;">• ${esc(typeof t === 'string' ? t : JSON.stringify(t))}</div>`
    }
    out += '</div>'
  }
  out += '</div>'
  return out
}

let _prevFullKey = ''
let _prevMsgKey = ''
let _streamingStarted = false

function smartRender() {
  const s = getState()
  const app = document.getElementById('app')
  if (!app) return

  if (s.route !== 'workspace' || !s.currentProjectId) {
    _prevFullKey = ''
    _prevMsgKey = ''
    _streamingStarted = false
    render()
    return
  }

  if (s.isStreaming) {
    if (!_streamingStarted) {
      _streamingStarted = true
      const msgsEl = document.getElementById('chat-messages')
      if (msgsEl) {
        msgsEl.innerHTML = renderMessages(s)
        const btn = document.getElementById('btn-send')
        if (btn) btn.disabled = true
      }
      return
    }
    const contentEl = document.querySelector('#streaming-msg .msg-content')
    if (contentEl) {
      contentEl.innerHTML = formatMd(s.streamingContent) + '<span class="streaming-cursor"></span>'
      const msgsEl = document.getElementById('chat-messages')
      if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight
    }
    return
  }

  if (_streamingStarted) {
    _streamingStarted = false
    _prevFullKey = ''
  }

  const fullKey = `${s.currentProjectId}-${s.currentConversationId}-${s.conversations.length}-${s.workspaceItems.length}-${s.messages.length}`
  if (fullKey !== _prevFullKey) {
    _prevFullKey = fullKey
    _prevMsgKey = ''
    render()
    requestAnimationFrame(() => {
      const msgsEl = document.getElementById('chat-messages')
      if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight
    })
    return
  }
}

subscribe(() => smartRender())

function closeModal() {
  const root = document.getElementById('modal-root')
  if (root) root.innerHTML = ''
}

window._closeModal = closeModal

window._submitCreateProject = async () => {
  const name = document.getElementById('input-project-name')?.value?.trim() || '未命名项目'
  const genre = document.getElementById('input-project-genre')?.value?.trim()
  await createProject(name, genre || undefined)
  closeModal()
  render()
}

window._submitAddItem = async () => {
  const s = getState()
  const item_type = document.getElementById('input-item-type')?.value
  const title = document.getElementById('input-item-title')?.value?.trim()
  const content = document.getElementById('input-item-content')?.value?.trim()
  if (!title) return
  await createWorkspaceItem(s.currentProjectId, { item_type, title, content })
  closeModal()
  render()
}

window._submitSaveEdit = async (itemId) => {
  const s = getState()
  const title = document.getElementById('edit-item-title')?.value?.trim()
  const content = document.getElementById('edit-item-content')?.value?.trim()
  const api = await import('./api.js')
  await api.updateWorkspaceItem(itemId, { title, content })
  await fetchWorkspaceItems(s.currentProjectId)
  closeModal()
  render()
}

window._confirmDeleteProject = async (projectId) => {
  await deleteProject(projectId)
  closeModal()
  render()
}

window._confirmDeleteConv = async (convId) => {
  const s = getState()
  await deleteConversation(convId)
  if (s.currentConversationId === convId) {
    setState({ currentConversationId: null, messages: [] })
    const ns = getState()
    if (ns.conversations.length > 0) {
      await selectConversation(ns.conversations[0].id)
    }
  }
  closeModal()
  render()
}

window._submitCreateAssistant = async () => {
  const name = document.getElementById('input-asst-name')?.value?.trim()
  const description = document.getElementById('input-asst-desc')?.value?.trim()
  const model = document.getElementById('input-asst-model')?.value?.trim()
  const system_prompt = document.getElementById('input-asst-prompt')?.value?.trim()
  if (!name) return
  const assistant = await createAssistant({ name, description, model, system_prompt })
  if (assistant) selectAssistant(assistant.id)
  closeModal()
  render()
}

window._submitSaveAssistant = async (id) => {
  const name = document.getElementById('input-asst-name')?.value?.trim()
  const description = document.getElementById('input-asst-desc')?.value?.trim()
  const model = document.getElementById('input-asst-model')?.value?.trim()
  const system_prompt = document.getElementById('input-asst-prompt')?.value?.trim()
  if (!name) return
  await updateAssistant(id, { name, description, model, system_prompt })
  closeModal()
  render()
}

function showModal(type, data) {
  let root = document.getElementById('modal-root')
  if (!root) {
    root = document.createElement('div')
    root.id = 'modal-root'
    document.body.appendChild(root)
  }

  let content = ''

  if (type === 'create-project') {
    content = html`
    <div class="modal-overlay" onclick="window._closeModal()">
      <div class="modal" onclick="event.stopPropagation()">
        <div class="modal-title">新建项目</div>
        <div class="modal-body">
          <div style="margin-bottom:12px;">
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">项目名称</label>
            <input id="input-project-name" class="chat-input" style="width:100%;border-radius:8px;" placeholder="可留空，稍后让 AI 帮你起名" />
          </div>
          <div>
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">类型（可选）</label>
            <input id="input-project-genre" class="chat-input" style="width:100%;border-radius:8px;" placeholder="如：玄幻、都市、科幻" />
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" onclick="window._closeModal()">取消</button>
          <button class="btn-primary" onclick="window._submitCreateProject()">创建</button>
        </div>
      </div>
    </div>`
  } else if (type === 'add-item') {
    content = html`
    <div class="modal-overlay" onclick="window._closeModal()">
      <div class="modal" onclick="event.stopPropagation()">
        <div class="modal-title">添加工作台条目</div>
        <div class="modal-body">
          <div style="margin-bottom:12px;">
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">类型</label>
            <select id="input-item-type" class="chat-input" style="width:100%;border-radius:8px;">
              <option value="world_setting">世界观设定</option>
              <option value="character_setting">角色设定</option>
              <option value="outline">大纲</option>
              <option value="chapter">章节</option>
            </select>
          </div>
          <div style="margin-bottom:12px;">
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">标题</label>
            <input id="input-item-title" class="chat-input" style="width:100%;border-radius:8px;" placeholder="标题" />
          </div>
          <div>
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">内容</label>
            <textarea id="input-item-content" class="chat-input" style="width:100%;min-height:120px;border-radius:8px;" placeholder="内容"></textarea>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" onclick="window._closeModal()">取消</button>
          <button class="btn-primary" onclick="window._submitAddItem()">添加</button>
        </div>
      </div>
    </div>`
  } else if (type === 'edit-item') {
    const item = data.item
    content = html`
    <div class="modal-overlay" onclick="window._closeModal()">
      <div class="modal" onclick="event.stopPropagation()">
        <div class="modal-title">编辑条目</div>
        <div class="modal-body">
          <div style="margin-bottom:12px;">
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">标题</label>
            <input id="edit-item-title" class="chat-input" style="width:100%;border-radius:8px;" value="${esc(item.title || '')}" />
          </div>
          <div>
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">内容</label>
            <textarea id="edit-item-content" class="chat-input" style="width:100%;min-height:200px;border-radius:8px;">${esc(item.content || '')}</textarea>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" onclick="window._closeModal()">取消</button>
          <button class="btn-primary" onclick="window._submitSaveEdit('${esc(item.id)}')">保存</button>
        </div>
      </div>
    </div>`
  } else if (type === 'confirm-delete-project') {
    content = html`
    <div class="modal-overlay" onclick="window._closeModal()">
      <div class="modal" onclick="event.stopPropagation()">
        <div class="modal-title">确认删除</div>
        <div class="modal-body">
          <p>确定要删除项目「${esc(data.name)}」吗？此操作不可撤销。</p>
        </div>
        <div class="modal-actions">
          <button class="btn" onclick="window._closeModal()">取消</button>
          <button class="btn-danger" onclick="window._confirmDeleteProject('${esc(data.id)}')">删除</button>
        </div>
      </div>
    </div>`
  } else if (type === 'confirm-delete-conv') {
    content = html`
    <div class="modal-overlay" onclick="window._closeModal()">
      <div class="modal" onclick="event.stopPropagation()">
        <div class="modal-title">确认删除</div>
        <div class="modal-body">
          <p>确定要删除对话「${esc(data.title)}」吗？</p>
        </div>
        <div class="modal-actions">
          <button class="btn" onclick="window._closeModal()">取消</button>
          <button class="btn-danger" onclick="window._confirmDeleteConv('${esc(data.id)}')">删除</button>
        </div>
      </div>
    </div>`
  } else if (type === 'create-assistant') {
    content = html`
    <div class="modal-overlay" onclick="window._closeModal()">
      <div class="modal" onclick="event.stopPropagation()" style="max-width:520px;">
        <div class="modal-title">新建助理</div>
        <div class="modal-body">
          <div style="margin-bottom:12px;">
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">助理名称</label>
            <input id="input-asst-name" class="chat-input" style="width:100%;border-radius:8px;" placeholder="如：角色设计助手" />
          </div>
          <div style="margin-bottom:12px;">
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">描述</label>
            <input id="input-asst-desc" class="chat-input" style="width:100%;border-radius:8px;" placeholder="简要描述助理的用途" />
          </div>
          <div style="margin-bottom:12px;">
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">模型（可选，留空使用默认模型）</label>
            <input id="input-asst-model" class="chat-input" style="width:100%;border-radius:8px;" placeholder="如：mimo-v2.5-pro" />
          </div>
          <div>
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">System Prompt</label>
            <textarea id="input-asst-prompt" class="chat-input" style="width:100%;min-height:160px;border-radius:8px;" placeholder="输入系统提示词，定义助理的行为和能力"></textarea>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" onclick="window._closeModal()">取消</button>
          <button class="btn-primary" onclick="window._submitCreateAssistant()">创建</button>
        </div>
      </div>
    </div>`
  } else if (type === 'edit-assistant') {
    const a = data
    content = html`
    <div class="modal-overlay" onclick="window._closeModal()">
      <div class="modal" onclick="event.stopPropagation()" style="max-width:520px;">
        <div class="modal-title">编辑助理</div>
        <div class="modal-body">
          <div style="margin-bottom:12px;">
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">助理名称</label>
            <input id="input-asst-name" class="chat-input" style="width:100%;border-radius:8px;" value="${esc(a.name)}" />
          </div>
          <div style="margin-bottom:12px;">
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">描述</label>
            <input id="input-asst-desc" class="chat-input" style="width:100%;border-radius:8px;" value="${esc(a.description || '')}" />
          </div>
          <div style="margin-bottom:12px;">
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">模型（可选，留空使用默认模型）</label>
            <input id="input-asst-model" class="chat-input" style="width:100%;border-radius:8px;" value="${esc(a.model || '')}" />
          </div>
          <div>
            <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">System Prompt</label>
            <textarea id="input-asst-prompt" class="chat-input" style="width:100%;min-height:160px;border-radius:8px;">${esc(a.system_prompt || '')}</textarea>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" onclick="window._closeModal()">取消</button>
          <button class="btn-primary" onclick="window._submitSaveAssistant('${esc(a.id)}')">保存</button>
        </div>
      </div>
    </div>`
  }

  root.innerHTML = content
  if (type === 'create-project') {
    setTimeout(() => document.getElementById('input-project-name')?.focus(), 50)
  }
}

document.addEventListener('click', async e => {
  const btn = e.target.closest('[data-action]')
  if (!btn) return
  const action = btn.dataset.action
  if (!action) return
  const s = getState()

  switch (action) {
    case 'create-project':
      showModal('create-project')
      break
    case 'open-project':
      navigateTo('workspace', { currentProjectId: btn.dataset.id })
      break
    case 'delete-project':
      e.stopPropagation()
      e.preventDefault()
      showModal('confirm-delete-project', {
        id: btn.dataset.id,
        name: btn.closest('.conv-item')?.querySelector('.conv-title')?.textContent || ''
      })
      break
    case 'rename-project':
      e.stopPropagation()
      e.preventDefault()
      showInlineRename(btn, 'project')
      break
    case 'go-home':
      navigateTo('projects', {})
      break
    case 'edit-project-name':
      showEditProjectName(s.currentProjectId)
      break
    case 'new-conv': {
      const title = `对话 ${s.conversations.length + 1}`
      await createConversation(s.currentProjectId, title)
      render()
      break
    }
    case 'select-conv':
      await selectConversation(btn.dataset.id)
      render()
      break
    case 'delete-conv':
      e.stopPropagation()
      e.preventDefault()
      showModal('confirm-delete-conv', {
        id: btn.dataset.id,
        title: btn.closest('.conv-item')?.querySelector('.conv-title')?.textContent || ''
      })
      break
    case 'rename-conv':
      e.stopPropagation()
      e.preventDefault()
      showInlineRename(btn, 'conversation')
      break
    case 'send':
      handleSend()
      break
    case 'regenerate':
      e.stopPropagation()
      if (s.currentConversationId && !s.isStreaming) {
        regenerateMessage(s.currentConversationId)
      }
      break
    case 'change-assistant':
      break
    case 'new-assistant':
      e.stopPropagation()
      showModal('create-assistant')
      break
    case 'edit-assistant':
      e.stopPropagation()
      const editId = btn.dataset.id
      const editAst = s.assistants.find(a => a.id === editId)
      if (editAst) showModal('edit-assistant', { ...editAst })
      break
    case 'delete-assistant':
      e.stopPropagation()
      const delAst = s.assistants.find(a => a.id === btn.dataset.id)
      if (delAst && confirm(`确定删除助理「${delAst.name}」？`)) {
        await deleteAssistant(btn.dataset.id)
        render()
      }
      break
    case 'approve-item':
      await updateItemStatus(btn.dataset.id, 'finalized', s.currentProjectId)
      render()
      break
    case 'lock-item':
      await updateItemStatus(btn.dataset.id, 'locked', s.currentProjectId)
      render()
      break
    case 'edit-item': {
      const item = s.workspaceItems.find(i => i.id === btn.dataset.id)
      if (item) showModal('edit-item', { item })
      break
    }
    case 'delete-item':
      await deleteWorkspaceItem(btn.dataset.id, s.currentProjectId)
      render()
      break
    case 'add-item':
      showModal('add-item')
      break
  }
})

document.addEventListener('keydown', e => {
  const input = document.getElementById('chat-input')
  if (!input) return
  if (e.key === 'Enter' && !e.shiftKey && document.activeElement === input) {
    e.preventDefault()
    handleSend()
  }
})

document.addEventListener('input', e => {
  if (e.target.id === 'chat-input') {
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
  }
})

document.addEventListener('change', e => {
  if (e.target.id === 'assistant-select') {
    selectAssistant(e.target.value)
    _prevFullKey = ''
    smartRender()
  }
})

;(async () => {
  await fetchProjects()
  render()
})()

function showEditProjectName(projectId) {
  const s = getState()
  const project = s.projects.find(p => p.id === projectId)
  if (!project) return
  const span = document.querySelector('[data-action="edit-project-name"]')
  if (!span) return
  const input = document.createElement('input')
  input.className = 'chat-input'
  input.style.cssText = 'font-size:14px;font-weight:700;padding:4px 10px;border-radius:6px;flex:1;min-width:0;'
  input.value = project.name
  span.replaceWith(input)
  input.focus()
  input.select()
  const finish = async () => {
    const newName = input.value.trim() || '未命名项目'
    await updateProject(projectId, { name: newName })
    await fetchProjects()
    render()
  }
  input.addEventListener('blur', finish)
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); input.blur() }
    if (e.key === 'Escape') { input.value = project.name; input.blur() }
  })
}

function showInlineRename(titleEl, type) {
  const id = titleEl.dataset.id
  const oldName = titleEl.textContent
  const input = document.createElement('input')
  input.className = 'chat-input'
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
  input.value = ''
  input.style.height = 'auto'
  sendMessage(s.currentConversationId, content)
}

function formatContent(text) {
  if (!text) return ''
  return esc(text).replace(/\n/g, '<br>')
}

let _mdCache = {}
function formatMd(text) {
  if (!text) return ''
  if (_mdCache[text]) return _mdCache[text]
  let html = esc(text)
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  html = html.replace(/`(.+?)`/g, '<code>$1</code>')
  html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
  html = html.replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>')
  html = html.replace(/\n\n/g, '<br><br>')
  html = html.replace(/\n/g, '<br>')
  if (text.length < 5000) _mdCache[text] = html
  return html
}

function formatTime(ts) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
  } catch { return ts }
}
