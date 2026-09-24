import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { Alert, Loading, PageHeader, RecordsTable, StatusBadge } from '../components/common.jsx'
import { L, createMap, formatSqm } from '../components/mapUtils.js'
import { formatDay } from './ParcelsPage.jsx'

const KIND = {
  transfer: { icon: '⇄', label: 'Transfer' },
  record_of_rights: { icon: '▤', label: 'Record of rights' },
  other: { icon: '◇', label: 'Document' },
}
const VIA = {
  transfer: 'by transfer',
  record: 'per record of rights',
  'named as seller': 'named as seller',
  'undated record': 'undated record',
}

function TwinMap({ twin }) {
  const el = useRef(null)
  useEffect(() => {
    const map = createMap(el.current)
    const layers = []
    if (twin.map_parcel) {
      layers.push(L.geoJSON(twin.map_parcel.geometry, { style: { color: '#1667b7', weight: 3, fillOpacity: 0.15 } })
        .bindTooltip(`Map parcel ${twin.map_parcel.survey_number}`).addTo(map))
    }
    twin.boundaries.forEach((b) => {
      layers.push(L.geoJSON(b.geometry, { style: { color: '#e67e22', weight: 2, dashArray: '6 4', fillOpacity: 0.05 } })
        .bindTooltip(`Boundary of ${b.record_number}`).addTo(map))
    })
    const group = L.featureGroup(layers)
    if (layers.length && group.getBounds().isValid()) map.fitBounds(group.getBounds(), { padding: [30, 30], maxZoom: 18 })
    return () => map.remove()
  }, [twin])
  if (!twin.map_parcel && !twin.boundaries.length) {
    return <p className="muted">This parcel is not on the loaded cadastral map and no boundary has been drawn.</p>
  }
  return <div ref={el} className="map-canvas small-map" />
}

