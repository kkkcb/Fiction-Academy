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
import { updateProject, summarizeToWorkspace, extractQuestions, generateWorkspaceItem, summarizeMessage, syncToWorkspace, updateWorkspaceItem } from './api.js'

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

function showToast(msg, type = 'info') {
  let box = document.querySelector('.toast-container')
  if (!box) {
    box = document.createElement('div')
    box.className = 'toast-container'
    document.body.appendChild(box)
  }
  const el = document.createElement('div')
  el.className = `toast ${type}`
  el.textContent = msg
  box.appendChild(el)
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; setTimeout(() => el.remove(), 300) }, 2500)
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
      <div class="sidebar-brand">
        <div class="sidebar-brand-title">Fiction Academy</div>
        <div class="sidebar-brand-sub">AI 小说创作平台</div>
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
    <div class="resize-handle-left" id="resize-left"></div>
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
      <div class="glass-header">
        <button class="btn" data-action="go-home" style="padding:6px 10px;font-size:12px;">← 返回</button>
        <span class="glass-header-title" data-action="edit-project-name" title="点击修改项目名称">${esc(s.projects.find(p => p.id === s.currentProjectId)?.name || '')}</span>
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
    <div class="resize-handle-left" id="resize-left"></div>
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
    <div class="resize-handle" id="resize-right"></div>
    <div class="sidebar-right">
      <div class="glass-header">
        <span class="glass-header-title">工作台</span>
        <div style="display:flex;gap:6px;">
          ${s.isSummarizing
            ? html`<button class="btn" disabled style="padding:4px 10px;font-size:12px;opacity:0.6;">⏳ 整理中...</button>`
            : html`<button class="btn" data-action="ai-summarize" style="padding:4px 10px;font-size:12px;">✨ 灵感</button>`
          }
          ${s.pendingQuestions.length > 0
            ? html`<button class="btn" data-action="show-questions" style="padding:4px 10px;font-size:12px;color:var(--accent);">❓ 待确认 (${s.pendingQuestions.length})</button>`
            : html`<button class="btn" data-action="extract-questions" style="padding:4px 10px;font-size:12px;">❓ 待确认</button>`
          }
          <button class="btn" data-action="add-item" style="padding:4px 10px;font-size:12px;">+ 添加</button>
        </div>
      </div>
      <div class="workspace-panel">
        ${s.pendingQuestions.length > 0 ? html`
          <div style="padding:12px 16px;border-bottom:1px solid var(--border-color);background:var(--accent-light);">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
              <span style="font-size:13px;font-weight:700;color:var(--accent);">❓ 待确认 (${s.pendingQuestions.length})</span>
              <div style="display:flex;gap:6px;">
                <button class="btn btn-sm" data-action="submit-answers" style="padding:3px 10px;font-size:11px;background:var(--accent);color:#fff;border:none;">提交回答</button>
                <button class="btn btn-sm" data-action="show-questions" style="padding:2px 8px;font-size:11px;">收起</button>
              </div>
            </div>
            ${s.pendingQuestions.map((q, i) => {
              const answered = s.questionAnswers[i]
              return html`
              <div style="margin-bottom:10px;padding:8px 10px;background:var(--bg-input);border-radius:8px;border-left:3px solid ${answered ? '#4caf50' : 'var(--accent)'};">
                <div style="font-size:12px;font-weight:600;color:var(--accent);margin-bottom:4px;">${esc(q.keyword)}</div>
                <div style="font-size:12px;color:var(--text-primary);margin-bottom:6px;">${esc(q.question)}</div>
                <div style="display:flex;flex-wrap:wrap;gap:4px;">
                  ${(q.options || []).map((opt, oi) => html`
                    <button class="btn btn-sm" data-action="answer-question" data-index="${i}" data-answer="${esc(opt)}"
                      style="padding:3px 8px;font-size:11px;${answered === opt ? 'background:var(--accent);color:#fff;border-color:var(--accent);' : ''}"
                    >${esc(opt)}</button>
                  `).join('')}
                </div>
                <div style="margin-top:4px;display:flex;gap:4px;">
                  <input class="chat-input" id="custom-answer-${i}" placeholder="自定义回答..." style="flex:1;padding:3px 8px;font-size:11px;border-radius:4px;min-height:0;" />
                  <button class="btn btn-sm" data-action="answer-custom" data-index="${i}" style="padding:3px 8px;font-size:11px;">确定</button>
                </div>
                ${answered ? html`<div style="margin-top:4px;font-size:11px;color:#4caf50;">✓ ${esc(answered)}</div>` : ''}
              </div>`
            }).join('')}
          </div>
        ` : ''}
        ${renderWorkspaceItems(s)}
        ${renderChronicle(s.chronicle)}
      </div>
    </div>
    <div class="mobile-tab-bar">
      <button data-action="mobile-show-left" class="${s._mobileTab === 'left' ? 'active' : ''}"><span>📂</span>项目</button>
      <button data-action="mobile-show-chat" class="${!s._mobileTab ? 'active' : ''}"><span>💬</span>对话</button>
      <button data-action="mobile-show-right" class="${s._mobileTab === 'right' ? 'active' : ''}"><span>📝</span>工作台</button>
    </div>
  </div>`
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
        ${m.role === 'assistant' ? html`
          <div class="msg-actions">
            <button class="btn btn-sm" data-action="copy-msg" data-index="${i}" title="复制内容">📋 复制</button>
            <button class="btn btn-sm" data-action="summarize-msg" data-index="${i}" title="总结另存为">📝 总结</button>
            <button class="btn btn-sm" data-action="sync-workspace" data-index="${i}" title="检测变更并更新工作台">🔄 更新工作台</button>
            ${isLastAssistant && !s.isStreaming ? html`
              <button class="btn btn-sm" data-action="regenerate" title="重新生成">🔄 重新生成</button>
            ` : ''}
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
  return s.workspaceItems.map(item => {
    const headings = (item.content || '').match(/^## .+$/gm) || []
    return html`
    <div class="ws-item ${item.status === 'locked' ? 'locked' : ''}">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
        <span class="ws-type-badge ${item.item_type === 'chapter' ? 'plot' : item.item_type === 'character_setting' ? 'character' : item.item_type === 'world_setting' ? 'setting' : 'theme'}">${TYPE_LABELS[item.item_type] || item.item_type}</span>
        <span class="ws-status ${item.status}">${STATUS_LABELS[item.status]}</span>
        ${headings.length > 0 ? html`<span style="font-size:11px;color:var(--text-tertiary);font-family:var(--font-mono);">${headings.length} 个章节</span>` : ''}
      </div>
      <div class="ws-title">${esc(item.title || '无标题')}</div>
      ${headings.length > 0 ? html`
        <div style="margin:6px 0;padding:6px 8px;background:var(--bg-secondary);border-radius:var(--radius-sm);font-size:11px;line-height:1.6;">
          ${headings.map(h => html`<div style="color:var(--text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(h.replace(/^##\s*/, ''))}</div>`).join('')}
        </div>
      ` : ''}
      <div class="markdown-body" style="font-size:12px;max-height:80px;overflow:hidden;line-height:1.5;">${formatMd((item.content || '').slice(0, 300))}</div>
      <div class="ws-actions">
        ${item.status === 'draft' ? html`<button class="btn-approve" data-action="approve-item" data-id="${esc(item.id)}">通过</button>` : ''}
        ${item.status === 'locked' ? html`<button class="btn-approve" data-action="unlock-item" data-id="${esc(item.id)}" style="color:#4caf50;background:rgba(76,175,80,0.15);border-color:rgba(76,175,80,0.3);">解锁</button>` : ''}
        ${item.status === 'draft' ? html`<button class="btn-approve" data-action="lock-item" data-id="${esc(item.id)}" style="color:var(--accent);background:rgba(240,165,0,0.15);border-color:rgba(240,165,0,0.3);">锁定</button>` : ''}
        ${item.status !== 'locked' ? html`<button class="btn-edit" data-action="edit-item" data-id="${esc(item.id)}">编辑</button>` : ''}
        ${item.status !== 'locked' ? html`<button class="btn-delete" data-action="delete-item" data-id="${esc(item.id)}">删除</button>` : ''}
      </div>
    </div>
  `}).join('')
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
let _autoScroll = false
let _savedScrollRatio = 1

function _scrollToBottom() {
  const msgsEl = document.getElementById('chat-messages')
  if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight
}

function _restoreScrollRatio() {
  const msgsEl = document.getElementById('chat-messages')
  if (msgsEl && msgsEl.scrollHeight > 0) {
    msgsEl.scrollTop = _savedScrollRatio * msgsEl.scrollHeight
  }
}

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
      _autoScroll = true
      const msgsEl = document.getElementById('chat-messages')
      if (msgsEl) {
        msgsEl.innerHTML = renderMessages(s)
        const btn = document.getElementById('btn-send')
        if (btn) btn.disabled = true
        msgsEl.scrollTop = msgsEl.scrollHeight
      }
      return
    }
    const contentEl = document.querySelector('#streaming-msg .msg-content')
    if (contentEl) {
      contentEl.innerHTML = formatMd(s.streamingContent) + '<span class="streaming-cursor"></span>'
      if (_autoScroll) {
        const msgsEl = document.getElementById('chat-messages')
        if (msgsEl) {
          const nearBottom = msgsEl.scrollHeight - msgsEl.scrollTop - msgsEl.clientHeight < 80
          if (nearBottom) msgsEl.scrollTop = msgsEl.scrollHeight
        }
      }
    }
    return
  }

  if (_streamingStarted) {
    _streamingStarted = false
    _prevFullKey = ''
    _autoScroll = false
  }

  const fullKey = `${s.currentProjectId}-${s.currentConversationId}-${s.conversations.length}-${s.workspaceItems.length}-${s.messages.length}`
  if (fullKey !== _prevFullKey) {
    const prevConvId = _prevFullKey.split('-')[1]
    const convChanged = _prevFullKey && prevConvId !== `${s.currentConversationId}`
    const msgsEl = document.getElementById('chat-messages')
    if (msgsEl && msgsEl.scrollHeight > 0) {
      _savedScrollRatio = msgsEl.scrollTop / msgsEl.scrollHeight
    }
    _prevFullKey = fullKey
    _prevMsgKey = ''
    render()
    if (convChanged || _savedScrollRatio >= 0.95) {
      requestAnimationFrame(_scrollToBottom)
    } else {
      requestAnimationFrame(_restoreScrollRatio)
    }
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

window._startGenerateItem = async () => {
  const s = getState()
  const item_type = document.getElementById('input-item-type')?.value
  if (s.messages.length === 0) { alert('当前对话为空，无法生成'); return }
  const btn = document.querySelector('[onclick="window._startGenerateItem()"]')
  if (btn) { btn.disabled = true; btn.textContent = 'AI 生成中...' }
  try {
    const result = await generateWorkspaceItem(s.currentProjectId, item_type, s.messages)
    closeModal()
    showModal('add-item', { generated: result })
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = '✨ AI 生成' }
    alert('生成失败: ' + err.message)
  }
}

