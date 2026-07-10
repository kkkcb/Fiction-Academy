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
    let detail = ''
    try {
      const body = await res.json()
      detail = body?.detail || body?.message || ''
    } catch {
      try { detail = await res.text() } catch {}
    }
    const error = new Error(detail ? `${detail}` : `HTTP ${res.status}`)
    error.status = res.status
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

  let processed = 0
  let pending = ''
  let fullContent = ''
  let finished = false

  const finish = () => {
    if (finished) return
    finished = true
    onDone()
  }

  const processLines = () => {
    const newData = xhr.responseText.substring(processed)
    processed = xhr.responseText.length
    pending += newData
    const lines = pending.split('\n')
    pending = lines.pop()
    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const obj = JSON.parse(line)
        if (obj.done) { finish(); return }
        if (obj.error) { onError(new Error(obj.error), fullContent); finished = true; return }
        if (obj.content) {
          fullContent += obj.content
          onChunk(obj.content)
        }
      } catch (e) {
        // partial JSON, will be retried on next chunk
      }
    }
  }

  xhr.onprogress = function () {
    if (finished) return
    processLines()
  }

  xhr.onload = function () {
    if (xhr.status >= 200 && xhr.status < 300) {
      if (pending.trim()) {
        try {
          const obj = JSON.parse(pending.trim())
          if (obj.done) { finish(); return }
          if (obj.error) { onError(new Error(obj.error), fullContent); finished = true; return }
          if (obj.content) {
            fullContent += obj.content
            onChunk(obj.content)
          }
        } catch (e) {
          // ignore residual parse error
        }
      }
      finish()
    } else {
      finished = true
      onError(new Error(`HTTP ${xhr.status}`), fullContent)
    }
  }

  xhr.onerror = function () {
    if (finished) return
    finished = true
    onError(new Error('Network error'), fullContent)
  }
  xhr.onabort = function () {
    if (finished) return
    finished = true
    onError(new Error('Request aborted'), fullContent)
  }

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

export async function getSkeleton(projectId) {
  return request('GET', `/projects/${projectId}/skeleton`)
}

export async function skeletonGuide(projectId, data) {
  return request('POST', `/projects/${projectId}/skeleton/guide`, data)
}

export async function checkWriteReadiness(projectId) {
  return request('GET', `/projects/${projectId}/skeleton/check-write`)
}

export async function generateChapterPlan(projectId, data) {
  return request('POST', `/projects/${projectId}/chapter-plan/generate`, data)
}

export async function getChapterPlan(projectId, chapterNumber) {
  return request('GET', `/projects/${projectId}/chapter-plan/${chapterNumber}`)
}

export async function confirmChapterPlan(projectId, chapterNumber) {
  return request('PUT', `/projects/${projectId}/chapter-plan/${chapterNumber}/confirm`)
}

export async function reviewChapter(projectId, chapterNumber, content) {
  return request('POST', `/projects/${projectId}/chapters/${chapterNumber}/review`, { chapter_content: content })
}
