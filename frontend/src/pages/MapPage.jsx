import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Alert, PageHeader } from '../components/common.jsx'
import { L, MAP_STATUS, createMap, escapeHtml, formatSqm } from '../components/mapUtils.js'
import { STATUS_META } from '../utils.js'

function popupHtml(p) {
  const records = p.records.length
    ? p.records
        .map(
          (r) =>
            `<li><a href="/records/${r.id}">${escapeHtml(r.record_number)}</a> · ${escapeHtml(r.owner_name || '—')} · ` +
            `${escapeHtml(r.area_value ?? '—')} ${escapeHtml(r.area_unit || '')} · ${escapeHtml(STATUS_META[r.validation_status]?.label || r.validation_status)}</li>`,
        )
        .join('')
    : '<li>No record refers to this parcel yet.</li>'
  return `<div class="map-popup">
    <strong>Survey ${escapeHtml(p.survey_number)}</strong><br/>
    ${escapeHtml(p.village || '—')}, ${escapeHtml(p.district || '—')}<br/>
    Map area: ${formatSqm(p.area_sqm)}<br/>
    <span class="muted">Status: ${escapeHtml(MAP_STATUS[p.map_status]?.label || p.map_status)} · Source: ${escapeHtml(p.source)}</span>
    <ul>${records}</ul></div>`
}

export default function MapPage() {
  const mapEl = useRef(null)
  const mapRef = useRef(null)
  const layersRef = useRef([])
  const [layer, setLayer] = useState(null)
  const [summary, setSummary] = useState(null)
  const [district, setDistrict] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [importing, setImporting] = useState(false)
  const fileRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const [l, b, s] = await Promise.all([api.gisLayer(), api.gisBoundaries(), api.gisSummary()])
      setLayer({ parcels: l, boundaries: b })
      setSummary(s)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    mapRef.current = createMap(mapEl.current)
    load()
    return () => {
      mapRef.current.remove()
      mapRef.current = null
    }
  }, [load])

  // Draw layers whenever data or the district filter changes.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !layer) return
    layersRef.current.forEach((l) => l.remove())
    const inDistrict = (f) => !district || f.properties.district === district
    const parcels = L.geoJSON(
      { ...layer.parcels, features: layer.parcels.features.filter(inDistrict) },
      {
        style: (f) => {
          const color = MAP_STATUS[f.properties.map_status]?.color || '#8795a5'
          return { color, weight: 2, fillColor: color, fillOpacity: 0.25 }
        },
        onEachFeature: (f, l) => {
          l.bindPopup(popupHtml(f.properties))
          l.bindTooltip(`${f.properties.survey_number}`, { permanent: false, direction: 'center' })
        },
      },
    ).addTo(map)
    const boundaries = L.geoJSON(layer.boundaries, {
      style: (f) => ({ color: f.properties.overlap ? '#c0392b' : '#e67e22', weight: 3, dashArray: '6 4', fill: false }),
      onEachFeature: (f, l) =>
        l.bindPopup(
          `<strong>Boundary of <a href="/records/${f.properties.record_id}">${escapeHtml(f.properties.record_number)}</a></strong><br/>` +
            `${escapeHtml(f.properties.owner_name || '—')} · survey ${escapeHtml(f.properties.survey_number)}` +
            (f.properties.overlap ? '<br/><b style="color:#c0392b">Overlaps another record’s boundary</b>' : ''),
        ),
    }).addTo(map)
    // Village markers so parcels can be found when zoomed out (parcels are too small to see).
    const villages = {}
    parcels.eachLayer((l) => {
      const p = l.feature.properties
      const key = `${p.village}|${p.district}`
      villages[key] = villages[key] || { name: p.village, district: p.district, bounds: L.latLngBounds([]), count: 0, worst: 'unlinked' }
      villages[key].bounds.extend(l.getBounds())
      villages[key].count += 1
      const rank = ['unlinked', 'verified', 'linked', 'issue', 'conflict']
      if (rank.indexOf(p.map_status) > rank.indexOf(villages[key].worst)) villages[key].worst = p.map_status
    })
    const markers = L.layerGroup(
      Object.values(villages).map((v) =>
        L.circleMarker(v.bounds.getCenter(), {
          radius: 9, color: '#fff', weight: 2, fillColor: MAP_STATUS[v.worst].color, fillOpacity: 0.95,
        })
          .bindTooltip(`${escapeHtml(v.name)}, ${escapeHtml(v.district)} · ${v.count} parcels (click to zoom)`)
          .on('click', () => map.fitBounds(v.bounds, { padding: [30, 30], maxZoom: 18 })),
      ),
    )
    const toggleMarkers = () => {
      if (map.getZoom() < 14) markers.addTo(map)
      else markers.remove()
    }
    map.on('zoomend', toggleMarkers)
    layersRef.current = [parcels, boundaries, markers, { remove: () => map.off('zoomend', toggleMarkers) }]
    const bounds = parcels.getBounds()
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [20, 20], maxZoom: 18 })
    toggleMarkers()
  }, [layer, district])

  async function importFile(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setImporting(true)
    setError('')
    setNotice('')
    const form = new FormData()
    form.append('file', file)
    try {
      const r = await api.importMap(form)
      setNotice(
        `Imported ${r.imported} parcel(s) from ${r.source}` +
          (r.skipped_count ? `; skipped ${r.skipped_count} (e.g. ${r.skipped[0]?.reason})` : '') +
          '. All records were re-checked against the map.',
      )
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setImporting(false)
    }
  }

  const districts = layer ? [...new Set(layer.parcels.features.map((f) => f.properties.district).filter(Boolean))].sort() : []

  return (
    <>
      <PageHeader
        title="Cadastral Map"
        subtitle="Parcels from the imported map layer, coloured by the state of their land records."
        actions={
          <>
            <input ref={fileRef} type="file" accept=".geojson,.json,application/geo+json,application/json" hidden onChange={importFile} />
            <button className="btn btn-ghost" onClick={() => fileRef.current?.click()} disabled={importing}>
              {importing ? 'Importing…' : '⇪ Import GeoJSON map'}
            </button>
          </>
        }
      />
      <Alert tone="info">
        Zoomed out, each village is a dot — click it (or choose a district) to see its parcels. The
        map layer loaded now is a <strong>fictional sample</strong> (placeholder locations, not real
        parcels). Import a real cadastral layer as GeoJSON in WGS84 with <code>survey_number</code> (or
        khasra_no), <code>village</code> and <code>district</code> properties. The background map is
        OpenStreetMap and needs an internet connection.
      </Alert>
      <Alert>{error}</Alert>
      <Alert tone="success">{notice}</Alert>

      {summary && (
        <div className="chips">
          <span className="chip static">Map parcels <span>{summary.parcels}</span></span>
          <span className="chip static">Records with a drawn boundary <span>{summary.records_with_boundary}</span></span>
          <span className="chip static">Records with map issues <span>{summary.records_with_map_issues}</span></span>
          <span className="chip static">Records not on map <span>{summary.records_not_on_map}</span></span>
          <select value={district} onChange={(e) => setDistrict(e.target.value)} className="chip-select">
            <option value="">All districts</option>
            {districts.map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
        </div>
      )}

      <section className="panel map-panel">
        <div ref={mapEl} className="map-canvas" />
        <div className="legend map-legend">
          {Object.entries(MAP_STATUS).map(([k, s]) => (
            <span key={k}>
              <span className="legend-dot" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
          <span>
            <span className="legend-line" /> Record boundary (red = overlap)
          </span>
        </div>
      </section>
    </>
  )
}
