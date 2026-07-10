import * as api from './api.js'

const state = {
  route: 'projects',
  currentProjectId: null,

  projects: [],

  conversations: [],
  currentConversationId: null,
  messages: [],
  streamingContent: '',
  isStreaming: false,
  isSummarizing: false,
  pendingQuestions: [],
  questionAnswers: {},

  assistants: [],
  currentAssistantId: '',

  workspaceItems: [],

  chronicle: null,

  skeleton: null,
  guideConversationId: null,
  guideMessages: [],
  guideCurrentPoint: null,
  isGuiding: false,

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
    setState({ projects: updated, error: null })
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
  } catch (e) {
    setState({ error: e.message })
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
    setState({ conversations: updated, currentConversationId: conversation.id, messages: [], error: null })
    return conversation
  } catch (e) {
    setState({ error: e.message })
    return null
  }
}

export async function selectConversation(conversationId) {
  _abortCurrentStream()
  const token = ++_convToken
  setState({ currentConversationId: conversationId })
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
    setState({ conversations: updated, error: null })
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
  const assistantId = state.currentAssistantId
  const targetConvId = conversationId

  setState({ isStreaming: true, streamingContent: '' })

  const abort = api.streamChat(
    conversationId,
    content,
    (chunk) => {
      if (state.currentConversationId !== targetConvId) return
      fullContent += chunk
      setState({ streamingContent: fullContent })
    },
    () => {
      state._currentAbort = null
      if (state.currentConversationId !== targetConvId) {
        setState({ isStreaming: false, streamingContent: '' })
        return
      }
      setState({
        messages: [...baseMessages, { role: 'assistant', content: fullContent }],
        streamingContent: '',
        isStreaming: false,
      })
    },
    (err, partialContent) => {
      state._currentAbort = null
      console.error('[sendMessage] stream error:', err)
      const finalContent = partialContent || fullContent
      const newMessages = finalContent
        ? [...baseMessages, { role: 'assistant', content: finalContent + '\n\n[生成中断]' }]
        : baseMessages
      if (state.currentConversationId !== targetConvId) {
        setState({ isStreaming: false, streamingContent: '' })
        return
      }
      setState({
        messages: newMessages,
        isStreaming: false,
        streamingContent: '',
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

export async function navigateTo(route, params = {}) {
  _abortCurrentStream()
  const token = ++_navToken

  const update = {
    route,
    currentConversationId: null,
    messages: [],
    streamingContent: '',
    isStreaming: false,
    workspaceItems: [],
    chronicle: null,
    ...params,
  }
  setState(update)

  if (route === 'workspace' && params.currentProjectId) {
    const pid = params.currentProjectId
    const results = await Promise.allSettled([
      fetchConversations(pid),
      fetchWorkspaceItems(pid),
      fetchChronicle(pid),
      fetchAssistants(),
      fetchSkeleton(pid),
    ])
    if (token !== _navToken) return

    const s = getState()
    if (s.conversations.length > 0) {
      setState({ currentConversationId: s.conversations[0].id })
      await fetchMessages(s.conversations[0].id)
      if (token !== _navToken) return
    } else {
      const conv = await createConversation(pid, '对话 1')
      if (token !== _navToken) return
      if (conv) setState({ currentConversationId: conv.id })
    }
  }
}

export async function fetchAssistants() {
  try {
    const assistants = await api.listAssistants()
    if (!state.currentAssistantId && assistants.length > 0) {
      setState({ assistants, currentAssistantId: assistants[0].id })
    } else {
      setState({ assistants })
    }
  } catch (e) {
    setState({ error: e.message })
  }
}

export function selectAssistant(assistantId) {
  setState({ currentAssistantId: assistantId })
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

export async function fetchSkeleton(projectId) {
  try {
    const skeleton = await api.getSkeleton(projectId)
    setState({ skeleton, guideCurrentPoint: skeleton.current_point, error: null })
  } catch (e) {
    setState({ error: e.message })
  }
}

export async function startGuide(projectId, point) {
  setState({ isGuiding: true, guideMessages: [], guideCurrentPoint: point || state.guideCurrentPoint })
  try {
    const r = await api.skeletonGuide(projectId, { step: 'intro', point: point || undefined })
    setState({
      guideConversationId: r.conversation_id,
      guideMessages: [{ role: 'assistant', content: r.reply }],
      guideCurrentPoint: r.current_point,
      skeleton: { ...state.skeleton, points: r.completeness ? { ...state.skeleton?.points, _summary: r.completeness } : state.skeleton?.points },
      error: null,
    })
  } catch (e) {
    setState({ isGuiding: false, error: e.message })
  }
}

export async function sendGuideReply(projectId, reply) {
  if (!state.guideConversationId || !state.guideCurrentPoint) return
  const point = state.guideCurrentPoint
  const newMsgs = [...state.guideMessages, { role: 'user', content: reply }]
  setState({ guideMessages: [...newMsgs, { role: 'assistant', content: '...' }] })
  try {
    const r = await api.skeletonGuide(projectId, {
      step: 'extract',
      user_reply: reply,
      conversation_id: state.guideConversationId,
      point,
    })
    const updatedMsgs = [...newMsgs, { role: 'assistant', content: r.reply }]
    setState({
      guideMessages: updatedMsgs,
      guideCurrentPoint: r.next_point || point,
      skeleton: { ...state.skeleton, points: { ...state.skeleton?.points, _summary: r.completeness } },
      isGuiding: !r.is_point_complete,
      error: null,
    })
    if (r.is_point_complete) {
      await fetchSkeleton(projectId)
    }
  } catch (e) {
    setState({
      guideMessages: [...newMsgs, { role: 'assistant', content: `[出错] ${e.message}` }],
      error: e.message,
    })
  }
}

export function closeGuide() {
  setState({ isGuiding: false, guideMessages: [], guideConversationId: null })
}

export async function checkWriteReadiness(projectId) {
  try {
    return await api.checkWriteReadiness(projectId)
  } catch (e) {
    setState({ error: e.message })
    return null
  }
}
