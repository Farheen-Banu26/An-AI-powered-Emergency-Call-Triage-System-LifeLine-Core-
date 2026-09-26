import { useState, useEffect, useRef, useCallback, useMemo } from "react"
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
  Camera,
  Heart,
  Bluetooth,
  Flame,
  Shield,
  Truck,
  HeartPulse,
  Play,
  Film,
  Clock,
  CheckCircle2,
  Circle,
  Send,
  Users,
  Compass,
  Check,
  Copy,
  ExternalLink,
  MessageSquare,
  HelpCircle,
  Navigation,
  Info,
  Layers,
  XCircle,
  CheckSquare,
  Sparkles,
  Image as ImageIcon,
} from "lucide-react"
import type {
  CapturedImage,
  VideoEvidence,
  DispatcherUpdate,
  SessionListItem,
  SummaryResponse,
  ChatMessage,
} from "../types"
import { api } from "../lib/api"
import { cn, priorityLabel, priorityColor, statusStyle } from "../lib/utils"
import { useLanguage } from "../context/LanguageContext"
import { translations } from "../i18n/translations"
import { LanguageSelector } from "../components/LanguageSelector"

interface TimelineEvent {
  id: string
  time: string
  title: string
  description?: string
  type: "start" | "speech" | "severity" | "question" | "location" | "service" | "evidence" | "system"
}

