export interface LocationData {
  latitude: number
  longitude: number
  accuracyMeters: number
  timestamp: string
  source: "Browser GPS" | "Manual Entry" | "IP Fallback"
  address?: string
  landmark?: string
  isLowAccuracy: boolean
  displayString: string
  status?: "reliable" | "low_accuracy" | "manual_override" | "unavailable" | "permission_denied"
}

export class LocationError extends Error {
  code: number // 1: PERMISSION_DENIED, 2: POSITION_UNAVAILABLE, 3: TIMEOUT, 0: UNSUPPORTED
  isPermissionDenied: boolean
  isTimeout: boolean
  isPositionUnavailable: boolean

  constructor(message: string, code: number = 0) {
    super(message)
    this.name = "LocationError"
    this.code = code
    this.isPermissionDenied = code === 1
    this.isPositionUnavailable = code === 2
    this.isTimeout = code === 3
  }
}

export async function detectLocation(): Promise<LocationData> {
  if (typeof window === "undefined" || !navigator.geolocation) {
    throw new LocationError("Geolocation is not supported by this browser.", 0)
  }

  // 1. Try High Accuracy positioning first (with 6s timeout)
  let pos: GeolocationPosition | null = null
  let lastError: GeolocationPositionError | null = null

  try {
    pos = await new Promise<GeolocationPosition>((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true,
        timeout: 6000,
        maximumAge: 0,
      })
    })
  } catch (err: any) {
    lastError = err as GeolocationPositionError
    // If permission was denied (Code 1), stop and report permission denied immediately
    if (lastError && lastError.code === 1) {
      throw new LocationError(
        "Location permission blocked or denied in browser.",
        1
      )
    }
  }

  // 2. If High Accuracy timed out (code 3) or failed (code 2), fallback to Standard Accuracy
  if (!pos) {
    try {
      pos = await new Promise<GeolocationPosition>((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: false,
          timeout: 10000,
          maximumAge: 60000,
        })
      })
    } catch (err: any) {
      lastError = err as GeolocationPositionError
      const code = lastError?.code || 0
      if (code === 1) {
        throw new LocationError(
          "Location permission blocked or denied in browser.",
          1
        )
      } else if (code === 3) {
        throw new LocationError("GPS acquisition timed out.", 3)
      } else {
        throw new LocationError("GPS position unavailable on device.", 2)
      }
    }
  }

  const { latitude, longitude, accuracy } = pos.coords
  const accuracyMeters = Math.round(accuracy || 50)
  const isLowAccuracy = accuracyMeters > 100
  const timestamp = new Date(pos.timestamp).toLocaleTimeString()

  // 3. Reverse Geocoding via OpenStreetMap Nominatim
  let address: string | undefined = undefined
  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}&zoom=18`,
      { signal: AbortSignal.timeout(4000) }
    )
    if (res.ok) {
      const data = await res.json()
      if (data && data.display_name) {
        address = data.display_name as string
      }
    }
  } catch {
    /* reverse geocoding failure is non-blocking — coordinates remain valid */
  }

  const coordStr = `${latitude.toFixed(5)}, ${longitude.toFixed(5)} (±${accuracyMeters}m)`
  const displayString = address ? `${address} [${coordStr}]` : coordStr

  return {
    latitude,
    longitude,
    accuracyMeters,
    timestamp,
    source: "Browser GPS",
    address,
    isLowAccuracy,
    displayString,
    status: isLowAccuracy ? "low_accuracy" : "reliable",
  }
}
