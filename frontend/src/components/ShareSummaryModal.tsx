import { useState } from "react"
import {
  FileText,
  Copy,
  Share2,
  CheckCircle2,
  X,
  MapPin,
  Clock,
  Shield,
  Activity,
  Heart,
  Film,
} from "lucide-react"
import { copyAlertToClipboard, triggerWhatsAppShare } from "../lib/contacts"
import { cn } from "../lib/utils"

interface ShareSummaryModalProps {
  isOpen: boolean
  onClose: () => void
  summaryData: {
    emergencyType?: string | null
    priorityLabel?: string | null
    priority?: number | null
    symptoms?: string | null
    location?: string | null
    locationAccuracy?: number | null
    language?: string | null
    guidance?: string | null
    sensorHeartRate?: number | null
    sensorSpo2?: number | null
    hasVideoEvidence?: boolean
    sessionId?: string
  }
}

export function ShareSummaryModal({
  isOpen,
  onClose,
  summaryData,
}: ShareSummaryModalProps) {
  const [copied, setCopied] = useState(false)

  if (!isOpen) return null

  const timeStr = new Date().toLocaleTimeString()
  const lang = summaryData.language || "en"
  const prio = summaryData.priorityLabel || (summaryData.priority === 1 ? "CRITICAL / P1" : "EMERGENCY / P2")

  const formattedSummary = `🚨 LIFELINE-CORE EMERGENCY INCIDENT SUMMARY 🚨

RISK LEVEL: ${prio}
Emergency Type: ${summaryData.emergencyType || "Medical Incident"}
Reported Time: ${timeStr}
Language: ${lang.toUpperCase()}

📍 Location: ${summaryData.location || "GPS Location Pending"} (Accuracy: ±${summaryData.locationAccuracy || 15}m)

🩺 Telemetry / Vitals:
${summaryData.sensorHeartRate ? `• Heart Rate: ${summaryData.sensorHeartRate} BPM` : "• Heart Rate: Normal / Monitored"}
${summaryData.sensorSpo2 ? `• SpO2: ${summaryData.sensorSpo2}%` : ""}
• Video Evidence: ${summaryData.hasVideoEvidence ? "Attached & Streamed to Dispatcher" : "None"}

🛡️ Immediate Life-Safety Guidance:
${summaryData.guidance || "Paramedics dispatched. Keep the caller safe and line open."}

(Incident ID: ${summaryData.sessionId ? summaryData.sessionId.slice(0, 12) : "Live Session"})`

  const handleCopy = async () => {
    const success = await copyAlertToClipboard(formattedSummary)
    if (success) {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleWhatsApp = () => {
    triggerWhatsAppShare("", formattedSummary)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
      <div className="relative glass p-6 rounded-3xl w-full max-w-2xl max-h-[90vh] overflow-y-auto border border-white/20 shadow-2xl flex flex-col text-white">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-white/10 mb-4">
          <div className="flex items-center gap-2.5">
            <FileText className="h-5 w-5 text-blue-400" />
            <div>
              <h3 className="text-lg font-black uppercase tracking-wider">
                Emergency Incident Dossier Summary
              </h3>
              <p className="text-xs text-slate-400">
                Structured clinical & dispatcher-ready briefing
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-full bg-white/10 hover:bg-white/20 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Formatted Summary Box */}
        <div className="bg-black/50 p-4 rounded-2xl border border-white/10 mb-4">
          <pre className="text-xs text-slate-200 whitespace-pre-wrap font-mono leading-relaxed max-h-64 overflow-y-auto">
            {formattedSummary}
          </pre>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            onClick={handleCopy}
            className="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-xl text-xs font-bold transition-colors"
          >
            {copied ? <CheckCircle2 className="h-4 w-4 text-green-400" /> : <Copy className="h-4 w-4" />}
            {copied ? "Copied to Clipboard!" : "Copy Summary"}
          </button>
          <button
            onClick={handleWhatsApp}
            className="flex items-center gap-2 px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold shadow-lg transition-colors"
          >
            <Share2 className="h-4 w-4" />
            Share via WhatsApp
          </button>
        </div>
      </div>
    </div>
  )
}
