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

  assistants: [],
  currentAssistantId: '',

  workspaceItems: [],

  chronicle: null,

  error: null,
}

const listeners = new Set()

export function subscribe(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function getState() {
  return { ...state }
}

export function setState(partial) {
  Object.assign(state, partial)
  for (const fn of listeners) {
    fn(state)
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
  setState({ currentConversationId: conversationId })
  await fetchMessages(conversationId)
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

function _requestReply(conversationId, content, baseMessages) {
  let fullContent = ''
  const assistantId = state.currentAssistantId

  setState({ isStreaming: true, streamingContent: '' })

  api.streamChat(
    conversationId,
    content,
    (chunk) => {
      fullContent += chunk
      setState({ streamingContent: fullContent })
    },
    () => {
      setState({
        messages: [...baseMessages, { role: 'assistant', content: fullContent }],
        streamingContent: '',
        isStreaming: false,
      })
    },
    (err) => {
      console.error('[sendMessage] stream error:', err)
      setState({
        isStreaming: false,
        streamingContent: '',
        error: err.message,
      })
    },
    assistantId,
  )
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
  _requestReply(conversationId, userMsg.content, trimmed)
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
    await Promise.all([
      fetchConversations(pid),
      fetchWorkspaceItems(pid),
      fetchChronicle(pid),
      fetchAssistants(),
    ])
    const s = getState()
    if (s.conversations.length > 0) {
      setState({ currentConversationId: s.conversations[0].id })
      await fetchMessages(s.conversations[0].id)
    } else {
      const conv = await createConversation(pid, '对话 1')
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