export default function ParcelTwinPage() {
  const { id } = useParams()
  const [twin, setTwin] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setTwin(null)
    api.parcelTwin(id).then(setTwin).catch((e) => setError(e.message))
  }, [id])

  if (error) return <Alert>{error}</Alert>
  if (!twin) return <Loading />

  const owner = twin.current_owner
  const dated = twin.events.filter((e) => e.date)
  const undated = twin.events.filter((e) => !e.date)
  const recordAreas = twin.events.filter((e) => e.area_sqm && e.validation_status !== 'rejected')

  return (
    <>
      <PageHeader
        title={`Parcel ${twin.survey_number || '—'} · ${twin.village || '—'}, ${twin.district || '—'}`}
        subtitle="Digital twin: every record, the map parcel and the ownership history of this parcel."
        actions={<Link to="/parcels" className="btn btn-ghost">← All parcels</Link>}
      />

      <div className="cards">
        <div className={`summary-card ${owner?.broken_chain ? 'tone-danger' : 'tone-success'}`}>
          <div className="card-label">Current owner (derived)</div>
          <div className="card-value owner-value">{owner?.name || 'Unknown'}</div>
          <div className="card-hint">
            {owner ? `${owner.since ? `since ${formatDay(owner.since)}, ` : ''}${VIA[owner.via] || owner.via}` : 'No dated records'}
            {owner?.broken_chain && <div className="error-text">Ownership chain is broken — verify before relying on this.</div>}
          </div>
        </div>
        <div className="summary-card">
          <div className="card-label">Records</div>
          <div className="card-value">{twin.records}</div>
          <div className="card-hint">{twin.transfers} transfer document(s)</div>
        </div>
        <div className="summary-card tone-muted">
          <div className="card-label">Map area</div>
          <div className="card-value area-value">{twin.map_parcel ? `${(twin.map_parcel.area_sqm / 10000).toFixed(3)} ha` : '—'}</div>
          <div className="card-hint">{twin.map_parcel ? twin.map_parcel.source : 'Not on the cadastral map'}</div>
        </div>
        <div className={`summary-card ${twin.issue_count ? 'tone-warning' : 'tone-success'}`}>
          <div className="card-label">History checks</div>
          <div className="card-value">{twin.issue_count}</div>
          <div className="card-hint">{twin.issue_count ? 'issue(s) to review' : 'No problems found'}</div>
        </div>
      </div>

      <section className="panel">
        <h2>Ownership chain</h2>
        {twin.chain.length === 0 ? (
          <p className="muted">No dated records yet — add document dates to build the chain.</p>
        ) : (
          <div className="chain">
            {twin.chain.map((p, i) => (
              <div key={i} className="chain-step">
                {i > 0 && (
                  <div className={`chain-arrow ${p.broken ? 'broken' : ''}`}>
                    <span>{p.via === 'transfer' ? p.document_type || 'Transfer' : 'No transfer on file'}</span>
                    <span className="chain-date">{formatDay(p.from)}</span>
                    {p.broken && <span className="chain-warn">⚠ seller / owner mismatch</span>}
                  </div>
                )}
                <div className={`chain-owner ${i === twin.chain.length - 1 ? 'current' : ''}`}>
                  <strong>{p.owner || 'Unknown'}</strong>
                  <span className="small muted">
                    {p.from ? formatDay(p.from) : 'before'} – {p.to ? formatDay(p.to) : i === twin.chain.length - 1 ? 'today' : '?'}
                  </span>
                  <span className="small muted">{VIA[p.via] || p.via} · {p.record_numbers.join(', ')}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="grid-2">
        <section className="panel">
          <h2>Timeline</h2>
          <ol className="timeline">
            {dated.map((e) => (
              <TimelineItem key={e.record_id} e={e} focus={e.record_id === twin.focus_record_id} />
            ))}
          </ol>
          {undated.length > 0 && (
            <>
              <h3>Undated records</h3>
              <ol className="timeline">
                {undated.map((e) => (
                  <TimelineItem key={e.record_id} e={e} focus={e.record_id === twin.focus_record_id} />
                ))}
              </ol>
            </>
          )}
        </section>
        <div>
          <section className="panel">
            <h2>History checks</h2>
            {twin.issues.length === 0 ? (
              <p className="muted">The ownership history is consistent.</p>
            ) : (
              <ul className="issues">
                {twin.issues.map((i, n) => (
                  <li key={n} className={`issue issue-${i.severity}`}>
                    <span className="issue-sev">{i.severity}</span>
                    <span>
                      {i.message}{' '}
                      {i.record_ids.map((rid, k) => (
                        <Link key={rid} to={`/records/${rid}`} className="issue-link">{i.record_numbers[k]} →</Link>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="panel">
            <h2>Map</h2>
            <TwinMap twin={twin} />
            {recordAreas.length > 0 && (
              <ul className="area-list small">
                {twin.map_parcel && <li><strong>Map:</strong> {formatSqm(twin.map_parcel.area_sqm)}</li>}
                {recordAreas.map((e) => (
                  <li key={e.record_id}>
                    <strong>{e.record_number}</strong> ({e.date ? e.date.slice(0, 4) : 'undated'}): {e.area_value} {e.area_unit} = {formatSqm(e.area_sqm)}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>

      <section className="panel">
        <h2>All records for this parcel</h2>
        <RecordsTable records={twin.records_detail} />
      </section>
    </>
  )
}

function TimelineItem({ e, focus }) {
  const kind = KIND[e.kind]
  return (
    <li className={`tl-item tl-${e.kind} ${e.validation_status === 'rejected' ? 'tl-rejected' : ''} ${focus ? 'tl-focus' : ''}`}>
      <span className="tl-icon" title={kind.label}>{kind.icon}</span>
      <div className="tl-body">
        <div className="tl-head">
          <strong>{e.date ? formatDay(e.date) : 'No date'}</strong> · {e.document_type}{' '}
          <Link to={`/records/${e.record_id}`} className="record-link small">{e.record_number}</Link>{' '}
          <StatusBadge status={e.validation_status} />
          {e.is_current_owner && <span className="tag current-tag">current owner</span>}
        </div>
        <div>
          {e.kind === 'transfer' ? (
            <>
              <span className="muted">{e.previous_owner}</span> → <strong>{e.owner_name}</strong>
            </>
          ) : (
            <>Owner: <strong>{e.owner_name || '—'}</strong></>
          )}
          {e.area_value !== null && e.area_value !== undefined && (
            <span className="muted"> · {e.area_value} {e.area_unit}</span>
          )}
          {e.validation_status === 'rejected' && <span className="muted"> · rejected, not used for the chain</span>}
        </div>
      </div>
    </li>
  )
}
