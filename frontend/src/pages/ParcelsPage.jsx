import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { Alert, EmptyState, Loading, PageHeader } from '../components/common.jsx'

export function formatDay(value) {
  if (!value) return '—'
  return new Date(`${value}T00:00:00`).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function ParcelsPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const [text, setText] = useState(q)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setData(null)
    api.parcels(q).then(setData).catch((e) => setError(e.message))
  }, [q])

  return (
    <>
      <PageHeader
        title="Parcel History"
        subtitle="One digital twin per parcel: all its records, the map parcel and the ownership timeline."
      />
      <Alert tone="info">
        Records are grouped into a parcel by survey number, village and district (Hindi and English spellings
        matched). The ownership chain is built from document dates and the previous-owner / seller of transfer
        documents in this system only — it does not query registration or revenue department databases.
      </Alert>
      <Alert>{error}</Alert>
      <form
        className="search-bar"
        onSubmit={(e) => {
          e.preventDefault()
          setParams(text.trim() ? { q: text.trim() } : {})
        }}
      >
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Survey no., village, owner or seller" />
        <button className="btn btn-primary">Search</button>
      </form>

      <section className="panel">
        {!data ? (
          <Loading />
        ) : data.items.length === 0 ? (
          <EmptyState>No parcels found.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Parcel</th>
                  <th>Current owner</th>
                  <th>Records</th>
                  <th>Transfers</th>
                  <th>History</th>
                  <th>Checks</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <Link to={`/parcels/record/${p.id}`} className="record-link">Survey {p.survey_number || '—'}</Link>
                      <div className="muted small">{p.village || '—'}, {p.district || '—'}</div>
                    </td>
                    <td>
                      {p.current_owner?.name || <span className="muted">Unknown</span>}
                      {p.current_owner?.since && <div className="muted small">since {formatDay(p.current_owner.since)}</div>}
                    </td>
                    <td>{p.records}</td>
                    <td>{p.transfers}</td>
                    <td className="small">
                      {p.first_date ? `${formatDay(p.first_date)} – ${formatDay(p.last_date)}` : <span className="muted">undated</span>}
                    </td>
                    <td>
                      {p.issue_count ? (
                        <span className={`sev sev-${p.worst_severity}`}>{p.issue_count} issue{p.issue_count > 1 ? 's' : ''}</span>
                      ) : (
                        <span className="muted small">OK</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}
