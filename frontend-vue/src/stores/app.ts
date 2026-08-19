import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '../api'
import { propertyLabel } from '../utils/format'
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
  PointInfo,
  PointsData,
  ConsultRecord,
  ConsultLeader,
  ConsultEntry,
  ConsultRound,
  ConsultEvent,
  StreamAbort,
  StreamError,
  ChatChunkType,
  ID,
  KgGraph,
  KgEntityInput,
  KgRelationInput,
  KgKnowledgeLayer,
  GoalState,
  GoalStep,
} from '../types'

let _navToken = 0
let _convToken = 0
let _kgToken = 0
let _loadingPoint: string | null = null

const ASSISTANT_KEY_PREFIX = 'fa_assistant_'

interface NavPatch {
  route?: string
  currentProjectId?: ID
  currentConversationId?: ID | null
  currentPoint?: string | null
  messages?: Message[]
  streamingContent?: string
  streamingThinking?: string
  isStreaming?: boolean
  consultFlow?: ConsultRecord | null
  workspaceItems?: WorkspaceItem[]
  chronicle?: Chronicle | null
  points?: PointInfo[]
  currentAssistantId?: string
}

interface ConsultFlowState {
  leader: ConsultLeader | null
  rounds: ConsultRound[]
  summary: string
  summaryThinking: string
  pending: string
}

