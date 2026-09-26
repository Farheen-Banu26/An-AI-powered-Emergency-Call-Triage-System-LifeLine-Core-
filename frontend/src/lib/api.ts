import type {
  HealthResponse,
  StatusResponse,
  SummaryResponse,
  SessionList,
  SensorTelemetry,
  VisualObservation,
} from "../types"

const API = "/api"

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json() as Promise<T>
}

export const api = {
  /* ── Health ── */
  health: () => json<HealthResponse>(`${API}/health`),

  /* ── Call / message ── */
  sendMessage: (sessionId: string, message: string, language: string = "en") =>
    json<{ success: boolean; session_id: string }>(`${API}/call/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message, language }),
    }),

  /* ── Emergency service selection ── */
  selectService: (sessionId: string, service: string) =>
    json<{ success: boolean; session_id: string; selected_service: string }>(
      `${API}/call/service`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, service }),
      },
    ),

  /* ── Camera / Upload Evidence Frame Upload with Gemini Vision ── */
  sendImageFrame: (
    sessionId: string,
    imageData: string,
    label = "Live Evidence Frame",
    source: "upload" | "camera" | "snapshot" | string = "camera",
    scene: string = "general"
  ) =>
    json<{
      status?: string
      success: boolean
      session_id: string
      timestamp: string
      source?: string
      scene?: string
      observations?: VisualObservation[]
      message: string
    }>(
      `${API}/call/image`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          image_data: imageData,
          label,
          source,
          scene,
        }),
      },
    ),

  /* ── Bluetooth Sensor Telemetry Upload ── */
  sendSensorData: (sessionId: string, sensorData: SensorTelemetry) =>
    json<{ success: boolean; session_id: string; telemetry: SensorTelemetry }>(
      `${API}/call/sensor-data`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          ...sensorData,
        }),
      },
    ),

  /* ── Question ── */
  getQuestion: (sessionId: string) =>
    json<{
      session_id: string
      question: string | null
      guidance: string | null
    }>(`${API}/call/question/${sessionId}`),

  getQuestionFull: (sessionId: string, lang = "en") =>
    json<{
      session_id: string
      question: string | null
      guidance: string | null
      audio_url: string | null
    }>(`${API}/call/question/${sessionId}/full?lang=${lang}`),

  /** Returns a URL suitable for `new Audio(url)` with exact message binding */
  audioUrl: (sessionId: string, lang = "en", text?: string) => {
    const base = `${API}/call/question/${encodeURIComponent(sessionId)}/audio?lang=${encodeURIComponent(lang)}`
    return text && text.trim() ? `${base}&text=${encodeURIComponent(text.trim())}` : base
  },

  /* ── Status / summary ── */
  getStatus: (sessionId: string) =>
    json<StatusResponse>(`${API}/call/status/${sessionId}`),

  getSummary: (sessionId: string) =>
    json<SummaryResponse>(`${API}/call/summary/${sessionId}`),

  /* ── Video Evidence Upload ── */
  sendVideoEvidence: async (
    sessionId: string,
    videoData: string,
    category: string = "general",
    notes: string = ""
  ) =>
    json<{ success: boolean; session_id: string; timestamp: string; message: string }>(
      `${API}/call/evidence/video`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          video_data: videoData,
          category,
          notes,
        }),
      }
    ),

  /* ── Dispatcher Two-Way Voice ── */
  sendDispatcherVoice: (sessionId: string, message: string, targetLanguage: string = "en") =>
    json<{ success: boolean; session_id: string; message: string; audio_base64?: string }>(
      `${API}/dispatcher/speak`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message,
          target_language: targetLanguage,
        }),
      }
    ),

  /* ── Sessions ── */
  listSessions: () => json<SessionList>(`${API}/call/sessions`),

  deleteSession: (sessionId: string) =>
    json<{ deleted: string; from_memory: boolean; from_db: boolean }>(
      `${API}/call/${sessionId}`,
      { method: "DELETE" },
    ),

  /* ── Location / GPS Update ── */
  updateLocation: (
    sessionId: string,
    locationData: {
      latitude?: number | null
      longitude?: number | null
      accuracy?: number | null
      source?: string
      address?: string | null
      landmark?: string | null
      display_string?: string | null
      is_low_accuracy?: boolean
      timestamp?: string | null
    }
  ) =>
    json<{ success: boolean; session_id: string; location_status: string; location_display: string }>(
      `${API}/call/location`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, ...locationData }),
      },
    ),
}