window._submitGeneratedItem = async () => {
  const btn = document.querySelector('[onclick="_submitGeneratedItem()"]') || document.querySelector('.modal-actions .btn-primary')
  if (btn) { btn.disabled = true; btn.textContent = '保存中...' }
  try {
    const s = getState()
    const title = document.getElementById('input-item-title')?.value?.trim()
    const subtitle = document.getElementById('input-item-subtitle')?.value?.trim() || ''
    const content = document.getElementById('input-item-content')?.value?.trim()
    const item_type = document.getElementById('input-item-gen-type')?.value || 'world_setting'
    if (!title) { showToast('请输入主标题', 'error'); if (btn) { btn.disabled = false; btn.textContent = '✓ 确认保存' }; return }
    await createWorkspaceItem(s.currentProjectId, { item_type, title, subtitle, content })
    await fetchWorkspaceItems(s.currentProjectId)
    closeModal()
    render()
    showToast('已保存到工作台', 'success')
  } catch (err) {
    showToast('保存失败: ' + err.message, 'error')
    if (btn) { btn.disabled = false; btn.textContent = '✓ 确认保存' }
  }
}

window._summarizeMsgIndex = null

window._startSummarizeMsg = async (itemType) => {
  const s = getState()
  const idx = window._summarizeMsgIndex
  if (idx === null) return
  const msg = s.messages[idx]
  if (!msg) return
  const btns = document.querySelectorAll('[onclick^="window._startSummarizeMsg"]')
  btns.forEach(b => { b.disabled = true; b.style.opacity = '0.5' })
  try {
    const result = await summarizeMessage(s.currentProjectId, msg.content, itemType)
    closeModal()
    showModal('summarize-msg', { generated: result })
  } catch (err) {
    btns.forEach(b => { b.disabled = false; b.style.opacity = '1' })
    alert('总结失败: ' + err.message)
  }
}

