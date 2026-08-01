import * as api from './api.js'

const state = {
  route: 'projects',
  currentProjectId: null,

  projects: [],

  conversations: [],
  currentConversationId: null,
  messages: [],
  streamingContent: '',
  streamingThinking: '',
  isStreaming: false,
  consultFlow: null,

  points: [],
  currentPoint: null,
  activeMode: 'point',

  isSummarizing: false,
  isArchiving: false,

  assistants: [],
  currentAssistantId: '',

  workspaceItems: [],

  chronicle: null,

  error: null,

  _mobileTab: null,
  _currentAbort: null,
}

const listeners = new Set()
const errorListeners = new Set()
let _navToken = 0
let _convToken = 0

export function subscribe(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function onError(fn) {
  errorListeners.add(fn)
  return () => errorListeners.delete(fn)
}

export function getState() {
  return { ...state }
}

export function setState(partial) {
  const prevError = state.error
  Object.assign(state, partial)
  for (const fn of [...listeners]) {
    try {
      fn(state)
    } catch (e) {
      console.error('[store] listener error:', e)
    }
  }
  if (partial.error && partial.error !== prevError) {
    for (const fn of [...errorListeners]) {
      try {
        fn(partial.error)
      } catch (e) {
        console.error('[store] error listener error:', e)
      }
    }
  }
}

export function setStateSilent(partial) {
  Object.assign(state, partial)
}

function _abortCurrentStream() {
  if (state._currentAbort) {
    state._currentAbort()
    state._currentAbort = null
  }
}

export async function deleteProject(projectId) {
  try {
    await api.deleteProject(projectId)
    const updated = state.projects.filter(p => p.id !== projectId)
    const patch = { projects: updated, error: null }
    if (state.currentProjectId === projectId) {
      _abortCurrentStream()
      patch.route = 'projects'
      patch.currentProjectId = null
      patch.conversations = []
      patch.currentConversationId = null
      patch.messages = []
      patch.points = []
      patch.workspaceItems = []
      patch.currentPoint = null
    }
    setState(patch)
  } catch (e) {
    setState({ error: e.message })
  }
}

export async function fetchProjects() {
  try {
    const projects = await api.listProjects()
    setState({ projects, error: null })
  } catch (e) {
    setState({ error: e.message })
  }
}

export async function createProject(name, genre) {
  try {
    const data = { name }
    if (genre) data.genre = genre
    const project = await api.createProject(data)
    setState({ projects: [project, ...state.projects], error: null })
    return project
  } catch (e) {
    setState({ error: e.message })
    return null
  }
}

export async function fetchConversations(projectId) {
  try {
    const conversations = await api.listConversations(projectId)
    setState({ conversations, error: null })
  } catch (e) {
    setState({ error: e.message })
  }
}

export async function createConversation(projectId, title) {
  try {
    const conversation = await api.createConversation(projectId, title)
    const updated = [conversation, ...state.conversations]
    setState({ conversations: updated, currentConversationId: conversation.id, messages: [], activeMode: 'free', currentPoint: null, error: null })
    return conversation
  } catch (e) {
    setState({ error: e.message })
    return null
  }
}

export async function selectConversation(conversationId) {
  _abortCurrentStream()
  const token = ++_convToken
  setState({ currentConversationId: conversationId, activeMode: 'free', currentPoint: null, consultFlow: null, streamingContent: '', streamingThinking: '' })
  try {
    const messages = await api.getMessages(conversationId)
    if (token !== _convToken) return
    setState({ messages, error: null })
  } catch (e) {
    if (token !== _convToken) return
    setState({ error: e.message })
  }
}

export async function deleteConversation(conversationId) {
  try {
    await api.deleteConversation(conversationId)
    const updated = state.conversations.filter(c => c.id !== conversationId)
    const patch = { conversations: updated, error: null }
    if (state.currentConversationId === conversationId) {
      patch.currentConversationId = null
      patch.messages = []
      patch.streamingContent = ''
      patch.isStreaming = false
    }
    setState(patch)
  } catch (e) {
    setState({ error: e.message })
  }
}

export async function renameConversation(conversationId, title) {
  try {
    await api.renameConversation(conversationId, title)
    const updated = state.conversations.map(c => c.id === conversationId ? { ...c, title } : c)
    setState({ conversations: updated, error: null })
  } catch (e) {
    setState({ error: e.message })
  }
}

export async function fetchMessages(conversationId) {
  try {
    const messages = await api.getMessages(conversationId)
    setState({ messages, error: null })
  } catch (e) {
    setState({ error: e.message })
  }
}

function _requestReply(conversationId, content, baseMessages, regenerate = false) {
  _abortCurrentStream()

  let fullContent = ''
  let thinkingContent = ''
  const assistantId = state.currentAssistantId
  const targetConvId = conversationId

  setState({ isStreaming: true, streamingContent: '', streamingThinking: '' })

  const abort = api.streamChat(
    conversationId,
    content,
    (chunk, type) => {
      if (state.currentConversationId !== targetConvId) return
      if (type === 'thinking') {
        thinkingContent += chunk
        setState({ streamingThinking: thinkingContent })
      } else {
        fullContent += chunk
        setState({ streamingContent: fullContent, streamingThinking: thinkingContent })
      }
    },
    () => {
      state._currentAbort = null
      if (state.currentConversationId !== targetConvId) {
        setState({ isStreaming: false, streamingContent: '', streamingThinking: '' })
        return
      }
      setState({
        messages: [...baseMessages, { role: 'assistant', content: fullContent, thinking: thinkingContent || undefined }],
        streamingContent: '',
        streamingThinking: '',
        isStreaming: false,
      })
    },
    (err, partialContent) => {
      state._currentAbort = null
      if (err.isAbort) {
        if (state.currentConversationId !== targetConvId) {
          setState({ isStreaming: false, streamingContent: '', streamingThinking: '' })
        }
        return
      }
      console.error('[sendMessage] stream error:', err)
      const finalContent = partialContent || fullContent
      const newMessages = finalContent
        ? [...baseMessages, { role: 'assistant', content: finalContent + '\n\n[生成中断]', thinking: thinkingContent || undefined }]
        : baseMessages
      if (state.currentConversationId !== targetConvId) {
        setState({ isStreaming: false, streamingContent: '', streamingThinking: '' })
        return
      }
      setState({
        messages: newMessages,
        isStreaming: false,
        streamingContent: '',
        streamingThinking: '',
        error: err.message,
      })
    },
    assistantId,
    regenerate,
  )

  state._currentAbort = abort
}

export function sendMessage(conversationId, content) {
  const userMsg = { role: 'user', content }
  const newMessages = [...state.messages, userMsg]
  setState({ messages: newMessages, error: null })
  _requestReply(conversationId, content, newMessages)
}

export function regenerateMessage(conversationId) {
  const msgs = state.messages
  if (msgs.length === 0) return
  const lastIdx = msgs.length - 1
  if (msgs[lastIdx].role !== 'assistant') return
  const userMsg = msgs[lastIdx - 1]
  if (!userMsg || userMsg.role !== 'user') return
  const trimmed = msgs.slice(0, lastIdx)
  setState({ messages: trimmed })
  _requestReply(conversationId, userMsg.content, trimmed, true)
}

export async function fetchWorkspaceItems(projectId) {
  try {
    const workspaceItems = await api.listWorkspaceItems(projectId)
    setState({ workspaceItems, error: null })
  } catch (e) {
    setState({ error: e.message })
  }
}

export async function createWorkspaceItem(projectId, data) {
  try {
    await api.createWorkspaceItem(projectId, data)
    await fetchWorkspaceItems(projectId)
  } catch (e) {
    setState({ error: e.message })
  }
}

export async function updateItemStatus(itemId, status, projectId) {
  try {
    await api.updateItemStatus(itemId, status)
    await fetchWorkspaceItems(projectId)
    if (status === 'finalized') {
      await fetchChronicle(projectId)
    }
  } catch (e) {
    setState({ error: e.message })
  }
}

export async function deleteWorkspaceItem(itemId, projectId) {
  try {
    await api.deleteWorkspaceItem(itemId)
    await fetchWorkspaceItems(projectId)
  } catch (e) {
    setState({ error: e.message })
  }
}

export async function fetchChronicle(projectId) {
  try {
    const chronicle = await api.getChronicle(projectId)
    setState({ chronicle, error: null })
  } catch (e) {
    setState({ error: e.message })
  }
}

export async function fetchPoints(projectId) {
  try {
    const data = await api.getPoints(projectId)
    setState({ points: data.points || [], error: null })
    return data
  } catch (e) {
    setState({ error: e.message })
    return null
  }
}

let _loadingPoint = null
export async function selectPoint(projectId, point) {
  if (_loadingPoint === point && state.currentPoint === point) return
  _loadingPoint = point
  _abortCurrentStream()
  const token = ++_convToken
  setState({ currentPoint: point, activeMode: 'point', currentConversationId: null, messages: [], consultFlow: null, streamingContent: '', streamingThinking: '' })
  try {
    const r = await api.ensurePointConversation(projectId, point)
    if (token !== _convToken) { _loadingPoint = null; return }
    setState({
      currentConversationId: r.conversation_id,
      messages: r.messages || [],
      error: null,
    })
  } catch (e) {
    if (token !== _convToken) { _loadingPoint = null; return }
    setState({ error: e.message })
  } finally {
    _loadingPoint = null
  }
}

export async function summarizeAndArchive(projectId, point) {
  if (!state.currentConversationId) return null
  setState({ isArchiving: true })
  try {
    const r = await api.summarizePoint(projectId, point, state.currentConversationId)
    await fetchPoints(projectId)
    await fetchWorkspaceItems(projectId)
    setState({ isArchiving: false, error: null })
    return r
  } catch (e) {
    setState({ isArchiving: false, error: e.message })
    return null
  }
}

export async function goalGenerate(projectId, point, idea) {
  const targetConvId = state.currentConversationId
  const baseMessages = state.messages
  const userMsg = { role: 'user', content: `/goal ${idea}` }
  setState({
    messages: [...baseMessages, userMsg],
    isStreaming: true,
    streamingContent: '',
    error: null,
  })
  try {
    const r = await api.autoGeneratePoint(projectId, point, targetConvId, idea)
    if (state.currentConversationId !== targetConvId) {
      setState({ isStreaming: false, streamingContent: '' })
      return r
    }
    const fieldsText = r.metadata && Object.keys(r.metadata).length > 0
      ? '\n\n**结构化字段：**\n' + Object.entries(r.metadata).map(([k, v]) => `- **${k}**: ${v}`).join('\n')
      : ''
    setState({
      messages: [...baseMessages, userMsg, { role: 'assistant', content: r.content + fieldsText }],
      streamingContent: '',
      isStreaming: false,
    })
    await fetchPoints(projectId)
    await fetchWorkspaceItems(projectId)
    if (state.currentConversationId === targetConvId) {
      await fetchMessages(targetConvId)
    }
    return r
  } catch (e) {
    if (state.currentConversationId !== targetConvId) {
      setState({ isStreaming: false, streamingContent: '' })
      return null
    }
    setState({
      messages: [...baseMessages, userMsg, { role: 'assistant', content: `[生成失败] ${e.message}` }],
      isStreaming: false,
      streamingContent: '',
      error: e.message,
    })
    return null
  }
}

export function expertConsult(projectId, point, idea) {
  const targetConvId = state.currentConversationId
  const baseMessages = state.messages
  const userMsg = { role: 'user', content: `/consult ${idea}` }

  const flow = { leader: null, rounds: [], summary: '', summaryThinking: '', pending: '🎯 故事核专家（统率者）正在定调...' }
  const entryMap = {}

  const findEntry = (round, expert) => entryMap[`${round}-${expert}`]

  const mkFlow = () => ({
    kind: 'consult_record',
    leader: flow.leader,
    rounds: flow.rounds.map(r => ({ ...r, entries: r.entries.map(e => ({ ...e })) })),
    summary: flow.summary,
    summaryThinking: flow.summaryThinking,
    pending: flow.pending,
  })

  setState({
    messages: [...baseMessages, userMsg],
    isStreaming: true,
    consultFlow: mkFlow(),
    streamingContent: '',
    error: null,
  })

  const abort = api.streamExpertConsult(
    projectId,
    point,
    targetConvId,
    idea,
    (event) => {
      if (state.currentConversationId !== targetConvId) return
      const ph = event.phase
      if (ph === 'leader_start') {
        flow.leader = { name: event.name, perspective: event.perspective, content: '', thinking: '' }
        flow.pending = '🎯 统率者正在定调...'
        setState({ consultFlow: mkFlow() })
      } else if (ph === 'leader_thinking_chunk') {
        if (flow.leader) flow.leader.thinking = (flow.leader.thinking || '') + event.chunk
        setState({ consultFlow: mkFlow() })
      } else if (ph === 'leader_chunk') {
        if (flow.leader) flow.leader.content += event.chunk
        setState({ consultFlow: mkFlow() })
      } else if (ph === 'leader_done') {
        if (flow.leader) { flow.leader.content = event.content }
        else { flow.leader = { name: event.name, perspective: event.perspective, content: event.content, thinking: '' } }
        flow.pending = '⏳ 各专家正在响应统率者定调...'
        setState({ consultFlow: mkFlow() })
      } else if (ph === 'round_start') {
        flow.rounds.push({ round: event.round, label: event.round === 1 ? '响应定调' : '交锋', entries: [] })
        flow.pending = `⏳ 第${event.round}轮讨论进行中...`
        setState({ consultFlow: mkFlow() })
      } else if (ph === 'expert_start') {
        const r = flow.rounds.find(x => x.round === event.round)
        if (r) {
          const entry = { name: event.name, perspective: event.perspective, content: '', thinking: '', is_leader: !!event.is_leader }
          r.entries.push(entry)
          entryMap[`${event.round}-${event.expert}`] = entry
        }
        setState({ consultFlow: mkFlow() })
      } else if (ph === 'expert_thinking_chunk') {
        const entry = findEntry(event.round, event.expert)
        if (entry) entry.thinking = (entry.thinking || '') + event.chunk
        setState({ consultFlow: mkFlow() })
      } else if (ph === 'expert_chunk') {
        const entry = findEntry(event.round, event.expert)
        if (entry) entry.content += event.chunk
        setState({ consultFlow: mkFlow() })
      } else if (ph === 'expert_done') {
        const entry = findEntry(event.round, event.expert)
        if (entry) entry.content = event.content
        flow.pending = '⏳ 等待更多专家发言...'
        setState({ consultFlow: mkFlow() })
      } else if (ph === 'summary_start') {
        flow.pending = '⏳ 统率者（主线策划）正在做最终裁决...'
        setState({ consultFlow: mkFlow() })
      } else if (ph === 'summary_thinking_chunk') {
        flow.summaryThinking += event.chunk
        setState({ consultFlow: mkFlow() })
      } else if (ph === 'summary_chunk') {
        flow.summary += event.chunk
        setState({ consultFlow: mkFlow() })
      } else if (ph === 'summary') {
        flow.summary = event.content
        const finalFlow = mkFlow()
        if (state.currentConversationId === targetConvId) {
          setState({
            messages: [...baseMessages, userMsg, { role: 'assistant', content: JSON.stringify(finalFlow), consult_kind: 'consult_record' }],
            consultFlow: null,
            streamingContent: '',
            isStreaming: false,
          })
        }
      } else if (ph === 'saved') {
        fetchPoints(projectId)
        fetchWorkspaceItems(projectId)
        if (state.currentConversationId === targetConvId) {
          fetchMessages(targetConvId)
        }
      }
    },
    () => {
      if (state.currentConversationId !== targetConvId) {
        setState({ isStreaming: false, consultFlow: null, streamingContent: '' })
        return
      }
      if (!flow.summary) {
        const partial = mkFlow()
        setState({
          messages: [...baseMessages, userMsg, { role: 'assistant', content: JSON.stringify({ ...partial, error: '会诊未产出完整结果' }) }],
          consultFlow: null,
          streamingContent: '',
          isStreaming: false,
        })
      } else {
        setState({ consultFlow: null, streamingContent: '', isStreaming: false })
      }
    },
    (err) => {
      if (err.isAbort) {
        if (state.currentConversationId !== targetConvId) {
          setState({ isStreaming: false, streamingContent: '' })
        }
        return
      }
      if (state.currentConversationId === targetConvId) {
        setState({
          messages: [...baseMessages, userMsg, { role: 'assistant', content: `[会诊失败] ${err.message}` }],
          streamingContent: '',
          isStreaming: false,
          error: err.message,
        })
      }
    },
  )

  state._currentAbort = abort
}

export async function navigateTo(route, params = {}) {
  _abortCurrentStream()
  const token = ++_navToken

  const update = {
    route,
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
  setState(update)

  if (route === 'workspace' && params.currentProjectId) {
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

export async function fetchAssistants() {
  try {
    const assistants = await api.listAssistants()
    let chosenId = state.currentAssistantId
    if (!chosenId && state.currentProjectId) {
      chosenId = _getSavedAssistant(state.currentProjectId)
    }
    if (!chosenId && assistants.length > 0) {
      chosenId = assistants[0].id
    }
    const valid = chosenId && assistants.some(a => a.id === chosenId)
    setState({ assistants, currentAssistantId: valid ? chosenId : (assistants[0]?.id || '') })
  } catch (e) {
    setState({ error: e.message })
  }
}

const ASSISTANT_KEY_PREFIX = 'fa_assistant_'

function _getSavedAssistant(projectId) {
  try { return localStorage.getItem(ASSISTANT_KEY_PREFIX + projectId) || '' } catch { return '' }
}

function _saveAssistant(projectId, assistantId) {
  if (!projectId) return
  try {
    if (assistantId) localStorage.setItem(ASSISTANT_KEY_PREFIX + projectId, assistantId)
    else localStorage.removeItem(ASSISTANT_KEY_PREFIX + projectId)
  } catch {}
}

export function selectAssistant(assistantId) {
  setStateSilent({ currentAssistantId: assistantId })
  if (state.currentProjectId) {
    _saveAssistant(state.currentProjectId, assistantId)
  }
}

export async function createAssistant(data) {
  try {
    const assistant = await api.createAssistant(data)
    setState({ assistants: [...state.assistants, assistant], error: null })
    return assistant
  } catch (e) {
    setState({ error: e.message })
    return null
  }
}

export async function updateAssistant(id, data) {
  try {
    const updated = await api.updateAssistant(id, data)
    const assistants = state.assistants.map(a => a.id === id ? updated : a)
    setState({ assistants, error: null })
  } catch (e) {
    setState({ error: e.message })
  }
}

export async function deleteAssistant(id) {
  try {
    await api.deleteAssistant(id)
    const assistants = state.assistants.filter(a => a.id !== id)
    const currentAssistantId = state.currentAssistantId === id ? (assistants[0]?.id || '') : state.currentAssistantId
    setState({ assistants, currentAssistantId, error: null })
  } catch (e) {
    setState({ error: e.message })
  }
}
