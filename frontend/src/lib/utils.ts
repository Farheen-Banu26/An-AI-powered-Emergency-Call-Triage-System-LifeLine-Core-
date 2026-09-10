export function cn(...cls: (string | false | null | undefined)[]): string {
  return cls.filter(Boolean).join(" ")
}

export function genId(): string {
  return crypto.randomUUID()
}

export function priorityLabel(p: number | null): string {
  if (p === 1) return "CRITICAL"
  if (p === 2) return "HIGH"
  if (p === 3) return "MEDIUM"
  if (p === 4) return "LOW"
  if (p === 5) return "INFO"
  return "—"
}

export function priorityColor(p: number | null): string {
  if (p === 1) return "text-red-500"
  if (p === 2) return "text-orange-400"
  if (p === 3) return "text-yellow-400"
  if (p === 4) return "text-blue-400"
  return "text-slate-500"
}

export function statusStyle(status: string): string {
  switch (status) {
    case "ready_to_dispatch":
      return "bg-green-500/15 text-green-400 border-green-500/30"
    case "gathering_info":
      return "bg-yellow-500/15 text-yellow-400 border-yellow-500/30"
    default:
      return "bg-slate-700/40 text-slate-400 border-slate-600/30"
  }
}

export function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}
