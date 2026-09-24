import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import ConflictItem from '../components/ConflictItem.jsx'
import { Alert, EmptyState, Loading, PageHeader, StatusBadge } from '../components/common.jsx'
import { display, formatArea } from '../utils.js'

export default function ConflictsPage() {
  const [params, setParams] = useSearchParams()
  const type = params.get('type') || ''
  const showDismissed = params.get('dismissed') === '1'
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [scanning, setScanning] = useState(false)

  const load = useCallback(() => {
    const query = { include_dismissed: showDismissed }
    if (type) query.type = type
    return api
      .conflicts(query)
      .then(setData)
      .catch((e) => setError(e.message))
  }, [type, showDismissed])

  useEffect(() => {
    setData(null)
    load()
  }, [load])

  function setFilter(next) {
    const p = {}
    if (next.type ?? type) p.type = next.type ?? type
    if (next.dismissed ?? showDismissed) p.dismissed = '1'
    setParams(p)
  }

  async function rescan() {
    setScanning(true)
    setNotice('')
    try {
      const r = await api.rescanConflicts()
      setNotice(`Re-checked ${r.records_checked} records: ${r.summary.open} open conflict(s).`)
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setScanning(false)
    }
  }

  const dismiss = async (c, note, reviewer) => {
    await api.dismissConflict({ key: c.key, note, reviewed_by: reviewer })
    setNotice(`${c.label} between ${c.record_numbers.join(' and ')} marked as not a conflict.`)
    await load()
  }
  const restore = async (c) => {
    await api.restoreConflict(c.key)
    setNotice(`${c.label} between ${c.record_numbers.join(' and ')} restored.`)
    await load()
  }

  const s = data?.summary

  return (
    <>
      <PageHeader
        title="Conflict Detection"
        subtitle="Records that disagree with each other about the same parcel, or share the same document."
        actions={
          <button className="btn btn-ghost" onClick={rescan} disabled={scanning}>
            {scanning ? 'Re-checking…' : '↻ Re-check all records'}
          </button>
        }
      />
      <Alert tone="info">
        Records are compared when they have the same survey / khasra number, village and district (Hindi
        and English spellings of places are matched). Owner names are compared exactly, by spelling
        similarity, or across Hindi/English script by sound. Areas are converted between units before
        comparing (Bigha is only compared with Bigha). These are rule-based checks, not AI, and do not use
        GIS or government databases.
      </Alert>
      <Alert>{error}</Alert>
      <Alert tone="success">{notice}</Alert>

      {s && (
        <div className="cards">
          <div className="summary-card tone-danger">
            <div className="card-label">Open conflicts</div>
            <div className="card-value">{s.open}</div>
            <div className="card-hint">{s.records_involved} records involved</div>
          </div>
          <div className="summary-card tone-muted">
            <div className="card-label">Marked not a conflict</div>
            <div className="card-value">{s.dismissed}</div>
            <div className="card-hint">Reviewed by an officer</div>
          </div>
        </div>
      )}

      {data && (
        <div className="chips">
          <button className={`chip ${!type ? 'active' : ''}`} onClick={() => setFilter({ type: '' })}>
            All <span>{s.open}</span>
          </button>
          {Object.entries(data.types).map(([key, t]) => (
            <button key={key} className={`chip ${type === key ? 'active' : ''}`} onClick={() => setFilter({ type: key })}>
              {t.label} <span>{s.by_type[key]}</span>
            </button>
          ))}
          <label className="checkbox inline">
            <input
              type="checkbox"
              checked={showDismissed}
              onChange={(e) => setFilter({ dismissed: e.target.checked })}
            />
            Show dismissed
          </label>
        </div>
      )}

      {!data ? (
        <Loading />
      ) : data.groups.length === 0 ? (
        <section className="panel">
          <EmptyState>No conflicts found{type ? ' of this type' : ''}.</EmptyState>
        </section>
      ) : (
        data.groups.map((g) => (
          <section key={g.key} className={`panel conflict-group group-${g.worst_severity}`}>
            <div className="panel-head">
              <h2>{g.title}</h2>
              <span className="muted small">{g.records.length} records</span>
            </div>
            <div className="table-wrap">
              <table className="table compact-table">
                <thead>
                  <tr>
                    <th>Record</th>
                    <th>Owner</th>
                    <th>Khata</th>
                    <th>Area</th>
                    <th>Document</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {g.records.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <Link to={`/records/${r.id}`} className="record-link">{r.record_number}</Link>
                        {r.is_sample && <span className="tag">Sample</span>}
                      </td>
                      <td>{display(r.owner_name)}</td>
                      <td>{display(r.khata_number)}</td>
                      <td>{formatArea(r)}</td>
                      <td>{r.document_type}</td>
                      <td><StatusBadge status={r.validation_status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="conflict-list">
              {g.conflicts.map((c) => (
                <ConflictItem key={c.key} conflict={c} onDismiss={dismiss} onRestore={restore} />
              ))}
            </ul>
          </section>
        ))
      )}
    </>
  )
}
