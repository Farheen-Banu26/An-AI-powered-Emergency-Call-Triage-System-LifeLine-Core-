import { useEffect, useRef } from "react"
import type { TranscriptEntry } from "../types"
import { cn, formatTime } from "../lib/utils"

interface Props {
  entries: TranscriptEntry[]
  placeholder?: string
}

export default function LiveTranscript({ entries, placeholder }: Props) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [entries])

  return (
    <div className="flex flex-1 flex-col overflow-y-auto rounded-2xl border border-white/5 bg-surface p-4">
      {entries.length === 0 ? (
        <div className="flex flex-1 items-center justify-center text-sm text-slate-600">
          {placeholder ?? "No messages yet"}
        </div>
      ) : (
        <div className="space-y-3">
          {entries.map((t, i) => (
            <div
              key={i}
              className={cn(
                "flex gap-3",
                t.role === "caller" && "justify-end",
                t.role === "system" && "justify-center",
              )}
            >
              <div
                className={cn(
                  "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
                  t.role === "caller" && "bg-red-600/15 border border-red-500/15 text-white",
                  t.role === "ai" && "bg-blue-600/15 border border-blue-500/15 text-blue-100",
                  t.role === "system" && "bg-slate-800/50 text-slate-500 text-xs rounded-xl",
                )}
              >
                {t.role !== "system" && (
                  <p className="mb-1 text-[10px] font-bold uppercase tracking-wider opacity-40">
                    {t.role === "caller" ? "You" : "AI Dispatcher"}
                  </p>
                )}
                <p>{t.text}</p>
                {t.role !== "system" && (
                  <p className="mt-1 text-right text-[9px] opacity-30">
                    {formatTime(t.timestamp)}
                  </p>
                )}
              </div>
            </div>
          ))}
          <div ref={endRef} />
        </div>
      )}
    </div>
  )
}
