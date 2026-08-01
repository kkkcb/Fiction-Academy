export type ID = string

export interface Project {
  id: ID
  name: string
  genre?: string | null
  chapter_name_template?: string
  created_at?: string
  updated_at?: string
}

export interface Conversation {
  id: ID
  project_id: ID
  title: string
  point?: string | null
  created_at?: string
  updated_at?: string
}

export type MessageRole = 'user' | 'assistant'

export interface Message {
  id?: ID
  conversation_id?: ID
  role: MessageRole
  content: string
  thinking?: string
  consult_kind?: string
  created_at?: string
}

export type WorkspaceItemType =
  | 'story_core'
  | 'world_setting'
  | 'character_setting'
  | 'outline'
  | 'outline_reverse'
  | 'foreshadow'
  | 'chapter_plan'
  | 'chapter'

export type WorkspaceItemStatus = 'draft' | 'finalized' | 'locked'

export interface WorkspaceItem {
  id: ID
  project_id: ID
  item_type: WorkspaceItemType
  status: WorkspaceItemStatus
  title?: string | null
  subtitle?: string
  content?: string
  chapter_number?: number | null
  sort_order?: number
  metadata?: string
  created_at?: string
  updated_at?: string
}

export interface WorkspaceItemInput {
  item_type?: WorkspaceItemType
  status?: WorkspaceItemStatus
  title?: string | null
  subtitle?: string
  content?: string
  chapter_number?: number | null
  sort_order?: number
  metadata?: string
}

export interface Assistant {
  id: ID
  name: string
  description?: string
  system_prompt?: string
  model?: string
  is_builtin?: number | boolean
  created_at?: string
  updated_at?: string
}

export interface AssistantInput {
  name?: string
  description?: string
  system_prompt?: string
  model?: string
}

export interface ChronicleEntry {
  title?: string
  description?: string
  time?: string
  event?: string
  name?: string
  periods?: ChronicleEntry[]
  [k: string]: unknown
}

export interface Chronicle {
  project_id?: ID
  timeline?: ChronicleEntry[]
  characters?: ChronicleEntry[]
  key_events?: ChronicleEntry[]
  unresolved_threads?: ChronicleEntry[]
  raw_text?: string
  updated_at?: string
}

export interface PointInfo {
  point: string
  label?: string
  desc?: string
  status?: string
  conversation_id?: ID | null
}

export interface PointsData {
  points: PointInfo[]
  current_point?: string
}

export interface EnsureConversationResult {
  conversation_id: ID
  messages: Message[]
}

export interface ChatStreamChunk {
  done?: boolean
  error?: string
  thinking?: string
  content?: string
}

export type ChatChunkType = 'thinking' | 'content'

export type StreamAbort = () => void

export interface StreamError extends Error {
  status?: number
  isAbort?: boolean
}

export type ConsultPhase =
  | 'leader_start'
  | 'leader_thinking_chunk'
  | 'leader_chunk'
  | 'leader_done'
  | 'round_start'
  | 'expert_start'
  | 'expert_thinking_chunk'
  | 'expert_chunk'
  | 'expert_done'
  | 'summary_start'
  | 'summary_thinking_chunk'
  | 'summary_chunk'
  | 'summary'
  | 'saved'
  | 'done'
  | 'error'

interface BaseConsultEvent {
  phase: ConsultPhase
}

export interface ConsultLeader {
  name: string
  perspective: string
  content: string
  thinking: string
}

export interface ConsultEntry {
  name: string
  perspective: string
  content: string
  thinking: string
  is_leader?: boolean
}

export interface ConsultRound {
  round: number
  label: string
  entries: ConsultEntry[]
}

export interface ConsultRecord {
  kind: 'consult_record'
  leader: ConsultLeader | null
  rounds: ConsultRound[]
  summary: string
  summaryThinking: string
  pending: string
  error?: string
}

export type ConsultEvent =
  | (BaseConsultEvent & { phase: 'leader_start'; name: string; perspective: string })
  | (BaseConsultEvent & { phase: 'leader_thinking_chunk'; chunk: string })
  | (BaseConsultEvent & { phase: 'leader_chunk'; chunk: string })
  | (BaseConsultEvent & { phase: 'leader_done'; name?: string; perspective?: string; content: string })
  | (BaseConsultEvent & { phase: 'round_start'; round: number })
  | (BaseConsultEvent & { phase: 'expert_start'; round: number; expert: string; name: string; perspective: string; is_leader?: boolean })
  | (BaseConsultEvent & { phase: 'expert_thinking_chunk'; round: number; expert: string; chunk: string })
  | (BaseConsultEvent & { phase: 'expert_chunk'; round: number; expert: string; chunk: string })
  | (BaseConsultEvent & { phase: 'expert_done'; round: number; expert: string; content: string })
  | (BaseConsultEvent & { phase: 'summary_start' })
  | (BaseConsultEvent & { phase: 'summary_thinking_chunk'; chunk: string })
  | (BaseConsultEvent & { phase: 'summary_chunk'; chunk: string })
  | (BaseConsultEvent & { phase: 'summary'; content: string })
  | (BaseConsultEvent & { phase: 'saved' })
  | (BaseConsultEvent & { phase: 'done' })
  | (BaseConsultEvent & { phase: 'error'; message: string })

export type ConsultEventHandler = (event: ConsultEvent) => void

export type PointKey =
  | 'story_core'
  | 'world_setting'
  | 'character_setting'
  | 'outline_reverse'
  | 'outline'

export type AssistantInputData = Record<string, unknown>
export type WorkspaceItemData = Record<string, unknown>
