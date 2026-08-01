import type {
  Project,
  Conversation,
  Message,
  WorkspaceItem,
  WorkspaceItemInput,
  WorkspaceItemStatus,
  Assistant,
  AssistantInput,
  Chronicle,
  PointsData,
  EnsureConversationResult,
  ChatChunkType,
  ConsultEvent,
  ConsultEventHandler,
  StreamAbort,
  StreamError,
  ID,
} from './types'

const BASE = '/api'

async function request<T = unknown>(method: string, url: string, body?: unknown): Promise<T> {
  const options: RequestInit = {
    method,
    headers: {},
  }
  if (body !== undefined) {
    options.headers = { 'Content-Type': 'application/json' }
    options.body = JSON.stringify(body)
  }
  const res = await fetch(BASE + url, options)
  if (!res.ok) {
    let detail = ''
    try {
      const errBody = await res.json()
      detail = errBody?.detail || errBody?.message || ''
    } catch {
      try { detail = await res.text() } catch {}
    }
    if (res.status === 401) detail = detail || '未授权，请检查配置'
    else if (res.status === 403) detail = detail || '无权限执行此操作'
    else if (res.status === 404) detail = detail || '资源不存在'
    else if (res.status >= 500) detail = detail || '服务器错误，请稍后重试'
    const error = new Error(detail ? `${detail}` : `HTTP ${res.status}`) as StreamError
    error.status = res.status
    throw error
  }
  return res.json() as Promise<T>
}

export function listProjects(): Promise<Project[]> {
  return request<Project[]>('GET', '/projects')
}

export function getProject(id: ID): Promise<Project> {
  return request<Project>('GET', `/projects/${id}`)
}

export function createProject(data: { name: string; genre?: string }): Promise<Project> {
  return request<Project>('POST', '/projects', data)
}

export function updateProject(id: ID, data: Partial<Project>): Promise<Project> {
  return request<Project>('PUT', `/projects/${id}`, data)
}

export async function deleteProject(id: ID): Promise<void> {
  await request<void>('DELETE', `/projects/${id}`)
}

export function listConversations(projectId: ID): Promise<Conversation[]> {
  return request<Conversation[]>('GET', `/projects/${projectId}/conversations`)
}

export function createConversation(projectId: ID, title: string): Promise<Conversation> {
  return request<Conversation>('POST', `/projects/${projectId}/conversations`, { title })
}

export async function deleteConversation(id: ID): Promise<void> {
  await request<void>('DELETE', `/conversations/${id}`)
}

export function renameConversation(id: ID, title: string): Promise<Conversation> {
  return request<Conversation>('PUT', `/conversations/${id}`, { title })
}

export function getMessages(conversationId: ID): Promise<Message[]> {
  return request<Message[]>('GET', `/conversations/${conversationId}/messages`)
}

export function streamExpertConsult(
  projectId: ID,
  point: string,
  conversationId: ID | '',
  idea: string,
  onEvent: ConsultEventHandler,
  onDone: () => void,
  onError: (err: StreamError) => void,
): StreamAbort {
  const xhr = new XMLHttpRequest()
  xhr.open('POST', `${BASE}/projects/${projectId}/points/${point}/expert-consult`)
  xhr.setRequestHeader('Content-Type', 'application/json')

  let processed = 0
  let pending = ''
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
    pending = lines.pop() as string
    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const obj = JSON.parse(line) as ConsultEvent
        if (obj.phase === 'error') {
          onError(new Error((obj as any).message || '会诊失败') as StreamError)
          finished = true
          return
        }
        onEvent(obj)
        if (obj.phase === 'done') {
          finish()
          return
        }
      } catch (e) {
        // partial JSON
      }
    }
  }

  xhr.onprogress = processLines
  xhr.onload = function () {
    if (xhr.status >= 200 && xhr.status < 300) {
      if (pending.trim()) {
        try {
          const obj = JSON.parse(pending.trim()) as ConsultEvent
          onEvent(obj)
        } catch (e) {}
      }
      finish()
    } else {
      finished = true
      onError(new Error(`HTTP ${xhr.status}`) as StreamError)
    }
  }
  xhr.onerror = function () {
    if (finished) return
    finished = true
    onError(new Error('Network error') as StreamError)
  }
  xhr.onabort = function () {
    if (finished) return
    finished = true
    const err = new Error('Request aborted') as StreamError
    err.isAbort = true
    onError(err)
  }

  xhr.send(JSON.stringify({ idea, conversation_id: conversationId || '' }))

  return function abort() { xhr.abort() }
}

export function streamChat(
  conversationId: ID,
  content: string,
  onChunk: (chunk: string, type?: ChatChunkType) => void,
  onDone: () => void,
  onError: (err: StreamError, partialContent: string) => void,
  assistantId: ID | '',
  regenerate = false,
): StreamAbort {
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
    pending = lines.pop() as string
    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const obj = JSON.parse(line)
        if (obj.done) { finish(); return }
        if (obj.error) { onError(new Error(obj.error) as StreamError, fullContent); finished = true; return }
        if (obj.thinking) { onChunk(obj.thinking, 'thinking') }
        if (obj.content) {
          fullContent += obj.content
          onChunk(obj.content, 'content')
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
          if (obj.error) { onError(new Error(obj.error) as StreamError, fullContent); finished = true; return }
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
      onError(new Error(`HTTP ${xhr.status}`) as StreamError, fullContent)
    }
  }

  xhr.onerror = function () {
    if (finished) return
    finished = true
    onError(new Error('Network error') as StreamError, fullContent)
  }
  xhr.onabort = function () {
    if (finished) return
    finished = true
    const err = new Error('Request aborted') as StreamError
    err.isAbort = true
    onError(err, fullContent)
  }

  xhr.send(JSON.stringify({ content, assistant_id: assistantId || '', regenerate }))

  return function abort() { xhr.abort() }
}

