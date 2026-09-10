import type { ReactNode } from "react"
import { cn } from "../lib/utils"

interface Props {
  icon: ReactNode
  label: string
  onClick?: () => void
  isActive?: boolean
  variant?: "default" | "emergency" | "safe"
  className?: string
}

export function ControlButton({
  icon,
  label,
  onClick,
  isActive = false,
  variant = "default",
  className,
}: Props) {
  const base =
    "flex flex-col items-center justify-center p-6 rounded-full transition-all duration-300 glass hover:scale-105 active:scale-95 cursor-pointer"

  const variants: Record<string, string> = {
    default: "text-slate-200 border-white/10",
    emergency: "text-emergency border-emergency/20",
    safe: "text-safe border-safe/20",
  }

  const active = isActive
    ? variant === "emergency"
      ? "emergency-glow border-emergency/50 bg-emergency/10"
      : "glow-active border-safe/50 bg-safe/10"
    : ""

  return (
    <button
      onClick={onClick}
      className={cn(base, variants[variant], active, className)}
      aria-label={label}
    >
      <div className="text-3xl mb-2">{icon}</div>
      <span className="text-xs font-semibold uppercase tracking-wider opacity-80">
        {label}
      </span>
    </button>
  )
}
