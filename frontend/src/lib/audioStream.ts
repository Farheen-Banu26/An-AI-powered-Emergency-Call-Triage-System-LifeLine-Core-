/**
 * WebSocket-based audio streaming with Client-Side Voice Activity Detection (VAD).
 *
 * Captures mic → downsamples to 16 kHz mono int16 PCM → monitors RMS energy
 * → buffers pre-roll frames → gates transmission on sustained speech
 * → enforces silence hangover → sends over WS.
 */

export type MicState = "idle" | "listening" | "speaking" | "processing"

export interface StreamCallbacks {
  onStateChange?: (state: MicState) => void
  onTranscript?: (text: string) => void
  onQuestion?: (
    text: string | null,
    guidance: string | null,
    status: string,
    priorityScore?: number | null,
    priorityLabel?: string | null,
    fakeLabel?: string | null,
    fakeProbability?: number | null,
    fakeSignals?: string[],
    audioBase64?: string,
    languageCode?: string,
  ) => void
  onProcessing?: () => void
  onConnected?: () => void
  onDisconnected?: () => void
  onError?: (msg: string) => void
}

/* ── VAD Configuration Constants ── */
export const VAD_CONFIG = {
  MIN_SPEECH_DURATION_MS: 180, // Minimum sustained voice energy to declare speech start (reject transient clicks)
  SILENCE_HANGOVER_MS: 600, // Optimized silence duration after speech before closing utterance
  PRE_ROLL_MS: 300, // Pre-roll history to prevent cutting initial consonants
  MIN_UTTERANCE_MS: 350, // Utterances shorter than this are discarded as transient noise
  ENERGY_MULTIPLIER: 1.8, // Speech threshold = noiseFloor * ENERGY_MULTIPLIER
  MIN_ABSOLUTE_RMS: 0.012, // Proven sensitive floor for laptop microphones with dynamic noise-floor adaptation
  MAX_SPEECH_DURATION_MS: 15000, // Safety cap to avoid infinite utterance
}

export class AudioStream {
  private ws: WebSocket | null = null
  private ctx: AudioContext | null = null
  private stream: MediaStream | null = null
  private processor: ScriptProcessorNode | null = null
  private source: MediaStreamAudioSourceNode | null = null

  // VAD tracking state
  private currentState: MicState = "idle"
  private noiseFloor: number = 0.01
  private speechStartTimestamp: number = 0
  private lastVoicedTimestamp: number = 0
  private isVoiced: boolean = false
  private preRollBuffer: ArrayBuffer[] = []
  private preRollMaxFrames: number = 5 // Computed dynamically based on chunk duration
  private speechFramesSent: number = 0
  private processingWatchdog: any = null

  constructor(
    private sessionId: string,
    private cb: StreamCallbacks,
    private language: string = "en",
  ) {}

