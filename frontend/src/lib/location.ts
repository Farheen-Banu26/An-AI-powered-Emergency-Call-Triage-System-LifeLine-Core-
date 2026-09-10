export async function detectLocation(): Promise<string> {
  const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("Geolocation unsupported"))
    navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 10_000 })
  })

  const { latitude, longitude } = pos.coords
  const fallback = `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`

  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}&zoom=18`,
    )
    if (!res.ok) return fallback
    const data = await res.json()
    return (data.display_name as string) ?? fallback
  } catch {
    return fallback
  }
}
