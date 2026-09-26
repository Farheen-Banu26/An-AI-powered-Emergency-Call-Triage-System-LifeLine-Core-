export interface EmergencyFacility {
  id: string
  name: string
  category: "hospital" | "trauma_center" | "ambulance_station" | "fire_station" | "police_station"
  distanceKm?: number
  address: string
  phone?: string
  lat?: number
  lon?: number
  searchUrl?: string
}

/**
 * Calculates Haversine great-circle distance between two points in km.
 */
export function calculateDistanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371 // Earth's radius in km
  const dLat = ((lat2 - lat1) * Math.PI) / 180
  const dLon = ((lon2 - lon1) * Math.PI) / 180
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2)
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  return parseFloat((R * c).toFixed(1))
}

/**
 * Generates map search actions for emergency services near the given coordinate.
 * Uses honest external search links (Google Maps / OpenStreetMap) to find live nearby facilities.
 */
export function getNearbySearchLinks(lat: number, lon: number): {
  hospitalsUrl: string
  traumaUrl: string
  ambulanceUrl: string
  osmUrl: string
} {
  return {
    hospitalsUrl: `https://www.google.com/maps/search/emergency+hospital/@${lat},${lon},14z`,
    traumaUrl: `https://www.google.com/maps/search/trauma+centre/@${lat},${lon},14z`,
    ambulanceUrl: `https://www.google.com/maps/search/ambulance+station/@${lat},${lon},14z`,
    osmUrl: `https://www.openstreetmap.org/search?query=emergency#map=15/${lat}/${lon}`,
  }
}

/**
 * Returns a directions navigation URL to specific coordinates.
 */
export function getDirectionsUrl(lat: number, lon: number): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}`
}
