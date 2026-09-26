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
  Bluetooth,
  Camera,
  Heart,
  CheckCircle2,
  Play,
  Pause,
  Square,
  RotateCcw,
  Compass,
  Film,
  CircleDot,
  Users,
  Share2,
  WifiOff,
  Accessibility,
  Phone,
  Copy,
  Check,
  Upload,
  Sparkles,
  Image as ImageIcon,
} from "lucide-react"
import type { IncidentData, TranscriptEntry, SensorTelemetry, VisualObservation } from "../types"
import { api } from "../lib/api"
import { AudioStream, type MicState } from "../lib/audioStream"
import { detectLocation, type LocationData } from "../lib/location"
import { BluetoothManager, isBluetoothSupported } from "../lib/bluetooth"
import { offlineManager } from "../lib/offlineManager"
import { cn, genId } from "../lib/utils"
import { useLanguage } from "../context/LanguageContext"
import { translations } from "../i18n/translations"
import { ControlButton } from "../components/ControlButton"
import { LanguageSelector } from "../components/LanguageSelector"
import { SummaryPanel } from "../components/SummaryPanel"
import LiveTranscript from "../components/LiveTranscript"
import GuidancePanel from "../components/GuidancePanel"
import { EmergencyContactsModal } from "../components/EmergencyContactsModal"
import { ShareSummaryModal } from "../components/ShareSummaryModal"
import { NearbyFacilitiesCard } from "../components/NearbyFacilitiesCard"
import {
  EMERGENCY_SERVICE_CONTACTS,
  triggerNativePhoneCall,
} from "../lib/contacts"

const SCENE_CATEGORIES = [
  { id: "road_accident", label: "🚗 Road Accident" },
  { id: "fire", label: "🔥 Fire Scene" },
  { id: "medical", label: "🩺 Medical / Injury" },
  { id: "public_safety", label: "⚠️ Hazard / Safety" },
  { id: "general", label: "📋 General" },
]

