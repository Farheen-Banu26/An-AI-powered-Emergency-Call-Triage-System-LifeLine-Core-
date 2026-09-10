import { useState, useEffect, useRef, useCallback } from "react"
import {
  Volume2,
  Radio,
  RefreshCw,
  MapPin,
  User,
  AlertCircle,
  AlertTriangle,
  Activity,
  FileText,
  ShieldCheck,
  Trash2,
  ChevronRight,
} from "lucide-react"
import type { DispatcherUpdate, SessionListItem, SummaryResponse } from "../types"
import { api } from "../lib/api"
import { cn, priorityLabel, priorityColor, statusStyle } from "../lib/utils"
import { useLanguage } from "../context/LanguageContext"
import { translations } from "../i18n/translations"
import { ControlButton } from "../components/ControlButton"
import { LanguageSelector } from "../components/LanguageSelector"
import { SummaryPanel } from "../components/SummaryPanel"

export default function AdminDashboard() {
  const { language } = useLanguage()
  const t = translations[language] ?? translations.en

  const [isSpeakerActive, setIsSpeakerActive] = useState(false)
  const [connected, setConnected] = useState(false)
  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [memSessions, setMemSessions] = useState<string[]>([])
  const [liveUpdates, setLiveUpdates] = useState<
    Record<string, DispatcherUpdate>
  >({})
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [summary, setSummary] = useState<SummaryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  /* ── Fetch session list ── */
  const fetchSessions = useCallback(async () => {
    try {
      const data = await api.listSessions()
      setSessions(data.persisted)
      setMemSessions(data.in_memory)
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  useEffect(() => {
    const i = setInterval(fetchSessions, 8000)
    return () => clearInterval(i)
  }, [fetchSessions])

  /* ── Dispatcher WebSocket ── */
  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss:" : "ws:"
    const ws = new WebSocket(
      `${proto}//${location.host}/api/dispatcher/ws`,
    )
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (evt) => {
      try {
        const u = JSON.parse(evt.data) as DispatcherUpdate
        setLiveUpdates((prev) => ({ ...prev, [u.session_id]: u }))
      } catch {
        /* ignore */
      }
    }

    return () => ws.close()
  }, [])

  /* ── Fetch summary for selected session ── */
  useEffect(() => {
    if (!selectedId) {
      setSummary(null)
      return
    }
    setLoading(true)
    api
      .getSummary(selectedId)
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false))
  }, [selectedId])

  /* ── AI Speaker: play latest question for selected session ── */
  const handleSpeakClick = async () => {
    const sid = selectedId ?? "demo"
    setIsSpeakerActive(true)
    try {
      const url = api.audioUrl(sid, language === "en" ? "en" : language)
      const audio = new Audio(url)
      await new Promise<void>((resolve) => {
        audio.onended = () => resolve()
        audio.onerror = () => resolve()
        audio.play().catch(() => resolve())
      })
    } finally {
      setIsSpeakerActive(false)
    }
  }

  /* ── Delete session ── */
  const handleDelete = async (sid: string) => {
    try {
      await api.deleteSession(sid)
      if (selectedId === sid) {
        setSelectedId(null)
        setSummary(null)
      }
      setLiveUpdates((prev) => {
        const copy = { ...prev }
        delete copy[sid]
        return copy
      })
      await fetchSessions()
    } catch {
      /* ignore */
    }
  }

  /* ── Merged list ── */
  const persistedIds = new Set(sessions.map((s) => s.session_id))
  const memOnly = memSessions.filter((id) => !persistedIds.has(id))

  /* ── Severity from summary ── */
  const severityLabel =
    summary?.priority === 1
      ? "Critical"
      : summary?.priority === 2
        ? "High"
        : summary?.priority === 3
          ? "Medium"
          : summary?.priority === 4
            ? "Low"
            : null

  /* ──────────── UI ──────────── */
  return (
    <div className="min-h-screen p-6 md:p-12 bg-dark flex flex-col items-center">
      {/* Header */}
      <div className="w-full max-w-6xl flex flex-col md:flex-row justify-between items-center mb-12 gap-6">
        <div className="flex flex-col">
          <h2 className="text-4xl font-black text-white uppercase tracking-tighter">
            {t.dashboard}
          </h2>
          <p className="text-safe font-bold tracking-[0.2em] uppercase text-sm">
            {t.subtitle}
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* Live badge */}
          <span
            className={cn(
              "flex items-center gap-2 rounded-full border px-3 py-1 text-[10px] font-bold uppercase tracking-wider",
              connected
                ? "border-green-500/30 bg-green-500/15 text-green-400"
                : "border-red-500/30 bg-red-500/15 text-red-400",
            )}
          >
            <Radio className="h-3 w-3" />
            {connected ? "Live" : "Disconnected"}
          </span>
          <button
            onClick={fetchSessions}
            className="rounded-lg border border-white/10 p-2 text-slate-400 transition-colors hover:text-white"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
          <LanguageSelector />
        </div>
      </div>

      {/* Main: AI Voice + Summary (old layout) */}
      <div className="flex flex-col md:flex-row gap-8 w-full max-w-5xl items-start mb-12">
        {/* AI Voice Control Panel */}
        <div className="flex-1 glass p-8 rounded-[2rem] border-white/5 h-full">
          <div className="flex items-center gap-3 mb-8">
            <Volume2 className="text-safe w-8 h-8" />
            <h3 className="text-2xl font-black text-white uppercase tracking-widest">
              {t.ai_title}
            </h3>
          </div>

          <p className="text-slate-400 mb-10 font-medium">{t.ai_desc}</p>

          <ControlButton
            icon={<Volume2 />}
            label={isSpeakerActive ? t.speaking : t.mic}
            onClick={handleSpeakClick}
            isActive={isSpeakerActive}
            variant="safe"
            className="w-full rounded-2xl p-12"
          />
        </div>

        {/* Summary Panel (from selected session or fallback) */}
        <div className="flex-1 w-full">
          <SummaryPanel
            data={{
              age: summary?.caller_age,
              emergency: summary?.emergency_type ?? "—",
              severity: severityLabel,
              location: summary?.location ?? "—",
              actionTaken: summary?.routed_service
                ? `${summary.routed_service} dispatched`
                : summary?.status === "ready_to_dispatch"
                  ? "Ready to dispatch"
                  : undefined,
            }}
          />

          {/* Guidance from selected */}
          {summary?.guidance && (
            <div className="mt-4 glass p-5 rounded-2xl border border-green-500/20">
              <div className="flex items-center gap-2 mb-2 text-green-400">
                <ShieldCheck className="h-4 w-4" />
                <span className="text-[10px] font-bold uppercase tracking-wider">
                  Guidance
                </span>
              </div>
              <p className="whitespace-pre-line text-sm leading-relaxed text-green-200/80">
                {summary.guidance}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Session List (live dispatch feed) */}
      <div className="w-full max-w-5xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Active Sessions ({sessions.length + memOnly.length})
          </h3>
        </div>

        <div className="space-y-3">
          {/* Persisted sessions */}
          {sessions.map((s) => {
            const live = liveUpdates[s.session_id]
            return (
              <div
                key={s.session_id}
                onClick={() => setSelectedId(s.session_id)}
                className={cn(
                  "group glass p-4 rounded-2xl cursor-pointer transition-all hover:border-white/20 flex items-center gap-4",
                  selectedId === s.session_id && "border-blue-500/30 bg-blue-500/5",
                )}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1">
                    <span className="text-sm font-bold text-white">
                      {live?.emergency_type ?? s.emergency_type ?? "Unknown"}
                    </span>
                    <span
                      className={cn(
                        "text-[10px] font-black",
                        priorityColor(
                          live?.score
                            ? Math.ceil(live.score / 2.5)
                            : s.priority,
                        ),
                      )}
                    >
                      {priorityLabel(
                        live?.score ? Math.ceil(live.score / 2.5) : s.priority,
                      )}
                    </span>
                    <span
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase",
                        statusStyle(live?.status ?? s.status),
                      )}
                    >
                      {(live?.status ?? s.status).replace(/_/g, " ")}
                    </span>
                    {/* Fake call badge */}
                    {live?.fake_label && live.fake_label !== "GENUINE" && (
                      <span
                        className={cn(
                          "flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase",
                          live.fake_label === "LIKELY_FAKE"
                            ? "border-red-500/40 bg-red-500/15 text-red-400"
                            : "border-yellow-500/40 bg-yellow-500/15 text-yellow-400",
                        )}
                      >
                        <AlertTriangle className="h-2.5 w-2.5" />
                        {live.fake_label === "LIKELY_FAKE" ? "FAKE" : "SUS"}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-4 text-[11px] text-slate-500">
                    <span className="flex items-center gap-1">
                      <MapPin className="h-3 w-3" />
                      {live?.location ?? s.location ?? "—"}
                    </span>
                    {(live?.caller_name ?? s.caller_name) && (
                      <span className="flex items-center gap-1">
                        <User className="h-3 w-3" />
                        {live?.caller_name ?? s.caller_name}
                      </span>
                    )}
                  </div>
                </div>

                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    handleDelete(s.session_id)
                  }}
                  className="rounded p-2 text-slate-600 opacity-0 transition-all hover:text-red-400 group-hover:opacity-100"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
                <ChevronRight className="h-4 w-4 text-slate-600" />
              </div>
            )
          })}

          {/* Memory-only sessions */}
          {memOnly.map((id) => {
            const live = liveUpdates[id]
            return (
              <div
                key={id}
                onClick={() => setSelectedId(id)}
                className={cn(
                  "group glass p-4 rounded-2xl cursor-pointer transition-all hover:border-white/20 flex items-center gap-4",
                  selectedId === id && "border-blue-500/30 bg-blue-500/5",
                )}
              >
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-bold text-white">
                    {live?.emergency_type ?? "Active Call"}
                  </span>
                  <span className="ml-3 text-[10px] text-slate-500 font-mono">
                    {id.slice(0, 8)}
                  </span>
                  {live && (
                    <p className="text-[11px] text-slate-500 truncate mt-1">
                      {live.transcript.slice(-80)}
                    </p>
                  )}
                </div>
                <ChevronRight className="h-4 w-4 text-slate-600" />
              </div>
            )
          })}

          {sessions.length === 0 && memOnly.length === 0 && (
            <p className="py-8 text-center text-xs text-slate-600">
              No active sessions
            </p>
          )}
        </div>
      </div>

      {/* Selected session detail overlay */}
      {selectedId && summary && !loading && (
        <div className="w-full max-w-5xl mt-8">
          <div className="glass p-6 rounded-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-bold text-white">
                {summary.emergency_type ?? "Incident"} — Detail
              </h3>
              <span className="text-[10px] text-slate-500 font-mono">
                {summary.session_id.slice(0, 12)}
              </span>
            </div>

            {/* Stats grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
              {[
                {
                  icon: <MapPin className="h-4 w-4" />,
                  label: "Location",
                  value: summary.location,
                },
                {
                  icon: <User className="h-4 w-4" />,
                  label: "Caller",
                  value: summary.caller_name,
                },
                {
                  icon: <AlertCircle className="h-4 w-4" />,
                  label: "Priority",
                  value: summary.priority != null ? priorityLabel(summary.priority) : null,
                },
                {
                  icon: <Activity className="h-4 w-4" />,
                  label: "Turns",
                  value: String(summary.turn_count),
                },
              ].map(
                (r) =>
                  r.value && (
                    <div
                      key={r.label}
                      className="bg-white/5 rounded-xl p-3 border border-white/5"
                    >
                      <div className="flex items-center gap-2 mb-1 text-slate-500">
                        {r.icon}
                        <span className="text-[10px] font-medium uppercase tracking-wider">
                          {r.label}
                        </span>
                      </div>
                      <p className="text-sm font-medium text-white truncate">
                        {r.value}
                      </p>
                    </div>
                  ),
              )}
            </div>

            {/* Summary text */}
            {summary.summary && (
              <div className="bg-white/5 rounded-xl p-4 mb-4 border border-white/5">
                <div className="flex items-center gap-2 mb-2 text-slate-500">
                  <FileText className="h-4 w-4" />
                  <span className="text-[10px] font-bold uppercase tracking-wider">
                    Summary
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-slate-300">
                  {summary.summary}
                </p>
              </div>
            )}

            {/* Fake Call Warning */}
            {(() => {
              const live = liveUpdates[selectedId]
              const fl = live?.fake_label
              const fp = live?.fake_probability
              const fs = live?.fake_signals ?? []
              if (!fl || fl === "GENUINE") return null
              return (
                <div
                  className={cn(
                    "rounded-xl p-4 mb-4 border flex items-start gap-3",
                    fl === "LIKELY_FAKE"
                      ? "bg-red-500/10 border-red-500/30"
                      : "bg-yellow-500/10 border-yellow-500/30",
                  )}
                >
                  <AlertTriangle
                    className={cn(
                      "h-5 w-5 shrink-0 mt-0.5",
                      fl === "LIKELY_FAKE" ? "text-red-400" : "text-yellow-400",
                    )}
                  />
                  <div className="flex-1">
                    <p
                      className={cn(
                        "text-sm font-bold uppercase tracking-wider",
                        fl === "LIKELY_FAKE" ? "text-red-300" : "text-yellow-300",
                      )}
                    >
                      {fl === "LIKELY_FAKE"
                        ? "Likely Fake Call"
                        : "Suspicious Call"}
                      {fp != null && (
                        <span className="ml-2 text-xs opacity-70 font-normal normal-case">
                          ({Math.round(fp * 100)}% confidence)
                        </span>
                      )}
                    </p>
                    {fs.length > 0 && (
                      <ul
                        className={cn(
                          "mt-1.5 text-xs list-disc list-inside",
                          fl === "LIKELY_FAKE" ? "text-red-300/70" : "text-yellow-300/70",
                        )}
                      >
                        {fs.map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ul>
                    )}
                    {fl === "LIKELY_FAKE" && (
                      <p className="mt-2 text-xs text-red-300/60">
                        Dispatch has been automatically blocked for this call.
                      </p>
                    )}
                  </div>
                </div>
              )
            })()}

            {/* Conversation transcript */}
            {summary.messages.length > 0 && (
              <div>
                <p className="mb-3 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Conversation ({summary.messages.length} messages)
                </p>
                <div className="space-y-2 max-h-[300px] overflow-y-auto">
                  {summary.messages.map((m, i) => (
                    <div
                      key={i}
                      className={cn(
                        "rounded-lg px-3 py-2 text-sm",
                        m.type === "human"
                          ? "border-l-2 border-red-500/40 bg-red-500/5 text-slate-300"
                          : "border-l-2 border-blue-500/40 bg-blue-500/5 text-slate-300",
                      )}
                    >
                      <span className="mr-2 text-[10px] font-bold uppercase text-slate-600">
                        {m.type === "human" ? "Caller" : "AI"}
                      </span>
                      {m.content}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Dispatch plan */}
            {summary.dispatch_plan.length > 0 && (
              <div className="mt-4">
                <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Dispatch Plan
                </p>
                <div className="space-y-2">
                  {summary.dispatch_plan.map((d, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between bg-white/5 rounded-lg border border-white/5 px-4 py-2.5"
                    >
                      <div>
                        <p className="text-sm font-medium text-white">
                          {d.service}
                        </p>
                        <p className="text-xs text-slate-500">{d.reason}</p>
                      </div>
                      <span
                        className={cn(
                          "text-xs font-bold",
                          priorityColor(d.priority),
                        )}
                      >
                        P{d.priority}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
