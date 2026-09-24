import { Link } from 'react-router-dom'
import { STATUS_META, display, formatArea, formatDate } from '../utils.js'

export function StatusBadge({ status }) {
  const meta = STATUS_META[status] || { label: status, tone: 'neutral' }
  return <span className={`badge badge-${meta.tone}`}>{meta.label}</span>
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  )
}

export function Alert({ tone = 'danger', children }) {
  if (!children) return null
  return <div className={`alert alert-${tone}`}>{children}</div>
}

export function Loading({ text = 'Loading…' }) {
  return <div className="loading">{text}</div>
}

export function EmptyState({ children }) {
  return <div className="empty">{children}</div>
}

export function IssueList({ issues }) {
  if (!issues?.length) return <p className="muted">No issues found by the rule checks.</p>
  return (
    <ul className="issues">
      {issues.map((issue, i) => (
        <li key={i} className={`issue issue-${issue.severity}`}>
          <span className="issue-sev">{issue.severity}</span>
          <span>
            {issue.message}
            {issue.related_record_ids?.map((rid) => (
              <Link key={rid} to={`/records/${rid}`} className="issue-link">
                Open record #{rid} →
              </Link>
            ))}
          </span>
        </li>
      ))}
    </ul>
  )
}

export function IssueCounts({ issues }) {
  const errors = issues.filter((i) => i.severity === 'error').length
  const warnings = issues.filter((i) => i.severity === 'warning').length
  if (!errors && !warnings) return <span className="muted">—</span>
  return (
    <span className="issue-counts">
      {errors > 0 && <span className="count-error">{errors} error{errors > 1 ? 's' : ''}</span>}
      {warnings > 0 && <span className="count-warning">{warnings} warning{warnings > 1 ? 's' : ''}</span>}
    </span>
  )
}

export function RecordsTable({ records, showIssues = false }) {
  if (!records.length) return <EmptyState>No records match the current filters.</EmptyState>
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Record No.</th>
            <th>Owner</th>
            <th>Survey / Khata</th>
            <th>Village · District</th>
            <th>Document</th>
            <th>Area</th>
            <th>Status</th>
            {showIssues ? <th>Issues</th> : <th>Uploaded</th>}
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <tr key={r.id}>
              <td>
                <Link to={`/records/${r.id}`} className="record-link">{r.record_number}</Link>
                {r.is_sample && <span className="tag">Sample</span>}
              </td>
              <td>{display(r.owner_name)}</td>
              <td>
                {display(r.survey_number)} <span className="muted">/ {display(r.khata_number)}</span>
              </td>
              <td>
                {display(r.village)} <span className="muted">· {display(r.district)}</span>
              </td>
              <td>
                <div>{r.document_type}</div>
                <div className="muted small">
                  {r.has_file ? `${r.file_type?.toUpperCase()} attached` : 'No file'}
                  {r.ocr_status === 'completed' && ' · OCR ✓'}
                </div>
              </td>
              <td>{formatArea(r)}</td>
              <td><StatusBadge status={r.validation_status} /></td>
              {showIssues ? (
                <td><IssueCounts issues={r.validation_issues} /></td>
              ) : (
                <td className="small">{formatDate(r.created_at)}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Pagination({ page, pageSize, total, onChange }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (total === 0) return null
  const from = (page - 1) * pageSize + 1
  const to = Math.min(total, page * pageSize)
  return (
    <div className="pagination">
      <span className="muted">
        Showing {from}–{to} of {total}
      </span>
      <div className="pagination-buttons">
        <button className="btn btn-ghost" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          ← Prev
        </button>
        <span>
          Page {page} of {pages}
        </span>
        <button className="btn btn-ghost" disabled={page >= pages} onClick={() => onChange(page + 1)}>
          Next →
        </button>
      </div>
    </div>
  )
}
