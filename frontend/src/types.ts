/* ── Backend API types (mirrors Python schemas) ── */

export interface DispatchAction {
  service: string
  priority: number
  reason: string
}

export interface VisualObservation {
  label: string
  description?: string | null
  confidence?: number | null
}

export interface CapturedImage {
  timestamp: string
  label: string
  image_data: string
  source?: "upload" | "camera" | "snapshot" | string
  scene?: string | null
  observations?: VisualObservation[]
}

export interface VideoEvidence {
  timestamp: string
  category: string
  duration_seconds: number
  video_data?: string | null
  location?: { latitude: number; longitude: number; accuracy_meters: number } | null
  notes?: string | null
}

export interface SensorTelemetry {
  heart_rate?: number | null
  spo2?: number | null
  battery_level?: number | null
  battery?: number | null
  device_name?: string
  status?: string
  notes?: string
  timestamp?: string
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
  captured_images?: CapturedImage[]
  video_evidence?: VideoEvidence[]
  sensor_telemetry?: SensorTelemetry | null
  selected_service?: string | null
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
  landmark?: string | null
  latitude?: number | null
  longitude?: number | null
  location_accuracy?: number | null
  location_source?: string | null
  location_status?: string | null
  location_display?: string | null
  details: string | null
  priority: number | null
  priority_score?: number | null
  priority_label?: string | null
  caller_name: string | null
  caller_age: number | null
  caller_phone: string | null
  casualties: number | null
  summary: string | null
  guidance: string | null
  current_question?: string | null
  missing_info?: string[]
  routed_service: string | null
  sop_steps: string[] | null
  dispatcher_notes: string | null
  dispatch_plan: DispatchAction[]
  fake_probability?: number | null
  fake_label?: string | null
  fake_signals?: string[]
  status: string
  turn_count: number
  messages: ChatMessage[]
  captured_images?: CapturedImage[]
  video_evidence?: VideoEvidence[]
  sensor_telemetry?: SensorTelemetry | null
  selected_service?: string | null
  selected_language?: string | null
  detected_language?: string | null
  original_transcript?: string | null
  translated_transcript?: string | null
  caller_question?: string | null
  caller_guidance?: string | null
  known_facts?: Record<string, any>
  previous_questions?: string[]
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
  chroma_status?: string
  mongodb_status?: string
}

export interface DispatcherUpdate {
  session_id: string
  transcript?: string
  original_transcript?: string
  caller_language?: string
  current_question?: string | null
  caller_question?: string | null
  caller_guidance?: string | null
  severity?: string | null
  score?: number | null
  summary?: string | null
  status?: string
  emergency_type?: string | null
  location?: string | null
  latitude?: number | null
  longitude?: number | null
  location_accuracy?: number | null
  location_source?: string | null
  location_status?: string | null
  location_display?: string | null
  caller_name?: string | null
  caller_age?: number | null
  caller_phone?: string | null
  casualties?: number | null
  guidance?: string | null
  sop_steps?: string[] | null
  dispatch_plan?: DispatchAction[]
  routed_service?: string | null
  fake_probability?: number | null
  fake_label?: string | null
  fake_signals?: string[]
  selected_service?: string | null
  sensor_telemetry?: SensorTelemetry | null
  captured_images?: CapturedImage[]
  video_evidence?: VideoEvidence[]
  missing_info?: string[]
  turn_count?: number
  language?: string
  known_facts?: Record<string, any>
  timestamp?: number | string
  caller_status?: string
  is_fast_path?: boolean
  dispatcher_instruction?: string
  caller_instruction?: string
  new_evidence_frame?: {
    timestamp: string
    label: string
    has_image: boolean
    source?: string
    scene?: string
    observations?: VisualObservation[]
  }
  new_video_evidence?: {
    timestamp: string
    category: string
    duration_seconds: number
    has_video: boolean
    location?: any
  }
}

export interface TranscriptEntry {
  role: "caller" | "ai" | "system"
  text: string
  timestamp: number
}
