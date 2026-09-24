import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { Alert, Loading, PageHeader, Pagination, RecordsTable } from '../components/common.jsx'
import { STATUS_META, STATUS_ORDER } from '../utils.js'

const PAGE_SIZE = 10

export default function ValidationPage() {
  const [params, setParams] = useSearchParams()
  const status = params.get('status') || 'flagged'
  const page = Number(params.get('page') || 1)
  const [counts, setCounts] = useState(null)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.summary().then((s) => setCounts(s.status_counts)).catch(() => {})
  }, [])

  useEffect(() => {
    setData(null)
    api
      .listRecords({ status, page, page_size: PAGE_SIZE })
      .then(setData)
      .catch((e) => setError(e.message))
  }, [status, page])

  return (
    <>
      <PageHeader
        title="Validation Status"
        subtitle="Records grouped by the result of rule checks and officer review."
      />
      <Alert tone="info">
        Current checks are simple rules on the entered details: required fields, survey-number
        format, area range, exact-match conflicts between records, and survey / khata numbers
        compared with the document's OCR text. AI, GIS and government database validation are not
        implemented yet. Open a record to verify or reject it.
      </Alert>
      <Alert>{error}</Alert>

      <div className="tabs">
        {STATUS_ORDER.map((s) => (
          <button
            key={s}
            className={`tab ${s === status ? 'active' : ''}`}
            onClick={() => setParams({ status: s })}
          >
            {STATUS_META[s].label}
            {counts && <span className="tab-count">{counts[s] ?? 0}</span>}
          </button>
        ))}
      </div>

      <section className="panel">
        {!data ? (
          <Loading />
        ) : (
          <>
            <RecordsTable records={data.items} showIssues />
            <Pagination
              page={data.page}
              pageSize={data.page_size}
              total={data.total}
              onChange={(p) => setParams({ status, page: String(p) })}
            />
          </>
        )}
      </section>
    </>
  )
}
