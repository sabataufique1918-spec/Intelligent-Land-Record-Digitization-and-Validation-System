import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import '@geoman-io/leaflet-geoman-free'
import '@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css'

export { L }

// Map colour for each parcel status (see backend routers/gis.py _map_status).
export const MAP_STATUS = {
  verified: { label: 'Verified record', color: '#1e8a4c' },
  linked: { label: 'Record, not yet verified', color: '#1667b7' },
  issue: { label: 'Area / boundary issue or flagged', color: '#b7791f' },
  conflict: { label: 'Overlap or owner conflict', color: '#c0392b' },
  unlinked: { label: 'No record yet', color: '#8795a5' },
}

export function createMap(element, options = {}) {
  const map = L.map(element, { zoomControl: true, ...options })
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 20,
    maxNativeZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map)
  map.setView([22.5, 79], 5) // India, until data is loaded
  return map
}

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch])
}

export function formatSqm(sqm) {
  if (sqm === null || sqm === undefined) return '—'
  return `${(sqm / 10000).toFixed(3)} ha (${Math.round(sqm).toLocaleString('en-IN')} m²)`
}

// Accept a GeoJSON geometry, Feature or FeatureCollection and return the first (Multi)Polygon geometry.
export function extractPolygon(json) {
  if (!json || typeof json !== 'object') return null
  if (json.type === 'Polygon' || json.type === 'MultiPolygon') return json
  if (json.type === 'Feature') return extractPolygon(json.geometry)
  if (json.type === 'FeatureCollection') {
    for (const f of json.features || []) {
      const g = extractPolygon(f)
      if (g) return g
    }
  }
  return null
}