  public setLanguage(newLanguage: string) {
    this.language = newLanguage
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "set_language", language: newLanguage }))
      console.log(`[VOICE] language=${newLanguage} event=language_updated session_id=${this.sessionId}`)
    }
  }

  private clearWatchdog() {
    if (this.processingWatchdog) {
      clearTimeout(this.processingWatchdog)
      this.processingWatchdog = null
    }
  }

  private setState(newState: MicState) {
    if (this.currentState !== newState) {
      this.currentState = newState
      if (newState === "processing") {
        this.clearWatchdog()
        this.processingWatchdog = setTimeout(() => {
          if (this.currentState === "processing") {
            console.warn(`[VOICE] language=${this.language} event=processing_watchdog_timeout session_id=${this.sessionId}`)
            this.setState("listening")
            this.cb.onError?.("Processing timeout. Please speak again.")
          }
        }, 15000)
      } else {
        this.clearWatchdog()
      }
      this.cb.onStateChange?.(newState)
    }
  }

  private calculateRMS(samples: Float32Array): number {
    let sum = 0
    for (let i = 0; i < samples.length; i++) {
      sum += samples[i] * samples[i]
    }
    return Math.sqrt(sum / samples.length)
  }

  async start() {
    // 1. Capture microphone with noise suppression and echo cancellation
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    })
    console.log(`[VOICE] language=${this.language} event=mic_started session_id=${this.sessionId}`)

    // 2. Audio context at native sample rate
    this.ctx = new AudioContext()
    this.source = this.ctx.createMediaStreamSource(this.stream)
    const bufferSize = 4096
    this.processor = this.ctx.createScriptProcessor(bufferSize, 1, 1)

    const nativeRate = this.ctx.sampleRate
    const targetRate = 16000
    const chunkDurationMs = (bufferSize / nativeRate) * 1000
    this.preRollMaxFrames = Math.max(3, Math.ceil(VAD_CONFIG.PRE_ROLL_MS / chunkDurationMs))

    // 3. Open WebSocket
    const proto = location.protocol === "https:" ? "wss:" : "ws:"
    this.ws = new WebSocket(
      `${proto}//${location.host}/api/stream/audio?session_id=${this.sessionId}&lang=${this.language}`,
    )
    this.ws.binaryType = "arraybuffer"

    this.ws.onopen = () => {
      console.log(`[VOICE] language=${this.language} event=websocket_connected session_id=${this.sessionId}`)
      this.setState("listening")
      this.cb.onConnected?.()

      this.processor!.onaudioprocess = (e) => {
        if (this.ws?.readyState !== WebSocket.OPEN) return
        const raw = e.inputBuffer.getChannelData(0)
        const now = performance.now()

        // ── 1. Calculate RMS Energy ─────────────────────────────
        const rms = this.calculateRMS(raw)
        const speechThreshold = Math.max(
          VAD_CONFIG.MIN_ABSOLUTE_RMS,
          this.noiseFloor * VAD_CONFIG.ENERGY_MULTIPLIER,
        )
        const isFrameAboveThreshold = rms >= speechThreshold

        // ── 2. Down-sample from native → 16 kHz mono Int16 ──────
        const ratio = nativeRate / targetRate
        const len = Math.floor(raw.length / ratio)
        const int16 = new Int16Array(len)
        for (let i = 0; i < len; i++) {
          const s = Math.max(-1, Math.min(1, raw[Math.floor(i * ratio)]))
          int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
        }
        const pcmBuffer = int16.buffer

        // ── 3. VAD State Machine ────────────────────────────────
        if (!this.isVoiced) {
          // Track background noise floor during quiet periods
          if (!isFrameAboveThreshold) {
            this.noiseFloor = this.noiseFloor * 0.95 + rms * 0.05
          }

          // Maintain rolling pre-roll buffer
          this.preRollBuffer.push(pcmBuffer)
          if (this.preRollBuffer.length > this.preRollMaxFrames) {
            this.preRollBuffer.shift()
          }

          if (isFrameAboveThreshold) {
            if (this.speechStartTimestamp === 0) {
              this.speechStartTimestamp = now
            } else if (now - this.speechStartTimestamp >= VAD_CONFIG.MIN_SPEECH_DURATION_MS) {
              // Sustained speech confirmed → Enter voiced mode
              this.isVoiced = true
              this.lastVoicedTimestamp = now
              this.speechFramesSent = 0
              console.log(`[VOICE] language=${this.language} event=vad_speech_started session_id=${this.sessionId}`)
              this.setState("speaking")

              // Flush pre-roll buffer to backend
              for (const frame of this.preRollBuffer) {
                this.ws.send(frame)
                this.speechFramesSent++
              }
              this.preRollBuffer = []

              // Send current frame
              this.ws.send(pcmBuffer)
              this.speechFramesSent++
            }
          } else {
            this.speechStartTimestamp = 0
          }
        } else {
          // Voiced mode active → Stream frame
          this.ws.send(pcmBuffer)
          this.speechFramesSent++

          if (isFrameAboveThreshold) {
            this.lastVoicedTimestamp = now
          }

          const silenceDuration = now - this.lastVoicedTimestamp
          const totalSpeechDuration = now - this.speechStartTimestamp

          // Silence hangover reached or max duration exceeded → Conclude utterance
          if (
            silenceDuration >= VAD_CONFIG.SILENCE_HANGOVER_MS ||
            totalSpeechDuration >= VAD_CONFIG.MAX_SPEECH_DURATION_MS
          ) {
            const utteranceDuration = now - this.speechStartTimestamp - silenceDuration
            this.isVoiced = false
            this.speechStartTimestamp = 0
            this.preRollBuffer = []

            if (utteranceDuration >= VAD_CONFIG.MIN_UTTERANCE_MS && this.speechFramesSent >= 4) {
              console.log(`[VOICE] language=${this.language} event=speech_end_sent session_id=${this.sessionId} frames=${this.speechFramesSent}`)
              this.setState("processing")
              this.cb.onProcessing?.()
              if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: "speech_end" }))
              }
            } else {
              // Discard transient click/pop
              this.setState("listening")
              if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: "speech_discard" }))
              }
            }
          }
        }
      }

      this.source!.connect(this.processor!)
      this.processor!.connect(this.ctx!.destination)
    }

    this.ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data as string)
        if (data.type === "transcript") {
          console.log(`[VOICE] language=${this.language} event=transcript_received session_id=${this.sessionId} text=${data.text}`)
          this.cb.onTranscript?.(data.text)
        } else if (data.type === "question") {
          this.clearWatchdog()
          this.setState("listening")
          this.cb.onQuestion?.(
            data.text,
            data.guidance,
            data.status,
            data.priority_score,
            data.priority_label,
            data.fake_label,
            data.fake_probability,
            data.fake_signals,
            data.audio_base64,
            data.language_code,
          )
        } else if (data.type === "processing") {
          this.setState("processing")
          this.cb.onProcessing?.()
        } else if (data.type === "vad_state") {
          if (data.state === "listening" || data.state === "speaking" || data.state === "processing") {
            this.setState(data.state)
          }
        } else if (data.type === "error") {
          this.clearWatchdog()
          this.setState("listening")
          this.cb.onError?.(data.message || "Speech processing error")
        }
      } catch {
        /* non-JSON binary frame */
      }
    }

    this.ws.onerror = () => {
      this.clearWatchdog()
      this.setState("idle")
      this.cb.onError?.("WebSocket connection error")
    }

    this.ws.onclose = () => {
      this.clearWatchdog()
      this.setState("idle")
      this.cb.onDisconnected?.()
    }
  }

  stop() {
    this.clearWatchdog()
    this.setState("idle")
    this.processor?.disconnect()
    this.source?.disconnect()
    if (this.ctx?.state !== "closed") this.ctx?.close()
    this.stream?.getTracks().forEach((t) => t.stop())
    this.ws?.close()
    this.processor = null
    this.source = null
    this.ctx = null
    this.stream = null
    this.ws = null
    this.isVoiced = false
    this.speechStartTimestamp = 0
    this.preRollBuffer = []
  }
}