export default function AdminDashboard() {
  const { language } = useLanguage()
  const t = translations[language] ?? translations.en

  // ── Connection & Session State ──
  const [wsState, setWsState] = useState<"connected" | "connecting" | "disconnected">("connecting")
  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [memSessions, setMemSessions] = useState<string[]>([])
  const [liveUpdates, setLiveUpdates] = useState<Record<string, DispatcherUpdate>>({})
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [summary, setSummary] = useState<SummaryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [timelineEvents, setTimelineEvents] = useState<Record<string, TimelineEvent[]>>({})

  // ── Modals & Previews ──
  const [previewImage, setPreviewImage] = useState<CapturedImage | string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  // ── Dispatcher Two-Way Voice State ──
  const [dispatcherVoiceText, setDispatcherVoiceText] = useState("")
  const [isSendingVoice, setIsSendingVoice] = useState(false)
  const [voiceSendSuccess, setVoiceSendSuccess] = useState(false)
  const [isSpeakerActive, setIsSpeakerActive] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const chatScrollRef = useRef<HTMLDivElement | null>(null)

  /* ── Add Timeline Milestone Helper ── */
  const recordTimelineEvent = useCallback((sessionId: string, event: Omit<TimelineEvent, "id" | "time">) => {
    const timeStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    const newEntry: TimelineEvent = {
      ...event,
      id: "ev_" + Date.now() + "_" + Math.random().toString(36).slice(2, 6),
      time: timeStr,
    }
    setTimelineEvents((prev) => {
      const currentList = prev[sessionId] || []
      // Avoid duplicate consecutive milestone events
      const isDuplicate = currentList.length > 0 && currentList[0].title === event.title && currentList[0].description === event.description
      if (isDuplicate) return prev
      return {
        ...prev,
        [sessionId]: [newEntry, ...currentList].slice(0, 40),
      }
    })
  }, [])

  /* ── Fetch Active Session List ── */
  const fetchSessions = useCallback(async () => {
    try {
      const data = await api.listSessions()
      setSessions(data.persisted || [])
      setMemSessions(data.in_memory || [])
    } catch {
      /* ignore network drop */
    }
  }, [])

  useEffect(() => {
    fetchSessions()
    const interval = setInterval(fetchSessions, 6000)
    return () => clearInterval(interval)
  }, [fetchSessions])

  /* ── Auto-select first active session if none selected ── */
  useEffect(() => {
    if (!selectedId) {
      if (sessions.length > 0) {
        setSelectedId(sessions[0].session_id)
      } else if (memSessions.length > 0) {
        setSelectedId(memSessions[0])
      }
    }
  }, [sessions, memSessions, selectedId])

  /* ── Dispatcher WebSocket with Live Reconnect ── */
  useEffect(() => {
    let isMounted = true
    let reconnectTimeout: any = null
    let pingInterval: any = null

    const connectWebSocket = () => {
      if (!isMounted) return
      setWsState("connecting")

      try {
        const proto = location.protocol === "https:" ? "wss:" : "ws:"
        const wsUrl = `${proto}//${location.host}/api/dispatcher/ws`
        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onopen = () => {
          if (!isMounted) {
            ws.close()
            return
          }
          setWsState("connected")
          pingInterval = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: "ping" }))
            }
          }, 20000)
        }

        ws.onclose = () => {
          if (!isMounted) return
          setWsState("disconnected")
          clearInterval(pingInterval)
          reconnectTimeout = setTimeout(connectWebSocket, 2000)
        }

        ws.onerror = () => {
          setWsState("disconnected")
        }

        ws.onmessage = (evt) => {
          try {
            const u = JSON.parse(evt.data) as DispatcherUpdate
            if (!u || !u.session_id) return

            setLiveUpdates((prev) => ({
              ...prev,
              [u.session_id]: { ...(prev[u.session_id] || {}), ...u },
            }))

            setMemSessions((prev) => (prev.includes(u.session_id) ? prev : [u.session_id, ...prev]))

            // Handle live new evidence frame
            if ((u as any).type === "new_evidence_frame" && (u as any).image_data) {
              const frameItem: CapturedImage = {
                image_data: (u as any).image_data,
                label: (u as any).label || "Evidence Frame",
                timestamp: (u as any).timestamp || new Date().toISOString(),
                source: (u as any).source || "snapshot",
                scene: (u as any).scene || "general",
                observations: (u as any).observations || [],
              }
              setLiveUpdates((prev) => {
                const cur = prev[u.session_id] || {}
                const existingImages = cur.captured_images || []
                return {
                  ...prev,
                  [u.session_id]: {
                    ...cur,
                    captured_images: [...existingImages, frameItem],
                  },
                }
              })
              recordTimelineEvent(u.session_id, {
                title: `Visual Evidence Received (${(u as any).source === "upload" ? "Uploaded Image" : "Snapshot"})`,
                description: `Scene: ${(u as any).scene || "General"}${(u as any).observations?.length ? ` • ${(u as any).observations.length} AI observation(s)` : ""}`,
                type: "system",
              })
            }

            // Record contextual milestones in timeline
            if (u.transcript) {
              recordTimelineEvent(u.session_id, {
                title: "Caller Utterance Received",
                description: `"${u.transcript.slice(0, 70)}${u.transcript.length > 70 ? "..." : ""}"`,
                type: "speech",
              })
            }
            if (u.severity) {
              recordTimelineEvent(u.session_id, {
                title: `Severity Evaluated: ${u.severity}`,
                description: u.score != null ? `Score ${u.score}/10` : undefined,
                type: "severity",
              })
            }
            if (u.current_question) {
              recordTimelineEvent(u.session_id, {
                title: "AI Question Emitted",
                description: u.current_question,
                type: "question",
              })
            }
            if (u.location) {
              recordTimelineEvent(u.session_id, {
                title: "Location Telemetry Updated",
                description: u.location_display || u.location,
                type: "location",
              })
            }
            if (u.selected_service) {
              recordTimelineEvent(u.session_id, {
                title: `Service Unit Targeted: ${u.selected_service.toUpperCase()}`,
                type: "service",
              })
            }
          } catch {
            /* ignore parse errors */
          }
        }
      } catch {
        if (isMounted) {
          setWsState("disconnected")
          reconnectTimeout = setTimeout(connectWebSocket, 3000)
        }
      }
    }

    connectWebSocket()

    return () => {
      isMounted = false
      clearTimeout(reconnectTimeout)
      clearInterval(pingInterval)
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [recordTimelineEvent])

  /* ── Fetch summary for selected session ── */
  const fetchSelectedSummary = useCallback(async () => {
    if (!selectedId) {
      setSummary(null)
      return
    }
    setLoading(true)
    try {
      const data = await api.getSummary(selectedId)
      setSummary(data)
    } catch {
      setSummary(null)
    } finally {
      setLoading(false)
    }
  }, [selectedId])

  useEffect(() => {
    fetchSelectedSummary()
  }, [fetchSelectedSummary])

  /* ── Auto-scroll chat box when new messages arrive ── */
  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight
    }
  }, [summary?.messages, liveUpdates[selectedId || ""]?.transcript])

  /* ── Speak / Audio Dispatch Replay ── */
  const handleSpeakClick = async () => {
    if (!selectedId) return
    const activeLive = liveUpdates[selectedId]
    const textToSpeak = activeLive?.guidance || summary?.guidance || activeLive?.summary || summary?.summary || activeLive?.current_question || summary?.current_question || ""
    if (!textToSpeak) return

    setIsSpeakerActive(true)
    try {
      const url = api.audioUrl(selectedId, language === "en" ? "en" : language, textToSpeak)
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

  /* ── Two-Way Dispatcher Spoken Voice Command ── */
  const handleSendDispatcherVoice = async () => {
    if (!selectedId || !dispatcherVoiceText.trim() || isSendingVoice) return
    setIsSendingVoice(true)
    const msg = dispatcherVoiceText.trim()
    try {
      const res = await api.sendDispatcherVoice(selectedId, msg, language)
      if (res.audio_base64) {
        const audio = new Audio(`data:audio/wav;base64,${res.audio_base64}`)
        audio.play().catch(() => {})
      }
      setVoiceSendSuccess(true)
      setTimeout(() => setVoiceSendSuccess(false), 3000)
      setDispatcherVoiceText("")
      recordTimelineEvent(selectedId, {
        title: "Dispatcher Spoken Instruction",
        description: `"${msg}"`,
        type: "system",
      })
      await fetchSelectedSummary()
    } catch {
      /* ignore */
    } finally {
      setIsSendingVoice(false)
    }
  }

  /* ── Delete / Archive Session ── */
  const handleDelete = async (sid: string) => {
    try {
      await api.deleteSession(sid)
      if (selectedId === sid) {
        const remaining = sessions.filter((s) => s.session_id !== sid)
        setSelectedId(remaining.length > 0 ? remaining[0].session_id : null)
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

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  // ── Combined Active Incident Data (Merged Summary + Live WebSocket) ──
  const activeLive = selectedId ? liveUpdates[selectedId] : undefined
  const activeSessionItem = sessions.find((s) => s.session_id === selectedId)

  const activeEmergencyType = activeLive?.emergency_type || summary?.emergency_type || activeSessionItem?.emergency_type || "Emergency Incident"
  const activeStatus = (activeLive?.status || summary?.status || activeSessionItem?.status || "gathering_info").replace(/_/g, " ")
  const activeSelectedService = activeLive?.selected_service || summary?.selected_service || activeLive?.routed_service || summary?.routed_service || null
  const activeCasualties = activeLive?.casualties ?? summary?.casualties ?? null

  const callerLangCode = activeLive?.caller_language || summary?.detected_language || null
  const selectedLangCode = activeLive?.language || summary?.selected_language || language || "en"
  const langDisplayMap: Record<string, string> = {
    en: "English",
    ta: "Tamil",
    hi: "Hindi",
    te: "Telugu",
    kn: "Kannada",
    ml: "Malayalam",
  }
  const activeLanguage =
    callerLangCode && callerLangCode !== selectedLangCode
      ? `Caller: ${langDisplayMap[callerLangCode] || callerLangCode.toUpperCase()} ➔ CAD: ${langDisplayMap[selectedLangCode] || selectedLangCode.toUpperCase()}`
      : langDisplayMap[selectedLangCode]
      ? `${langDisplayMap[selectedLangCode]} (${selectedLangCode.toUpperCase()})`
      : selectedLangCode.toUpperCase()

  const activeTurnCount = activeLive?.turn_count ?? summary?.turn_count ?? activeSessionItem?.turn_count ?? 0

  // ── Severity & Risk Derivation ──
  const activeSeverityLabel = activeLive?.severity || summary?.priority_label || (summary?.priority ? (summary.priority === 1 ? "CRITICAL" : summary.priority === 2 ? "HIGH" : summary.priority === 3 ? "MEDIUM" : "LOW") : "MODERATE")
  const activeScore = activeLive?.score ?? summary?.priority_score ?? (summary?.priority ? 10 - summary.priority * 2 : null)
  const isRuleAiAgreed = activeScore != null && activeSeverityLabel !== "LOW"

  // ── Current AI Follow-up Question ──
  const activeQuestion = activeLive?.current_question || summary?.current_question || null

  // ── Location Derivation ──
  const activeLocation = activeLive?.location_display || activeLive?.location || summary?.location_display || summary?.location || activeSessionItem?.location || null
  const activeLat = activeLive?.latitude ?? summary?.latitude ?? null
  const activeLon = activeLive?.longitude ?? summary?.longitude ?? null
  const activeAccuracy = activeLive?.location_accuracy ?? summary?.location_accuracy ?? null
  const activeLocSource = activeLive?.location_source ?? summary?.location_source ?? (activeLat ? "GPS" : null)

  // ── Information Completeness Checklist ──
  const completenessItems = useMemo(() => {
    const known = { ...(summary?.known_facts || {}), ...(activeLive?.known_facts || {}) }
    const detailsText = (summary?.details || "") + " " + (activeLive?.summary || "") + " " + (summary?.summary || "")

    return [
      {
        id: "loc",
        label: "Location Coordinates / Landmark",
        status: activeLocation ? "available" : "missing",
        value: activeLocation || "Pending caller/GPS",
      },
      {
        id: "casualties",
        label: "Number of People Affected",
        status: activeCasualties != null ? "available" : "unknown",
        value: activeCasualties != null ? `${activeCasualties} person(s)` : "Awaiting count",
      },
      {
        id: "conscious",
        label: "Consciousness State",
        status: "conscious" in known || /conscious|unconscious/i.test(detailsText) ? "available" : "unknown",
        value: known.conscious === false || /unconscious/i.test(detailsText) ? "Unconscious" : known.conscious === true || /conscious/i.test(detailsText) ? "Conscious" : "Awaiting confirmation",
      },
      {
        id: "breathing",
        label: "Breathing Condition",
        status: "breathing" in known || /breathing|breath/i.test(detailsText) ? "available" : "unknown",
        value: known.breathing === false || /not breathing|cannot breathe|no breath/i.test(detailsText) ? "Difficulty / Not Breathing" : /breathing/i.test(detailsText) ? "Breathing reported" : "Awaiting confirmation",
      },
      {
        id: "injury",
        label: "Injury & Trauma",
        status: "injuries" in known || /injured|injury|hurt|wound|burn|fracture/i.test(detailsText) ? "available" : "unknown",
        value: known.injuries ? String(known.injuries) : /injured|wound|burn/i.test(detailsText) ? "Injuries reported" : "Awaiting report",
      },
      {
        id: "bleeding",
        label: "Bleeding Status",
        status: "bleeding" in known || /bleeding|bleed|blood/i.test(detailsText) ? "available" : "unknown",
        value: /heavy bleeding|severe bleed|uncontrolled/i.test(detailsText) ? "Severe Uncontrolled Bleeding" : /bleeding/i.test(detailsText) ? "Bleeding reported" : "None / Unconfirmed",
      },
      {
        id: "danger",
        label: "Immediate Hazard / Danger",
        status: "hazards" in known || /fire|smoke|trapped|hazard|collapse|spill|threat/i.test(detailsText) ? "available" : "unknown",
        value: known.hazards ? String(known.hazards) : /fire|smoke|trapped/i.test(detailsText) ? "Active Hazard Present" : "Clear / None reported",
      },
    ]
  }, [activeLocation, activeCasualties, summary, activeLive])

  const availableCount = completenessItems.filter((item) => item.status === "available").length
  const completenessPercent = Math.round((availableCount / completenessItems.length) * 100)

  // ── Live Conversation Deduplication ──
  const conversationMessages = useMemo(() => {
    const rawMessages: ChatMessage[] = summary?.messages || []
    const deduped: { role: "caller" | "ai"; content: string; key: string }[] = []
    const seen = new Set<string>()

    for (let i = 0; i < rawMessages.length; i++) {
      const m = rawMessages[i]
      const cleanContent = m.content.trim()
      if (!cleanContent) continue
      const isCaller = m.type === "human" || m.type === "caller" || m.type === "user"
      const role = isCaller ? "caller" : "ai"
      const signature = `${role}:${cleanContent}`

      if (!seen.has(signature)) {
        seen.add(signature)
        deduped.push({
          role,
          content: cleanContent,
          key: `msg_${i}_${signature.slice(0, 20)}`,
        })
      }
    }

    // Append latest live transcript if not already present
    if (activeLive?.transcript && activeLive.transcript.trim()) {
      const liveText = activeLive.transcript.trim()
      const liveSig = `caller:${liveText}`
      if (!seen.has(liveSig)) {
        deduped.push({
          role: "caller",
          content: liveText,
          key: `live_caller_${Date.now()}`,
        })
      }
    }

    return deduped
  }, [summary?.messages, activeLive?.transcript])

  // ── Visual Evidence & Sensor Telemetry ──
  const evidenceImages: CapturedImage[] = (summary?.captured_images?.length ? summary.captured_images : activeLive?.captured_images) || []
  const evidenceVideos: VideoEvidence[] = (summary?.video_evidence?.length ? summary.video_evidence : activeLive?.video_evidence) || []
  const sensorData = activeLive?.sensor_telemetry || summary?.sensor_telemetry || null

  const activeMilestones: TimelineEvent[] = (selectedId && timelineEvents[selectedId]) || [
    {
      id: "init",
      time: "Live CAD",
      title: "Active Incident Session Connected",
      description: `Session ID: ${selectedId || "Pending"}`,
      type: "start",
    },
  ]

  const persistedIds = new Set(sessions.map((s) => s.session_id))
  const memoryOnlyIds = memSessions.filter((id) => !persistedIds.has(id))
  const allSessionIds = [...sessions.map((s) => s.session_id), ...memoryOnlyIds]

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-blue-600 selection:text-white">
      {/* ── Top-Level Navigation Bar / CAD Status Header ── */}
      <header className="border-b border-white/10 bg-slate-900/90 backdrop-blur-md sticky top-0 z-40 px-4 md:px-8 py-3.5 flex flex-wrap items-center justify-between gap-3 shadow-md">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-red-600/20 text-red-400 border border-red-500/30 shadow-inner">
            <Radio className="h-5 w-5 animate-pulse text-red-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base md:text-lg font-black uppercase tracking-wider text-white">
                LifeLine-Core CAD Dispatcher
              </h1>
              <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30">
                PRO CONSOLE
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Autonomous AI Emergency Call Triage & Real-Time CAD Monitoring
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          {/* Connection Status Badge */}
          <div
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-bold font-mono uppercase tracking-wider shadow-sm",
              wsState === "connected"
                ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-400"
                : wsState === "connecting"
                  ? "bg-yellow-500/15 border-yellow-500/30 text-yellow-400 animate-pulse"
                  : "bg-red-500/15 border-red-500/30 text-red-400"
            )}
            title="Real-Time Dispatcher WebSocket Connection State"
          >
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                wsState === "connected"
                  ? "bg-emerald-400 shadow-[0_0_8px_#10b981]"
                  : wsState === "connecting"
                    ? "bg-yellow-400 shadow-[0_0_8px_#eab308]"
                    : "bg-red-500 shadow-[0_0_8px_#ef4444]"
              )}
            />
            {wsState === "connected" ? "LIVE CAD" : wsState === "connecting" ? "RECONNECTING" : "DISCONNECTED"}
          </div>

          <button
            onClick={fetchSessions}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white border border-white/10 text-xs font-bold transition-colors"
            title="Refresh Incident Session Feed"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>

          <LanguageSelector />
        </div>
      </header>

      {/* ── Active Incident Switcher Bar ── */}
      <div className="bg-slate-900/60 border-b border-white/5 px-4 md:px-8 py-2.5 flex items-center gap-2 overflow-x-auto">
        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 shrink-0 mr-2">
          <Layers className="h-3.5 w-3.5 text-blue-400" />
          Active Incidents ({allSessionIds.length}):
        </span>

        {allSessionIds.length === 0 ? (
          <span className="text-xs text-slate-500 italic">No live emergency calls in progress</span>
        ) : (
          allSessionIds.map((sid) => {
            const isSelected = selectedId === sid
            const sItem = sessions.find((s) => s.session_id === sid)
            const live = liveUpdates[sid]
            const type = live?.emergency_type || sItem?.emergency_type || "Emergency Call"
            const prio = live?.score ? (live.score >= 8 ? "CRITICAL" : live.score >= 5 ? "HIGH" : "MEDIUM") : sItem?.priority ? priorityLabel(sItem.priority) : "P1"

            return (
              <button
                key={sid}
                onClick={() => setSelectedId(sid)}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-bold transition-all shrink-0 border",
                  isSelected
                    ? "bg-blue-600 border-blue-400 text-white shadow-lg ring-2 ring-blue-500/30"
                    : "bg-white/5 hover:bg-white/10 border-white/10 text-slate-300"
                )}
              >
                <span className={cn(
                  "h-2 w-2 rounded-full",
                  prio.includes("CRIT") ? "bg-red-400" : prio.includes("HIGH") ? "bg-orange-400" : "bg-yellow-400"
                )} />
                <span className="truncate max-w-[140px]">{type}</span>
                <span className="font-mono text-[10px] opacity-70">#{sid.slice(0, 6)}</span>
              </button>
            )
          })
        )}
      </div>

      {/* ── Main Dispatcher Work Area ── */}
      <main className="flex-1 p-4 md:p-6 max-w-7xl w-full mx-auto grid grid-cols-1 lg:grid-cols-12 gap-5">
        {!selectedId ? (
          <div className="lg:col-span-12 py-20 flex flex-col items-center justify-center text-center glass rounded-3xl border border-white/10 p-8 shadow-2xl">
            <Radio className="h-16 w-16 text-slate-600 mb-4 animate-pulse" />
            <h3 className="text-xl font-bold text-white mb-2">Awaiting Emergency Incident Data</h3>
            <p className="text-sm text-slate-400 max-w-md">
              The CAD Console is listening on the real-time WebSocket. When a caller initiates a voice or text emergency call from /user, it will immediately appear here for live monitoring.
            </p>
          </div>
        ) : (
          <>
            {/* ═══════════════════════════════════════════════
                LEFT COLUMN: Incident Overview, Severity, Summary, Completeness (7 cols)
               ═══════════════════════════════════════════════ */}
            <div className="lg:col-span-7 flex flex-col gap-5">
              {/* ── SECTION B: ACTIVE INCIDENT OVERVIEW ── */}
              <div className="bg-slate-900/90 border border-white/10 rounded-2xl p-5 shadow-xl">
                <div className="flex items-center justify-between border-b border-white/10 pb-3 mb-4 flex-wrap gap-2">
                  <div className="flex items-center gap-2.5">
                    <span className="p-2 rounded-xl bg-blue-600/20 text-blue-400 border border-blue-500/30">
                      <Shield className="h-4 w-4" />
                    </span>
                    <div>
                      <h2 className="text-sm font-black uppercase tracking-wider text-white flex items-center gap-2">
                        Active Incident Dossier
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/10 text-slate-300">
                          {selectedId}
                        </span>
                      </h2>
                      <p className="text-xs text-slate-400">Live Telemetry & Triage Stream</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleCopy(selectedId, "sid")}
                      className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-slate-300 text-xs transition-colors flex items-center gap-1"
                      title="Copy Session ID"
                    >
                      {copiedId === "sid" ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
                      <span className="text-[10px]">Copy ID</span>
                    </button>
                    <button
                      onClick={() => handleDelete(selectedId)}
                      className="p-1.5 rounded-lg bg-red-600/20 hover:bg-red-600/40 text-red-300 border border-red-500/30 text-xs transition-colors flex items-center gap-1"
                      title="Archive / Close Session"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      <span className="text-[10px]">Close</span>
                    </button>
                  </div>
                </div>

                {/* Grid Overview Cards */}
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                  <div className="bg-black/30 border border-white/5 rounded-xl p-3">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                      Incident Category
                    </span>
                    <span className="text-sm font-black text-white block truncate">{activeEmergencyType}</span>
                  </div>

                  <div className="bg-black/30 border border-white/5 rounded-xl p-3">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                      Triage Status
                    </span>
                    <span className={cn(
                      "text-xs font-bold uppercase px-2 py-0.5 rounded-md inline-block border",
                      statusStyle(activeStatus.replace(/ /g, "_"))
                    )}>
                      {activeStatus}
                    </span>
                  </div>

                  <div className="bg-black/30 border border-white/5 rounded-xl p-3">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                      Target Service
                    </span>
                    <span className="text-xs font-bold text-amber-300 flex items-center gap-1">
                      <Truck className="h-3.5 w-3.5 text-amber-400" />
                      {activeSelectedService ? activeSelectedService.toUpperCase() : "Awaiting Selection"}
                    </span>
                  </div>

                  <div className="bg-black/30 border border-white/5 rounded-xl p-3">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                      Affected Casualties
                    </span>
                    <span className="text-xs font-bold text-white flex items-center gap-1">
                      <Users className="h-3.5 w-3.5 text-slate-400" />
                      {activeCasualties != null ? `${activeCasualties} Person(s)` : "Not Reported"}
                    </span>
                  </div>

                  <div className="bg-black/30 border border-white/5 rounded-xl p-3">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                      Spoken Language
                    </span>
                    <span className="text-xs font-bold text-slate-200 uppercase font-mono">
                      {activeLanguage}
                    </span>
                  </div>

                  <div className="bg-black/30 border border-white/5 rounded-xl p-3">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                      Conversation Turns
                    </span>
                    <span className="text-xs font-bold text-slate-200 font-mono">
                      {activeTurnCount} turn(s) processed
                    </span>
                  </div>
                </div>
              </div>

              {/* ── SECTION C: SEVERITY / RISK CARD ── */}
              <div className="bg-slate-900/90 border border-white/10 rounded-2xl p-5 shadow-xl">
                <div className="flex items-center justify-between border-b border-white/10 pb-3 mb-4">
                  <div className="flex items-center gap-2">
                    <Activity className="h-4 w-4 text-red-400" />
                    <h3 className="text-xs font-black uppercase tracking-wider text-white">
                      Severity & Risk Assessment
                    </h3>
                  </div>
                  {/* Fake call / Authenticity badge */}
                  {(activeLive?.fake_label || summary?.fake_label) && (
                    <span className={cn(
                      "text-[10px] font-black uppercase px-2.5 py-0.5 rounded-full border flex items-center gap-1",
                      (activeLive?.fake_label || summary?.fake_label) === "GENUINE"
                        ? "bg-green-500/15 border-green-500/30 text-green-300"
                        : (activeLive?.fake_label || summary?.fake_label) === "LIKELY_FAKE"
                          ? "bg-red-500/20 border-red-500/40 text-red-300"
                          : "bg-yellow-500/20 border-yellow-500/40 text-yellow-300"
                    )}>
                      <AlertTriangle className="h-3 w-3" />
                      {activeLive?.fake_label || summary?.fake_label}
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-center">
                  <div className="flex flex-col gap-1 p-3.5 bg-black/40 border border-white/10 rounded-xl">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Triage Category
                    </span>
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        "text-xl font-black font-mono tracking-tight",
                        activeSeverityLabel.includes("CRITICAL") ? "text-red-400 animate-pulse" : activeSeverityLabel.includes("HIGH") ? "text-orange-400" : activeSeverityLabel.includes("MEDIUM") ? "text-yellow-400" : "text-green-400"
                      )}>
                        {activeSeverityLabel}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400 font-mono">
                      Risk Score: {activeScore != null ? `${activeScore} / 10` : "Assessed by AI & Rules"}
                    </span>
                  </div>

                  <div className="sm:col-span-2 flex flex-col gap-2 p-3.5 bg-black/40 border border-white/10 rounded-xl text-xs">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Evaluation Consensus & Factors
                    </span>
                    <p className="text-slate-300 text-xs leading-relaxed">
                      {isRuleAiAgreed ? (
                        <span className="text-emerald-300 font-medium">
                          ✓ Rule-based deterministic keyword scoring ({activeScore}/10) & AI triage agree on high urgency.
                        </span>
                      ) : (
                        <span className="text-slate-300 font-medium">
                          Multi-factor triage evaluated from caller dialogue, symptoms, and live telemetry.
                        </span>
                      )}
                    </p>
                    {activeLive?.fake_signals && activeLive.fake_signals.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {activeLive.fake_signals.map((sig, idx) => (
                          <span key={idx} className="text-[10px] bg-red-500/20 text-red-300 border border-red-500/30 px-2 py-0.5 rounded-full">
                            {sig}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* ── SECTION D: INCIDENT SUMMARY ── */}
              <div className="bg-slate-900/90 border border-white/10 rounded-2xl p-5 shadow-xl">
                <div className="flex items-center justify-between border-b border-white/10 pb-3 mb-3">
                  <div className="flex items-center gap-2 text-slate-300">
                    <FileText className="h-4 w-4 text-blue-400" />
                    <h3 className="text-xs font-black uppercase tracking-wider text-white">
                      Structured Incident Summary Brief
                    </h3>
                  </div>
                  <span className="text-[10px] font-mono text-slate-400 uppercase">
                    AI Auto-Updating
                  </span>
                </div>

                <div className="bg-black/30 border border-white/5 rounded-xl p-4 text-xs leading-relaxed text-slate-200">
                  {activeLive?.summary || summary?.summary ? (
                    <p className="whitespace-pre-line font-medium text-slate-200">
                      {activeLive?.summary || summary?.summary}
                    </p>
                  ) : (
                    <p className="text-slate-500 italic">
                      Incident summary is generating dynamically as caller speaks...
                    </p>
                  )}
                </div>

                {/* Guidance Banner */}
                {(activeLive?.guidance || summary?.guidance) && (
                  <div className="mt-3 p-3.5 bg-emerald-950/30 border border-emerald-500/30 rounded-xl text-xs flex items-start gap-2.5">
                    <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
                    <div>
                      <span className="text-[10px] font-black uppercase tracking-wider text-emerald-400 block mb-0.5">
                        Active Guidance Provided to Caller
                      </span>
                      <p className="text-emerald-200 leading-relaxed">
                        {activeLive?.guidance || summary?.guidance}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* ── SECTION E: INFORMATION COMPLETENESS ── */}
              <div className="bg-slate-900/90 border border-white/10 rounded-2xl p-5 shadow-xl">
                <div className="flex items-center justify-between border-b border-white/10 pb-3 mb-3">
                  <div className="flex items-center gap-2">
                    <CheckSquare className="h-4 w-4 text-indigo-400" />
                    <h3 className="text-xs font-black uppercase tracking-wider text-white">
                      Information Completeness Matrix
                    </h3>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold font-mono text-indigo-300">
                      {completenessPercent}% Confirmed ({availableCount}/{completenessItems.length})
                    </span>
                  </div>
                </div>

                {/* Progress bar */}
                <div className="w-full bg-slate-800 rounded-full h-2 mb-4 overflow-hidden border border-white/10">
                  <div
                    className="bg-gradient-to-r from-blue-500 to-emerald-500 h-full transition-all duration-500 rounded-full"
                    style={{ width: `${completenessPercent}%` }}
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                  {completenessItems.map((item) => (
                    <div
                      key={item.id}
                      className={cn(
                        "p-2.5 rounded-xl border flex items-start gap-2 transition-colors",
                        item.status === "available"
                          ? "bg-emerald-950/20 border-emerald-500/30 text-slate-200"
                          : "bg-black/20 border-white/5 text-slate-400"
                      )}
                    >
                      {item.status === "available" ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
                      ) : (
                        <Circle className="h-4 w-4 text-amber-500/60 shrink-0 mt-0.5" />
                      )}
                      <div className="min-w-0 flex-1">
                        <p className="text-[10px] uppercase font-bold text-slate-400">{item.label}</p>
                        <p className="text-xs font-medium text-slate-200 truncate">{item.value}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* ═══════════════════════════════════════════════
                RIGHT COLUMN: Current Question, Live Conversation, Location, Evidence, Timeline (5 cols)
               ═══════════════════════════════════════════════ */}
            <div className="lg:col-span-5 flex flex-col gap-5">
              {/* ── SECTION G: CURRENT AI FOLLOW-UP QUESTION ── */}
              <div className="bg-slate-900/90 border border-blue-500/30 rounded-2xl p-5 shadow-xl ring-1 ring-blue-500/20">
                <div className="flex items-center justify-between border-b border-white/10 pb-2.5 mb-3">
                  <div className="flex items-center gap-2">
                    <HelpCircle className="h-4 w-4 text-blue-400 animate-bounce" />
                    <h3 className="text-xs font-black uppercase tracking-wider text-blue-300">
                      CURRENT AI QUESTION
                    </h3>
                  </div>
                  <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30">
                    Live Dispatch Question
                  </span>
                </div>

                <div className="bg-blue-950/40 border border-blue-500/30 rounded-xl p-4 mb-3">
                  <p className="text-sm font-bold text-blue-100 leading-relaxed">
                    {activeQuestion ? `"${activeQuestion}"` : `"Emergency service active. Please describe what happened."`}
                  </p>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-400">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-yellow-400 animate-pulse" />
                    Awaiting caller response...
                  </span>
                  <button
                    onClick={handleSpeakClick}
                    disabled={isSpeakerActive}
                    className="flex items-center gap-1 text-xs font-bold text-emerald-400 hover:text-emerald-300 transition-colors"
                  >
                    <Volume2 className="h-3.5 w-3.5" />
                    {isSpeakerActive ? "Playing..." : "Play TTS Audio"}
                  </button>
                </div>
              </div>

              {/* ── SECTION F: LIVE CONVERSATION (Caller vs AI Dispatcher) ── */}
              <div className="bg-slate-900/90 border border-white/10 rounded-2xl p-5 shadow-xl flex flex-col h-[380px]">
                <div className="flex items-center justify-between border-b border-white/10 pb-2.5 mb-3">
                  <div className="flex items-center gap-2 text-slate-300">
                    <MessageSquare className="h-4 w-4 text-red-400" />
                    <h3 className="text-xs font-black uppercase tracking-wider text-white">
                      Live Emergency Dialogue ({conversationMessages.length} Turns)
                    </h3>
                  </div>
                  <span className="text-[10px] font-mono text-slate-400">
                    Chronological Feed
                  </span>
                </div>

                <div
                  ref={chatScrollRef}
                  className="flex-1 overflow-y-auto space-y-2.5 pr-2"
                >
                  {conversationMessages.length === 0 ? (
                    <div className="h-full flex items-center justify-center text-center p-4 text-slate-500 italic text-xs">
                      No speech recorded yet. Dialogue will appear live as caller speaks.
                    </div>
                  ) : (
                    conversationMessages.map((msg) => (
                      <div
                        key={msg.key}
                        className={cn(
                          "p-3 rounded-xl text-xs leading-relaxed transition-all",
                          msg.role === "caller"
                            ? "bg-red-500/10 border-l-4 border-red-500 text-slate-200 ml-0 mr-4"
                            : "bg-blue-500/10 border-l-4 border-blue-500 text-slate-200 ml-4 mr-0"
                        )}
                      >
                        <div className="flex items-center justify-between mb-1 opacity-75">
                          <span className={cn(
                            "text-[10px] font-black uppercase tracking-wider",
                            msg.role === "caller" ? "text-red-400" : "text-blue-400"
                          )}>
                            {msg.role === "caller" ? "CALLER" : "AI DISPATCHER"}
                          </span>
                        </div>
                        <p className="font-medium text-slate-100">{msg.content}</p>
                      </div>
                    ))
                  )}
                </div>

                {/* Two-Way Dispatcher Spoken Input */}
                <div className="mt-3 pt-3 border-t border-white/10 flex flex-col gap-2">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Inject spoken instruction to caller..."
                      value={dispatcherVoiceText}
                      onChange={(e) => setDispatcherVoiceText(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleSendDispatcherVoice()}
                      className="flex-1 bg-black/40 border border-white/10 rounded-xl px-3 py-1.5 text-xs text-white outline-none focus:border-blue-500"
                    />
                    <button
                      onClick={handleSendDispatcherVoice}
                      disabled={!dispatcherVoiceText.trim() || isSendingVoice}
                      className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-all disabled:opacity-40 flex items-center gap-1 shrink-0"
                    >
                      {isSendingVoice ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                      Speak
                    </button>
                  </div>
                  {voiceSendSuccess && (
                    <span className="text-[10px] text-emerald-400 flex items-center gap-1 font-bold">
                      <CheckCircle2 className="h-3 w-3" /> Transmitted & synthesized in caller language!
                    </span>
                  )}
                </div>
              </div>

              {/* ── SECTION H: LOCATION ── */}
              <div className="bg-slate-900/90 border border-white/10 rounded-2xl p-5 shadow-xl">
                <div className="flex items-center justify-between border-b border-white/10 pb-2.5 mb-3">
                  <div className="flex items-center gap-2">
                    <MapPin className="h-4 w-4 text-emerald-400" />
                    <h3 className="text-xs font-black uppercase tracking-wider text-white">
                      Incident Location
                    </h3>
                  </div>
                  {activeLocSource && (
                    <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                      SOURCE: {activeLocSource.toUpperCase()}
                    </span>
                  )}
                </div>

                <div className="bg-black/30 border border-white/5 rounded-xl p-3.5 mb-3 text-xs">
                  {activeLocation ? (
                    <div>
                      <p className="text-sm font-bold text-white flex items-start gap-1.5">
                        <MapPin className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
                        {activeLocation}
                      </p>
                      <div className="grid grid-cols-2 gap-2 mt-2 pt-2 border-t border-white/5 font-mono text-[11px] text-slate-400">
                        <span>Lat/Lon: {activeLat != null && activeLon != null ? `${activeLat.toFixed(5)}, ${activeLon.toFixed(5)}` : "Approximate"}</span>
                        <span>Accuracy: {activeAccuracy != null ? `± ${Math.round(activeAccuracy)} m` : "Normal"}</span>
                      </div>
                    </div>
                  ) : (
                    <p className="text-slate-500 italic">Location awaiting GPS lock or caller report</p>
                  )}
                </div>

                {activeLat != null && activeLon != null && (
                  <a
                    href={`https://www.google.com/maps?q=${activeLat},${activeLon}`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-center gap-1.5 w-full py-2 rounded-xl bg-white/5 hover:bg-white/10 text-emerald-400 border border-emerald-500/30 text-xs font-bold transition-colors"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Open Coordinates in Google Maps
                  </a>
                )}
              </div>

              {/* ── SECTION I: EVIDENCE & TELEMETRY ── */}
              <div className="bg-slate-900/90 border border-white/10 rounded-2xl p-5 shadow-xl">
                <div className="flex items-center justify-between border-b border-white/10 pb-2.5 mb-3">
                  <div className="flex items-center gap-2">
                    <Film className="h-4 w-4 text-purple-400" />
                    <h3 className="text-xs font-black uppercase tracking-wider text-white">
                      Field Evidence & Biometric Telemetry
                    </h3>
                  </div>
                </div>

                {/* Biometric Telemetry */}
                {sensorData ? (
                  <div className="mb-4 p-3 bg-red-950/20 border border-red-500/30 rounded-xl flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2.5">
                      <Heart className="h-5 w-5 text-red-500 animate-pulse" />
                      <div>
                        <span className="text-[10px] font-bold uppercase text-slate-400 block">
                          Bluetooth Sensor Live
                        </span>
                        <span className="text-sm font-black font-mono text-white">
                          {sensorData.heart_rate != null ? `${sensorData.heart_rate} BPM` : "Connected"}
                        </span>
                      </div>
                    </div>
                    {sensorData.spo2 != null && (
                      <span className="text-xs font-bold font-mono text-blue-300">
                        SpO2: {sensorData.spo2}%
                      </span>
                    )}
                  </div>
                ) : null}

                {/* Evidence Media Frames & Videos */}
                {evidenceImages.length === 0 && evidenceVideos.length === 0 && !sensorData ? (
                  <p className="text-xs text-slate-500 italic p-3 bg-black/20 rounded-xl text-center">
                    No live camera or sensor telemetry received yet
                  </p>
                ) : (
                  <div className="space-y-3">
                    {/* Evidence Media Frames & Uploads */}
                    {evidenceImages.length > 0 && (
                      <div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-2">
                          Visual Evidence & Observations ({evidenceImages.length})
                        </span>
                        <div className="space-y-3">
                          {evidenceImages.map((img, i) => {
                            const isUpload = img.source === "upload"
                            const sourceLabel = isUpload ? "Uploaded Image" : "Snapshot"
                            const sceneLabel = img.scene ? img.scene.replace(/_/g, " ") : "General"
                            return (
                              <div
                                key={i}
                                className="p-3 bg-black/40 border border-white/10 rounded-xl flex flex-col gap-2.5"
                              >
                                <div className="flex items-center justify-between text-[10px] font-mono">
                                  <span
                                    className={cn(
                                      "px-2 py-0.5 rounded font-bold uppercase border",
                                      isUpload
                                        ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                                        : "bg-blue-500/20 text-blue-300 border-blue-500/30"
                                    )}
                                  >
                                    Source: {sourceLabel}
                                  </span>
                                  <span className="text-slate-400 uppercase font-semibold">
                                    Scene: {sceneLabel}
                                  </span>
                                </div>

                                <div
                                  onClick={() => setPreviewImage(img)}
                                  className="aspect-video rounded-lg overflow-hidden border border-white/10 cursor-pointer hover:border-blue-400 transition-colors bg-black"
                                >
                                  <img
                                    src={img.image_data}
                                    alt={`Evidence ${i}`}
                                    className="w-full h-full object-cover"
                                  />
                                </div>

                                {img.observations && img.observations.length > 0 && (
                                  <div className="bg-slate-900/80 border border-indigo-500/30 rounded-lg p-2.5 space-y-1.5 text-xs">
                                    <div className="flex items-center gap-1.5 text-indigo-300 font-bold text-[10px] uppercase tracking-wider">
                                      <Sparkles className="h-3 w-3 text-indigo-400" />
                                      <span>AI Visual Observations</span>
                                    </div>
                                    <ul className="space-y-1.5 text-slate-200 text-xs">
                                      {img.observations.map((obs, oIdx) => (
                                        <li key={oIdx} className="flex flex-col gap-0.5">
                                          <div className="flex items-start gap-1.5">
                                            <span className="text-indigo-400 font-bold">•</span>
                                            <span className="font-semibold text-slate-100">{obs.label}</span>
                                            {obs.confidence != null && (
                                              <span className="text-[10px] font-mono text-indigo-300 bg-indigo-950/60 px-1.5 py-0.2 rounded border border-indigo-500/30">
                                                {Math.round(obs.confidence <= 1 ? obs.confidence * 100 : obs.confidence)}%
                                              </span>
                                            )}
                                          </div>
                                          {obs.description && obs.description !== obs.label && (
                                            <p className="text-[11px] text-slate-400 pl-3.5 leading-relaxed">
                                              {obs.description}
                                            </p>
                                          )}
                                        </li>
                                      ))}
                                    </ul>
                                    <div className="text-[10px] text-amber-300 flex items-center gap-1 pt-1 border-t border-white/5">
                                      <AlertTriangle className="h-3 w-3 text-amber-400 shrink-0" />
                                      <span>⚠ AI observation — dispatcher verification required</span>
                                    </div>
                                  </div>
                                )}
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )}

                    {/* Videos */}
                    {evidenceVideos.length > 0 && (
                      <div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1.5">
                          Recorded Video Clips ({evidenceVideos.length})
                        </span>
                        <div className="space-y-2">
                          {evidenceVideos.map((vid, i) => (
                            <div key={i} className="p-2 bg-black/40 border border-white/10 rounded-xl flex flex-col gap-1.5">
                              <div className="flex justify-between text-[10px] text-slate-400 font-mono">
                                <span>{vid.category.toUpperCase()}</span>
                                <span>{vid.duration_seconds}s</span>
                              </div>
                              {vid.video_data && (
                                <video src={vid.video_data} controls className="w-full rounded aspect-video bg-black" />
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* ── SECTION J: INCIDENT TIMELINE ── */}
              <div className="bg-slate-900/90 border border-white/10 rounded-2xl p-5 shadow-xl">
                <div className="flex items-center justify-between border-b border-white/10 pb-2.5 mb-3">
                  <div className="flex items-center gap-2">
                    <Clock className="h-4 w-4 text-cyan-400" />
                    <h3 className="text-xs font-black uppercase tracking-wider text-white">
                      Incident Milestone Timeline
                    </h3>
                  </div>
                </div>

                <div className="space-y-2.5 max-h-56 overflow-y-auto pr-1">
                  {activeMilestones.map((item) => (
                    <div
                      key={item.id}
                      className="text-xs p-2 rounded-xl bg-black/30 border border-white/5 flex items-start gap-2.5"
                    >
                      <span className="text-[10px] font-mono text-cyan-400 mt-0.5 shrink-0">
                        {item.time}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="font-bold text-slate-200">{item.title}</p>
                        {item.description && (
                          <p className="text-[11px] text-slate-400 truncate">{item.description}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}
      </main>

      {/* ── Image Full-View Modal ── */}
      {previewImage && (
        <div
          onClick={() => setPreviewImage(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm p-4 cursor-pointer"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="relative max-w-3xl w-full max-h-[90vh] overflow-y-auto rounded-2xl border border-white/20 bg-slate-900 shadow-2xl p-4 flex flex-col gap-3"
          >
            <div className="flex items-center justify-between pb-2 border-b border-white/10">
              <div className="flex items-center gap-2">
                <ImageIcon className="h-4 w-4 text-emerald-400" />
                <span className="text-xs font-bold uppercase tracking-wider text-white">
                  Visual Evidence Detail
                </span>
                {typeof previewImage === "object" && previewImage.source && (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 uppercase">
                    {previewImage.source}
                  </span>
                )}
                {typeof previewImage === "object" && previewImage.scene && (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/10 text-slate-300 border border-white/10 uppercase">
                    Scene: {previewImage.scene}
                  </span>
                )}
              </div>
              <button
                onClick={() => setPreviewImage(null)}
                className="rounded-full bg-black/70 p-1.5 text-white/80 hover:text-white hover:bg-black/90 transition-colors"
              >
                ✕
              </button>
            </div>

            <div className="rounded-xl overflow-hidden bg-black max-h-[55vh] flex items-center justify-center">
              <img
                src={typeof previewImage === "string" ? previewImage : previewImage.image_data}
                alt="Full Evidence"
                className="max-h-[55vh] w-auto object-contain"
              />
            </div>

            {typeof previewImage === "object" && previewImage.observations && previewImage.observations.length > 0 && (
              <div className="bg-slate-950/80 border border-indigo-500/30 rounded-xl p-3 space-y-2 text-xs">
                <div className="flex items-center gap-1.5 text-indigo-300 font-bold uppercase tracking-wider text-[11px]">
                  <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
                  <span>AI VISUAL OBSERVATIONS</span>
                </div>
                <ul className="space-y-2 text-slate-200">
                  {previewImage.observations.map((obs, idx) => (
                    <li key={idx} className="flex flex-col gap-0.5">
                      <div className="flex items-start gap-1.5">
                        <span className="text-indigo-400 font-bold">•</span>
                        <span className="font-semibold text-slate-100">{obs.label}</span>
                        {obs.confidence != null && (
                          <span className="text-[10px] font-mono text-indigo-300 bg-indigo-950/60 px-1.5 py-0.2 rounded border border-indigo-500/30">
                            {Math.round(obs.confidence <= 1 ? obs.confidence * 100 : obs.confidence)}%
                          </span>
                        )}
                      </div>
                      {obs.description && obs.description !== obs.label && (
                        <p className="text-[11px] text-slate-400 pl-3.5 leading-relaxed">
                          {obs.description}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
                <p className="text-[11px] text-amber-300 flex items-center gap-1.5 pt-1 border-t border-white/5">
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                  ⚠ AI observation — dispatcher verification required
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
