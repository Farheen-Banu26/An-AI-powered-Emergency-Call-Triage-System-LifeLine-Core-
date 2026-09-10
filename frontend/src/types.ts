/* ── Backend API types (mirrors Python schemas) ── */

export interface DispatchAction {
  service: string
  priority: number
  reason: string
}

export interface IncidentData {
  emergency_type: string | null
  location: string | null
  details: string | null
  priority: number | null
  caller_name: string | null
  caller_age: number | null
  caller_phone: string | null
  casualties: number | null
  estimated_arrival: string | null
  summary: string | null
  guidance: string | null
  missing_info: string[]
  status: string
  dispatch_plan: DispatchAction[]
  retrieved_context: string | null
  question: string | null
  routed_service: string | null
  priority_score: number | null
  priority_label: string | null
  fake_probability: number | null
  fake_label: string | null
  fake_signals: string[]
}

export interface StatusResponse {
  session_id: string
  incident: IncidentData
  conversation_turns: number
}

export interface ChatMessage {
  type: string
  content: string
}

export interface SummaryResponse {
  session_id: string
  emergency_type: string | null
  location: string | null
  details: string | null
  priority: number | null
  caller_name: string | null
  caller_age: number | null
  caller_phone: string | null
  casualties: number | null
  summary: string | null
  guidance: string | null
  routed_service: string | null
  sop_steps: string[] | null
  dispatcher_notes: string | null
  dispatch_plan: DispatchAction[]
  status: string
  turn_count: number
  messages: ChatMessage[]
}

export interface SessionListItem {
  session_id: string
  emergency_type: string | null
  status: string
  priority: number | null
  location: string | null
  caller_name: string | null
  turn_count: number
  created_at: string
  updated_at: string
}

export interface SessionList {
  in_memory: string[]
  persisted: SessionListItem[]
}

export interface HealthResponse {
  status: string
  version: string
  llm_provider: string
  model: string
  active_sessions: number
}

export interface DispatcherUpdate {
  session_id: string
  transcript: string
  severity: string | null
  score: number | null
  summary: string | null
  status: string
  emergency_type: string | null
  location: string | null
  caller_name: string | null
  caller_age: number | null
  caller_phone: string | null
  guidance: string | null
  sop_steps: string[] | null
  dispatch_plan: DispatchAction[]
  routed_service: string | null
  fake_probability: number | null
  fake_label: string | null
  fake_signals: string[]
}

export interface TranscriptEntry {
  role: "caller" | "ai" | "system"
  text: string
  timestamp: number
}
