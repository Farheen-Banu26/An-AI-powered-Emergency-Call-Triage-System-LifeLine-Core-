import { ShieldCheck } from "lucide-react"

interface Props {
  guidance: string
}

export default function GuidancePanel({ guidance }: Props) {
  // Split numbered items from the guidance string
  const lines = guidance
    .split(/\n/)
    .map((l) => l.trim())
    .filter(Boolean)

  return (
    <div className="rounded-2xl border border-green-500/20 bg-green-500/5 p-5">
      <div className="mb-3 flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-green-400" />
        <h3 className="text-xs font-bold uppercase tracking-wider text-green-400">
          Safety Guidance
        </h3>
      </div>
      <ul className="space-y-2">
        {lines.map((line, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-green-200/80">
            <span className="mt-0.5 text-green-500">•</span>
            <span>{line.replace(/^\d+[\.\)]\s*/, "")}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
