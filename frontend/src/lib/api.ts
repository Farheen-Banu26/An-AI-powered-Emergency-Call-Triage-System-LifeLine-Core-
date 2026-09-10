import type {
  HealthResponse,
  StatusResponse,
  SummaryResponse,
  SessionList,
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
  sendMessage: (sessionId: string, message: string) =>
    json<{ success: boolean; session_id: string }>(`${API}/call/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
    }),

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

  /** Returns a URL suitable for `new Audio(url)` */
  audioUrl: (sessionId: string, lang = "en") =>
    `${API}/call/question/${sessionId}/audio?lang=${lang}`,

  /* ── Status / summary ── */
  getStatus: (sessionId: string) =>
    json<StatusResponse>(`${API}/call/status/${sessionId}`),

  getSummary: (sessionId: string) =>
    json<SummaryResponse>(`${API}/call/summary/${sessionId}`),

  /* ── Sessions ── */
  listSessions: () => json<SessionList>(`${API}/call/sessions`),

  deleteSession: (sessionId: string) =>
    json<{ deleted: string; from_memory: boolean; from_db: boolean }>(
      `${API}/call/${sessionId}`,
      { method: "DELETE" },
    ),
}
