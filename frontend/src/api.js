const BASE = import.meta.env.VITE_API_BASE_URL || ''

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${BASE}${path}`, options)
  } catch {
    throw new Error('Cannot reach the backend. Is the FastAPI server running?')
  }
  const isJson = response.headers.get('content-type')?.includes('application/json')
  const body = isJson ? await response.json() : null
  if (!response.ok) {
    const detail = body?.detail
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg).join('; ')
      : detail || `Request failed (${response.status})`
    throw new Error(message)
  }
  return body
}

function json(method, data) {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }
}

export const api = {
  health: () => request('/api/health'),
  summary: () => request('/api/dashboard/summary'),
  options: () => request('/api/meta/options'),
  listRecords: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined),
    )
    return request(`/api/records?${qs}`)
  },
  getRecord: (id) => request(`/api/records/${id}`),
  uploadRecord: (formData) => request('/api/records/upload', { method: 'POST', body: formData }),
  updateRecord: (id, data) => request(`/api/records/${id}`, json('PATCH', data)),
  setStatus: (id, data) => request(`/api/records/${id}/status`, json('PATCH', data)),
  revalidate: (id) => request(`/api/records/${id}/validate`, { method: 'POST' }),
  ocrStatus: () => request('/api/ocr/status'),
  ocrExtract: (formData) => request('/api/ocr/extract', { method: 'POST', body: formData }),
  runOcr: (id, language, useAi = true) =>
    request(`/api/records/${id}/ocr`, json('POST', { language, use_ai: useAi })),
  conflicts: (params = {}) => request(`/api/conflicts?${new URLSearchParams(params)}`),
  recordConflicts: (id) => request(`/api/records/${id}/conflicts`),
  dismissConflict: (data) => request('/api/conflicts/dismiss', json('POST', data)),
  restoreConflict: (key) => request(`/api/conflicts/dismiss/${encodeURIComponent(key)}`, { method: 'DELETE' }),
  rescanConflicts: () => request('/api/conflicts/rescan', { method: 'POST' }),
  gisSummary: () => request('/api/gis/summary'),
  gisLayer: (district) => request(`/api/gis/layer${district ? `?district=${encodeURIComponent(district)}` : ''}`),
  gisBoundaries: () => request('/api/gis/boundaries'),
  importMap: (formData) => request('/api/gis/import', { method: 'POST', body: formData }),
  recordGis: (id) => request(`/api/records/${id}/gis`),
  setBoundary: (id, geometry, source = 'drawn') => request(`/api/records/${id}/boundary`, json('PUT', { geometry, source })),
  boundaryFromMap: (id) => request(`/api/records/${id}/boundary/from-map`, { method: 'POST' }),
  deleteBoundary: (id) => request(`/api/records/${id}/boundary`, { method: 'DELETE' }),
  parcels: (q) => request(`/api/parcels${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  parcelTwin: (recordId) => request(`/api/parcels/by-record/${recordId}`),
  trainingStats: () => request('/api/training/stats'),
  recordLines: (id) => request(`/api/records/${id}/lines`),
  cutLines: (id, language) => request(`/api/records/${id}/lines`, json('POST', { language })),
  saveLine: (lineId, data) => request(`/api/training/lines/${lineId}`, json('PUT', data)),
  trainingExportUrl: () => `${BASE}/api/training/export`,
  fileUrl: (id, download = false) => `${BASE}/api/records/${id}/file${download ? '?download=true' : ''}`,
}
