import {
  AlertTriangle,
  MapPin,
  User,
  Phone,
  Users,
  Siren,
  FileText,
} from "lucide-react"
import type { IncidentData } from "../types"
import { priorityLabel, priorityColor, cn } from "../lib/utils"
import StatusBadge from "./StatusBadge"

interface Props {
  incident: IncidentData | null
}

export default function IncidentSummary({ incident }: Props) {
  if (!incident) {
    return (
      <div className="rounded-2xl border border-white/5 bg-surface p-6 text-center text-sm text-slate-600">
        Incident data will appear here as you speak with the AI dispatcher.
      </div>
    )
  }

  const rows: { icon: React.ReactNode; label: string; value: string | null }[] = [
    { icon: <AlertTriangle className="h-3.5 w-3.5" />, label: "Type", value: incident.emergency_type },
    { icon: <MapPin className="h-3.5 w-3.5" />, label: "Location", value: incident.location },
    { icon: <User className="h-3.5 w-3.5" />, label: "Caller", value: incident.caller_name },
    { icon: <Phone className="h-3.5 w-3.5" />, label: "Phone", value: incident.caller_phone },
    { icon: <Users className="h-3.5 w-3.5" />, label: "Casualties", value: incident.casualties != null ? String(incident.casualties) : null },
    { icon: <Siren className="h-3.5 w-3.5" />, label: "Service", value: incident.routed_service },
  ]

  return (
    <div className="rounded-2xl border border-white/5 bg-surface p-5">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
          Incident Summary
        </h3>
        <StatusBadge
          label={incident.status === "ready_to_dispatch" ? "Dispatched" : "In Progress"}
          status={incident.status}
        />
      </div>

      {/* Priority + Severity bar */}
      {(incident.priority != null || incident.priority_label) && (
        <div className="mb-4 flex gap-2">
          {incident.priority != null && (
            <div
              className={cn(
                "flex flex-1 items-center justify-between rounded-xl border px-4 py-2",
                incident.priority === 1
                  ? "border-red-500/30 bg-red-500/10"
                  : incident.priority === 2
                    ? "border-orange-500/30 bg-orange-500/10"
                    : "border-yellow-500/30 bg-yellow-500/10",
              )}
            >
              <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">Priority</span>
              <span className={cn("text-sm font-black", priorityColor(incident.priority))}>
                {priorityLabel(incident.priority)}
              </span>
            </div>
          )}
          {incident.priority_label && (
            <div
              className={cn(
                "flex flex-1 items-center justify-between rounded-xl border px-4 py-2",
                incident.priority_label === "CRITICAL (Cat 1)"
                  ? "border-red-500/30 bg-red-500/10"
                  : incident.priority_label.startsWith("EMERGENCY")
                    ? "border-orange-500/30 bg-orange-500/10"
                    : incident.priority_label.startsWith("URGENT")
                      ? "border-yellow-500/30 bg-yellow-500/10"
                      : "border-slate-500/30 bg-slate-500/10",
              )}
            >
              <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">Severity</span>
              <span className={cn(
                "text-xs font-black",
                incident.priority_label === "CRITICAL (Cat 1)" ? "text-red-500"
                  : incident.priority_label.startsWith("EMERGENCY") ? "text-orange-400"
                  : incident.priority_label.startsWith("URGENT") ? "text-yellow-400"
                  : "text-slate-400",
              )}>
                {incident.priority_label}
              </span>
            </div>
          )}
          {incident.priority_score != null && (
            <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-surface-light px-3 py-2">
              <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">Score</span>
              <span className={cn(
                "text-lg font-black tabular-nums",
                incident.priority_score >= 8 ? "text-red-500"
                  : incident.priority_score >= 5 ? "text-orange-400"
                  : incident.priority_score >= 3 ? "text-yellow-400"
                  : "text-slate-400",
              )}>
                {incident.priority_score}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Detail rows */}
      <div className="space-y-3">
        {rows.map(
          (r) =>
            r.value && (
              <div key={r.label} className="flex items-start gap-3">
                <span className="mt-0.5 text-slate-500">{r.icon}</span>
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-wider text-slate-600">
                    {r.label}
                  </p>
                  <p className="text-sm text-slate-200">{r.value}</p>
                </div>
              </div>
            ),
        )}
      </div>

      {/* Summary text */}
      {incident.summary && (
        <div className="mt-4 border-t border-white/5 pt-4">
          <div className="flex items-center gap-2 mb-2">
            <FileText className="h-3.5 w-3.5 text-slate-500" />
            <p className="text-[10px] font-medium uppercase tracking-wider text-slate-600">
              Summary
            </p>
          </div>
          <p className="text-xs leading-relaxed text-slate-400">{incident.summary}</p>
        </div>
      )}

      {/* Dispatch plan */}
      {incident.dispatch_plan.length > 0 && (
        <div className="mt-4 border-t border-white/5 pt-4">
          <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-slate-600">
            Dispatch Plan
          </p>
          <div className="space-y-2">
            {incident.dispatch_plan.map((d, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-lg border border-white/5 bg-surface-light px-3 py-2"
              >
                <span className="text-xs font-medium text-slate-300">{d.service}</span>
                <span className={cn("text-[10px] font-bold", priorityColor(d.priority))}>
                  P{d.priority}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