window._submitSummarizeSave = async () => {
  const btn = document.querySelector('[onclick="_submitSummarizeSave()"]') || document.querySelector('.modal-actions .btn-primary')
  if (btn) { btn.disabled = true; btn.textContent = '保存中...' }
  try {
    const s = getState()
    const subtitle = document.getElementById('input-save-subtitle')?.value?.trim() || ''
    const rawContent = document.getElementById('input-save-content')?.value?.trim()
    const item_type = document.getElementById('input-save-type')?.value || 'world_setting'
    if (!rawContent) { showToast('内容不能为空', 'error'); if (btn) { btn.disabled = false; btn.textContent = '💾 保存到工作台' }; return }

    const heading = subtitle ? `## ${subtitle}\n\n` : ''
    const newSection = heading + rawContent

    const existing = s.workspaceItems.find(w => w.item_type === item_type)
    if (existing) {
      const merged = (existing.content || '').rstrip ? (existing.content || '').replace(/\s+$/, '') : (existing.content || '').trimEnd()
      const updatedContent = merged + '\n\n' + newSection
      await updateWorkspaceItem(existing.id, { content: updatedContent })
      showToast('已补充到「' + (existing.title || existing.item_type) + '」', 'success')
    } else {
      const title = document.getElementById('input-save-title')?.value?.trim() || '世界观设定'
      await createWorkspaceItem(s.currentProjectId, { item_type, title, subtitle: '', content: newSection })
      showToast('已创建新文档', 'success')
    }
    await fetchWorkspaceItems(s.currentProjectId)
    closeModal()
    render()
  } catch (err) {
    showToast('保存失败: ' + err.message, 'error')
    if (btn) { btn.disabled = false; btn.textContent = '💾 保存到工作台' }
  }
}

