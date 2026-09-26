import {
  Hospital,
  Navigation,
  ExternalLink,
  ShieldAlert,
} from "lucide-react"
import {
  getNearbySearchLinks,
} from "../lib/facilities"

interface NearbyFacilitiesCardProps {
  latitude?: number | null
  longitude?: number | null
}

export function NearbyFacilitiesCard({ latitude, longitude }: NearbyFacilitiesCardProps) {
  const hasCoords = typeof latitude === "number" && typeof longitude === "number"
  const lat = latitude || 13.0827
  const lon = longitude || 80.2707
  const searchLinks = getNearbySearchLinks(lat, lon)

  return (
    <div className="glass p-5 rounded-2xl border border-white/10 flex flex-col gap-3.5 text-white">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-blue-400">
          <Hospital className="h-4 w-4" />
          <h4 className="text-xs font-bold uppercase tracking-wider">
            Nearby Emergency Facilities Lookup
          </h4>
        </div>
        <span className="text-[10px] text-slate-400 font-mono">
          {hasCoords ? "Live GPS Reference" : "City Reference"}
        </span>
      </div>

      {/* Safety Disclaimer */}
      <p className="text-[11px] text-slate-400 leading-tight">
        <strong className="text-amber-400">Navigation Only:</strong> Real-time mapping actions for nearest hospital emergency rooms, trauma centers, and facilities. Does not claim autonomous ambulance dispatch.
      </p>

      {/* Search Actions */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        <a
          href={searchLinks.hospitalsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-between p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 hover:bg-blue-500/20 transition-all text-xs font-semibold text-blue-200"
        >
          <span className="flex items-center gap-2">
            <Hospital className="h-4 w-4 text-blue-400" />
            Find Nearest Emergency ER
          </span>
          <ExternalLink className="h-3.5 w-3.5 text-blue-300" />
        </a>

        <a
          href={searchLinks.traumaUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-between p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 hover:bg-rose-500/20 transition-all text-xs font-semibold text-rose-200"
        >
          <span className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-rose-400" />
            Find Trauma Centers
          </span>
          <ExternalLink className="h-3.5 w-3.5 text-rose-300" />
        </a>

        <a
          href={searchLinks.ambulanceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-between p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 hover:bg-amber-500/20 transition-all text-xs font-semibold text-amber-200"
        >
          <span className="flex items-center gap-2">
            <Navigation className="h-4 w-4 text-amber-400" />
            Ambulance Stations Map
          </span>
          <ExternalLink className="h-3.5 w-3.5 text-amber-300" />
        </a>

        <a
          href={searchLinks.osmUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-between p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 hover:bg-emerald-500/20 transition-all text-xs font-semibold text-emerald-200"
        >
          <span className="flex items-center gap-2">
            <Navigation className="h-4 w-4 text-emerald-400" />
            OpenStreetMap Search
          </span>
          <ExternalLink className="h-3.5 w-3.5 text-emerald-300" />
        </a>
      </div>
    </div>
  )
}