export default function CallPage() {
  const { language } = useLanguage()
  const t = translations[language] ?? translations.en

  const [sessionId] = useState(genId)
  const [isMicActive, setIsMicActive] = useState(false)
  const [micState, setMicState] = useState<MicState>("idle")
  const [isSpeakerActive, setIsSpeakerActive] = useState(false)
  const [isPlayingAudio, setIsPlayingAudio] = useState(false)
  const [isAudioPaused, setIsAudioPaused] = useState(false)
  const [isBluetoothActive, setIsBluetoothActive] = useState(false)
  const [bluetoothDeviceName, setBluetoothDeviceName] = useState<string | null>(null)
  const [sensorTelemetry, setSensorTelemetry] = useState<SensorTelemetry | null>(null)
  const [isSending, setIsSending] = useState(false)
  const [selectedService, setSelectedService] = useState<string | null>(null)

  // ── Accessibility & Offline State ──
  const [isVoiceFirstMode, setIsVoiceFirstMode] = useState(false)
  const [isOnline, setIsOnline] = useState(offlineManager.getOnlineStatus())

  // ── Modals State ──
  const [showContactsModal, setShowContactsModal] = useState(false)
  const [showSummaryModal, setShowSummaryModal] = useState(false)
  const [serviceCallFeedback, setServiceCallFeedback] = useState<string | null>(null)
  const [copiedServicePhoneId, setCopiedServicePhoneId] = useState<string | null>(null)

  // ── Video & Image Evidence Recording State ──
  const [showVideo, setShowVideo] = useState(false)
  const [videoCategory, setVideoCategory] = useState<string>("road_accident")
  const [isRecordingVideo, setIsRecordingVideo] = useState(false)
  const [recordingSeconds, setRecordingSeconds] = useState(0)
  const [isCapturingFrame, setIsCapturingFrame] = useState(false)
  const [capturedFrames, setCapturedFrames] = useState<{ timestamp: string; url: string; source?: string; scene?: string; observations?: VisualObservation[] }[]>([])
  const [recordedClips, setRecordedClips] = useState<{ timestamp: string; category: string; duration: number }[]>([])

  // ── Image Upload & Gemini Vision State ──
  const [selectedUploadFile, setSelectedUploadFile] = useState<{
    file: File
    name: string
    sizeBytes: number
    dataUrl: string
  } | null>(null)
  const [isAnalyzingUpload, setIsAnalyzingUpload] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [latestVisualAnalysis, setLatestVisualAnalysis] = useState<{
    dataUrl: string
    source: string
    scene: string
    observations: VisualObservation[]
    status?: string
    message?: string
  } | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  // ── Location State ──
  const [locationData, setLocationData] = useState<LocationData | null>(null)
  const [locationDisplay, setLocationDisplay] = useState("Awaiting location...")
  const [isLocating, setIsLocating] = useState(false)
  const [showManualLocation, setShowManualLocation] = useState(false)
  const [manualLandmark, setManualLandmark] = useState("")

  // ── Dialogue & Triage State ──
  const [textInput, setTextInput] = useState("")
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([])
  const [incident, setIncident] = useState<IncidentData | null>(null)
  const [guidance, setGuidance] = useState<string | null>(null)
  const [currentQuestion, setCurrentQuestion] = useState<string | null>(null)
  const [fakeLabel, setFakeLabel] = useState<string | null>(null)
  const [fakeProbability, setFakeProbability] = useState<number | null>(null)
  const [fakeSignals, setFakeSignals] = useState<string[]>([])
  const [detectedLang, setDetectedLang] = useState<string | null>(null)

  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<AudioStream | null>(null)
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null)
  const bleManagerRef = useRef<BluetoothManager | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const videoChunksRef = useRef<Blob[]>([])
  const recordTimerRef = useRef<any>(null)

  /* ── Monitor Offline/Online Network Changes ── */
  useEffect(() => {
    return offlineManager.onStatusChange((online) => {
      setIsOnline(online)
      if (!online) {
        addEntry("system", "⚠️ Limited connectivity. Offline safety guidance active.")
      } else {
        addEntry("system", "🟢 Online connection restored. Syncing session telemetry.")
      }
    })
  }, [])

  /* ── Sync Language to Active AudioStream ── */
  useEffect(() => {
    if (streamRef.current && isMicActive) {
      streamRef.current.setLanguage(language)
    }
  }, [language, isMicActive])

  /* ── Helpers ── */
  const addEntry = useCallback(
    (role: TranscriptEntry["role"], text: string) =>
      setTranscript((p) => [...p, { role, text, timestamp: Date.now() }]),
    [],
  )

  const [isAutoplayBlocked, setIsAutoplayBlocked] = useState(false)
  const audioQueueRef = useRef<{ id: string; text?: string; base64Audio?: string; url?: string; priority?: "critical" | "normal" }[]>([])
  const isPlayingRef = useRef(false)

  /* ── TTS Audio Queue Manager with Priority & Non-Overlapping Playback ── */
  const processNextInQueue = useCallback(() => {
    if (audioQueueRef.current.length === 0) {
      setIsPlayingAudio(false)
      setIsAudioPaused(false)
      setIsSpeakerActive(false)
      isPlayingRef.current = false
      return
    }

    const nextItem = audioQueueRef.current.shift()!
    isPlayingRef.current = true
    setIsPlayingAudio(true)
    setIsAudioPaused(false)
    setIsSpeakerActive(true)

    try {
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause()
        audioPlayerRef.current = null
      }

      let audio: HTMLAudioElement
      if (nextItem.base64Audio) {
        audio = new Audio(`data:audio/wav;base64,${nextItem.base64Audio}`)
      } else {
        const url = nextItem.url || (nextItem.text ? api.audioUrl(sessionId, language === "en" ? "en" : language, nextItem.text) : api.audioUrl(sessionId, language === "en" ? "en" : language))
        audio = new Audio(url)
      }

      audioPlayerRef.current = audio

      audio.onended = () => {
        processNextInQueue()
      }
      audio.onerror = () => {
        processNextInQueue()
      }

      audio.play().then(() => {
        setIsAutoplayBlocked(false)
      }).catch((err) => {
        console.warn("Audio autoplay blocked by browser policy:", err)
        setIsAutoplayBlocked(true)
        setIsPlayingAudio(false)
        setIsSpeakerActive(false)
        isPlayingRef.current = false
      })
    } catch {
      processNextInQueue()
    }
  }, [sessionId, language])

  const enqueueAudio = useCallback((item: { id: string; text?: string; base64Audio?: string; url?: string; priority?: "critical" | "normal" }) => {
    if (item.priority === "critical") {
      if (isPlayingRef.current && audioPlayerRef.current) {
        audioPlayerRef.current.pause()
      }
      audioQueueRef.current.unshift(item)
      processNextInQueue()
    } else {
      audioQueueRef.current.push(item)
      if (!isPlayingRef.current) {
        processNextInQueue()
      }
    }
  }, [processNextInQueue])

  const playTTSAudio = useCallback(
    async (text?: string, base64Audio?: string, priority: "critical" | "normal" = "normal") => {
      enqueueAudio({
        id: Math.random().toString(),
        text,
        base64Audio,
        priority,
      })
    },
    [enqueueAudio],
  )

  const pauseAudio = () => {
    if (audioPlayerRef.current && isPlayingAudio) {
      audioPlayerRef.current.pause()
      setIsAudioPaused(true)
      setIsPlayingAudio(false)
      isPlayingRef.current = false
    }
  }

  const resumeAudio = () => {
    if (audioPlayerRef.current && isAudioPaused) {
      audioPlayerRef.current.play().then(() => {
        setIsPlayingAudio(true)
        setIsAudioPaused(false)
        isPlayingRef.current = true
      }).catch(() => {})
    }
  }

  const stopAudio = () => {
    if (audioPlayerRef.current) {
      audioPlayerRef.current.pause()
      audioPlayerRef.current.currentTime = 0
      audioPlayerRef.current = null
    }
    audioQueueRef.current = []
    setIsPlayingAudio(false)
    setIsAudioPaused(false)
    setIsSpeakerActive(false)
    isPlayingRef.current = false
  }

  const replayAudio = async () => {
    stopAudio()
    const textToReplay = currentQuestion || guidance || undefined
    await playTTSAudio(textToReplay, undefined, "critical")
  }

  const fetchStatus = useCallback(async () => {
    if (!isOnline) return
    try {
      const s = await api.getStatus(sessionId)
      setIncident(s.incident)
      if (s.incident.guidance) setGuidance(s.incident.guidance)
      if (s.incident.question) setCurrentQuestion(s.incident.question)
      if (s.incident.fake_label) setFakeLabel(s.incident.fake_label)
      if (s.incident.fake_probability != null) setFakeProbability(s.incident.fake_probability)
      if (s.incident.fake_signals?.length) setFakeSignals(s.incident.fake_signals)
    } catch {
      /* session might not exist yet */
    }
  }, [sessionId, isOnline])

  /* ── Emergency service selection ── */
  const handleEmergencySelection = async (service: string) => {
    setSelectedService(service)
    try {
      if (isOnline) {
        await api.selectService(sessionId, service)
      }
      addEntry("system", `Emergency Service selected: ${service.toUpperCase()}`)
    } catch {
      /* ignore */
    }
  }

  /* ── Direct emergency service calling ── */
  const handleServiceCall = (serviceName: string, phone: string) => {
    const success = triggerNativePhoneCall(phone)
    if (success) {
      setServiceCallFeedback(
        `Call action initiated for ${serviceName} (${phone}). If phone calling is not available on this device, please dial directly or click Copy.`
      )
    } else {
      setServiceCallFeedback(
        `Phone calling is not available on this device. Please dial ${phone} directly.`
      )
    }
    setTimeout(() => setServiceCallFeedback(null), 8000)
    addEntry("system", `Direct call initiated for ${serviceName}: ${phone}`)
  }

  const handleCopyServicePhone = async (phone: string, id: string) => {
    try {
      await navigator.clipboard.writeText(phone)
      setCopiedServicePhoneId(id)
      setTimeout(() => setCopiedServicePhoneId(null), 2000)
    } catch {
      /* ignore */
    }
  }

  /* ── Real Web Bluetooth Lifecycle ── */
  const handleBluetoothClick = async () => {
    if (isBluetoothActive) {
      bleManagerRef.current?.disconnect()
      setIsBluetoothActive(false)
      setBluetoothDeviceName(null)
      addEntry("system", "Bluetooth sensor disconnected.")
      return
    }

    if (!isBluetoothSupported()) {
      addEntry(
        "system",
        "Web Bluetooth is not supported in this browser. Use Chrome/Edge on HTTPS or localhost.",
      )
      return
    }

    const manager = new BluetoothManager({
      onConnected: (name: string) => {
        setIsBluetoothActive(true)
        setBluetoothDeviceName(name)
        addEntry("system", `Bluetooth device connected: ${name}`)
      },
      onDisconnected: () => {
        setIsBluetoothActive(false)
        setBluetoothDeviceName(null)
        addEntry("system", "Bluetooth device disconnected.")
      },
      onTelemetry: async (data: SensorTelemetry) => {
        setSensorTelemetry(data)
        if (data.heart_rate) {
          addEntry("system", `Biometric Telemetry: Heart Rate = ${data.heart_rate} BPM (${data.notes || "Live"})`)
        }
        try {
          if (isOnline) {
            await api.sendSensorData(sessionId, data)
          }
        } catch {
          /* ignore */
        }
      },
      onError: (msg: string) => {
        addEntry("system", `Bluetooth Notice: ${msg}`)
        setIsBluetoothActive(false)
      },
    })

    bleManagerRef.current = manager
    addEntry("system", "Searching for Bluetooth emergency sensor...")
    const success = await manager.connect()
    if (!success && !isBluetoothActive) {
      addEntry("system", "Bluetooth pairing cancelled or unavailable.")
    }
  }

  /* ── Location Retrieval & Fallback ── */
  const handleLocationClick = async () => {
    setIsLocating(true)
    try {
      const loc = await detectLocation()
      setLocationData(loc)
      setLocationDisplay(loc.displayString)
      setShowManualLocation(false)
      addEntry("system", `Location captured: ${loc.displayString} (Source: ${loc.source})`)
      // Persist GPS to backend session so LangGraph AI has location context
      try {
        await api.updateLocation(sessionId, {
          latitude: loc.latitude,
          longitude: loc.longitude,
          accuracy: loc.accuracyMeters,
          source: loc.source,
          address: loc.address ?? null,
          display_string: loc.displayString,
          is_low_accuracy: loc.isLowAccuracy,
          timestamp: loc.timestamp,
        })
      } catch {
        /* location sync non-blocking */
      }
    } catch (err: any) {
      if (err?.isPermissionDenied || err?.code === 1) {
        setLocationDisplay("Location permission blocked. Please allow location in browser settings & click Retry.")
      } else if (err?.isTimeout || err?.code === 3) {
        setLocationDisplay("GPS request timed out. Click Retry GPS or enter landmark.")
      } else if (err?.isPositionUnavailable || err?.code === 2) {
        setLocationDisplay("GPS position unavailable. Please enter landmark below.")
      } else {
        setLocationDisplay("Location unavailable. Please enter landmark below.")
      }
      setShowManualLocation(true)
    } finally {
      setIsLocating(false)
    }
  }

  const handleApplyManualLocation = async () => {
    if (!manualLandmark.trim()) return
    const manualLoc: LocationData = {
      latitude: locationData?.latitude || 0,
      longitude: locationData?.longitude || 0,
      accuracyMeters: locationData?.accuracyMeters || 10,
      timestamp: new Date().toLocaleTimeString(),
      source: "Manual Entry",
      address: manualLandmark.trim(),
      landmark: manualLandmark.trim(),
      isLowAccuracy: false,
      displayString: locationData?.latitude && locationData?.longitude
        ? `${manualLandmark.trim()} [${locationData.latitude.toFixed(5)}, ${locationData.longitude.toFixed(5)}]`
        : `${manualLandmark.trim()} (Manual Landmark)`,
      status: "manual_override",
    }
    setLocationData(manualLoc)
    setLocationDisplay(manualLoc.displayString)
    setShowManualLocation(false)
    addEntry("system", `Landmark location specified: ${manualLoc.displayString}`)
    // Persist manual location to backend session
    try {
      await api.updateLocation(sessionId, {
        latitude: locationData?.latitude ?? null,
        longitude: locationData?.longitude ?? null,
        accuracy: locationData?.accuracyMeters ?? 10,
        source: "Manual Entry",
        address: manualLoc.address ?? null,
        landmark: manualLandmark.trim(),
        display_string: manualLoc.displayString,
        is_low_accuracy: false,
        timestamp: manualLoc.timestamp,
      })
    } catch {
      /* location sync non-blocking */
    }
  }

  /* ── Video Stream & Emergency Visual Evidence Recording ── */
  const startVideo = async () => {
    setShowVideo(true)
    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: true, // Capture synchronized emergency audio + video
        })
        if (videoRef.current) {
          videoRef.current.srcObject = stream
        }
      }
    } catch {
      // Keep modal open so caller can still upload image evidence even if camera is unavailable
      addEntry("system", "Live camera preview unavailable. You can still upload image evidence.")
    }
  }

  const stopVideo = () => {
    if (isRecordingVideo) {
      stopVideoRecording()
    }
    if (videoRef.current?.srcObject) {
      const stream = videoRef.current.srcObject as MediaStream
      stream.getTracks().forEach((tr) => tr.stop())
    }
    setShowVideo(false)
  }

  const startVideoRecording = () => {
    if (!videoRef.current?.srcObject) return
    const stream = videoRef.current.srcObject as MediaStream
    videoChunksRef.current = []

    try {
      const options = MediaRecorder.isTypeSupported("video/webm;codecs=vp9,opus")
        ? { mimeType: "video/webm;codecs=vp9,opus" }
        : { mimeType: "video/webm" }

      const recorder = new MediaRecorder(stream, options)
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          videoChunksRef.current.push(e.data)
        }
      }

      recorder.onstop = async () => {
        const blob = new Blob(videoChunksRef.current, { type: "video/webm" })
        const reader = new FileReader()
        reader.readAsDataURL(blob)
        reader.onloadend = async () => {
          const base64Data = reader.result as string
          try {
            if (isOnline) {
              await api.sendVideoEvidence(
                sessionId,
                base64Data,
                videoCategory,
                `Recorded evidence: ${recordingSeconds}s (${videoCategory})`
              )
            }
            setRecordedClips((prev) => [
              ...prev,
              {
                timestamp: new Date().toLocaleTimeString(),
                category: videoCategory,
                duration: recordingSeconds,
              },
            ])
            addEntry("system", `Emergency visual evidence (${videoCategory}, ${recordingSeconds}s) transmitted to dispatchers.`)
          } catch (err) {
            addEntry("system", "Failed to transmit video evidence.")
          }
        }
      }

      recorder.start(1000)
      mediaRecorderRef.current = recorder
      setIsRecordingVideo(true)
      setRecordingSeconds(0)

      recordTimerRef.current = setInterval(() => {
        setRecordingSeconds((s) => s + 1)
      }, 1000)
    } catch (err) {
      addEntry("system", `MediaRecorder error: ${err instanceof Error ? err.message : "Recording failed"}`)
    }
  }

  const stopVideoRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop()
    }
    if (recordTimerRef.current) {
      clearInterval(recordTimerRef.current)
      recordTimerRef.current = null
    }
    setIsRecordingVideo(false)
  }

  const captureEvidenceFrame = async () => {
    if (!videoRef.current || isCapturingFrame) return
    setIsCapturingFrame(true)

    try {
      const video = videoRef.current
      const canvas = document.createElement("canvas")
      canvas.width = video.videoWidth || 640
      canvas.height = video.videoHeight || 480
      const ctx = canvas.getContext("2d")
      if (!ctx) throw new Error("Could not initialize canvas 2D context")

      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      const dataUrl = canvas.toDataURL("image/jpeg", 0.85)

      if (isOnline) {
        const res = await api.sendImageFrame(
          sessionId,
          dataUrl,
          `Snapshot: ${videoCategory}`,
          "snapshot",
          videoCategory
        )
        setCapturedFrames((prev) => [
          ...prev,
          {
            timestamp: res.timestamp || new Date().toISOString(),
            url: dataUrl,
            source: "snapshot",
            scene: videoCategory,
            observations: res.observations || [],
          },
        ])
        if (res.observations && res.observations.length > 0) {
          setLatestVisualAnalysis({
            dataUrl,
            source: "Camera Snapshot",
            scene: videoCategory,
            observations: res.observations,
          })
        }
      }

      addEntry("system", `Emergency evidence frame captured (${videoCategory}) and transmitted.`)
    } catch (err) {
      addEntry("system", `Frame capture error: ${err instanceof Error ? err.message : "Failed to capture"}`)
    } finally {
      setIsCapturingFrame(false)
    }
  }

  /* ── Image Upload & Gemini Vision Analysis Handlers ── */
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setUploadError(null)
    const file = e.target.files?.[0]
    if (!file) return

    const validTypes = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    if (!validTypes.includes(file.type.toLowerCase())) {
      setUploadError("Unsupported file format. Please upload JPG, PNG, or WEBP.")
      return
    }

    if (file.size > 10 * 1024 * 1024) {
      setUploadError("File size exceeds 10MB limit. Please select a smaller image.")
      return
    }

    const reader = new FileReader()
    reader.onload = () => {
      const dataUrl = reader.result as string
      setSelectedUploadFile({
        file,
        name: file.name,
        sizeBytes: file.size,
        dataUrl,
      })
    }
    reader.readAsDataURL(file)
  }

  const handleUploadAndAnalyze = async () => {
    if (!selectedUploadFile) return
    setIsAnalyzingUpload(true)
    setUploadError(null)

    try {
      if (isOnline) {
        const res = await api.sendImageFrame(
          sessionId,
          selectedUploadFile.dataUrl,
          `Uploaded: ${selectedUploadFile.name}`,
          "upload",
          videoCategory
        )

        setCapturedFrames((prev) => [
          ...prev,
          {
            timestamp: res.timestamp || new Date().toISOString(),
            url: selectedUploadFile.dataUrl,
            source: "upload",
            scene: videoCategory,
            observations: res.observations || [],
          },
        ])

        setLatestVisualAnalysis({
          dataUrl: selectedUploadFile.dataUrl,
          source: "Uploaded Image",
          scene: videoCategory,
          observations: res.observations || [],
          status: res.status,
          message: res.message,
        })

        addEntry(
          "system",
          `Visual evidence uploaded (${selectedUploadFile.name}) and analyzed via Gemini Vision.`
        )
      } else {
        setUploadError("Offline mode: visual evidence will be synced when connection is restored.")
      }
      setSelectedUploadFile(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
    } catch (err) {
      setUploadError("Visual analysis unavailable. The uploaded evidence was not analyzed.")
    } finally {
      setIsAnalyzingUpload(false)
    }
  }

  const handleCancelUpload = () => {
    setSelectedUploadFile(null)
    setUploadError(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  /* ── Mic: WebSocket audio streaming (Speech-to-Speech Flow) ── */
  const toggleMic = async () => {
    if (isMicActive) {
      streamRef.current?.stop()
      streamRef.current = null
      setIsMicActive(false)
      setMicState("idle")
      return
    }

    if (!isOnline) {
      // Offline fallback speech simulation
      addEntry("system", "⚠️ Offline mode active — use quick action buttons or text input for instant first aid.")
      return
    }

    const stream = new AudioStream(
      sessionId,
      {
        onStateChange: (st: MicState) => {
          setMicState(st)
        },
        onConnected: () => {
          setIsMicActive(true)
          setMicState("listening")
          addEntry("system", `Microphone connected — speaking language: ${language.toUpperCase()}`)
        },
        onTranscript: (text: string) => {
          addEntry("caller", text)
        },
        onProcessing: () => {
          setMicState("processing")
        },
        onQuestion: async (
          text: string | null,
          g: string | null,
          status: string,
          pScore?: number | null,
          pLabel?: string | null,
          fLabel?: string | null,
          fProb?: number | null,
          fSignals?: string[],
          audioBase64?: string,
          langCode?: string
        ) => {
          setMicState("listening")
          if (langCode) setDetectedLang(langCode)
          if (text) {
            addEntry("ai", text)
            setCurrentQuestion(text)
            // Speech-to-Speech: automatically speak response aloud in native language
            const isCritical = (pScore && pScore >= 8) || pLabel === "CRITICAL"
            await playTTSAudio(text, audioBase64, isCritical ? "critical" : "normal")
          }
          if (g) setGuidance(g)
          if (pScore != null || pLabel) {
            setIncident((prev) =>
              prev
                ? {
                    ...prev,
                    priority_score: pScore ?? prev.priority_score,
                    priority_label: pLabel ?? prev.priority_label,
                  }
                : prev,
            )
          }
          if (fLabel) setFakeLabel(fLabel)
          if (fProb != null) setFakeProbability(fProb)
          if (fSignals?.length) setFakeSignals(fSignals)
          void fetchStatus()
          if (status === "ready_to_dispatch") {
            setSelectedService(null)
          }
        },
        onDisconnected: () => {
          setIsMicActive(false)
          setMicState("idle")
        },
        onError: (msg: string) => {
          addEntry("system", `Audio Stream: ${msg}`)
          if (msg.includes("WebSocket") || msg.includes("denied") || msg.includes("not supported")) {
            setIsMicActive(false)
            setMicState("idle")
          } else {
            setMicState("listening")
          }
        },
      },
      language,
    )

    try {
      await stream.start()
      streamRef.current = stream
    } catch {
      addEntry("system", "Microphone access denied. Please grant microphone permission in browser or use text input.")
      setIsMicActive(false)
      setMicState("idle")
    }
  }

  /* ── Text message (REST fallback) ── */
  const sendText = async () => {
    const msg = textInput.trim()
    if (!msg || isSending) return

    setTextInput("")
    setIsSending(true)
    addEntry("caller", msg)

    if (!isOnline) {
      // Local deterministic offline guidance
      const localGuidance = offlineManager.getOfflineGuidance(msg, language)
      setGuidance(localGuidance)
      addEntry("ai", localGuidance)
      offlineManager.queueAction("message", { message: msg, timestamp: new Date().toISOString() })
      setIsSending(false)
      return
    }

    try {
      const fullMsg =
        !incident && locationDisplay !== "Awaiting location..." && locationDisplay !== "Location denied or unavailable"
          ? `${msg} [Location: ${locationDisplay}]`
          : msg
      await api.sendMessage(sessionId, fullMsg, language)

      const [q] = await Promise.all([api.getQuestion(sessionId), fetchStatus()])
      if (q.question) {
        addEntry("ai", q.question)
        setCurrentQuestion(q.question)
        await playTTSAudio(q.question)
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

  /* ── Detect location on mount and send to backend ── */
  useEffect(() => {
    detectLocation()
      .then(async (loc) => {
        setLocationData(loc)
        setLocationDisplay(loc.displayString)
        // Send GPS to backend session immediately so AI has location context
        // before the first caller message is processed
        try {
          await api.updateLocation(sessionId, {
            latitude: loc.latitude,
            longitude: loc.longitude,
            accuracy: loc.accuracyMeters,
            source: loc.source,
            address: loc.address ?? null,
            display_string: loc.displayString,
            is_low_accuracy: loc.isLowAccuracy,
            timestamp: loc.timestamp,
          })
        } catch {
          /* location sync is non-blocking — session may not exist yet, will retry on next message */
        }
      })
      .catch((err: any) => {
        if (err?.isPermissionDenied || err?.code === 1) {
          setLocationDisplay("Location permission blocked. Click Retry GPS or enter landmark.")
        } else if (err?.isTimeout || err?.code === 3) {
          setLocationDisplay("GPS request timed out. Click Retry GPS or enter landmark.")
        } else {
          setLocationDisplay("Location unavailable. Click Retry GPS or enter landmark.")
        }
      })
  }, [])

  /* ── Non-destructive language update for active audio stream ── */
  useEffect(() => {
    if (isMicActive && streamRef.current) {
      streamRef.current.setLanguage(language)
      addEntry("system", `Microphone speaking language updated to ${language.toUpperCase()}`)
    }
  }, [language, isMicActive])

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
    <div className="min-h-screen p-4 md:p-10 bg-dark text-white flex flex-col items-center">
      {/* ── Offline Network Warning Banner ── */}
      {!isOnline && (
        <div className="w-full max-w-6xl mb-4 p-3.5 rounded-2xl bg-amber-500/15 border border-amber-500/40 text-amber-300 flex items-center justify-between text-xs font-bold animate-pulse">
          <div className="flex items-center gap-2">
            <WifiOff className="h-4 w-4" />
            <span>⚠️ Limited Connectivity — Offline Safety Mode Active. Local First Aid Guidance Available.</span>
          </div>
          <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-amber-500/20">Offline</span>
        </div>
      )}

      {/* ── Fake Call Warning Banner ── */}
      {fakeLabel && fakeLabel !== "GENUINE" && (
        <div
          className={cn(
            "w-full max-w-6xl mb-6 p-4 rounded-2xl border flex items-start gap-3 shadow-lg",
            fakeLabel === "LIKELY_FAKE"
              ? "bg-red-500/15 border-red-500/40 text-red-300"
              : "bg-yellow-500/15 border-yellow-500/40 text-yellow-300",
          )}
        >
          <AlertTriangle className="h-6 w-6 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-bold text-sm uppercase tracking-wider">
              {fakeLabel === "LIKELY_FAKE"
                ? "Potential Non-Emergency / Test Call Detected"
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
                Emergency dispatch paused. If this is a real emergency, please speak your situation clearly.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Header */}
      <div className="w-full max-w-6xl flex flex-col md:flex-row justify-between items-center mb-6 gap-4">
        <div className="flex flex-col">
          <h2 className="text-3xl md:text-4xl font-black uppercase tracking-tighter flex items-center gap-3">
            {t.user_title}
            <span className="text-xs bg-red-600/20 text-red-400 border border-red-500/30 px-2.5 py-1 rounded-full font-mono uppercase tracking-normal">
              Emergency CAD Hub
            </span>
          </h2>
          <p className="text-red-500 font-bold tracking-[0.2em] uppercase text-xs md:text-sm">
            {t.user_emergency} • {language === "ta" ? "தமிழ் பயன்முறை" : language === "hi" ? "हिंदी मोड" : "English Mode"}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsVoiceFirstMode(!isVoiceFirstMode)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-bold transition-all",
              isVoiceFirstMode
                ? "bg-purple-600 text-white border-purple-500 shadow-lg shadow-purple-600/30"
                : "bg-white/5 text-slate-300 border-white/10 hover:bg-white/10"
            )}
            title="Toggle Voice-First High Accessibility Mode"
          >
            <Accessibility className="h-3.5 w-3.5" />
            Voice-First Mode
          </button>
          <LanguageSelector />
        </div>
      </div>

      {/* ── Action Hub Shortcuts (Contacts, Share Dossier) ── */}
      <div className="w-full max-w-4xl mb-6 flex flex-wrap items-center justify-between gap-3 bg-white/5 p-3 rounded-2xl border border-white/10">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowContactsModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-red-600 to-rose-700 hover:from-red-500 hover:to-rose-600 text-white rounded-xl text-xs font-bold shadow-lg transition-all"
          >
            <Users className="h-4 w-4" />
            1-Tap Emergency Contacts
          </button>
          <button
            onClick={() => setShowSummaryModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 text-slate-200 hover:text-white rounded-xl text-xs font-bold transition-all"
          >
            <Share2 className="h-4 w-4" />
            Share Emergency Dossier
          </button>
        </div>
        <span className="text-[11px] text-slate-400 font-mono">
          Session ID: {sessionId.slice(0, 10)}...
        </span>
      </div>

      {/* ── VOICE-FIRST ACCESSIBILITY MODE UI ── */}
      {isVoiceFirstMode ? (
        <div className="w-full max-w-3xl my-6 glass p-8 rounded-3xl border border-purple-500/30 flex flex-col items-center text-center shadow-2xl animate-fadeIn">
          <span className="text-xs uppercase tracking-widest text-purple-400 font-bold mb-2">
            Voice-First Accessibility Mode Active
          </span>
          <h3 className="text-2xl font-black mb-6">
            {language === "ta" ? "பேச மைக் பொத்தானைத் தொடவும்" : language === "hi" ? "बोलने के लिए माइक दबाएं" : "Touch Microphone to Speak"}
          </h3>

          {/* Giant Accessible Mic Button */}
          <button
            onClick={toggleMic}
            className={cn(
              "w-48 h-48 rounded-full flex flex-col items-center justify-center gap-3 transition-all transform active:scale-95 shadow-2xl mb-8",
              isMicActive
                ? "bg-red-600 text-white ring-8 ring-red-500/40 animate-pulse"
                : "bg-blue-600 hover:bg-blue-500 text-white ring-8 ring-blue-500/20"
            )}
          >
            <Mic className="h-16 w-16" />
            <span className="font-black text-sm uppercase tracking-wider">
              {isMicActive ? "LISTENING..." : "PRESS TO SPEAK"}
            </span>
          </button>

          {/* Audio controls for spoken guidance */}
          <div className="flex items-center gap-4">
            <button
              onClick={replayAudio}
              className="flex items-center gap-2 px-6 py-3 rounded-2xl bg-white/10 hover:bg-white/20 text-sm font-bold text-white shadow-lg transition-colors"
            >
              <RotateCcw className="h-4 w-4 text-blue-400" />
              {language === "ta" ? "மீண்டும் பேசவும்" : language === "hi" ? "फिर से सुनें" : "Speak Again"}
            </button>
            <button
              onClick={stopAudio}
              className="flex items-center gap-2 px-6 py-3 rounded-2xl bg-red-500/20 hover:bg-red-500/30 text-sm font-bold text-red-300 border border-red-500/30 shadow-lg transition-colors"
            >
              <Square className="h-4 w-4 fill-current" />
              Stop
            </button>
          </div>

          {guidance && (
            <div className="mt-8 p-6 rounded-2xl bg-black/40 border border-white/10 text-left w-full">
              <span className="text-xs uppercase font-bold text-green-400 mb-1 block">Live Guidance Spoken:</span>
              <p className="text-base text-green-200 font-medium leading-relaxed">{guidance}</p>
            </div>
          )}
        </div>
      ) : (
        <>
          {/* Emergency Service Direct Selector */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6 w-full max-w-4xl">
            <ControlButton
              isActive={selectedService === "ambulance"}
              onClick={() => handleEmergencySelection("ambulance")}
              className="bg-red-600/90 border-none hover:bg-red-600"
              icon={<Ambulance />}
              label="Ambulance"
            />
            <ControlButton
              isActive={selectedService === "police"}
              onClick={() => handleEmergencySelection("police")}
              className="bg-blue-600/90 border-none hover:bg-blue-600"
              icon={<Shield />}
              label="Police"
            />
            <ControlButton
              isActive={selectedService === "fire"}
              onClick={() => handleEmergencySelection("fire")}
              className="bg-orange-600/90 border-none hover:bg-orange-600"
              icon={<Flame />}
              label="Fire Service"
            />
            <ControlButton
              isActive={selectedService === "rescue"}
              onClick={() => handleEmergencySelection("rescue")}
              className="bg-green-600/90 border-none hover:bg-green-600"
              icon={<LifeBuoy />}
              label="Rescue Team"
            />
            <ControlButton
              isActive={selectedService === "bluecross"}
              onClick={() => handleEmergencySelection("bluecross")}
              className="bg-cyan-600/90 border-none hover:bg-cyan-600"
              icon={<PlusCircle />}
              label="Blue Cross"
            />
          </div>

          {selectedService && (
            <div className="w-full max-w-4xl mb-6 p-4 rounded-2xl bg-white/10 border border-white/20 backdrop-blur-md shadow-xl animate-fadeIn">
              {selectedService in EMERGENCY_SERVICE_CONTACTS ? (
                (() => {
                  const serviceConfig =
                    EMERGENCY_SERVICE_CONTACTS[
                      selectedService as keyof typeof EMERGENCY_SERVICE_CONTACTS
                    ]
                  return (
                    <div className="flex flex-col gap-3">
                      <div className="flex items-center justify-between flex-wrap gap-2 border-b border-white/10 pb-2">
                        <div className="flex items-center gap-2">
                          <span className="p-2 rounded-xl bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">
                            <Phone className="h-4 w-4" />
                          </span>
                          <div>
                            <h4 className="text-sm font-black uppercase tracking-wider text-white">
                              {serviceConfig.name} — Direct Call Options
                            </h4>
                            <p className="text-xs text-slate-300">
                              Direct device calling action for {serviceConfig.name}. Select a configured contact below:
                            </p>
                          </div>
                        </div>
                        <span className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full bg-yellow-400/20 text-yellow-300 border border-yellow-400/30">
                          Direct Telephony Handler
                        </span>
                      </div>

                      {serviceCallFeedback && (
                        <div className="p-2.5 rounded-xl bg-blue-500/20 border border-blue-500/40 text-blue-200 text-xs flex items-center justify-between gap-2 animate-fadeIn">
                          <span>{serviceCallFeedback}</span>
                          <button
                            onClick={() => setServiceCallFeedback(null)}
                            className="text-slate-400 hover:text-white text-xs"
                          >
                            ✕
                          </button>
                        </div>
                      )}

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-1">
                        {serviceConfig.contacts.map((contact, idx) => {
                          const contactId = `service_${serviceConfig.id}_${idx}`
                          return (
                            <div
                              key={idx}
                              className="p-3.5 rounded-xl bg-black/40 border border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                            >
                              <div>
                                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                                  {contact.label}
                                </span>
                                <span className="text-sm font-bold text-white font-mono">
                                  {contact.phone}
                                </span>
                              </div>
                              <div className="flex items-center gap-2">
                                <button
                                  onClick={() =>
                                    handleServiceCall(serviceConfig.name, contact.phone)
                                  }
                                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-green-600 hover:bg-green-500 text-white text-xs font-bold shadow-md transition-colors"
                                  title={`Call ${serviceConfig.name} (${contact.phone})`}
                                >
                                  <Phone className="h-3.5 w-3.5" />
                                  Call {serviceConfig.name}
                                </button>
                                <button
                                  onClick={() =>
                                    handleCopyServicePhone(contact.phone, contactId)
                                  }
                                  className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-slate-300 text-xs transition-colors"
                                  title="Copy Number"
                                >
                                  {copiedServicePhoneId === contactId ? (
                                    <Check className="h-3.5 w-3.5 text-green-400" />
                                  ) : (
                                    <Copy className="h-3.5 w-3.5 text-slate-300" />
                                  )}
                                </button>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )
                })()
              ) : (
                <div className="text-sm md:text-base font-bold text-white flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-yellow-400" />
                  Service Target:{" "}
                  <span className="text-yellow-400 font-black tracking-wider">
                    {selectedService.toUpperCase()}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Control Buttons Bar */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8 w-full max-w-4xl">
            <ControlButton
              icon={<Mic />}
              label={isMicActive ? "Mic Live (VAD)" : t.user_mic}
              onClick={toggleMic}
              isActive={isMicActive}
              variant="emergency"
            />
            <ControlButton
              icon={<Video />}
              label="Visual Evidence"
              onClick={startVideo}
              isActive={showVideo}
            />
            <ControlButton
              icon={isPlayingAudio ? <Volume2 className="animate-bounce" /> : <Volume2 />}
              label={isPlayingAudio ? "Speaking..." : t.user_speaker}
              onClick={replayAudio}
              isActive={isPlayingAudio}
              variant="safe"
            />
            <ControlButton
              icon={<MapPin />}
              label={isLocating ? "Locating..." : "GPS Location"}
              onClick={handleLocationClick}
              isActive={isLocating}
            />
            <ControlButton
              icon={<Bluetooth />}
              label={isBluetoothActive ? (bluetoothDeviceName?.slice(0, 10) || "BLE Live") : "Bluetooth"}
              onClick={handleBluetoothClick}
              isActive={isBluetoothActive}
              variant="safe"
            />
          </div>

          {/* ── Autoplay Blocked Banner ── */}
          {isAutoplayBlocked && (
            <div className="w-full max-w-2xl mb-4">
              <button
                onClick={() => {
                  setIsAutoplayBlocked(false)
                  processNextInQueue()
                }}
                className="w-full bg-safe/20 border border-safe/40 text-safe font-bold py-3 px-4 rounded-2xl text-xs flex items-center justify-center gap-2 hover:bg-safe/30 transition-all shadow-lg animate-pulse"
              >
                <Volume2 className="w-4 h-4" />
                🔊 Click to enable voice responses (Browser sound permission)
              </button>
            </div>
          )}

          {/* ── Audio Playback Control Bar (Replay, Pause, Stop) ── */}
          {(isPlayingAudio || isAudioPaused || guidance) && (
            <div className="w-full max-w-2xl mb-6 glass p-3.5 rounded-2xl border border-blue-500/30 flex items-center justify-between shadow-lg bg-blue-950/20">
              <div className="flex items-center gap-3">
                <div className={cn(
                  "p-2 rounded-xl flex items-center justify-center",
                  isPlayingAudio ? "bg-blue-500 text-white animate-pulse" : "bg-white/10 text-slate-400"
                )}>
                  <Volume2 className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider text-blue-300">
                    {isPlayingAudio ? "🔊 Spoken Guidance Active" : isAudioPaused ? "⏸ Audio Paused" : "Voice Guidance Available"}
                  </p>
                  <p className="text-xs text-slate-400 line-clamp-1">
                    {currentQuestion || guidance || "Emergency guidance instructions"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={replayAudio}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-xs font-bold text-white transition-colors"
                  title="Replay Voice Guidance"
                >
                  <RotateCcw className="h-3.5 w-3.5 text-blue-400" />
                  Replay
                </button>
                {isPlayingAudio ? (
                  <button
                    onClick={pauseAudio}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-yellow-500/20 hover:bg-yellow-500/30 text-xs font-bold text-yellow-300 border border-yellow-500/30 transition-colors"
                    title="Pause Audio"
                  >
                    <Pause className="h-3.5 w-3.5" />
                    Pause
                  </button>
                ) : isAudioPaused ? (
                  <button
                    onClick={resumeAudio}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-green-500/20 hover:bg-green-500/30 text-xs font-bold text-green-300 border border-green-500/30 transition-colors"
                    title="Resume Audio"
                  >
                    <Play className="h-3.5 w-3.5" />
                    Resume
                  </button>
                ) : null}
                <button
                  onClick={stopAudio}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-red-500/20 hover:bg-red-500/30 text-xs font-bold text-red-300 border border-red-500/30 transition-colors"
                  title="Stop Audio"
                >
                  <Square className="h-3 w-3 fill-current" />
                  Stop
                </button>
              </div>
            </div>
          )}

          {/* ── Live Voice Activity Status Bar (when Mic is active) ── */}
          {isMicActive && (
            <div className="w-full max-w-2xl mb-6 glass p-4 rounded-2xl border border-blue-500/30 flex items-center justify-between animate-fadeIn shadow-lg">
              <div className="flex items-center gap-3">
                {micState === "listening" && (
                  <>
                    <span className="relative flex h-3.5 w-3.5">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-green-500"></span>
                    </span>
                    <div>
                      <p className="text-sm font-bold text-green-400">🟢 Listening...</p>
                      <p className="text-xs text-slate-400">Speak naturally in {language.toUpperCase()} (Tamil / Hindi / English)</p>
                    </div>
                  </>
                )}
                {micState === "speaking" && (
                  <>
                    <span className="relative flex h-3.5 w-3.5">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-blue-500"></span>
                    </span>
                    <div>
                      <p className="text-sm font-bold text-blue-400 animate-pulse">🔵 Speech detected...</p>
                      <p className="text-xs text-slate-400">Capturing voice utterance</p>
                    </div>
                  </>
                )}
                {micState === "processing" && (
                  <>
                    <span className="relative flex h-3.5 w-3.5">
                      <span className="animate-spin inline-flex h-3.5 w-3.5 border-2 border-indigo-400 border-t-transparent rounded-full"></span>
                    </span>
                    <div>
                      <p className="text-sm font-bold text-indigo-400">🟣 Processing...</p>
                      <p className="text-xs text-slate-400">Fast-path triage + Multilingual AI response</p>
                    </div>
                  </>
                )}
                {micState === "idle" && (
                  <p className="text-xs text-slate-400">Click microphone to speak</p>
                )}
              </div>
              <div className="flex items-center gap-2">
                {detectedLang && (
                  <span className="text-[10px] uppercase font-bold px-2 py-1 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                    Lang: {detectedLang.toUpperCase()}
                  </span>
                )}
                <span className="text-[10px] uppercase font-bold px-2 py-1 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">
                  Low-Latency VAD
                </span>
              </div>
            </div>
          )}

          {/* ── Live Bluetooth Biometrics Bar (if active) ── */}
          {isBluetoothActive && sensorTelemetry && (
            <div className="w-full max-w-2xl mb-6 glass p-4 rounded-2xl border border-green-500/30 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Heart className="h-6 w-6 text-red-500 animate-pulse" />
                <div>
                  <p className="text-xs font-bold uppercase text-slate-400">
                    {bluetoothDeviceName || "Live Bluetooth Wearable"}
                  </p>
                  <p className="text-sm font-black text-white">
                    {sensorTelemetry.heart_rate ? `${sensorTelemetry.heart_rate} BPM` : "Reading Sensor..."}
                    <span className="ml-2 text-xs font-normal text-slate-400">
                      {sensorTelemetry.notes || ""}
                    </span>
                  </p>
                </div>
              </div>
              <span className="text-[10px] uppercase font-bold px-2 py-1 rounded bg-green-500/20 text-green-400 border border-green-500/30">
                Live Stream
              </span>
            </div>
          )}

          {/* ── Location Confidence & Accuracy Card ── */}
          <div className="w-full max-w-2xl mb-6 glass p-4 rounded-2xl border border-white/10 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-blue-400">
                <MapPin className="h-4 w-4" />
                <span className="text-xs font-bold uppercase tracking-wider">Caller Location Data</span>
              </div>
              {locationData && (
                <span className={cn(
                  "text-[10px] font-bold px-2.5 py-0.5 rounded-full border flex items-center gap-1.5",
                  locationData.accuracyMeters < 20
                    ? "bg-green-500/20 text-green-300 border-green-500/30"
                    : locationData.accuracyMeters <= 100
                      ? "bg-amber-500/20 text-amber-300 border-amber-500/30"
                      : "bg-red-500/20 text-red-300 border-red-500/30"
                )}>
                  <span className={cn(
                    "w-1.5 h-1.5 rounded-full",
                    locationData.accuracyMeters < 20
                      ? "bg-green-400"
                      : locationData.accuracyMeters <= 100
                        ? "bg-amber-400"
                        : "bg-red-400"
                  )} />
                  {locationData.accuracyMeters < 20
                    ? `High Accuracy (±${locationData.accuracyMeters}m)`
                    : locationData.accuracyMeters <= 100
                      ? `Moderate Accuracy (±${locationData.accuracyMeters}m)`
                      : `Low Accuracy (±${locationData.accuracyMeters}m)`}
                </span>
              )}
            </div>

            <p className="text-xs md:text-sm text-slate-200 font-mono bg-black/30 p-2.5 rounded-xl border border-white/5 truncate">
              {locationDisplay}
            </p>

            <div className="flex items-center gap-2 pt-1">
              <button
                onClick={handleLocationClick}
                disabled={isLocating}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-xs font-medium text-white transition-colors disabled:opacity-50"
              >
                <Compass className="h-3.5 w-3.5 text-blue-400" />
                {isLocating ? "Refreshing..." : "Retry GPS"}
              </button>
              <button
                onClick={() => setShowManualLocation(!showManualLocation)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-xs font-medium text-slate-300 transition-colors"
              >
                Enter Landmark / Address
              </button>
            </div>

            {showManualLocation && (
              <div className="mt-2 p-3 rounded-xl bg-black/40 border border-white/10 flex flex-col gap-2 animate-fadeIn">
                <p className="text-xs text-slate-400 font-medium">Specify nearest landmark, gate, or cross-street:</p>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={manualLandmark}
                    onChange={(e) => setManualLandmark(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleApplyManualLocation()}
                    placeholder="e.g. Near Apollo Hospital Gate 2, Mount Road"
                    className="flex-1 bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-xs text-white outline-none focus:border-blue-500/50"
                  />
                  <button
                    onClick={handleApplyManualLocation}
                    disabled={!manualLandmark.trim()}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold transition-colors disabled:opacity-40"
                  >
                    Save
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Text input area (REST fallback) */}
          <div className="w-full max-w-2xl mb-8 flex gap-3">
            <input
              type="text"
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendText()}
              placeholder={
                isSending ? "Processing..." : "Type text message if unable to speak..."
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

          {/* Main content: transcript + summary/guidance + nearby facilities */}
          <div className="flex flex-col lg:flex-row gap-8 w-full max-w-5xl items-start mb-8">
            {/* Live Transcript */}
            <div className="flex-1 w-full min-h-[350px] max-h-[500px]">
              <LiveTranscript
                entries={transcript}
                placeholder={
                  isMicActive
                    ? "🎙️ Listening... Speak naturally to provide emergency details."
                    : "Press Mic or type a message to start voice triage."
                }
              />
            </div>

            {/* Summary panel + guidance + facilities */}
            <div className="flex-1 w-full flex flex-col gap-6">
              <SummaryPanel
                data={{
                  age: incident?.caller_age,
                  emergency:
                    incident?.emergency_type ??
                    (selectedService ? selectedService.toUpperCase() : undefined),
                  severity: severityLabel,
                  location:
                    incident?.location ??
                    (locationDisplay !== "Awaiting location..." && locationDisplay !== "Location unavailable"
                      ? locationDisplay
                      : undefined),
                  actionTaken: incident?.routed_service
                    ? `${incident.routed_service} dispatched`
                    : undefined,
                }}
              />

              {guidance && <GuidancePanel guidance={guidance} />}

              {/* Nearby Facilities Card */}
              <NearbyFacilitiesCard
                latitude={locationData?.latitude}
                longitude={locationData?.longitude}
              />
            </div>
          </div>
        </>
      )}

      {/* ── Emergency Visual Evidence Recording Modal ── */}
      {showVideo && (
        <div className="video-overlay fixed inset-0 z-50 flex items-center justify-center p-4 md:p-6 bg-black/85 backdrop-blur-md">
          <div className="relative glass p-4 md:p-6 rounded-3xl w-full max-w-3xl flex flex-col border border-white/20 shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Film className="h-5 w-5 text-red-500" />
                <h3 className="text-base md:text-lg font-black uppercase tracking-wider text-white">
                  Emergency Visual Evidence Recorder
                </h3>
              </div>
              <button
                onClick={stopVideo}
                className="p-2 bg-white/10 hover:bg-white/20 rounded-full text-slate-300 hover:text-white transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Category Selector */}
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400 mr-1">Scene:</span>
              {SCENE_CATEGORIES.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setVideoCategory(c.id)}
                  className={cn(
                    "px-3 py-1 rounded-full text-xs font-bold transition-all",
                    videoCategory === c.id
                      ? "bg-red-600 text-white shadow-md shadow-red-600/30"
                      : "bg-white/5 text-slate-400 hover:text-white border border-white/5"
                  )}
                >
                  {c.label}
                </button>
              ))}
            </div>

            {/* Camera Viewport */}
            <div className="relative w-full aspect-video rounded-2xl overflow-hidden bg-black border border-white/10 mb-4">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-cover"
              />
              {isRecordingVideo && (
                <div className="absolute top-4 left-4 z-10 flex items-center gap-2 bg-red-600/90 text-white px-3 py-1.5 rounded-full font-mono text-xs font-bold shadow-lg animate-pulse">
                  <span className="h-2.5 w-2.5 rounded-full bg-white animate-ping" />
                  REC {Math.floor(recordingSeconds / 60).toString().padStart(2, "0")}:{(recordingSeconds % 60).toString().padStart(2, "0")}
                </div>
              )}
            </div>

            {/* Controls */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                {!isRecordingVideo ? (
                  <button
                    onClick={startVideoRecording}
                    className="flex items-center gap-2 px-5 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-2xl font-bold text-xs uppercase tracking-wider shadow-lg transition-colors"
                  >
                    <CircleDot className="h-4 w-4" />
                    Record Video Evidence
                  </button>
                ) : (
                  <button
                    onClick={stopVideoRecording}
                    className="flex items-center gap-2 px-5 py-2.5 bg-slate-700 hover:bg-slate-600 text-white rounded-2xl font-bold text-xs uppercase tracking-wider shadow-lg transition-colors"
                  >
                    <Square className="h-4 w-4 fill-current text-red-500" />
                    Stop & Transmit Video
                  </button>
                )}

                <button
                  onClick={captureEvidenceFrame}
                  disabled={isCapturingFrame}
                  className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 rounded-2xl text-white font-bold text-xs uppercase tracking-wider transition-colors shadow-lg disabled:opacity-50"
                >
                  {isCapturingFrame ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Camera className="h-4 w-4" />
                  )}
                  Capture Snapshot
                </button>

                {/* Upload Image Evidence Button */}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/jpg"
                  onChange={handleFileSelect}
                  className="hidden"
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isAnalyzingUpload}
                  className="flex items-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 rounded-2xl text-white font-bold text-xs uppercase tracking-wider transition-colors shadow-lg disabled:opacity-50"
                >
                  <Upload className="h-4 w-4" />
                  Upload Evidence
                </button>
              </div>

              {(recordedClips.length > 0 || capturedFrames.length > 0) && (
                <div className="flex items-center gap-2 bg-black/40 px-3 py-1.5 rounded-xl border border-white/10 text-xs text-green-300">
                  <CheckCircle2 className="h-4 w-4 text-green-400" />
                  <span>{recordedClips.length} clip(s), {capturedFrames.length} frame(s) sent</span>
                </div>
              )}
            </div>

            {/* Error Message */}
            {uploadError && (
              <div className="mt-3 p-3 bg-red-950/50 border border-red-500/40 rounded-xl flex items-center justify-between text-xs text-red-200">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
                  <span>{uploadError}</span>
                </div>
                <button onClick={() => setUploadError(null)} className="text-red-400 hover:text-white">
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}

            {/* Pre-Upload Selected File Card */}
            {selectedUploadFile && (
              <div className="mt-4 p-4 bg-slate-900/90 border border-emerald-500/30 rounded-2xl">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <ImageIcon className="h-4 w-4 text-emerald-400" />
                    <span className="text-xs font-bold uppercase tracking-wider text-emerald-300">
                      Selected Evidence Image
                    </span>
                  </div>
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                    Scene: {SCENE_CATEGORIES.find((c) => c.id === videoCategory)?.label || videoCategory}
                  </span>
                </div>

                <div className="flex flex-col sm:flex-row items-center gap-4">
                  <div className="w-32 h-24 rounded-xl overflow-hidden bg-black border border-white/10 shrink-0">
                    <img
                      src={selectedUploadFile.dataUrl}
                      alt={selectedUploadFile.name}
                      className="w-full h-full object-cover"
                    />
                  </div>

                  <div className="flex-1 text-xs space-y-1 w-full sm:w-auto">
                    <p className="font-bold text-slate-200 truncate">{selectedUploadFile.name}</p>
                    <p className="text-slate-400 font-mono text-[11px]">
                      Size: {(selectedUploadFile.sizeBytes / 1024).toFixed(1)} KB
                    </p>
                    <p className="text-slate-400 text-[11px]">
                      Format: {selectedUploadFile.file.type.replace("image/", "").toUpperCase()}
                    </p>
                  </div>

                  <div className="flex sm:flex-col gap-2 w-full sm:w-auto">
                    <button
                      onClick={handleUploadAndAnalyze}
                      disabled={isAnalyzingUpload}
                      className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50"
                    >
                      {isAnalyzingUpload ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Analyzing...
                        </>
                      ) : (
                        <>
                          <Sparkles className="h-4 w-4" />
                          Analyze & Upload
                        </>
                      )}
                    </button>
                    <button
                      onClick={handleCancelUpload}
                      disabled={isAnalyzingUpload}
                      className="flex-1 sm:flex-none px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* AI Visual Observation Result Card */}
            {latestVisualAnalysis && (
              <div className="mt-4 p-4 bg-slate-900/95 border border-indigo-500/30 rounded-2xl shadow-xl">
                <div className="flex items-center justify-between border-b border-white/10 pb-2.5 mb-3">
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-indigo-400" />
                    <h4 className="text-xs font-black uppercase tracking-wider text-white">
                      VISUAL ANALYSIS
                    </h4>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                      Source: {latestVisualAnalysis.source}
                    </span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/10 text-slate-300 border border-white/10">
                      Scene: {SCENE_CATEGORIES.find((c) => c.id === latestVisualAnalysis.scene)?.label || latestVisualAnalysis.scene}
                    </span>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row items-start gap-4 mb-3">
                  <div className="w-28 h-20 rounded-xl overflow-hidden bg-black border border-white/10 shrink-0">
                    <img
                      src={latestVisualAnalysis.dataUrl}
                      alt="Analyzed Evidence"
                      className="w-full h-full object-cover"
                    />
                  </div>

                  <div className="flex-1">
                    <span className="text-[10px] font-black uppercase tracking-wider text-indigo-300 block mb-1.5">
                      AI VISUAL OBSERVATIONS
                    </span>
                    {latestVisualAnalysis.observations && latestVisualAnalysis.observations.length > 0 ? (
                      <ul className="space-y-2 text-xs text-slate-200">
                        {latestVisualAnalysis.observations.map((obs, idx) => (
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
                    ) : latestVisualAnalysis.status === "unavailable" || latestVisualAnalysis.status === "error" ? (
                      <p className="text-xs text-amber-300 italic">
                        {latestVisualAnalysis.message || "Visual analysis unavailable. The uploaded evidence was not analyzed."}
                      </p>
                    ) : (
                      <p className="text-xs text-slate-400 italic">
                        No distinct critical hazards observed.
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-1.5 p-2 bg-amber-950/30 border border-amber-500/30 rounded-xl text-[11px] text-amber-300">
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                  <span>⚠ AI-generated observation — dispatcher verification required</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Emergency Contacts Modal ── */}
      <EmergencyContactsModal
        isOpen={showContactsModal}
        onClose={() => setShowContactsModal(false)}
        emergencyType={incident?.emergency_type || (selectedService ? selectedService.toUpperCase() : null)}
        priorityLabel={severityLabel}
        location={locationDisplay}
        guidance={guidance}
        language={language}
        sessionId={sessionId}
      />

      {/* ── Share Summary Dossier Modal ── */}
      <ShareSummaryModal
        isOpen={showSummaryModal}
        onClose={() => setShowSummaryModal(false)}
        summaryData={{
          emergencyType: incident?.emergency_type || (selectedService ? selectedService.toUpperCase() : null),
          priorityLabel: severityLabel,
          priority: incident?.priority,
          location: locationDisplay,
          locationAccuracy: locationData?.accuracyMeters,
          language,
          guidance,
          sensorHeartRate: sensorTelemetry?.heart_rate,
          sensorSpo2: sensorTelemetry?.spo2,
          hasVideoEvidence: recordedClips.length > 0 || capturedFrames.length > 0,
          sessionId,
        }}
      />
    </div>
  )
}
