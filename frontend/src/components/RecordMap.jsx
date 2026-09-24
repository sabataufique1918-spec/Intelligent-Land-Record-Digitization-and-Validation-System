import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { Alert } from './common.jsx'
import { L, createMap, escapeHtml, extractPolygon, formatSqm } from './mapUtils.js'

// Map + boundary tools for one record. onRecordChange receives the updated record after an edit.
export default function RecordMap({ record, onRecordChange }) {
  const mapEl = useRef(null)
  const mapRef = useRef(null)
  const layersRef = useRef({})
  const fileRef = useRef(null)
  const [report, setReport] = useState(null)
  const [context, setContext] = useState(null)
  const [mode, setMode] = useState('view') // view | draw | edit
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    mapRef.current = createMap(mapEl.current)
    return () => {
      mapRef.current.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    setError('')
    api.recordGis(record.id).then(setReport).catch((e) => setError(e.message))
    if (record.district) api.gisLayer(record.district).then(setContext).catch(() => setContext(null))
  }, [record])

  // Redraw: neighbouring parcels (grey), this record's map parcel (blue), its boundary (orange).
  useEffect(() => {
    const map = mapRef.current
    if (!map || !report) return
    Object.values(layersRef.current).forEach((l) => l && l.remove())
    const layers = {}
    if (context) {
      layers.context = L.geoJSON(context, {
        style: { color: '#8795a5', weight: 1, fillOpacity: 0.05 },
        onEachFeature: (f, l) => l.bindTooltip(escapeHtml(f.properties.survey_number)),
      }).addTo(map)
    }
    if (report.map_parcel) {
      layers.parcel = L.geoJSON(report.map_parcel.geometry, {
        style: { color: '#1667b7', weight: 3, fillColor: '#1667b7', fillOpacity: 0.15 },
      })
        .bindTooltip(`Map parcel ${escapeHtml(report.map_parcel.survey_number)}`)
        .addTo(map)
    }
    if (report.record_boundary) {
      const overlap = report.issues.some((i) => i.code === 'BOUNDARY_OVERLAP')
      layers.boundary = L.geoJSON(report.record_boundary, {
        style: { color: overlap ? '#c0392b' : '#e67e22', weight: 3, dashArray: '6 4', fillOpacity: 0.1 },
      })
        .bindTooltip('This record’s boundary')
        .addTo(map)
    }
    layersRef.current = layers
    const focus = layers.boundary || layers.parcel || layers.context
    if (focus && focus.getBounds().isValid()) {
      map.fitBounds(focus.getBounds(), { padding: [30, 30], maxZoom: 19 })
    }
  }, [report, context])

  async function act(fn) {
    setBusy(true)
    setError('')
    try {
      const updated = await fn()
      onRecordChange(updated)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  function startDraw() {
    const map = mapRef.current
    setMode('draw')
    map.pm.enableDraw('Polygon', { snappable: true, snapDistance: 15 })
    map.once('pm:create', (e) => {
      const geometry = e.layer.toGeoJSON().geometry
      e.layer.remove()
      map.pm.disableDraw()
      setMode('view')
      act(() => api.setBoundary(record.id, geometry, 'drawn'))
    })
  }

  function cancelDraw() {
    mapRef.current.pm.disableDraw()
    mapRef.current.off('pm:create')
    setMode('view')
  }

  function startEdit() {
    const layer = layersRef.current.boundary
    if (!layer) return
    layer.eachLayer((l) => l.pm.enable({ snappable: true }))
    setMode('edit')
  }

  function saveEdit() {
    const layer = layersRef.current.boundary
    let geometry = null
    layer.eachLayer((l) => {
      l.pm.disable()
      geometry = geometry || l.toGeoJSON().geometry
    })
    setMode('view')
    if (geometry) act(() => api.setBoundary(record.id, geometry, 'drawn'))
  }

  function cancelEdit() {
    setMode('view')
    setReport({ ...report }) // redraw original
  }

  async function uploadFile(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    try {
      const geometry = extractPolygon(JSON.parse(await file.text()))
      if (!geometry) throw new Error('No Polygon or MultiPolygon found in the file.')
      act(() => api.setBoundary(record.id, geometry, 'uploaded'))
    } catch (err) {
      setError(err.message.startsWith('No Polygon') ? err.message : 'The file is not valid GeoJSON.')
    }
  }

  const mp = report?.map_parcel
  const b = report?.boundary

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Map &amp; boundary (GIS)</h2>
        <Link to="/map" className="link small">Full map →</Link>
      </div>
      <Alert>{error}</Alert>
      {report && !report.layer_loaded && (
        <p className="muted">No cadastral map layer is loaded. Import one on the Map page.</p>
      )}
      {report && (
        <dl className="gis-facts">
          <div>
            <dt>Map parcel</dt>
            <dd>
              {mp ? (
                <>
                  Survey {mp.survey_number}, {mp.village} — {formatSqm(mp.area_sqm)}
                  <div className="muted small">Source: {mp.source}</div>
                </>
              ) : (
                'Not found on the map'
              )}
            </dd>
          </div>
          <div>
            <dt>Recorded area</dt>
            <dd>
              {report.record_area_sqm ? formatSqm(report.record_area_sqm) : `${record.area_value ?? '—'} ${record.area_unit || ''} (not converted)`}
              {mp?.area_difference_pct !== undefined && (
                <div className={`small ${mp.area_difference_pct > 10 ? 'error-text' : 'muted'}`}>
                  {mp.area_difference_pct}% different from the map
                </div>
              )}
            </dd>
          </div>
          <div>
            <dt>Record boundary</dt>
            <dd>
              {b ? (
                <>
                  {formatSqm(b.area_sqm)} · {b.source}
                  {b.iou_with_map !== undefined && (
                    <div className={`small ${b.iou_with_map < 80 ? 'error-text' : 'muted'}`}>
                      {b.iou_with_map}% match with map parcel
                    </div>
                  )}
                  {b.overlaps?.map((o) => (
                    <div key={o.record_id} className="small error-text">
                      Overlaps <Link to={`/records/${o.record_id}`}>{o.record_number}</Link> ({o.survey_number}) by{' '}
                      {Math.round(o.overlap_sqm).toLocaleString('en-IN')} m²
                    </div>
                  ))}
                </>
              ) : (
                'None drawn'
              )}
            </dd>
          </div>
        </dl>
      )}

      <div ref={mapEl} className="map-canvas small-map" />

      <div className="actions-row compact map-actions">
        {mode === 'view' && (
          <>
            <button className="btn btn-ghost btn-sm" onClick={startDraw} disabled={busy}>
              ✎ {record.boundary ? 'Redraw' : 'Draw'} boundary
            </button>
            {record.boundary && (
              <button className="btn btn-ghost btn-sm" onClick={startEdit} disabled={busy}>
                Edit points
              </button>
            )}
            {mp && (
              <button className="btn btn-ghost btn-sm" onClick={() => act(() => api.boundaryFromMap(record.id))} disabled={busy}>
                Use map parcel
              </button>
            )}
            <input ref={fileRef} type="file" accept=".geojson,.json" hidden onChange={uploadFile} />
            <button className="btn btn-ghost btn-sm" onClick={() => fileRef.current?.click()} disabled={busy}>
              Upload GeoJSON
            </button>
            {record.boundary && (
              <button className="btn btn-ghost btn-sm" onClick={() => act(() => api.deleteBoundary(record.id))} disabled={busy}>
                Remove
              </button>
            )}
          </>
        )}
        {mode === 'draw' && (
          <>
            <span className="small muted">Click on the map to add corners; click the first corner to finish.</span>
            <button className="btn btn-ghost btn-sm" onClick={cancelDraw}>Cancel</button>
          </>
        )}
        {mode === 'edit' && (
          <>
            <span className="small muted">Drag the corner points, then save.</span>
            <button className="btn btn-primary btn-sm" onClick={saveEdit}>Save boundary</button>
            <button className="btn btn-ghost btn-sm" onClick={cancelEdit}>Cancel</button>
          </>
        )}
      </div>
      <p className="muted small">
        Blue = cadastral map parcel, orange dashed = this record’s boundary (red if it overlaps another
        record), grey = neighbouring parcels.
      </p>
    </section>
  )
}
