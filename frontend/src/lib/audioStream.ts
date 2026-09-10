/**
 * WebSocket-based audio streaming to the backend.
 *
 * Captures mic → downsamples to 16 kHz mono int16 PCM → sends over WS.
 * Receives JSON messages: { type: "transcript" | "question", ... }
 */

export interface StreamCallbacks {
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
  ) => void
  onProcessing?: () => void
  onConnected?: () => void
  onDisconnected?: () => void
  onError?: (msg: string) => void
}

export class AudioStream {
  private ws: WebSocket | null = null
  private ctx: AudioContext | null = null
  private stream: MediaStream | null = null
  private processor: ScriptProcessorNode | null = null
  private source: MediaStreamAudioSourceNode | null = null

  constructor(
    private sessionId: string,
    private cb: StreamCallbacks,
    private language: string = "en",
  ) {}

  async start() {
    // 1. Capture microphone
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })

    // 2. Audio context at native sample rate (we resample manually)
    this.ctx = new AudioContext()
    this.source = this.ctx.createMediaStreamSource(this.stream)
    this.processor = this.ctx.createScriptProcessor(4096, 1, 1)

    const nativeRate = this.ctx.sampleRate
    const targetRate = 16000

    // 3. Open WebSocket through Vite proxy
    const proto = location.protocol === "https:" ? "wss:" : "ws:"
    this.ws = new WebSocket(
      `${proto}//${location.host}/api/stream/audio?session_id=${this.sessionId}&lang=${this.language}`,
    )
    this.ws.binaryType = "arraybuffer"

    this.ws.onopen = () => {
      this.cb.onConnected?.()

      // Start sending PCM frames
      this.processor!.onaudioprocess = (e) => {
        if (this.ws?.readyState !== WebSocket.OPEN) return
        const raw = e.inputBuffer.getChannelData(0)

        // Down-sample from native → 16 kHz
        const ratio = nativeRate / targetRate
        const len = Math.floor(raw.length / ratio)
        const int16 = new Int16Array(len)
        for (let i = 0; i < len; i++) {
          const s = Math.max(-1, Math.min(1, raw[Math.floor(i * ratio)]))
          int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
        }
        this.ws!.send(int16.buffer)
      }

      this.source!.connect(this.processor!)
      this.processor!.connect(this.ctx!.destination)
    }

    this.ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data as string)
        if (data.type === "transcript") {
          this.cb.onTranscript?.(data.text)
        } else if (data.type === "question") {
          this.cb.onQuestion?.(data.text, data.guidance, data.status, data.priority_score, data.priority_label, data.fake_label, data.fake_probability, data.fake_signals)
        } else if (data.type === "processing") {
          this.cb.onProcessing?.()
        }
        // 'ping' type is silently ignored (keep-alive)
      } catch {
        /* binary frame or non-JSON — ignore */
      }
    }

    this.ws.onerror = () => this.cb.onError?.("WebSocket connection error")
    this.ws.onclose = () => this.cb.onDisconnected?.()
  }

  stop() {
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
  }
}