export const useAppStore = defineStore('app', () => {
  const route = ref<string>('projects')
  const currentProjectId = ref<ID | null>(null)

  const projects = ref<Project[]>([])

  const currentProject = computed<Project | null>(() =>
    projects.value.find(p => p.id === currentProjectId.value) ?? null
  )

  const conversations = ref<Conversation[]>([])
  const currentConversationId = ref<ID | null>(null)
  const messages = ref<Message[]>([])
  const streamingContent = ref<string>('')
  const streamingThinking = ref<string>('')
  const isStreaming = ref<boolean>(false)
  const consultFlow = ref<ConsultRecord | null>(null)

  const points = ref<PointInfo[]>([])
  const currentPoint = ref<string | null>(null)
  const activeMode = ref<'point' | 'free'>('point')

  const isSummarizing = ref<boolean>(false)
  const isArchiving = ref<boolean>(false)

  const assistants = ref<Assistant[]>([])
  const currentAssistantId = ref<ID | ''>('')

  const workspaceItems = ref<WorkspaceItem[]>([])

  // ===== 小说写作（中央区视图 + 流式写章状态） =====
  const centerView = ref<'chat' | 'writing'>('chat')
  const isWritingChapter = ref(false)
  const writingPhase = ref('')
  const writingContent = ref('')
  const writingChapterNumber = ref<number | null>(null)
  const writingChapterTitle = ref('')
  let writingAbort: (() => void) | null = null

  const chapters = computed(() =>
    workspaceItems.value
      .filter(i => i.item_type === 'chapter')
      .sort((a, b) => (a.chapter_number || 0) - (b.chapter_number || 0)),
  )
  const totalChapterWords = computed(() =>
    chapters.value.reduce((sum, c) => sum + (c.content?.length || 0), 0),
  )

  const chronicle = ref<Chronicle | null>(null)

  const kgGraph = ref<KgGraph>({ entities: [], relations: [] })
  const kgLoading = ref<boolean>(false)

  const goalState = ref<GoalState | null>(null)
  const goalLoading = ref<boolean>(false)

  const lintResult = ref<import('../api').LintResult | null>(null)
  const lintLoading = ref<boolean>(false)

  const error = ref<string | null>(null)
  const success = ref<string | null>(null)
  const messagesLoading = ref<boolean>(false)

  let _successTimer: ReturnType<typeof setTimeout> | null = null
  /** 操作成功反馈（3s 自动消失），由 ToastHost 展示 */
  function notifySuccess(msg: string) {
    success.value = msg
    if (_successTimer) clearTimeout(_successTimer)
    _successTimer = setTimeout(() => { success.value = null }, 3000)
  }

  const _currentAbort = ref<StreamAbort | null>(null)

  function _finalizeStream(keepPartial: boolean) {
    const abort = _currentAbort.value
    _currentAbort.value = null
    if (abort) abort()
    if (keepPartial && streamingContent.value.trim()) {
      messages.value = [...messages.value, {
        role: 'assistant',
        content: streamingContent.value + '\n\n[已手动停止]',
        thinking: streamingThinking.value || undefined,
      }]
    }
    streamingContent.value = ''
    streamingThinking.value = ''
    consultFlow.value = null
    isStreaming.value = false
  }

  /** 离开对话/页面时中断流式请求（丢弃部分输出）。 */
  function _abortCurrentStream() {
    if (_currentAbort.value || isStreaming.value) _finalizeStream(false)
  }

  /** 用户主动停止生成：保留已生成的部分内容。 */
  function stopStreaming() {
    _finalizeStream(true)
  }

  async function deleteProject(projectId: ID) {
    try {
      await api.deleteProject(projectId)
      projects.value = projects.value.filter(p => p.id !== projectId)
      error.value = null
      if (currentProjectId.value === projectId) {
        _abortCurrentStream()
        route.value = 'projects'
        currentProjectId.value = null
        conversations.value = []
        currentConversationId.value = null
        messages.value = []
        points.value = []
        workspaceItems.value = []
        currentPoint.value = null
      }
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function fetchProjects() {
    try {
      projects.value = await api.listProjects()
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function createProject(name: string, genre?: string, rulesText?: string) {
    try {
      const data: { name: string; genre?: string; rules_text?: string } = { name }
      if (genre) data.genre = genre
      if (rulesText) data.rules_text = rulesText
      const project = await api.createProject(data)
      projects.value = [project, ...projects.value]
      error.value = null
      return project
    } catch (e) {
      error.value = (e as Error).message
      return null
    }
  }

  async function renameProject(projectId: ID, name: string) {
    try {
      const updated = await api.updateProject(projectId, { name })
      projects.value = projects.value.map(p => p.id === updated.id ? updated : p)
      error.value = null
      notifySuccess('已重命名')
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function updateProjectRules(rulesText: string) {
    if (!currentProjectId.value) return
    try {
      const updated = await api.updateProject(currentProjectId.value, { rules_text: rulesText })
      projects.value = projects.value.map(p => p.id === updated.id ? updated : p)
      error.value = null
      notifySuccess('创作守则已保存')
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function fetchConversations(projectId: ID) {
    try {
      conversations.value = await api.listConversations(projectId)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function createConversation(projectId: ID, title: string) {
    try {
      const conversation = await api.createConversation(projectId, title)
      conversations.value = [conversation, ...conversations.value]
      currentConversationId.value = conversation.id
      messages.value = []
      activeMode.value = 'free'
      centerView.value = 'chat'
      currentPoint.value = null
      error.value = null
      return conversation
    } catch (e) {
      error.value = (e as Error).message
      return null
    }
  }

  async function selectConversation(conversationId: ID) {
    _abortCurrentStream()
    const token = ++_convToken
    currentConversationId.value = conversationId
    activeMode.value = 'free'
    centerView.value = 'chat'  // 从写作视图切回对话
    currentPoint.value = null
    consultFlow.value = null
    streamingContent.value = ''
    streamingThinking.value = ''
    messagesLoading.value = true
    try {
      const msgs = await api.getMessages(conversationId)
      if (token !== _convToken) return
      messages.value = msgs
      error.value = null
    } catch (e) {
      if (token !== _convToken) return
      error.value = (e as Error).message
    } finally {
      if (token === _convToken) messagesLoading.value = false
    }
  }

  async function deleteConversation(conversationId: ID) {
    try {
      await api.deleteConversation(conversationId)
      conversations.value = conversations.value.filter(c => c.id !== conversationId)
      error.value = null
      if (currentConversationId.value === conversationId) {
        currentConversationId.value = null
        messages.value = []
        streamingContent.value = ''
        isStreaming.value = false
      }
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function deleteMessage(messageId: ID) {
    try {
      await api.deleteMessage(messageId)
      messages.value = messages.value.filter(m => m.id !== messageId)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function renameConversation(conversationId: ID, title: string) {
    try {
      await api.renameConversation(conversationId, title)
      conversations.value = conversations.value.map(c => c.id === conversationId ? { ...c, title } : c)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function fetchMessages(conversationId: ID) {
    try {
      messages.value = await api.getMessages(conversationId)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  function _requestReply(conversationId: ID, content: string, baseMessages: Message[], regenerate = false) {
    _abortCurrentStream()

    let fullContent = ''
    let thinkingContent = ''
    const assistantId = currentAssistantId.value
    const targetConvId = conversationId

    isStreaming.value = true
    streamingContent.value = ''
    streamingThinking.value = ''

    // 流式节流：chunk 高频到达时按固定间隔刷新响应式状态，避免每 chunk 全量重渲染
    const FLUSH_INTERVAL = 80
    let flushTimer: ReturnType<typeof setTimeout> | null = null
    let latestThinking = ''
    let latestContent = ''
    const flush = () => {
      flushTimer = null
      streamingThinking.value = latestThinking
      streamingContent.value = latestContent
    }
    const scheduleFlush = () => {
      if (flushTimer == null) flushTimer = setTimeout(flush, FLUSH_INTERVAL)
    }
    const flushNow = () => {
      if (flushTimer != null) { clearTimeout(flushTimer); flushTimer = null }
      flush()
    }

    const abort = api.streamChat(
      conversationId,
      content,
      (chunk: string, type?: ChatChunkType) => {
        if (currentConversationId.value !== targetConvId) return
        if (type === 'thinking') {
          thinkingContent += chunk
          latestThinking = thinkingContent
        } else {
          fullContent += chunk
          latestContent = fullContent
          latestThinking = thinkingContent
        }
        scheduleFlush()
      },
      () => {
        _currentAbort.value = null
        flushNow()
        if (currentConversationId.value !== targetConvId) {
          isStreaming.value = false
          streamingContent.value = ''
          streamingThinking.value = ''
          return
        }
        messages.value = [...baseMessages, { role: 'assistant', content: fullContent, thinking: thinkingContent || undefined }]
        streamingContent.value = ''
        streamingThinking.value = ''
        isStreaming.value = false
        // 静默刷新：拿回服务端消息 id / created_at（时间戳、字数、稳定 key 都依赖它），
        // 同时保留本地思考链（服务端不存 thinking）
        void (async () => {
          try {
            const msgs = await api.getMessages(targetConvId)
            if (currentConversationId.value !== targetConvId) return
            const localThinking = messages.value.map(m => m.thinking)
            messages.value = msgs.map((m, i) => (localThinking[i] ? { ...m, thinking: localThinking[i] } : m))
          } catch { /* 刷新失败保持乐观消息即可 */ }
        })()
      },
      (err: StreamError, partialContent: string) => {
        _currentAbort.value = null
        if (err.isAbort) {
          if (currentConversationId.value !== targetConvId) {
            isStreaming.value = false
            streamingContent.value = ''
            streamingThinking.value = ''
          }
          return
        }
        console.error('[sendMessage] stream error:', err)
        flushNow()
        const finalContent = partialContent || fullContent
        const newMessages: Message[] = finalContent
          ? [...baseMessages, { role: 'assistant', content: finalContent + '\n\n[生成中断]', thinking: thinkingContent || undefined }]
          : baseMessages
        if (currentConversationId.value !== targetConvId) {
          isStreaming.value = false
          streamingContent.value = ''
          streamingThinking.value = ''
          return
        }
        messages.value = newMessages
        isStreaming.value = false
        streamingContent.value = ''
        streamingThinking.value = ''
        error.value = err.message
      },
      assistantId,
      regenerate,
    )

    _currentAbort.value = abort
  }

  function sendMessage(conversationId: ID, content: string) {
    const userMsg: Message = { role: 'user', content }
    const newMessages = [...messages.value, userMsg]
    messages.value = newMessages
    error.value = null
    _requestReply(conversationId, content, newMessages)
  }

  function regenerateMessage(conversationId: ID) {
    const msgs = messages.value
    if (msgs.length === 0) return
    const lastIdx = msgs.length - 1
    if (msgs[lastIdx].role !== 'assistant') return
    const userMsg = msgs[lastIdx - 1]
    if (!userMsg || userMsg.role !== 'user') return
    const trimmed = msgs.slice(0, lastIdx)
    messages.value = trimmed
    _requestReply(conversationId, userMsg.content, trimmed, true)
  }

  async function fetchWorkspaceItems(projectId: ID) {
    try {
      workspaceItems.value = await api.listWorkspaceItems(projectId)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  // ===== 连续写作（Copilot 式）：自然语言目标 → 逐章生成 → 按章审阅 =====
  const batchWriting = ref(false)
  const batchTarget = ref(0)
  const batchDone = ref(0)
  const batchHint = ref('')
  const batchPauseForReview = ref(true)
  const batchPaused = ref(false)   // 每章完成后暂停，等用户审阅
  const batchStopping = ref(false)
  let _resumeResolve: (() => void) | null = null
  let _batchAbort = false

  async function startBatchWriting(projectId: ID, target: number, hint: string, pauseForReview: boolean, fast = false) {
    if (batchWriting.value || isWritingChapter.value) return
    _batchAbort = false
    batchWriting.value = true
    batchTarget.value = target
    batchDone.value = 0
    batchHint.value = hint
    batchPauseForReview.value = pauseForReview
    centerView.value = 'writing'
    for (let i = 0; i < target; i++) {
      if (_batchAbort) break
      const ok = await writeNextChapter(projectId, false, hint, fast)
      if (!ok) break
      batchDone.value = i + 1
      if (pauseForReview && i < target - 1 && !_batchAbort) {
        batchPaused.value = true
        await new Promise<void>(r => { _resumeResolve = r })
        batchPaused.value = false
      }
    }
    batchWriting.value = false
    batchPaused.value = false
    if (!_batchAbort && batchDone.value >= target) notifySuccess(`目标达成：已连续完成 ${target} 章`)
  }

  function resumeBatch() {
    batchPaused.value = false
    _resumeResolve?.()
    _resumeResolve = null
  }

  function stopBatchWriting() {
    _batchAbort = true
    stopWritingChapter()
    batchPaused.value = false
    _resumeResolve?.()
    _resumeResolve = null
  }

  // ===== 侧栏折叠（Notion 式：图标栏 + Ctrl+\ 快捷键 + 状态记忆） =====
  const sidebarCollapsed = ref(localStorage.getItem('fa_sidebar_collapsed') === '1')

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
    localStorage.setItem('fa_sidebar_collapsed', sidebarCollapsed.value ? '1' : '0')
  }

  /** 进入项目时用的模式：记住每本书上次所在（骨架工作台/小说创作） */
  function lastProjectMode(pid: ID): 'workspace' | 'writing' {
    return localStorage.getItem('fa_mode_' + pid) === 'writing' ? 'writing' : 'workspace'
  }

  function openProject(pid: ID) {
    navigateTo(lastProjectMode(pid), { currentProjectId: pid })
  }

  function openWriting() {
    // 小说写作已独立为一级页面（骨架定稿后写作是主战场）
    if (currentProjectId.value) {
      navigateTo('writing', { currentProjectId: currentProjectId.value })
      return
    }
    centerView.value = centerView.value === 'writing' ? 'chat' : 'writing'
  }

  function stopWritingChapter() {
    writingAbort?.()
  }

  function writeNextChapter(projectId: ID, regenerate = false, hint = '', fast = false): Promise<boolean> {
    if (isWritingChapter.value) return Promise.resolve(false)
    return new Promise(resolve => {
      _writeRun(projectId, regenerate, hint, fast, resolve)
    })
  }

  async function _writeRun(projectId: ID, regenerate: boolean, hint: string, fast: boolean, done: (ok: boolean) => void) {
    isWritingChapter.value = true
    writingContent.value = ''
    writingChapterNumber.value = null
    writingChapterTitle.value = ''
    writingPhase.value = regenerate ? '正在准备重写本章…' : '正在准备写作…'
    centerView.value = 'writing'
    writingAbort = api.streamWriteChapter(projectId, { user_hint: hint, regenerate, fast }, {
      onPhase: meta => {
        writingPhase.value = meta.message || ''
        if (meta.chapter_number) writingChapterNumber.value = meta.chapter_number
        if (meta.chapter_title) writingChapterTitle.value = meta.chapter_title
      },
      onChunk: text => {
        writingPhase.value = ''
        writingContent.value += text
      },
      onDone: async () => {
        isWritingChapter.value = false
        writingPhase.value = ''
        notifySuccess('本章已完成并存档，编年史已更新')
        await fetchWorkspaceItems(projectId)
        await fetchKgGraph(projectId).catch(() => {})
        done(true)
      },
      onError: (err, partial) => {
        isWritingChapter.value = false
        writingPhase.value = ''
        if (err.isAbort) {
          notifySuccess('已停止（已有内容保留为草稿）')
        } else {
          error.value = `章节生成失败：${err.message}`
        }
        if (partial) fetchWorkspaceItems(projectId)
        done(false)
      },
    })
  }

  async function createWorkspaceItem(projectId: ID, data: WorkspaceItemInput) {
    try {
      await api.createWorkspaceItem(projectId, data)
      await fetchWorkspaceItems(projectId)
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function updateItemStatus(itemId: ID, status: WorkspaceItemStatus, projectId: ID) {
    try {
      await api.updateItemStatus(itemId, status)
      await fetchWorkspaceItems(projectId)
      if (status === 'finalized') {
        await fetchChronicle(projectId)
        notifySuccess('已定稿')
      } else if (status === 'locked') {
        notifySuccess('已锁定')
      } else {
        notifySuccess('已解锁为草稿')
      }
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function deleteWorkspaceItem(itemId: ID, projectId: ID) {
    try {
      await api.deleteWorkspaceItem(itemId)
      await fetchWorkspaceItems(projectId)
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function updateWorkspaceItem(itemId: ID, data: WorkspaceItemInput) {
    try {
      await api.updateWorkspaceItem(itemId, data)
      if (currentProjectId.value) {
        await fetchWorkspaceItems(currentProjectId.value)
      }
      error.value = null
      notifySuccess('已保存')
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function fetchChronicle(projectId: ID) {
    try {
      chronicle.value = await api.getChronicle(projectId)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function fetchKgGraph(projectId: ID, chapter?: number, layers?: KgKnowledgeLayer[]) {
    const token = ++_kgToken
    kgLoading.value = true
    try {
      const graph = await api.getKgGraph(projectId, chapter, layers)
      if (token !== _kgToken) return  // 过期响应（用户已继续滑动）直接丢弃
      kgGraph.value = graph
      error.value = null
    } catch (e) {
      if (token !== _kgToken) return
      error.value = (e as Error).message
    } finally {
      if (token === _kgToken) kgLoading.value = false
    }
  }

  async function startGoal(projectId: ID, description: string) {
    goalLoading.value = true
    error.value = null
    try {
      goalState.value = await api.startGoal(projectId, description)
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      goalLoading.value = false
    }
  }

  async function confirmGoalPlan(projectId: ID, goalId: ID, steps?: GoalStep[]) {
    goalLoading.value = true
    try {
      goalState.value = await api.confirmGoalPlan(projectId, goalId, steps)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      goalLoading.value = false
    }
  }

  async function executeGoalStep(projectId: ID, goalId: ID, stepIndex: number, userInput?: string) {
    goalLoading.value = true
    try {
      goalState.value = await api.executeGoalStep(projectId, goalId, stepIndex, userInput)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      goalLoading.value = false
    }
  }

  async function skipGoalStep(projectId: ID, goalId: ID, stepIndex: number) {
    goalLoading.value = true
    try {
      goalState.value = await api.skipGoalStep(projectId, goalId, stepIndex)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      goalLoading.value = false
    }
  }

  async function cancelGoal(projectId: ID, goalId: ID) {
    goalLoading.value = true
    try {
      goalState.value = await api.cancelGoal(projectId, goalId)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      goalLoading.value = false
    }
  }

  function clearGoal() {
    goalState.value = null
  }

  async function runLint(projectId: ID) {
    lintLoading.value = true
    error.value = null
    try {
      lintResult.value = await api.lintProject(projectId)
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      lintLoading.value = false
    }
  }

  function clearLint() {
    lintResult.value = null
  }

  async function createKgEntity(projectId: ID, data: KgEntityInput) {
    try {
      await api.createKgEntity(projectId, data)
      await fetchKgGraph(projectId)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function updateKgEntity(projectId: ID, entityId: ID, data: Partial<KgEntityInput>) {
    try {
      await api.updateKgEntity(entityId, data)
      await fetchKgGraph(projectId)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function deleteKgEntity(projectId: ID, entityId: ID) {
    try {
      await api.deleteKgEntity(entityId)
      await fetchKgGraph(projectId)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function createKgRelation(projectId: ID, data: KgRelationInput) {
    try {
      await api.createKgRelation(projectId, data)
      await fetchKgGraph(projectId)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function deleteKgRelation(projectId: ID, relationId: ID) {
    try {
      await api.deleteKgRelation(relationId)
      await fetchKgGraph(projectId)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function extractKg(projectId: ID, opts: { text?: string; conversation_id?: string; message_limit?: number } = {}) {
    kgLoading.value = true
    try {
      const result = await api.extractKg(projectId, opts)
      await fetchKgGraph(projectId)
      error.value = null
      if (result?.stats) {
        const s = result.stats
        notifySuccess(`提取完成：新增 ${s.entities_new || 0} 实体 / ${s.relations_new || 0} 关系`)
      }
      return result
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      kgLoading.value = false
    }
  }

  async function extractKgFromItem(projectId: ID, itemId: ID) {
    kgLoading.value = true
    try {
      const result = await api.extractKgFromItem(projectId, itemId)
      await fetchKgGraph(projectId)
      error.value = null
      return result
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      kgLoading.value = false
    }
  }

  async function fetchPoints(projectId: ID) {
    try {
      const data: PointsData = await api.getPoints(projectId)
      points.value = data.points || []
      error.value = null
      return data
    } catch (e) {
      error.value = (e as Error).message
      return null
    }
  }

  async function selectPoint(projectId: ID, point: string) {
    if (_loadingPoint === point && currentPoint.value === point) return
    _loadingPoint = point
    _abortCurrentStream()
    const token = ++_convToken
    currentPoint.value = point
    activeMode.value = 'point'
    centerView.value = 'chat'  // 从写作视图切回对话
    currentConversationId.value = null
    messages.value = []
    consultFlow.value = null
    streamingContent.value = ''
    streamingThinking.value = ''
    messagesLoading.value = true
    try {
      const r = await api.ensurePointConversation(projectId, point)
      if (token !== _convToken) { _loadingPoint = null; return }
      currentConversationId.value = r.conversation_id
      messages.value = r.messages || []
      error.value = null
    } catch (e) {
      if (token !== _convToken) { _loadingPoint = null; return }
      error.value = (e as Error).message
    } finally {
      if (token === _convToken) {
        _loadingPoint = null
        messagesLoading.value = false
      }
    }
  }

  async function summarizeAndArchive(projectId: ID, point: string) {
    if (!currentConversationId.value) return null
    isArchiving.value = true
    try {
      const r = await api.summarizePoint(projectId, point, currentConversationId.value)
      await Promise.allSettled([
        fetchPoints(projectId),
        fetchWorkspaceItems(projectId),
        fetchProjects(),  // 故事核可能触发 AI 自动命名，刷新项目名
      ])
      isArchiving.value = false
      error.value = null
      notifySuccess('点位已总结并存档')
      return r
    } catch (e) {
      isArchiving.value = false
      error.value = (e as Error).message
      return null
    }
  }

  async function goalGenerate(projectId: ID, point: string, idea: string) {
    const targetConvId = currentConversationId.value
    const baseMessages = messages.value
    const userMsg: Message = { role: 'user', content: `/gen ${idea}` }
    messages.value = [...baseMessages, userMsg]
    isStreaming.value = true
    streamingContent.value = ''
    error.value = null
    try {
      const r = await api.autoGeneratePoint(projectId, point, targetConvId || '', idea)
      if (currentConversationId.value !== targetConvId) {
        isStreaming.value = false
        streamingContent.value = ''
        return r
      }
      const fieldsText = r.metadata && Object.keys(r.metadata).length > 0
        ? '\n\n**结构化字段：**\n' + Object.entries(r.metadata).map(([k, v]) => `- **${propertyLabel(k)}**: ${v}`).join('\n')
        : ''
      messages.value = [...baseMessages, userMsg, { role: 'assistant', content: r.content + fieldsText }]
      streamingContent.value = ''
      isStreaming.value = false
      await Promise.allSettled([
        fetchPoints(projectId),
        fetchWorkspaceItems(projectId),
        fetchProjects(),  // 快速生成可能产出书名并触发自动命名
      ])
      if (currentConversationId.value === targetConvId) {
        await fetchMessages(targetConvId as ID)
      }
      return r
    } catch (e) {
      if (currentConversationId.value !== targetConvId) {
        isStreaming.value = false
        streamingContent.value = ''
        return null
      }
      messages.value = [...baseMessages, userMsg, { role: 'assistant', content: `[生成失败] ${(e as Error).message}` }]
      isStreaming.value = false
      streamingContent.value = ''
      error.value = (e as Error).message
      return null
    }
  }

  function expertConsult(projectId: ID, point: string, idea: string) {
    const targetConvId = currentConversationId.value
    const baseMessages = messages.value
    const userMsg: Message = { role: 'user', content: `/consult ${idea}` }

    const flow: ConsultFlowState = { leader: null, rounds: [], summary: '', summaryThinking: '', pending: '🎯 故事核专家（统率者）正在定调...' }
    const entryMap: Record<string, ConsultEntry> = {}

    const findEntry = (round: number, expert: string): ConsultEntry | undefined => entryMap[`${round}-${expert}`]

    const mkFlow = (): ConsultRecord => ({
      kind: 'consult_record',
      leader: flow.leader,
      rounds: flow.rounds.map(r => ({ ...r, entries: r.entries.map(e => ({ ...e })) })),
      summary: flow.summary,
      summaryThinking: flow.summaryThinking,
      pending: flow.pending,
    })

    messages.value = [...baseMessages, userMsg]
    isStreaming.value = true
    consultFlow.value = mkFlow()
    streamingContent.value = ''
    error.value = null

    const abort = api.streamExpertConsult(
      projectId,
      point,
      targetConvId || '',
      idea,
      (event: ConsultEvent) => {
        if (currentConversationId.value !== targetConvId) return
        const ph = event.phase
        if (ph === 'leader_start') {
          flow.leader = { name: event.name, perspective: event.perspective, content: '', thinking: '' }
          flow.pending = '🎯 统率者正在定调...'
          consultFlow.value = mkFlow()
        } else if (ph === 'leader_thinking_chunk') {
          if (flow.leader) flow.leader.thinking = (flow.leader.thinking || '') + event.chunk
          consultFlow.value = mkFlow()
        } else if (ph === 'leader_chunk') {
          if (flow.leader) flow.leader.content += event.chunk
          consultFlow.value = mkFlow()
        } else if (ph === 'leader_done') {
          if (flow.leader) { flow.leader.content = event.content }
          else { flow.leader = { name: event.name || '', perspective: event.perspective || '', content: event.content, thinking: '' } }
          flow.pending = '⏳ 各专家正在响应统率者定调...'
          consultFlow.value = mkFlow()
        } else if (ph === 'round_start') {
          flow.rounds.push({ round: event.round, label: event.round === 1 ? '响应定调' : '交锋', entries: [] })
          flow.pending = `⏳ 第${event.round}轮讨论进行中...`
          consultFlow.value = mkFlow()
        } else if (ph === 'expert_start') {
          const r = flow.rounds.find(x => x.round === event.round)
          if (r) {
            const entry: ConsultEntry = { name: event.name, perspective: event.perspective, content: '', thinking: '', is_leader: !!event.is_leader }
            r.entries.push(entry)
            entryMap[`${event.round}-${event.expert}`] = entry
          }
          consultFlow.value = mkFlow()
        } else if (ph === 'expert_thinking_chunk') {
          const entry = findEntry(event.round, event.expert)
          if (entry) entry.thinking = (entry.thinking || '') + event.chunk
          consultFlow.value = mkFlow()
        } else if (ph === 'expert_chunk') {
          const entry = findEntry(event.round, event.expert)
          if (entry) entry.content += event.chunk
          consultFlow.value = mkFlow()
        } else if (ph === 'expert_done') {
          const entry = findEntry(event.round, event.expert)
          if (entry) entry.content = event.content
          flow.pending = '⏳ 等待更多专家发言...'
          consultFlow.value = mkFlow()
        } else if (ph === 'summary_start') {
          flow.pending = '⏳ 统率者（主线策划）正在做最终裁决...'
          consultFlow.value = mkFlow()
        } else if (ph === 'summary_thinking_chunk') {
          flow.summaryThinking += event.chunk
          consultFlow.value = mkFlow()
        } else if (ph === 'summary_chunk') {
          flow.summary += event.chunk
          consultFlow.value = mkFlow()
        } else if (ph === 'summary') {
          flow.summary = event.content
          const finalFlow = mkFlow()
          if (currentConversationId.value === targetConvId) {
            messages.value = [...baseMessages, userMsg, { role: 'assistant', content: JSON.stringify(finalFlow), consult_kind: 'consult_record' }]
            consultFlow.value = null
            streamingContent.value = ''
            isStreaming.value = false
          }
        } else if (ph === 'saved') {
          fetchPoints(projectId)
          fetchWorkspaceItems(projectId)
          if (currentConversationId.value === targetConvId) {
            fetchMessages(targetConvId as ID)
          }
        }
      },
      () => {
        if (currentConversationId.value !== targetConvId) {
          isStreaming.value = false
          consultFlow.value = null
          streamingContent.value = ''
          return
        }
        if (!flow.summary) {
          const partial = mkFlow()
          messages.value = [...baseMessages, userMsg, { role: 'assistant', content: JSON.stringify({ ...partial, error: '会诊未产出完整结果' }) }]
          consultFlow.value = null
          streamingContent.value = ''
          isStreaming.value = false
        } else {
          consultFlow.value = null
          streamingContent.value = ''
          isStreaming.value = false
        }
      },
      (err: StreamError) => {
        if (err.isAbort) {
          if (currentConversationId.value !== targetConvId) {
            isStreaming.value = false
            streamingContent.value = ''
          }
          return
        }
        if (currentConversationId.value === targetConvId) {
          messages.value = [...baseMessages, userMsg, { role: 'assistant', content: `[会诊失败] ${err.message}` }]
          streamingContent.value = ''
          isStreaming.value = false
          error.value = err.message
        }
      },
    )

    _currentAbort.value = abort
  }

  async function navigateTo(routeVal: string, params: NavPatch = {}) {
    // 丝滑切换：同项目内 工作台⇄写作 只换视图，不重置不重拉（消除割裂感）
    const sameProjectSwitch =
      (routeVal === 'workspace' || routeVal === 'writing') &&
      (route.value === 'workspace' || route.value === 'writing') &&
      (params.currentProjectId ?? currentProjectId.value) === currentProjectId.value &&
      !!currentProjectId.value
    if (sameProjectSwitch) {
      route.value = routeVal
      localStorage.setItem('fa_mode_' + currentProjectId.value, routeVal)
      centerView.value = 'chat'
      return
    }

    _abortCurrentStream()
    writingAbort?.()
    isWritingChapter.value = false
    writingContent.value = ''
    writingPhase.value = ''
    centerView.value = 'chat'
    const token = ++_navToken

    const patch: NavPatch = {
      route: routeVal,
      currentConversationId: null,
      currentPoint: null,
      messages: [],
      streamingContent: '',
      streamingThinking: '',
      isStreaming: false,
      consultFlow: null,
      workspaceItems: [],
      chronicle: null,
      points: [],
      currentAssistantId: '',
      ...params,
    }

    if (patch.route !== undefined) route.value = patch.route
    if (patch.currentProjectId !== undefined) currentProjectId.value = patch.currentProjectId
    if (patch.currentConversationId !== undefined) currentConversationId.value = patch.currentConversationId
    if (patch.currentPoint !== undefined) currentPoint.value = patch.currentPoint
    if (patch.messages !== undefined) messages.value = patch.messages
    if (patch.streamingContent !== undefined) streamingContent.value = patch.streamingContent
    if (patch.streamingThinking !== undefined) streamingThinking.value = patch.streamingThinking
    if (patch.isStreaming !== undefined) isStreaming.value = patch.isStreaming
    if (patch.consultFlow !== undefined) consultFlow.value = patch.consultFlow
    if (patch.workspaceItems !== undefined) workspaceItems.value = patch.workspaceItems
    if (patch.chronicle !== undefined) chronicle.value = patch.chronicle
    if (patch.points !== undefined) points.value = patch.points
    if (patch.currentAssistantId !== undefined) currentAssistantId.value = patch.currentAssistantId

    if ((routeVal === 'workspace' || routeVal === 'writing') && params.currentProjectId) {
      localStorage.setItem('fa_mode_' + params.currentProjectId, routeVal)
      const pid = params.currentProjectId
      await Promise.allSettled([
        fetchConversations(pid),
        fetchWorkspaceItems(pid),
        fetchChronicle(pid),
        fetchAssistants(),
      ])
      if (token !== _navToken) return

      const pointsData = await fetchPoints(pid)
      if (token !== _navToken) return

      const startPoint = pointsData?.current_point || 'story_core'
      await selectPoint(pid, startPoint)
    }
  }

  async function fetchAssistants() {
    try {
      const list = await api.listAssistants()
      // 默认不选择助理（跟随点位角色/默认助手）；仅保留用户主动选择过的
      let chosenId: ID | '' = currentAssistantId.value
      if (!chosenId && currentProjectId.value) {
        chosenId = _getSavedAssistant(currentProjectId.value)
      }
      const valid = chosenId && list.some(a => a.id === chosenId)
      assistants.value = list
      currentAssistantId.value = valid ? chosenId : ''
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  function _getSavedAssistant(projectId: ID): ID | '' {
    try { return localStorage.getItem(ASSISTANT_KEY_PREFIX + projectId) || '' } catch { return '' }
  }

  function _saveAssistant(projectId: ID | null, assistantId: ID | '') {
    if (!projectId) return
    try {
      if (assistantId) localStorage.setItem(ASSISTANT_KEY_PREFIX + projectId, assistantId)
      else localStorage.removeItem(ASSISTANT_KEY_PREFIX + projectId)
    } catch {}
  }

  function selectAssistant(assistantId: ID) {
    currentAssistantId.value = assistantId
    if (currentProjectId.value) {
      _saveAssistant(currentProjectId.value, assistantId)
    }
  }

  async function createAssistant(data: AssistantInput) {
    try {
      const assistant = await api.createAssistant(data)
      assistants.value = [...assistants.value, assistant]
      error.value = null
      return assistant
    } catch (e) {
      error.value = (e as Error).message
      return null
    }
  }

  async function updateAssistant(id: ID, data: AssistantInput) {
    try {
      const updated = await api.updateAssistant(id, data)
      assistants.value = assistants.value.map(a => a.id === id ? updated : a)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  async function deleteAssistant(id: ID) {
    try {
      await api.deleteAssistant(id)
      const list = assistants.value.filter(a => a.id !== id)
      assistants.value = list
      currentAssistantId.value = currentAssistantId.value === id ? (list[0]?.id || '') : currentAssistantId.value
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  return {
    route,
    currentProjectId,
    currentProject,
    projects,
    conversations,
    currentConversationId,
    messages,
    streamingContent,
    streamingThinking,
    isStreaming,
    consultFlow,
    points,
    currentPoint,
    activeMode,
    centerView,
    chapters,
    totalChapterWords,
    isWritingChapter,
    writingPhase,
    writingContent,
    writingChapterNumber,
    writingChapterTitle,
    batchWriting,
    batchTarget,
    batchDone,
    batchHint,
    batchPaused,
    batchPauseForReview,
    startBatchWriting,
    resumeBatch,
    stopBatchWriting,
    sidebarCollapsed,
    lastProjectMode,
    openProject,
    toggleSidebar,
    openWriting,
    stopWritingChapter,
    writeNextChapter,
    isSummarizing,
    isArchiving,
    assistants,
    currentAssistantId,
    workspaceItems,
    chronicle,
    kgGraph,
    kgLoading,
    goalState,
    goalLoading,
    lintResult,
    lintLoading,
    error,
    success,
    messagesLoading,
    notifySuccess,

    deleteProject,
    fetchProjects,
    createProject,
    renameProject,
    updateProjectRules,
    fetchConversations,
    createConversation,
    selectConversation,
    deleteConversation,
    deleteMessage,
    renameConversation,
    fetchMessages,
    sendMessage,
    regenerateMessage,
    stopStreaming,
    fetchWorkspaceItems,
    createWorkspaceItem,
    updateItemStatus,
    deleteWorkspaceItem,
    updateWorkspaceItem,
    fetchChronicle,
    fetchKgGraph,
    createKgEntity,
    updateKgEntity,
    deleteKgEntity,
    createKgRelation,
    deleteKgRelation,
    extractKg,
    extractKgFromItem,
    startGoal,
    confirmGoalPlan,
    executeGoalStep,
    skipGoalStep,
    cancelGoal,
    clearGoal,
    runLint,
    clearLint,
    fetchPoints,
    selectPoint,
    summarizeAndArchive,
    goalGenerate,
    expertConsult,
    navigateTo,
    fetchAssistants,
    selectAssistant,
    createAssistant,
    updateAssistant,
    deleteAssistant,
  }
})
