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
  KgGraph,
  KgEntity,
  KgEntityInput,
  KgRelationInput,
  KgExtractResult,
  GoalState,
  GoalStep,
  Author,
  PromptLibrary,
  PromptHistoryItem,
  DistillDigest,
} from './types'

const BASE = '/api'

// 流式请求的空闲超时：连续 STREAM_IDLE_TIMEOUT_MS 没有收到任何数据视为服务器挂起
const STREAM_IDLE_TIMEOUT_MS = 120_000

interface IdleWatchdog {
  touch: () => void
  cancel: () => void
}

function makeIdleWatchdog(onTimeout: () => void, timeoutMs: number = STREAM_IDLE_TIMEOUT_MS): IdleWatchdog {
  let timer: ReturnType<typeof setTimeout> | null = null
  const schedule = () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(onTimeout, timeoutMs)
  }
  return {
    touch: schedule,
    cancel() {
      if (timer) clearTimeout(timer)
      timer = null
    },
  }
}

function parseHttpError(status: number, body: string): StreamError {
  let detail = ''
  try {
    const obj = JSON.parse(body)
    detail = obj?.detail || obj?.message || ''
  } catch {}
  const err = new Error(detail || `HTTP ${status}`) as StreamError
  err.status = status
  return err
}

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

export function getAuthors(): Promise<Author[]> {
  return request<Author[]>('GET', '/authors')
}

export function getPrompts(): Promise<PromptLibrary> {
  return request<PromptLibrary>('GET', '/prompts')
}

export function savePromptOverride(key: string, text: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('PUT', `/prompts/${encodeURIComponent(key)}`, { text })
}

export function resetPromptOverride(key: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('DELETE', `/prompts/${encodeURIComponent(key)}`)
}

export function getPromptHistory(key: string): Promise<{ items: PromptHistoryItem[] }> {
  return request<{ items: PromptHistoryItem[] }>('GET', `/prompts/${encodeURIComponent(key)}/history`)
}

export function resolveDistillConflicts(
  projectId: ID,
  choices: { id: number; decision: 'old' | 'new' | 'custom'; custom_text?: string }[],
): Promise<{ ok: boolean; resolved: number }> {
  return request<{ ok: boolean; resolved: number }>(
    'POST', `/projects/${projectId}/distill-conflicts/resolve`, { choices })
}

export function getDistillDigest(projectId: ID): Promise<DistillDigest> {
  return request<DistillDigest>('GET', `/projects/${projectId}/distill-conflicts/digest`)
}

export function createProject(data: { name: string; genre?: string; rules_text?: string; author_key?: string }): Promise<Project> {
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

export function deleteMessage(messageId: ID): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('DELETE', `/messages/${messageId}`)
}

export interface HotItem {
  title: string
  hot: string
  url: string
  summary?: string
}

export interface HotListResult {
  source: string
  label: string
  cached: boolean
  stale?: boolean
  items: HotItem[]
}

export function getHotList(source: string): Promise<HotListResult> {
  return request<HotListResult>('GET', `/hot?source=${encodeURIComponent(source)}`)
}

export interface DiscussResult {
  ok: boolean
  kind?: 'excerpt' | 'page' | 'weibo_posts'
  summary?: string
  reason?: string
  hint?: string
}

export function getHotDiscuss(url: string, title: string, source: string): Promise<DiscussResult> {
  return request<DiscussResult>('GET',
    `/hot/discuss?url=${encodeURIComponent(url)}&title=${encodeURIComponent(title)}&source=${encodeURIComponent(source)}`)
}

export interface Material {
  id: ID
  title: string
  source?: string
  url?: string
  hot?: string
  note?: string
  created_at?: string
}

export function listMaterials(): Promise<Material[]> {
  return request<Material[]>('GET', '/materials')
}

export function createMaterial(data: Partial<Material>): Promise<Material> {
  return request<Material>('POST', '/materials', data)
}

