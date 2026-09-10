import { cn } from "../lib/utils"

interface Props {
  label: string
  status: string
}

export default function StatusBadge({ label, status }: Props) {
  const style =
    status === "ready_to_dispatch"
      ? "bg-green-500/15 text-green-400 border-green-500/30"
      : status === "gathering_info"
        ? "bg-yellow-500/15 text-yellow-400 border-yellow-500/30"
        : "bg-slate-700/40 text-slate-400 border-slate-600/30"

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider",
        style,
      )}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          status === "ready_to_dispatch" ? "bg-green-400" : status === "gathering_info" ? "bg-yellow-400 animate-pulse" : "bg-slate-500",
        )}
      />
      {label}
    </span>
  )
}
