import { Link, useLocation } from "react-router-dom"
import { Activity, Shield, Phone } from "lucide-react"
import { cn } from "../lib/utils"

export default function Navbar() {
  const { pathname } = useLocation()

  return (
    <nav className="sticky top-0 z-50 border-b border-white/5 bg-darker/80 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-600">
            <Activity className="h-4 w-4 text-white" />
          </div>
          <span className="text-sm font-bold tracking-wide text-white">
            LIFELINE<span className="text-red-500">CORE</span>
          </span>
        </Link>

        {/* Nav links */}
        <div className="flex items-center gap-1">
          <Link
            to="/call"
            className={cn(
              "flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
              pathname === "/call"
                ? "bg-red-600/20 text-red-400"
                : "text-slate-400 hover:text-white hover:bg-white/5",
            )}
          >
            <Phone className="h-3.5 w-3.5" />
            Emergency
          </Link>
          <Link
            to="/admin"
            className={cn(
              "flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
              pathname === "/admin"
                ? "bg-blue-600/20 text-blue-400"
                : "text-slate-400 hover:text-white hover:bg-white/5",
            )}
          >
            <Shield className="h-3.5 w-3.5" />
            Dispatcher
          </Link>
        </div>
      </div>
    </nav>
  )
}
