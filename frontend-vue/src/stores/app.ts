import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '../api'
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
} from '../types'

let _navToken = 0
let _convToken = 0
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

  const chronicle = ref<Chronicle | null>(null)

  const error = ref<string | null>(null)

  const _currentAbort = ref<StreamAbort | null>(null)

  function _abortCurrentStream() {
    if (_currentAbort.value) {
      _currentAbort.value()
      _currentAbort.value = null
    }
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

  async function createProject(name: string, genre?: string) {
    try {
      const data: { name: string; genre?: string } = { name }
      if (genre) data.genre = genre
      const project = await api.createProject(data)
      projects.value = [project, ...projects.value]
      error.value = null
      return project
    } catch (e) {
      error.value = (e as Error).message
      return null
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
    currentPoint.value = null
    consultFlow.value = null
    streamingContent.value = ''
    streamingThinking.value = ''
    try {
      const msgs = await api.getMessages(conversationId)
      if (token !== _convToken) return
      messages.value = msgs
      error.value = null
    } catch (e) {
      if (token !== _convToken) return
      error.value = (e as Error).message
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

    const abort = api.streamChat(
      conversationId,
      content,
      (chunk: string, type?: ChatChunkType) => {
        if (currentConversationId.value !== targetConvId) return
        if (type === 'thinking') {
          thinkingContent += chunk
          streamingThinking.value = thinkingContent
        } else {
          fullContent += chunk
          streamingContent.value = fullContent
          streamingThinking.value = thinkingContent
        }
      },
      () => {
        _currentAbort.value = null
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
    currentConversationId.value = null
    messages.value = []
    consultFlow.value = null
    streamingContent.value = ''
    streamingThinking.value = ''
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
      _loadingPoint = null
    }
  }

  async function summarizeAndArchive(projectId: ID, point: string) {
    if (!currentConversationId.value) return null
    isArchiving.value = true
    try {
      const r = await api.summarizePoint(projectId, point, currentConversationId.value)
      await fetchPoints(projectId)
      await fetchWorkspaceItems(projectId)
      isArchiving.value = false
      error.value = null
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
    const userMsg: Message = { role: 'user', content: `/goal ${idea}` }
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
        ? '\n\n**结构化字段：**\n' + Object.entries(r.metadata).map(([k, v]) => `- **${k}**: ${v}`).join('\n')
        : ''
      messages.value = [...baseMessages, userMsg, { role: 'assistant', content: r.content + fieldsText }]
      streamingContent.value = ''
      isStreaming.value = false
      await fetchPoints(projectId)
      await fetchWorkspaceItems(projectId)
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
    _abortCurrentStream()
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

    if (routeVal === 'workspace' && params.currentProjectId) {
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
      let chosenId: ID | '' = currentAssistantId.value
      if (!chosenId && currentProjectId.value) {
        chosenId = _getSavedAssistant(currentProjectId.value)
      }
      if (!chosenId && list.length > 0) {
        chosenId = list[0].id
      }
      const valid = chosenId && list.some(a => a.id === chosenId)
      assistants.value = list
      currentAssistantId.value = valid ? chosenId : (list[0]?.id || '')
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
    isSummarizing,
    isArchiving,
    assistants,
    currentAssistantId,
    workspaceItems,
    chronicle,
    error,
    _currentAbort,

    deleteProject,
    fetchProjects,
    createProject,
    fetchConversations,
    createConversation,
    selectConversation,
    deleteConversation,
    renameConversation,
    fetchMessages,
    sendMessage,
    regenerateMessage,
    fetchWorkspaceItems,
    createWorkspaceItem,
    updateItemStatus,
    deleteWorkspaceItem,
    updateWorkspaceItem,
    fetchChronicle,
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