window._toggleEditPreview = (mode) => {
  const previewArea = document.getElementById('edit-preview-area')
  const sourceArea = document.getElementById('edit-item-content')
  const previewBtn = document.getElementById('edit-preview-btn')
  const sourceBtn = document.getElementById('edit-source-btn')
  if (mode === 'preview') {
    previewArea.innerHTML = formatMd(sourceArea.value)
    previewArea.style.display = 'block'
    sourceArea.style.display = 'none'
    previewBtn.style.background = 'var(--accent)'
    previewBtn.style.color = '#fff'
    sourceBtn.style.background = ''
    sourceBtn.style.color = ''
  } else {
    previewArea.style.display = 'none'
    sourceArea.style.display = 'block'
    sourceBtn.style.background = 'var(--accent)'
    sourceBtn.style.color = '#fff'
    previewBtn.style.background = ''
    previewBtn.style.color = ''
  }
}

window._submitSaveEdit = async (itemId) => {
  const btn = document.querySelector(`[onclick*="_submitSaveEdit"]`)
  if (btn) { btn.disabled = true; btn.textContent = '保存中...' }
  try {
    const s = getState()
    const title = document.getElementById('edit-item-title')?.value?.trim()
    const subtitle = document.getElementById('edit-item-subtitle')?.value?.trim()
    const content = document.getElementById('edit-item-content')?.value?.trim()
    await updateWorkspaceItem(itemId, { title, subtitle, content })
    await fetchWorkspaceItems(s.currentProjectId)
    closeModal()
    render()
    showToast('编辑已保存', 'success')
  } catch (err) {
    showToast('保存失败: ' + err.message, 'error')
    if (btn) { btn.disabled = false; btn.textContent = '保存' }
  }
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
    const genResult = data?.generated
    content = html`
    <div class="modal-overlay" onclick="window._closeModal()">
      <div class="modal" onclick="event.stopPropagation()" style="max-width:600px;">
        <div class="modal-title">${genResult ? '检查 AI 生成内容' : 'AI 生成工作台条目'}</div>
        <div class="modal-body">
          ${genResult ? html`
            <div style="display:flex;gap:8px;margin-bottom:12px;">
              <div style="flex:1;">
                <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">主标题</label>
                <input id="input-item-title" class="chat-input" style="width:100%;border-radius:8px;" value="${esc(genResult.title)}" />
              </div>
              <div style="flex:1;">
                <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">副标题</label>
                <input id="input-item-subtitle" class="chat-input" style="width:100%;border-radius:8px;" placeholder="如：基础设定、xx门派..." />
              </div>
            </div>
            <div style="margin-bottom:12px;">
              <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">保存类型</label>
              <select id="input-item-gen-type" class="chat-input" style="width:100%;border-radius:8px;">
                <option value="world_setting" ${genResult.item_type === 'world_setting' ? 'selected' : ''}>🌍 世界观设定</option>
                <option value="character_setting" ${genResult.item_type === 'character_setting' ? 'selected' : ''}>👤 角色设定</option>
                <option value="outline" ${genResult.item_type === 'outline' ? 'selected' : ''}>📋 故事大纲</option>
              </select>
            </div>
            <div>
              <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">内容（可直接编辑修改）</label>
              <textarea id="input-item-content" data-item-type="${esc(genResult.item_type)}" class="chat-input" style="width:100%;min-height:280px;border-radius:8px;font-size:12px;">${esc(genResult.content)}</textarea>
            </div>
          ` : html`
            <div style="margin-bottom:12px;">
              <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">选择类型</label>
              <select id="input-item-type" class="chat-input" style="width:100%;border-radius:8px;">
                <option value="world_setting">🌍 世界观设定</option>
                <option value="character_setting">👤 角色设定</option>
                <option value="outline">📋 故事大纲</option>
              </select>
            </div>
            <div style="font-size:12px;color:var(--text-tertiary);">AI 将根据当前对话历史自动生成内容，生成后你可以检查和修改。</div>
          `}
        </div>
        <div class="modal-actions">
          <button class="btn" onclick="window._closeModal()">取消</button>
          ${genResult
            ? html`<button class="btn-primary" onclick="window._submitGeneratedItem()">✓ 确认保存</button>`
            : html`<button class="btn-primary" onclick="window._startGenerateItem()">✨ AI 生成</button>`
          }
        </div>
      </div>
    </div>`
  } else if (type === 'summarize-msg') {
    const genResult = data?.generated
    const s = getState()
    content = html`
    <div class="modal-overlay" onclick="window._closeModal()">
      <div class="modal" onclick="event.stopPropagation()" style="max-width:600px;">
        <div class="modal-title">${genResult ? '检查并保存' : '📝 总结另存为'}</div>
        <div class="modal-body">
          ${genResult ? html`
            <div style="display:flex;gap:8px;margin-bottom:12px;">
              <div style="flex:1;">
                <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">保存类型</label>
                <select id="input-save-type" class="chat-input" style="width:100%;border-radius:8px;">
                  <option value="world_setting" ${genResult.item_type === 'world_setting' ? 'selected' : ''}>🌍 世界观设定</option>
                  <option value="character_setting" ${genResult.item_type === 'character_setting' ? 'selected' : ''}>👤 角色设定</option>
                  <option value="outline" ${genResult.item_type === 'outline' ? 'selected' : ''}>📋 故事大纲</option>
                </select>
              </div>
              <div style="flex:1;">
                <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">章节标题</label>
                <input id="input-save-subtitle" class="chat-input" style="width:100%;border-radius:8px;" value="${esc(genResult.subtitle || '')}" placeholder="AI 建议或自定义..." />
              </div>
            </div>
            ${(() => {
              const existing = s.workspaceItems?.find(w => w.item_type === genResult.item_type)
              if (existing) {
                return html`<div style="margin-bottom:12px;padding:8px 12px;background:var(--accent-light);border-radius:var(--radius-sm);font-size:12px;color:var(--accent);">
                  📎 将补充到已有文档「${esc(existing.title)}」中（以 ## 章节标题追加）
                </div>`
              }
              return html`<div style="margin-bottom:12px;padding:8px 12px;background:var(--chip-finalized-bg);border-radius:var(--radius-sm);font-size:12px;color:var(--chip-finalized);">
                ✨ 该类型尚无文档，将创建新文档
              </div>`
            })()}
            <input type="hidden" id="input-save-title" value="${esc(genResult.title)}" />
            <div>
              <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">内容（可直接编辑修改）</label>
              <textarea id="input-save-content" class="chat-input" data-item-type="${esc(genResult.item_type)}" style="width:100%;min-height:280px;border-radius:8px;font-size:12px;">${esc(genResult.content)}</textarea>
            </div>
          ` : html`
            <div style="font-size:13px;color:var(--text-primary);margin-bottom:12px;">选择总结类型：</div>
            <div style="display:flex;flex-direction:column;gap:8px;">
              <button class="btn" onclick="window._startSummarizeMsg('world_setting')" style="padding:12px;text-align:left;">
                <div style="font-weight:600;">🌍 世界观设定</div>
                <div style="font-size:11px;color:var(--text-secondary);margin-top:2px;">提取地理、势力、规则、历史、修炼体系等</div>
              </button>
              <button class="btn" onclick="window._startSummarizeMsg('character_setting')" style="padding:12px;text-align:left;">
                <div style="font-weight:600;">👤 角色设定</div>
                <div style="font-size:11px;color:var(--text-secondary);margin-top:2px;">提取姓名、外貌、性格、能力、人际关系等</div>
              </button>
              <button class="btn" onclick="window._startSummarizeMsg('outline')" style="padding:12px;text-align:left;">
                <div style="font-weight:600;">📋 故事大纲</div>
                <div style="font-size:11px;color:var(--text-secondary);margin-top:2px;">提取主线、支线、关键事件、转折点等</div>
              </button>
            </div>
          `}
        </div>
        <div class="modal-actions">
          <button class="btn" onclick="window._closeModal()">取消</button>
          ${genResult
            ? html`<button class="btn-primary" onclick="window._submitSummarizeSave()">💾 ${s.workspaceItems?.find(w => w.item_type === genResult.item_type) ? '补充到文档' : '创建新文档'}</button>`
            : ''
          }
        </div>
      </div>
    </div>`
  } else if (type === 'sync-workspace') {
    const syncData = data?.result
    const wsItems = data?.workspaceItems || []
    content = html`
    <div class="modal-overlay" onclick="window._closeModal()">
      <div class="modal" onclick="event.stopPropagation()" style="max-width:700px;">
        <div class="modal-title">🔄 同步到工作台</div>
        <div class="modal-body">
          ${!syncData ? html`<div style="text-align:center;padding:20px;">正在分析变更...</div>` : ''}
          ${syncData && syncData.updates?.length === 0 && syncData.suggestions?.length === 0 ? html`
            <div style="text-align:center;padding:20px;color:var(--text-secondary);">未检测到需要更新的内容</div>
          ` : ''}
          ${syncData?.updates?.map((u, i) => html`
            <div style="margin-bottom:16px;padding:12px;background:var(--bg-input);border-radius:8px;border-left:3px solid var(--accent);">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
                <span style="font-weight:600;font-size:13px;">📝 ${esc(u.item_title)}</span>
                <span style="font-size:11px;color:var(--accent);">${esc(u.changes_summary)}</span>
              </div>
              <div style="display:flex;gap:8px;margin-bottom:6px;" id="sync-new-fields-${i}" style="display:none;">
                <div style="flex:1;">
                  <label style="font-size:11px;color:var(--text-secondary);">新条目标题</label>
                  <input id="sync-new-title-${i}" class="chat-input" style="width:100%;border-radius:6px;font-size:12px;padding:4px 8px;margin-top:2px;" value="${esc(u.item_title)}" />
                </div>
                <div style="flex:1;">
                  <label style="font-size:11px;color:var(--text-secondary);">副标题</label>
                  <input id="sync-new-subtitle-${i}" class="chat-input" style="width:100%;border-radius:6px;font-size:12px;padding:4px 8px;margin-top:2px;" placeholder="如：基础设定、xx门派..." />
                </div>
              </div>
              <div style="margin-bottom:6px;">
                <label style="font-size:11px;color:var(--text-secondary);">更新后内容（可编辑）：</label>
                <textarea id="sync-update-${i}" data-item-id="${esc(u.item_id)}" class="chat-input" style="width:100%;min-height:200px;border-radius:6px;font-size:12px;margin-top:4px;">${esc(u.updated_content)}</textarea>
              </div>
              <div style="display:flex;align-items:center;gap:6px;justify-content:flex-end;">
                <select id="sync-target-${i}" class="chat-input" style="border-radius:6px;font-size:11px;padding:3px 6px;max-width:200px;">
                  <option value="${esc(u.item_id)}">→ ${esc(u.item_title)}（推荐）</option>
                  ${wsItems.filter(w => w.id !== u.item_id).map(w => html`
                    <option value="${esc(w.id)}">→ ${esc(w.title)}${w.subtitle ? ' / ' + esc(w.subtitle) : ''}</option>
                  `).join('')}
                  <option value="__new__">➕ 创建为新条目</option>
                </select>
                <button class="btn btn-sm" data-action="apply-sync-update" data-sync-index="${i}" style="padding:3px 10px;font-size:11px;background:var(--accent);color:#fff;border:none;">保存</button>
              </div>
            </div>
          `).join('') || ''}
          ${syncData?.suggestions?.map((s, si) => html`
            <div style="margin-bottom:16px;padding:12px;background:var(--bg-input);border-radius:8px;border-left:3px solid #4caf50;">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
                <span style="font-weight:600;font-size:13px;">✨ 新建议：${esc(s.title)}</span>
                <span style="font-size:11px;color:#4caf50;">${esc(s.reason)}</span>
              </div>
              <div style="display:flex;gap:8px;margin-bottom:6px;">
                <div style="flex:1;">
                  <label style="font-size:11px;color:var(--text-secondary);">主标题</label>
                  <input id="sync-suggest-title-${si}" class="chat-input" style="width:100%;border-radius:6px;font-size:12px;padding:4px 8px;margin-top:2px;" value="${esc(s.title)}" />
                </div>
                <div style="flex:1;">
                  <label style="font-size:11px;color:var(--text-secondary);">副标题</label>
                  <input id="sync-suggest-subtitle-${si}" class="chat-input" style="width:100%;border-radius:6px;font-size:12px;padding:4px 8px;margin-top:2px;" value="${esc(s.subtitle || '')}" placeholder="如：基础设定、xx门派..." />
                </div>
              </div>
              <div style="margin-bottom:6px;">
                <textarea id="sync-suggest-${si}" data-item-type="${esc(s.item_type)}" class="chat-input" style="width:100%;min-height:150px;border-radius:6px;font-size:12px;margin-top:4px;">${esc(s.content)}</textarea>
              </div>
              <div style="display:flex;gap:6px;justify-content:flex-end;">
                <button class="btn btn-sm" data-action="apply-sync-suggest" data-sync-index="${si}" style="padding:3px 10px;font-size:11px;background:#4caf50;color:#fff;border:none;">创建条目</button>
              </div>
            </div>
          `).join('') || ''}
        </div>
        <div class="modal-actions">
          <button class="btn" onclick="window._closeModal()">关闭</button>
        </div>
      </div>
    </div>`
  } else if (type === 'edit-item') {
    const item = data.item
    content = html`
    <div class="modal-overlay" onclick="window._closeModal()">
      <div class="modal" onclick="event.stopPropagation()" style="max-width:700px;">
        <div class="modal-title">编辑条目</div>
        <div class="modal-body">
          <div style="display:flex;gap:8px;margin-bottom:12px;">
            <div style="flex:1;">
              <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">主标题</label>
              <input id="edit-item-title" class="chat-input" style="width:100%;border-radius:8px;" value="${esc(item.title || '')}" />
            </div>
            <div style="flex:1;">
              <label style="display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;">副标题</label>
              <input id="edit-item-subtitle" class="chat-input" style="width:100%;border-radius:8px;" value="${esc(item.subtitle || '')}" />
            </div>
          </div>
          <div style="display:flex;gap:6px;margin-bottom:6px;">
            <button class="btn btn-sm" id="edit-preview-btn" style="padding:2px 8px;font-size:11px;background:var(--accent);color:#fff;" onclick="window._toggleEditPreview('preview')">预览</button>
            <button class="btn btn-sm" id="edit-source-btn" style="padding:2px 8px;font-size:11px;" onclick="window._toggleEditPreview('source')">源码</button>
          </div>
          <div>
            <div id="edit-preview-area" class="markdown-body" style="width:100%;min-height:300px;max-height:500px;overflow-y:auto;padding:12px;background:var(--bg-input);border-radius:8px;font-size:13px;line-height:1.6;">${formatMd(item.content || '')}</div>
            <textarea id="edit-item-content" class="chat-input" style="display:none;width:100%;min-height:300px;border-radius:8px;font-size:12px;">${esc(item.content || '')}</textarea>
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
    case 'copy-msg':
      e.stopPropagation()
      const copyIdx = parseInt(btn.dataset.index)
      const copyMsg = s.messages[copyIdx]
      if (copyMsg) {
        try {
          await navigator.clipboard.writeText(copyMsg.content)
          const orig = btn.textContent
          btn.textContent = '✓ 已复制'
          setTimeout(() => { btn.textContent = orig }, 1500)
        } catch {
          const ta = document.createElement('textarea')
          ta.value = copyMsg.content
          document.body.appendChild(ta)
          ta.select()
          document.execCommand('copy')
          document.body.removeChild(ta)
          btn.textContent = '✓ 已复制'
          setTimeout(() => { btn.textContent = '📋 复制' }, 1500)
        }
      }
      break
    case 'summarize-msg':
      e.stopPropagation()
      const smIdx = parseInt(btn.dataset.index)
      window._summarizeMsgIndex = smIdx
      showModal('summarize-msg')
      break
    case 'sync-workspace':
      e.stopPropagation()
      const swIdx = parseInt(btn.dataset.index)
      const swMsg = s.messages[swIdx]
      if (!swMsg) break
      showModal('sync-workspace', { workspaceItems: s.workspaceItems })
      try {
        const swResult = await syncToWorkspace(s.currentProjectId, swMsg.content, s.workspaceItems)
        showModal('sync-workspace', { result: swResult, workspaceItems: s.workspaceItems })
      } catch (err) {
        alert('同步分析失败: ' + err.message)
        closeModal()
      }
      break
    case 'apply-sync-update':
      e.stopPropagation()
      btn.disabled = true
      btn.textContent = '保存中...'
      try {
        const suIdx = parseInt(btn.dataset.syncIndex)
        const suTextarea = document.getElementById(`sync-update-${suIdx}`)
        const suSelect = document.getElementById(`sync-target-${suIdx}`)
        if (!suTextarea) break
        const suContent = suTextarea.value.trim()
        if (!suContent) { showToast('内容不能为空', 'error'); btn.disabled = false; btn.textContent = '保存'; break }
        const suTargetId = suSelect?.value
        if (suTargetId === '__new__') {
          const suNewTitle = document.getElementById(`sync-new-title-${suIdx}`)?.value?.trim() || '更新内容'
          const suNewSubtitle = document.getElementById(`sync-new-subtitle-${suIdx}`)?.value?.trim() || ''
          await createWorkspaceItem(s.currentProjectId, { item_type: 'world_setting', title: suNewTitle, subtitle: suNewSubtitle, content: suContent })
        } else if (suTargetId) {
          await updateWorkspaceItem(suTargetId, { content: suContent })
        }
        await fetchWorkspaceItems(s.currentProjectId)
        btn.textContent = '✓ 已保存'
        btn.disabled = true
        btn.style.opacity = '0.5'
        if (suSelect) suSelect.disabled = true
        render()
        showToast('已同步到工作台', 'success')
      } catch (err) {
        showToast('保存失败: ' + err.message, 'error')
        btn.disabled = false
        btn.textContent = '保存'
      }
      break
    case 'apply-sync-suggest':
      e.stopPropagation()
      btn.disabled = true
      btn.textContent = '创建中...'
      try {
        const ssIdx = parseInt(btn.dataset.syncIndex)
        const ssTextarea = document.getElementById(`sync-suggest-${ssIdx}`)
        if (!ssTextarea) break
        const ssType = ssTextarea.dataset.itemType
        const ssTitle = document.getElementById(`sync-suggest-title-${ssIdx}`)?.value?.trim() || '新条目'
        const ssSubtitle = document.getElementById(`sync-suggest-subtitle-${ssIdx}`)?.value?.trim() || ''
        const ssContent = ssTextarea.value.trim()
        if (!ssContent) { showToast('内容不能为空', 'error'); btn.disabled = false; btn.textContent = '创建条目'; break }
        await createWorkspaceItem(s.currentProjectId, { item_type: ssType || 'world_setting', title: ssTitle, subtitle: ssSubtitle, content: ssContent })
        await fetchWorkspaceItems(s.currentProjectId)
        btn.textContent = '✓ 已创建'
        btn.disabled = true
        btn.style.opacity = '0.5'
        render()
        showToast('新条目已创建', 'success')
      } catch (err) {
        showToast('创建失败: ' + err.message, 'error')
        btn.disabled = false
        btn.textContent = '创建条目'
      }
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
    case 'unlock-item':
      await updateItemStatus(btn.dataset.id, 'draft', s.currentProjectId)
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
    case 'ai-summarize':
      e.stopPropagation()
      const userMsgs = s.messages.filter(m => m.role === 'user')
      if (userMsgs.length === 0) { alert('当前对话中没有你的消息'); break }
      const summaryContent = userMsgs.map((m, i) => `${i + 1}. ${m.content}`).join('\n\n')
      setState({ isSummarizing: true })
      smartRender()
      try {
        await summarizeToWorkspace(s.currentProjectId, summaryContent, 'world_setting', '灵感笔记')
        await fetchWorkspaceItems(s.currentProjectId)
        setState({ isSummarizing: false })
        render()
      } catch (err) {
        setState({ isSummarizing: false })
        render()
        alert('整理失败: ' + err.message)
      }
      break
    case 'mobile-show-left': {
      const cur1 = getState()
      const tab = cur1._mobileTab === 'left' ? null : 'left'
      setState({ _mobileTab: tab })
      const sl = document.querySelector('.sidebar-left')
      const sr = document.querySelector('.sidebar-right')
      if (sl) sl.classList.toggle('mobile-show', tab === 'left')
      if (sr) sr.classList.remove('mobile-show')
      render()
      break
    }
    case 'mobile-show-chat': {
      setState({ _mobileTab: null })
      const sl2 = document.querySelector('.sidebar-left')
      const sr2 = document.querySelector('.sidebar-right')
      if (sl2) sl2.classList.remove('mobile-show')
      if (sr2) sr2.classList.remove('mobile-show')
      render()
      break
    }
    case 'mobile-show-right': {
      const cur3 = getState()
      const tab3 = cur3._mobileTab === 'right' ? null : 'right'
      setState({ _mobileTab: tab3 })
      const sl3 = document.querySelector('.sidebar-left')
      const sr3 = document.querySelector('.sidebar-right')
      if (sl3) sl3.classList.remove('mobile-show')
      if (sr3) sr3.classList.toggle('mobile-show', tab3 === 'right')
      render()
      break
    }
    case 'extract-questions':
      e.stopPropagation()
      const uMsgs = s.messages.filter(m => m.role === 'user')
      if (uMsgs.length === 0) { alert('当前对话中没有你的消息'); break }
      setState({ isSummarizing: true })
      smartRender()
      try {
        const result = await extractQuestions(s.currentProjectId, uMsgs.map(m => m.content))
        setState({ isSummarizing: false, pendingQuestions: result.questions || [], questionAnswers: {} })
        render()
      } catch (err) {
        setState({ isSummarizing: false })
        render()
        alert('提取失败: ' + err.message)
      }
      break
    case 'show-questions':
      e.stopPropagation()
      setState({ pendingQuestions: [] })
      render()
      break
    case 'dismiss-question':
      e.stopPropagation()
      const idx = parseInt(btn.dataset.index)
      const updated = s.pendingQuestions.filter((_, i) => i !== idx)
      const newAnswers = { ...s.questionAnswers }
      delete newAnswers[idx]
      setState({ pendingQuestions: updated, questionAnswers: newAnswers })
      render()
      break
    case 'answer-question':
      e.stopPropagation()
      const aIdx = parseInt(btn.dataset.index)
      const aAnswer = btn.dataset.answer
      setState({ questionAnswers: { ...s.questionAnswers, [aIdx]: aAnswer } })
      render()
      break
    case 'answer-custom':
      e.stopPropagation()
      const cIdx = parseInt(btn.dataset.index)
      const cInput = document.getElementById(`custom-answer-${cIdx}`)
      const cAnswer = cInput?.value?.trim()
      if (!cAnswer) break
      setState({ questionAnswers: { ...s.questionAnswers, [cIdx]: cAnswer } })
      render()
      break
    case 'submit-answers':
      e.stopPropagation()
      const answers = s.questionAnswers
      const questions = s.pendingQuestions
      if (Object.keys(answers).length === 0) { alert('请至少回答一个问题'); break }
      const replyParts = questions
        .filter((_, i) => answers[i])
        .map((q, i) => `**${q.keyword}**：${answers[i]}`)
      const replyContent = replyParts.join('\n')
      setState({ pendingQuestions: [], questionAnswers: {} })
      if (s.currentConversationId) {
        sendMessage(s.currentConversationId, replyContent)
      }
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
  }
  const syncTargetMatch = e.target.id?.match(/^sync-target-(\d+)$/)
  if (syncTargetMatch) {
    const idx = syncTargetMatch[1]
    const fieldsEl = document.getElementById(`sync-new-fields-${idx}`)
    if (fieldsEl) {
      fieldsEl.style.display = e.target.value === '__new__' ? 'flex' : 'none'
    }
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
  _autoScroll = true
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

function initResizeHandles() {
  let activeHandle = null
  let startX = 0
  let startWidth = 0
  let targetPanel = null

  const onMouseDown = (e) => {
    const handle = e.target.closest('.resize-handle, .resize-handle-left')
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
