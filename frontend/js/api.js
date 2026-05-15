const BASE = '/api'

async function request(method, url, body) {
  const options = {
    method,
    headers: {},
  }
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(body)
  }
  const res = await fetch(BASE + url, options)
  if (!res.ok) {
    const error = new Error(`HTTP ${res.status}`)
    error.status = res.status
    try {
      error.body = await res.json()
    } catch {
      error.body = null
    }
    throw error
  }
  return res.json()
}

export async function listProjects() {
  return request('GET', '/projects')
}

export async function getProject(id) {
  return request('GET', `/projects/${id}`)
}

export async function createProject(data) {
  return request('POST', '/projects', data)
}

export async function updateProject(id, data) {
  return request('PUT', `/projects/${id}`, data)
}

export async function deleteProject(id) {
  return request('DELETE', `/projects/${id}`)
}

export async function listConversations(projectId) {
  return request('GET', `/projects/${projectId}/conversations`)
}

export async function createConversation(projectId, title) {
  return request('POST', `/projects/${projectId}/conversations`, { title })
}

export async function deleteConversation(id) {
  return request('DELETE', `/conversations/${id}`)
}

export async function renameConversation(id, title) {
  return request('PUT', `/conversations/${id}`, { title })
}

export async function getMessages(conversationId) {
  return request('GET', `/conversations/${conversationId}/messages`)
}

export function streamChat(conversationId, content, onChunk, onDone, onError, assistantId, regenerate = false) {
  const xhr = new XMLHttpRequest()
  xhr.open('POST', `${BASE}/conversations/${conversationId}/chat/stream`)
  xhr.setRequestHeader('Content-Type', 'application/json')

  let buffer = ''
  let finished = false

  const finish = () => {
    if (finished) return
    finished = true
    onDone()
  }

  xhr.onprogress = function () {
    if (finished) return
    const newData = xhr.responseText.substring(buffer.length)
    buffer = xhr.responseText
    const lines = newData.split('\n')
    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const obj = JSON.parse(line)
        if (obj.done) { finish(); return }
        if (obj.error) { onError(new Error(obj.error)); finished = true; return }
        if (obj.content) onChunk(obj.content)
      } catch {}
    }
  }

  xhr.onload = function () {
    if (xhr.status >= 200 && xhr.status < 300) finish()
    else { finished = true; onError(new Error(`HTTP ${xhr.status}`)) }
  }

  xhr.onerror = function () { finished = true; onError(new Error('Network error')) }
  xhr.onabort = function () { finished = true; onError(new Error('Request aborted')) }

  xhr.send(JSON.stringify({ content, assistant_id: assistantId || '', regenerate }))

  return function abort() { xhr.abort() }
}

export async function listAssistants() {
  return request('GET', '/assistants')
}

export async function createAssistant(data) {
  return request('POST', '/assistants', data)
}

export async function updateAssistant(id, data) {
  return request('PUT', `/assistants/${id}`, data)
}

export async function deleteAssistant(id) {
  return request('DELETE', `/assistants/${id}`)
}

export async function listWorkspaceItems(projectId) {
  return request('GET', `/projects/${projectId}/workspace`)
}

export async function createWorkspaceItem(projectId, data) {
  return request('POST', `/projects/${projectId}/workspace`, data)
}

export async function updateWorkspaceItem(itemId, data) {
  return request('PUT', `/workspace/${itemId}`, data)
}

export async function updateItemStatus(itemId, status) {
  return request('PUT', `/workspace/${itemId}/status`, { status })
}

export async function deleteWorkspaceItem(itemId) {
  return request('DELETE', `/workspace/${itemId}`)
}

export async function summarizeToWorkspace(projectId, content, itemType, title) {
  return request('POST', `/projects/${projectId}/summarize`, { content, item_type: itemType, title })
}

export async function extractQuestions(projectId, userMessages) {
  return request('POST', `/projects/${projectId}/extract-questions`, { user_messages: userMessages })
}

export async function generateWorkspaceItem(projectId, itemType, messages) {
  return request('POST', `/projects/${projectId}/generate-item`, { item_type: itemType, conversation_messages: messages })
}

export async function summarizeMessage(projectId, content, itemType) {
  return request('POST', `/projects/${projectId}/summarize-message`, { content, item_type: itemType })
}

export async function syncToWorkspace(projectId, aiMessage, workspaceItems) {
  return request('POST', `/projects/${projectId}/sync-workspace`, { ai_message: aiMessage, workspace_items: workspaceItems })
}

export async function getChronicle(projectId) {
  return request('GET', `/projects/${projectId}/chronicle`)
}

export async function updateChronicle(projectId, data) {
  return request('PUT', `/projects/${projectId}/chronicle`, data)
}

export async function refreshChronicle(projectId) {
  return request('POST', `/projects/${projectId}/chronicle/refresh`)
}