export function listAssistants(): Promise<Assistant[]> {
  return request<Assistant[]>('GET', '/assistants')
}

export function createAssistant(data: AssistantInput): Promise<Assistant> {
  return request<Assistant>('POST', '/assistants', data)
}

export function updateAssistant(id: ID, data: AssistantInput): Promise<Assistant> {
  return request<Assistant>('PUT', `/assistants/${id}`, data)
}

export async function deleteAssistant(id: ID): Promise<void> {
  await request<void>('DELETE', `/assistants/${id}`)
}

export function listWorkspaceItems(projectId: ID): Promise<WorkspaceItem[]> {
  return request<WorkspaceItem[]>('GET', `/projects/${projectId}/workspace`)
}

export function createWorkspaceItem(projectId: ID, data: WorkspaceItemInput): Promise<WorkspaceItem> {
  return request<WorkspaceItem>('POST', `/projects/${projectId}/workspace`, data)
}

export function updateWorkspaceItem(itemId: ID, data: WorkspaceItemInput): Promise<WorkspaceItem> {
  return request<WorkspaceItem>('PUT', `/workspace/${itemId}`, data)
}

export function updateItemStatus(itemId: ID, status: WorkspaceItemStatus): Promise<WorkspaceItem> {
  return request<WorkspaceItem>('PUT', `/workspace/${itemId}/status`, { status })
}

export async function deleteWorkspaceItem(itemId: ID): Promise<void> {
  await request<void>('DELETE', `/workspace/${itemId}`)
}

export function summarizeToWorkspace(projectId: ID, content: string, itemType: string, title: string): Promise<WorkspaceItem> {
  return request<WorkspaceItem>('POST', `/projects/${projectId}/summarize`, { content, item_type: itemType, title })
}

export function extractQuestions(projectId: ID, userMessages: string[]): Promise<{ questions: string[] }> {
  return request('POST', `/projects/${projectId}/extract-questions`, { user_messages: userMessages })
}

export function generateWorkspaceItem(projectId: ID, itemType: string, messages: Message[]): Promise<WorkspaceItem> {
  return request<WorkspaceItem>('POST', `/projects/${projectId}/generate-item`, { item_type: itemType, conversation_messages: messages })
}

export function summarizeMessage(projectId: ID, content: string, itemType: string): Promise<WorkspaceItem> {
  return request<WorkspaceItem>('POST', `/projects/${projectId}/summarize-message`, { content, item_type: itemType })
}

export function syncToWorkspace(projectId: ID, aiMessage: string, workspaceItems: WorkspaceItem[]): Promise<unknown> {
  return request('POST', `/projects/${projectId}/sync-workspace`, { ai_message: aiMessage, workspace_items: workspaceItems })
}

export function getChronicle(projectId: ID): Promise<Chronicle> {
  return request<Chronicle>('GET', `/projects/${projectId}/chronicle`)
}

export function updateChronicle(projectId: ID, data: Partial<Chronicle>): Promise<Chronicle> {
  return request<Chronicle>('PUT', `/projects/${projectId}/chronicle`, data)
}

export function refreshChronicle(projectId: ID): Promise<Chronicle> {
  return request<Chronicle>('POST', `/projects/${projectId}/chronicle/refresh`)
}

export function getSkeleton(projectId: ID): Promise<unknown> {
  return request('GET', `/projects/${projectId}/skeleton`)
}

export function skeletonGuide(projectId: ID, data: unknown): Promise<unknown> {
  return request('POST', `/projects/${projectId}/skeleton/guide`, data)
}

export function checkWriteReadiness(projectId: ID): Promise<{ ready: boolean; reasons?: string[] }> {
  return request('GET', `/projects/${projectId}/skeleton/check-write`)
}

export function generateChapterPlan(projectId: ID, data: unknown): Promise<unknown> {
  return request('POST', `/projects/${projectId}/chapter-plan/generate`, data)
}

export function getChapterPlan(projectId: ID, chapterNumber: number): Promise<unknown> {
  return request('GET', `/projects/${projectId}/chapter-plan/${chapterNumber}`)
}

export function confirmChapterPlan(projectId: ID, chapterNumber: number): Promise<unknown> {
  return request('PUT', `/projects/${projectId}/chapter-plan/${chapterNumber}/confirm`)
}

export function reviewChapter(projectId: ID, chapterNumber: number, content: string): Promise<unknown> {
  return request('POST', `/projects/${projectId}/chapters/${chapterNumber}/review`, { chapter_content: content })
}

export function getPoints(projectId: ID): Promise<PointsData> {
  return request<PointsData>('GET', `/projects/${projectId}/points`)
}

export function ensurePointConversation(projectId: ID, point: string): Promise<EnsureConversationResult> {
  return request<EnsureConversationResult>('POST', `/projects/${projectId}/points/${point}/ensure-conversation`)
}

export function summarizePoint(projectId: ID, point: string, conversationId: ID): Promise<unknown> {
  return request('POST', `/projects/${projectId}/points/${point}/summarize`, { conversation_id: conversationId })
}

export function autoGeneratePoint(projectId: ID, point: string, conversationId: ID | '', idea: string): Promise<{ content: string; metadata?: Record<string, unknown> }> {
  return request('POST', `/projects/${projectId}/points/${point}/auto-generate`, { idea, conversation_id: conversationId || '' })
}