export function deleteMaterial(id: ID): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('DELETE', `/materials/${id}`)
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
    watchdog.cancel()
    onDone()
  }

  const watchdog = makeIdleWatchdog(() => {
    if (finished) return
    finished = true
    const err = new Error(`服务器 ${STREAM_IDLE_TIMEOUT_MS / 1000}s 无响应，已断开（可重试）`) as StreamError
    err.status = 504
    onError(err)
    xhr.abort()
  })

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

  xhr.onprogress = () => {
    watchdog.touch()
    processLines()
  }
  xhr.onload = function () {
    watchdog.cancel()
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
      onError(parseHttpError(xhr.status, xhr.responseText))
    }
  }
  xhr.onerror = function () {
    if (finished) return
    finished = true
    watchdog.cancel()
    onError(new Error('Network error') as StreamError)
  }
  xhr.onabort = function () {
    if (finished) return
    finished = true
    watchdog.cancel()
    const err = new Error('Request aborted') as StreamError
    err.isAbort = true
    onError(err)
  }

  watchdog.touch()
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
  attach = false,
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
    watchdog.cancel()
    onDone()
  }

  const watchdog = makeIdleWatchdog(() => {
    if (finished) return
    finished = true
    const err = new Error(`服务器 ${STREAM_IDLE_TIMEOUT_MS / 1000}s 无响应，已断开（可重试）`) as StreamError
    err.status = 504
    onError(err, fullContent)
    xhr.abort()
  })

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
        if (obj.stopped) { finish(); return }
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
    watchdog.touch()
    processLines()
  }

  xhr.onload = function () {
    watchdog.cancel()
    if (xhr.status >= 200 && xhr.status < 300) {
      if (pending.trim()) {
        try {
          const obj = JSON.parse(pending.trim())
          if (obj.done) { finish(); return }
          if (obj.stopped) { finish(); return }
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
      onError(parseHttpError(xhr.status, xhr.responseText), fullContent)
    }
  }

  xhr.onerror = function () {
    if (finished) return
    finished = true
    watchdog.cancel()
    onError(new Error('Network error') as StreamError, fullContent)
  }
  xhr.onabort = function () {
    if (finished) return
    finished = true
    watchdog.cancel()
    const err = new Error('Request aborted') as StreamError
    err.isAbort = true
    onError(err, fullContent)
  }

  watchdog.touch()
  xhr.send(JSON.stringify({ content, assistant_id: assistantId || '', regenerate, attach }))

  // 生成在服务端后台运行；abort 只断开本地订阅，stopChatStream 才真正停止
  return function abort() { xhr.abort() }
}

/** 停止服务端后台聊天生成（已生成部分保留） */
export function stopChatStream(conversationId: ID): Promise<{ ok: boolean; stopped: boolean }> {
  return request('POST', `/conversations/${conversationId}/chat/stop`)
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

export interface WriteChapterMeta {
  chapter_number?: number
  chapter_title?: string
  plan?: string
  message?: string
}

export interface WriteChapterDone {
  item_id?: ID
  chapter_number?: number
  chapter_title?: string
  word_count?: number
}

export interface WriteChapterEvents {
  onPhase: (meta: WriteChapterMeta) => void
  onChunk: (text: string) => void
  onThinking?: (text: string) => void
  onDone: (info: WriteChapterDone) => void
  onError: (err: StreamError, partialContent: string) => void
}

/** 一键写下一章：NDJSON 流（章纲阶段 phase → 正文 content → done） */
export function streamWriteChapter(
  projectId: ID,
  opts: { user_hint?: string; regenerate?: boolean; fast?: boolean; chapter?: number },
  events: WriteChapterEvents,
): StreamAbort {
  const xhr = new XMLHttpRequest()
  xhr.open('POST', `${BASE}/projects/${projectId}/chapters/write-stream`)
  xhr.setRequestHeader('Content-Type', 'application/json')

  let processed = 0
  let pending = ''
  let fullContent = ''
  let finished = false
  let doneInfo: WriteChapterDone = {}

  const finish = () => {
    if (finished) return
    finished = true
    watchdog.cancel()
    onDoneSafe()
  }

  const watchdog = makeIdleWatchdog(() => {
    if (finished) return
    finished = true
    const err = new Error('生成仍在进行（网关为整包返回，精细模式一章可达数分钟），请耐心等待') as StreamError
    err.status = 504
    events.onError(err, fullContent)
    xhr.abort()
  }, 600_000)

  function onDoneSafe() {
    // 流可能在 done 行之后还有 onload 触发，只回调一次由 finished 保证
    events.onDone(doneInfo)
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
        if (obj.done) {
          doneInfo = {
            item_id: obj.item_id,
            chapter_number: obj.chapter_number,
            chapter_title: obj.chapter_title,
            word_count: obj.word_count,
          }
          finish()
          return
        }
        if (obj.error) {
          if (!finished) {
            finished = true
            watchdog.cancel()
            events.onError(new Error(obj.error) as StreamError, fullContent)
          }
          return
        }
        if (obj.phase) events.onPhase(obj)
        if (obj.thinking) events.onThinking?.(obj.thinking)
        if (obj.content) {
          fullContent += obj.content
          events.onChunk(obj.content)
        }
      } catch {
        // partial JSON
      }
    }
  }

  xhr.onprogress = () => {
    if (finished) return
    watchdog.touch()
    processLines()
  }

  xhr.onload = () => {
    watchdog.cancel()
    if (xhr.status >= 200 && xhr.status < 300) {
      if (pending.trim() && !finished) processLines()
      finish()
    } else {
      if (finished) return
      finished = true
      events.onError(parseHttpError(xhr.status, xhr.responseText), fullContent)
    }
  }

  xhr.onerror = () => {
    if (finished) return
    finished = true
    watchdog.cancel()
    events.onError(new Error('Network error') as StreamError, fullContent)
  }

  xhr.onabort = () => {
    if (finished) return
    finished = true
    watchdog.cancel()
    const err = new Error('Request aborted') as StreamError
    err.isAbort = true
    events.onError(err, fullContent)
  }

  watchdog.touch()
  xhr.send(JSON.stringify({ user_hint: opts.user_hint || '', regenerate: !!opts.regenerate, fast: !!opts.fast, chapter: opts.chapter ?? null }))

  return function abort() { xhr.abort() }
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

export function getKgGraph(projectId: ID, chapter?: number, layers?: string[]): Promise<KgGraph> {
  const params = new URLSearchParams()
  if (chapter !== undefined) params.set('chapter', String(chapter))
  if (layers && layers.length) params.set('layers', layers.join(','))
  const qs = params.toString()
  return request<KgGraph>('GET', `/projects/${projectId}/kg/graph${qs ? '?' + qs : ''}`)
}

export function listKgEntities(projectId: ID, type?: string, layer?: string): Promise<KgEntity[]> {
  const params = new URLSearchParams()
  if (type) params.set('type', type)
  if (layer) params.set('layer', layer)
  const qs = params.toString()
  return request<KgEntity[]>('GET', `/projects/${projectId}/kg/entities${qs ? '?' + qs : ''}`)
}

export function createKgEntity(projectId: ID, data: KgEntityInput): Promise<KgEntity> {
  return request<KgEntity>('POST', `/projects/${projectId}/kg/entities`, data)
}

export function updateKgEntity(entityId: ID, data: Partial<KgEntityInput>): Promise<KgEntity> {
  return request<KgEntity>('PUT', `/kg/entities/${entityId}`, data)
}

export async function deleteKgEntity(entityId: ID): Promise<void> {
  await request<void>('DELETE', `/kg/entities/${entityId}`)
}

export function createKgRelation(projectId: ID, data: KgRelationInput): Promise<unknown> {
  return request('POST', `/projects/${projectId}/kg/relations`, data)
}

export async function deleteKgRelation(relationId: ID): Promise<void> {
  await request<void>('DELETE', `/kg/relations/${relationId}`)
}

export function extractKg(projectId: ID, data: { text?: string; conversation_id?: string; message_limit?: number }): Promise<KgExtractResult> {
  return request<KgExtractResult>('POST', `/projects/${projectId}/kg/extract`, data)
}

export function extractKgFromItem(projectId: ID, itemId: ID): Promise<KgExtractResult> {
  return request<KgExtractResult>('POST', `/projects/${projectId}/kg/extract-item/${itemId}`)
}

export function startGoal(projectId: ID, description: string): Promise<GoalState> {
  return request<GoalState>('POST', `/projects/${projectId}/goal/start`, { description })
}

export function getGoal(projectId: ID, goalId: ID): Promise<GoalState> {
  return request<GoalState>('GET', `/projects/${projectId}/goal/${goalId}`)
}

export function confirmGoalPlan(projectId: ID, goalId: ID, steps?: GoalStep[]): Promise<GoalState> {
  return request<GoalState>('POST', `/projects/${projectId}/goal/${goalId}/confirm-plan`, { steps })
}

export function executeGoalStep(projectId: ID, goalId: ID, stepIndex: number, userInput?: string): Promise<GoalState> {
  return request<GoalState>('POST', `/projects/${projectId}/goal/${goalId}/execute-step`, { step_index: stepIndex, user_input: userInput || '' })
}

export function skipGoalStep(projectId: ID, goalId: ID, stepIndex: number): Promise<GoalState> {
  return request<GoalState>('POST', `/projects/${projectId}/goal/${goalId}/skip`, { step_index: stepIndex })
}

export function cancelGoal(projectId: ID, goalId: ID): Promise<GoalState> {
  return request<GoalState>('POST', `/projects/${projectId}/goal/${goalId}/cancel`)
}

export interface LintIssue {
  severity: 'error' | 'warning' | 'info'
  category: string
  description: string
  location: string
  suggestion: string
}

export interface LintResult {
  issues: LintIssue[]
  summary: string
  consistency_score: number
  error?: string
}

export function lintProject(projectId: ID): Promise<LintResult> {
  return request<LintResult>('POST', `/projects/${projectId}/lint`)
}

export interface WritingStatus {
  batch?: BatchInfo | null
  in_progress: boolean
  current_chapter?: number
  current_title?: string
  fast?: boolean
  chapters: number
  max_chapter?: number
  total_words: number
}

export function getWritingStatus(projectId: ID): Promise<WritingStatus> {
  return request<WritingStatus>('GET', `/projects/${projectId}/writing/status`)
}

export interface StoryWebChapter {
  chapter: number; title: string; words: number; types: string[]; plot: string; emotion: string
}
export interface StoryWebThread {
  kind: string; name: string; chapters: number[]
  setup_ch?: number | null; payoff_chs?: number[]
}
export interface StoryWeb {
  chapters: StoryWebChapter[]
  threads: StoryWebThread[]
  missing_web: number
}
export function getStoryWeb(projectId: ID): Promise<StoryWeb> {
  return request<StoryWeb>('GET', `/projects/${projectId}/story-web`)
}
export function backfillStoryWeb(projectId: ID, limit: number): Promise<{ updated: number; remaining: number }> {
  return request('POST', `/projects/${projectId}/story-web/backfill`, { limit })
}

export interface WritingLive {
  in_progress: boolean
  chapter?: number
  title?: string
  fast?: boolean
  thinking_tail?: string
  content?: string
  words?: number
}

export function getWritingLive(projectId: ID): Promise<WritingLive> {
  return request<WritingLive>('GET', `/projects/${projectId}/writing/live`)
}

export interface WritingTaskDeficient { chapter: number; title: string; words: number; target: number }
export interface WritingTasks {
  volume: { target: number; done: number; total_words: number }
  deficient: WritingTaskDeficient[]
  missing_web: number
  empty_draft_chapters: number[]
}
export function getWritingTasks(projectId: ID): Promise<WritingTasks> {
  return request<WritingTasks>('GET', `/projects/${projectId}/writing/tasks`)
}

export interface BatchInfo {
  active: boolean; target: number; done: number; paused: boolean
  awaiting_review: boolean; hint: string; fast: boolean; last_error?: string | null
}
export function startWritingBatch(projectId: ID, body: { target: number; hint?: string; fast?: boolean; pause_each?: boolean }): Promise<BatchInfo & { ok: boolean }> {
  return request('POST', `/projects/${projectId}/writing/batch`, body)
}
export function controlWritingBatch(projectId: ID, action: 'pause' | 'resume' | 'stop'): Promise<BatchInfo & { ok: boolean }> {
  return request('POST', `/projects/${projectId}/writing/batch/control`, { action })
}

export interface VolumeEntry {
  vol: number; name: string; chapters: string; premise: string
  core_conflict: string; key_nodes: string[]; climax: string; hook_to_next: string
}
export interface VolumeOutline {
  exists: boolean; volumes: VolumeEntry[]; total_chapters?: number; content?: string
}
export function getVolumeOutline(projectId: ID): Promise<VolumeOutline> {
  return request<VolumeOutline>('GET', `/projects/${projectId}/volume-outline`)
}
export function generateVolumeOutline(projectId: ID): Promise<{ volumes: VolumeEntry[]; total_chapters?: number }> {
  return request('POST', `/projects/${projectId}/volume-outline/generate`)
}

export function ensureStudioConversation(projectId: ID): Promise<{ conversation_id: ID }> {
  return request('POST', `/projects/${projectId}/studio/ensure`)
}

export interface StudioBuildResult {
  ok: boolean
  generated: { point: string; label: string; chars: number }[]
  skipped: string[]
  errors: string[]
}

export interface StudioDistillResult {
  ok: boolean
  applied: { point: string; label: string; action: string; note: string; chars: number }[]
  leftover: string
  message: string
}

export function studioBuild(projectId: ID): Promise<StudioBuildResult> {
  return request('POST', `/projects/${projectId}/studio/build`)
}

/** 语音转写加标点（只加标点不改字，失败原样返回） */
export function punctuate(text: string): Promise<{ text: string }> {
  return request('POST', `/punctuate`, { text })
}

export function studioDistill(projectId: ID): Promise<StudioDistillResult> {
  return request('POST', `/projects/${projectId}/studio/distill`)
}

/** 大纲语音对话 → 生成倒推+正向大纲草稿 */
export function outlineDistill(projectId: ID): Promise<StudioBuildResult> {
  return request('POST', `/projects/${projectId}/outline-studio/distill`)
}
