import { useState, useRef, useEffect, useCallback } from "react"
import {
  Mic,
  Video,
  Volume2,
  MapPin,
  X,
  Ambulance,
  Shield,
  Flame,
  LifeBuoy,
  PlusCircle,
  Send,
  Loader2,
  AlertTriangle,
  Bluetooth
} from "lucide-react"
import type { IncidentData, TranscriptEntry } from "../types"
import { api } from "../lib/api"
import { AudioStream } from "../lib/audioStream"
import { detectLocation } from "../lib/location"
import { cn, genId } from "../lib/utils"
import { useLanguage } from "../context/LanguageContext"
import { translations } from "../i18n/translations"
import { ControlButton } from "../components/ControlButton"
import { LanguageSelector } from "../components/LanguageSelector"
import { SummaryPanel } from "../components/SummaryPanel"
import LiveTranscript from "../components/LiveTranscript"
import GuidancePanel from "../components/GuidancePanel"

export default function CallPage() {
  const { language } = useLanguage()
  const t = translations[language] ?? translations.en

  const [sessionId] = useState(genId)
  const [isMicActive, setIsMicActive] = useState(false)
  const [isSpeakerActive, setIsSpeakerActive] = useState(false)
  const [isBluetoothActive, setIsBluetoothActive] = useState(false) // new
  const [isSending, setIsSending] = useState(false)
  const [selectedService, setSelectedService] = useState<string | null>(null)
  const [showVideo, setShowVideo] = useState(false)
  const [location, setLocation] = useState("Awaiting location...")
  const [isLocating, setIsLocating] = useState(false)
  const [textInput, setTextInput] = useState("")
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([])
  const [incident, setIncident] = useState<IncidentData | null>(null)
  const [guidance, setGuidance] = useState<string | null>(null)
  const [fakeLabel, setFakeLabel] = useState<string | null>(null)
  const [fakeProbability, setFakeProbability] = useState<number | null>(null)
  const [fakeSignals, setFakeSignals] = useState<string[]>([])

  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<AudioStream | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  /* ── Helpers ── */
  const addEntry = useCallback(
    (role: TranscriptEntry["role"], text: string) =>
      setTranscript((p) => [...p, { role, text, timestamp: Date.now() }]),
    [],
  )

  const playTTS = useCallback(async () => {
    try {
      const url = api.audioUrl(sessionId, language === "en" ? "en" : language)
      const audio = new Audio(url)
      audioRef.current = audio
      setIsSpeakerActive(true)
      await new Promise<void>((resolve) => {
        audio.onended = () => resolve()
        audio.onerror = () => resolve()
        audio.play().catch(() => resolve())
      })
    } finally {
      setIsSpeakerActive(false)
      audioRef.current = null
    }
  }, [sessionId, language])

  const fetchStatus = useCallback(async () => {
    try {
      const s = await api.getStatus(sessionId)
      setIncident(s.incident)
      if (s.incident.guidance) setGuidance(s.incident.guidance)
      // Track fake call detection
      if (s.incident.fake_label) setFakeLabel(s.incident.fake_label)
      if (s.incident.fake_probability != null) setFakeProbability(s.incident.fake_probability)
      if (s.incident.fake_signals?.length) setFakeSignals(s.incident.fake_signals)
    } catch {
      /* session might not exist yet */
    }
  }, [sessionId])

  /* ── Emergency service selection ── */
  const handleEmergencySelection = (service: string) => {
    setSelectedService(service)
  }

  /* ── Speaker: play latest AI question ── */
  const handleSpeakerClick = async () => {
    setIsSpeakerActive(true)
    try {
      await playTTS()
    } finally {
      setIsSpeakerActive(false)
    }
  }

  /* ── Bluetooth toggle ── */
  const handleBluetoothClick = () => {
    setIsBluetoothActive((prev) => !prev)
    addEntry("system", `Bluetooth ${!isBluetoothActive ? "enabled" : "disabled"}`)
  }

  /* ── Location ── */
  const handleLocationClick = async () => {
    setIsLocating(true)
    try {
      const addr = await detectLocation()
      setLocation(addr)
    } catch {
      setLocation("Location denied or unavailable")
    } finally {
      setIsLocating(false)
    }
  }

  /* ── Video ── */
  const startVideo = async () => {
    setShowVideo(true)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false,
      })
      if (videoRef.current) videoRef.current.srcObject = stream
    } catch {
      setShowVideo(false)
    }
  }

  const stopVideo = () => {
    if (videoRef.current?.srcObject) {
      const stream = videoRef.current.srcObject as MediaStream
      stream.getTracks().forEach((tr) => tr.stop())
    }
    setShowVideo(false)
  }

  /* ── Mic: WebSocket audio streaming ── */
  const toggleMic = async () => {
    if (isMicActive) {
      streamRef.current?.stop()
      streamRef.current = null
      setIsMicActive(false)
      return
    }

    const stream = new AudioStream(sessionId, {
      onConnected: () => {
        setIsMicActive(true)
        addEntry("system", "Connected — speak now, AI is listening...")
      },
      onTranscript: (text) => addEntry("caller", text),
      onProcessing: () => addEntry("system", "Processing your message..."),
      onQuestion: async (text, g, status, pScore, pLabel, fLabel, fProb, fSignals) => {
        if (text) {
          addEntry("ai", text)
          await playTTS()
        }
        if (g) setGuidance(g)
        // Update incident with priority data from WebSocket immediately
        if (pScore != null || pLabel) {
          setIncident((prev) =>
            prev
              ? { ...prev, priority_score: pScore ?? prev.priority_score, priority_label: pLabel ?? prev.priority_label }
              : prev,
          )
        }
        // Update fake call detection data from WebSocket immediately
        if (fLabel) setFakeLabel(fLabel)
        if (fProb != null) setFakeProbability(fProb)
        if (fSignals?.length) setFakeSignals(fSignals)
        void fetchStatus()
        if (status === "ready_to_dispatch") {
          setSelectedService(null)
        }
      },
      onDisconnected: () => setIsMicActive(false),
      onError: (msg) => {
        addEntry("system", `Error: ${msg}`)
        setIsMicActive(false)
      },
    }, language)

    try {
      await stream.start()
      streamRef.current = stream
    } catch {
      addEntry("system", "Mic access denied. Use text input.")
    }
  }

  /* ── Text message (REST fallback) ── */
  const sendText = async () => {
    const msg = textInput.trim()
    if (!msg || isSending) return

    setTextInput("")
    setIsSending(true)
    addEntry("caller", msg)

    try {
      const fullMsg =
        !incident && location !== "Awaiting location..."
          ? `${msg} [Location: ${location}]`
          : msg
      await api.sendMessage(sessionId, fullMsg)

      const [q] = await Promise.all([api.getQuestion(sessionId), fetchStatus()])
      if (q.question) {
        addEntry("ai", q.question)
        await playTTS()
      }
      if (q.guidance) setGuidance(q.guidance)
    } catch (err) {
      addEntry(
        "system",
        `Error: ${err instanceof Error ? err.message : "Unknown error"}`,
      )
    } finally {
      setIsSending(false)
    }
  }

  /* ── Detect location on mount ── */
  useEffect(() => {
    detectLocation()
      .then(setLocation)
      .catch(() => setLocation("Location unavailable"))
  }, [])

  /* ── Reconnect WebSocket when language changes while mic is active ── */
  useEffect(() => {
    if (isMicActive && streamRef.current) {
      streamRef.current.stop()
      streamRef.current = null
      setIsMicActive(false)
      addEntry("system", `Language changed — reconnecting...`)
      const timer = setTimeout(() => void toggleMic(), 400)
      return () => clearTimeout(timer)
    }
  }, [language])

  /* ── Severity label from incident data ── */
  const severityLabel =
    incident?.priority === 1
      ? "Critical"
      : incident?.priority === 2
        ? "High"
        : incident?.priority === 3
          ? "Medium"
          : incident?.priority === 4
            ? "Low"
            : null

  /* ──────────── UI ──────────── */
  return (
    <div className="min-h-screen p-6 md:p-12 bg-dark text-white flex flex-col items-center">
      {/* ── Fake Call Warning Banner ── */}
      {fakeLabel && fakeLabel !== "GENUINE" && (
        <div
          className={cn(
            "w-full max-w-6xl mb-6 p-4 rounded-2xl border flex items-start gap-3",
            fakeLabel === "LIKELY_FAKE"
              ? "bg-red-500/15 border-red-500/40 text-red-300"
              : "bg-yellow-500/15 border-yellow-500/40 text-yellow-300",
          )}
        >
          <AlertTriangle className="h-6 w-6 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-bold text-sm uppercase tracking-wider">
              {fakeLabel === "LIKELY_FAKE"
                ? "Potential Fake Call Detected"
                : "Suspicious Call Activity"}
              {fakeProbability != null && (
                <span className="ml-2 opacity-70 font-normal normal-case">
                  ({Math.round(fakeProbability * 100)}% confidence)
                </span>
              )}
            </p>
            {fakeSignals.length > 0 && (
              <ul className="mt-1 text-xs opacity-80 list-disc list-inside">
                {fakeSignals.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            )}
            {fakeLabel === "LIKELY_FAKE" && (
              <p className="mt-2 text-xs opacity-70">
                Emergency dispatch has been paused. If this is a real emergency, please provide more details.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Header */}
      <div className="w-full max-w-6xl flex flex-col md:flex-row justify-between items-center mb-12 gap-6">
        <div className="flex flex-col">
          <h2 className="text-4xl font-black uppercase tracking-tighter">
            {t.user_title}
          </h2>
          <p className="text-red-500 font-bold tracking-[0.2em] uppercase text-sm">
            {t.user_emergency}
          </p>
        </div>
        <LanguageSelector />
      </div>

      {/* Emergency Selection Buttons */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-8 w-full max-w-4xl">
        <ControlButton
          isActive={selectedService === "ambulance"}
          onClick={() => handleEmergencySelection("ambulance")}
          className="bg-red-600 border-none"
          icon={<Ambulance />}
          label="Ambulance"
        />
        <ControlButton
          isActive={selectedService === "police"}
          onClick={() => handleEmergencySelection("police")}
          className="bg-blue-600 border-none"
          icon={<Shield />}
          label="Police"
        />
        <ControlButton
          isActive={selectedService === "fire"}
          onClick={() => handleEmergencySelection("fire")}
          className="bg-orange-600 border-none"
          icon={<Flame />}
          label="Fire Service"
        />
        <ControlButton
          isActive={selectedService === "rescue"}
          onClick={() => handleEmergencySelection("rescue")}
          className="bg-green-600 border-none"
          icon={<LifeBuoy />}
          label="Rescue Team"
        />
        <ControlButton
          isActive={selectedService === "bluecross"}
          onClick={() => handleEmergencySelection("bluecross")}
          className="bg-cyan-600 border-none"
          icon={<PlusCircle />}
          label="Blue Cross"
        />
      </div>

      {selectedService && (
        <p className="mb-8 text-xl font-bold text-white bg-white/10 px-6 py-2 rounded-full border border-white/10">
          Selected Service:{" "}
          <span className="text-yellow-400">
            {selectedService.toUpperCase()}
          </span>
        </p>
      )}

      {/* Control Buttons */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-6 mb-12">
        <ControlButton
          icon={<Mic />}
          label={t.user_mic}
          onClick={toggleMic}
          isActive={isMicActive}
          variant="emergency"
        />
        <ControlButton
          icon={<Video />}
          label={t.user_video}
          onClick={startVideo}
        />
        <ControlButton
          icon={<Volume2 />}
          label={t.user_speaker}
          onClick={handleSpeakerClick}
          isActive={isSpeakerActive}
          variant="safe"
        />
        <ControlButton
          icon={<MapPin />}
          label={isLocating ? "..." : t.user_location}
          onClick={handleLocationClick}
          isActive={isLocating}
        />
        {/* Bluetooth button */}
        <ControlButton
          icon={<Bluetooth />}
          label="Bluetooth"
          onClick={handleBluetoothClick}
          isActive={isBluetoothActive}
          variant="safe"
        />
      </div>

      {/* Location bar */}
      <div className="w-full max-w-xl">
        <div className="glass p-6 rounded-2xl mb-8 flex items-center gap-4">
          <MapPin className="text-blue-500 shrink-0" />
          <p className="text-slate-300 font-medium truncate">{location}</p>
        </div>
      </div>

      {/* Text input area */}
      <div className="w-full max-w-xl mb-8 flex gap-3">
        <input
          type="text"
          value={textInput}
          onChange={(e) => setTextInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendText()}
          placeholder={
            isSending ? "Processing..." : "Type your emergency message..."
          }
          disabled={isSending}
          className="flex-1 rounded-2xl border border-white/10 bg-white/5 backdrop-blur px-5 py-4 text-sm text-white outline-none placeholder:text-slate-600 focus:border-blue-500/50 disabled:opacity-50"
        />
        <button
          onClick={sendText}
          disabled={!textInput.trim() || isSending}
          className="flex items-center justify-center rounded-2xl bg-accent px-5 text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-30"
        >
          {isSending ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <Send className="h-5 w-5" />
          )}
        </button>
      </div>

      {/* Main content: transcript + sidebar */}
      <div className="flex flex-col lg:flex-row gap-8 w-full max-w-5xl items-start">
        {/* Transcript */}
        <div className="flex-1 w-full min-h-[350px] max-h-[500px]">
          <LiveTranscript
            entries={transcript}
            placeholder={
              isMicActive
                ? "Listening..."
                : "Press Mic or type a message to begin"
            }
          />
        </div>

        {/* Summary panel + guidance */}
        <div className="flex-1 w-full flex flex-col gap-6">
          <SummaryPanel
            data={{
              age: incident?.caller_age,
              emergency:
                incident?.emergency_type ??
                (selectedService ? selectedService.toUpperCase() : undefined),
              severity: severityLabel,
              location: incident?.location ?? (location !== "Awaiting location..." ? location : undefined),
              actionTaken: incident?.routed_service
                ? `${incident.routed_service} dispatched`
                : undefined,
            }}
          />

          {guidance && <GuidancePanel guidance={guidance} />}
        </div>
      </div>

      {/* Video overlay */}
      {showVideo && (
        <div className="video-overlay fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/80 backdrop-blur-sm">
          <div className="relative glass p-4 rounded-3xl w-full max-w-2xl aspect-video">
            <button
              onClick={stopVideo}
              className="absolute top-6 right-6 z-10 p-2 bg-red-500 rounded-full text-white cursor-pointer hover:bg-red-600 transition-colors"
            >
              <X />
            </button>
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="w-full h-full object-cover rounded-2xl bg-black"
            />
          </div>
        </div>
      )}
    </div>
  )
}
