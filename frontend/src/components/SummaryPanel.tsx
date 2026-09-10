import {
  FileText,
  AlertCircle,
  MapPin,
  User,
  Activity,
} from "lucide-react"
import { cn } from "../lib/utils"

interface SummaryData {
  age?: number | null
  emergency?: string | null
  severity?: string | null
  location?: string | null
  actionTaken?: string | null
}

interface Props {
  data: SummaryData
}

const severityColors: Record<string, string> = {
  Low: "text-green-400",
  Medium: "text-yellow-400",
  High: "text-orange-400",
  Critical: "text-red-500",
}

export function SummaryPanel({ data }: Props) {
  return (
    <div className="glass p-6 rounded-3xl w-full max-w-md shadow-2xl">
      <div className="flex items-center gap-3 mb-6 border-b border-white/10 pb-4">
        <FileText className="text-safe w-6 h-6" />
        <h2 className="text-base font-bold uppercase tracking-widest text-white">
          Incident Summary
        </h2>
      </div>

      <div className="space-y-4">
        {data.age != null && (
          <div className="flex items-center gap-3">
            <User className="w-5 h-5 opacity-60" />
            <div>
              <p className="text-[10px] uppercase opacity-50 font-semibold">
                Patient Age
              </p>
              <p className="text-sm font-medium">{data.age}</p>
            </div>
          </div>
        )}

        {data.emergency && (
          <div className="flex items-center gap-3">
            <AlertCircle className="w-5 h-5 opacity-60" />
            <div>
              <p className="text-[10px] uppercase opacity-50 font-semibold">
                Emergency Type
              </p>
              <p className="text-sm font-medium">{data.emergency}</p>
            </div>
          </div>
        )}

        {data.severity && (
          <div className="flex items-center gap-3">
            <Activity className="w-5 h-5 opacity-60" />
            <div>
              <p className="text-[10px] uppercase opacity-50 font-semibold">
                Severity Level
              </p>
              <p
                className={cn(
                  "text-sm font-bold",
                  severityColors[data.severity] ?? "text-slate-300",
                )}
              >
                {data.severity}
              </p>
            </div>
          </div>
        )}

        {data.location && (
          <div className="flex items-center gap-3">
            <MapPin className="w-5 h-5 opacity-60" />
            <div>
              <p className="text-[10px] uppercase opacity-50 font-semibold">
                Location
              </p>
              <p className="text-xs leading-relaxed">{data.location}</p>
            </div>
          </div>
        )}

        {data.actionTaken && (
          <div className="mt-4 bg-white/5 p-3 rounded-xl border border-white/5">
            <p className="text-[10px] uppercase opacity-50 font-semibold mb-1">
              Actions Taken
            </p>
            <p className="text-safe text-xs font-medium">{data.actionTaken}</p>
          </div>
        )}
      </div>
    </div>
  )
}
