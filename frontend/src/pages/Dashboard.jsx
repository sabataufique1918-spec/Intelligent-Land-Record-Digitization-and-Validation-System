import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { Alert, Loading, PageHeader, RecordsTable } from '../components/common.jsx'
import { STATUS_META, STATUS_ORDER } from '../utils.js'

const STAGE_LABEL = { available: 'Working', basic: 'Basic', planned: 'Planned', setup: 'Needs setup' }

function SummaryCard({ label, value, hint, tone = 'primary', to }) {
  const body = (
    <>
      <div className="card-label">{label}</div>
      <div className="card-value">{value}</div>
      {hint && <div className="card-hint">{hint}</div>}
    </>
  )
  return to ? (
    <Link to={to} className={`summary-card tone-${tone}`}>{body}</Link>
  ) : (
    <div className={`summary-card tone-${tone}`}>{body}</div>
  )
}

function BarList({ rows }) {
  const max = Math.max(1, ...rows.map((r) => r.count))
  if (!rows.length) return <p className="muted">No data yet.</p>
  return (
    <ul className="bar-list">
      {rows.map((row) => (
        <li key={row.label}>
          <div className="bar-row">
            <span>{row.label}</span>
            <span className="bar-count">{row.count}</span>
          </div>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(row.count / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

function StatusBreakdown({ counts, total }) {
  return (
    <>
      <div className="stacked">
        {STATUS_ORDER.map((s) =>
          counts[s] ? (
            <div
              key={s}
              className={`stacked-seg seg-${STATUS_META[s].tone}`}
              style={{ width: `${(counts[s] / Math.max(total, 1)) * 100}%` }}
              title={`${STATUS_META[s].label}: ${counts[s]}`}
            />
          ) : null,
        )}
      </div>
      <ul className="legend">
        {STATUS_ORDER.map((s) => (
          <li key={s}>
            <Link to={`/validation?status=${s}`}>
              <span className={`legend-dot seg-${STATUS_META[s].tone}`} />
              {STATUS_META[s].label}
              <strong>{counts[s] || 0}</strong>
            </Link>
          </li>
        ))}
      </ul>
    </>
  )
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.summary().then(setData).catch((e) => setError(e.message))
  }, [])

  if (error) return <Alert>{error}</Alert>
  if (!data) return <Loading />

  const c = data.status_counts
  const awaitingReview = (c.pending || 0) + (c.rules_passed || 0) + (c.flagged || 0)

  return (
    <>
      <PageHeader
        title="Officer Dashboard"
        subtitle="Overview of digitized land records and their validation status."
        actions={<Link to="/upload" className="btn btn-primary">+ Upload Document</Link>}
      />

      <div className="cards">
        <SummaryCard label="Total Records" value={data.total_records} hint={`${data.documents_uploaded} with documents · ${data.ocr_completed} OCR processed`} to="/records" />
        <SummaryCard label="Awaiting Review" value={awaitingReview} hint="Not yet verified or rejected by an officer" tone="warning" to="/validation" />
        <SummaryCard label="Flagged by Rules" value={c.flagged} hint="Errors or conflicts found" tone="danger" to="/validation?status=flagged" />
        <SummaryCard label="Open Conflicts" value={data.open_conflicts} hint="Records disagreeing about the same parcel" tone="danger" to="/conflicts" />
        <SummaryCard label="Verified" value={c.verified} hint="Approved by an officer" tone="success" to="/validation?status=verified" />
        <SummaryCard label="Rejected" value={c.rejected} hint="Sent back for correction" tone="muted" to="/validation?status=rejected" />
      </div>

      <div className="grid-2">
        <section className="panel">
          <h2>Validation Status</h2>
          <StatusBreakdown counts={c} total={data.total_records} />
        </section>
        <section className="panel">
          <h2>Records by District</h2>
          <BarList rows={data.by_district} />
        </section>
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2>Recent Records</h2>
          <Link to="/records" className="link">View all →</Link>
        </div>
        <RecordsTable records={data.recent_records} />
      </section>

      <div className="grid-2">
        <section className="panel">
          <h2>Records by Document Type</h2>
          <BarList rows={data.by_document_type} />
        </section>
        <section className="panel">
          <h2>Processing Pipeline Status</h2>
          <p className="muted small">
            What works in this build. Modules marked Planned are not implemented yet.
          </p>
          <ol className="pipeline">
            {data.pipeline.map((stage) => (
              <li key={stage.key} className={`stage stage-${stage.status}`}>
                <div className="stage-head">
                  <span>{stage.name}</span>
                  <span className={`stage-tag tag-${stage.status}`}>{STAGE_LABEL[stage.status]}</span>
                </div>
                <div className="muted small">{stage.detail}</div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </>
  )
}
