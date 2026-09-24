import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { Alert, Loading, PageHeader, Pagination, RecordsTable } from '../components/common.jsx'
import { STATUS_META } from '../utils.js'

const PAGE_SIZE = 10

export default function RecordsPage() {
  const [params, setParams] = useSearchParams()
  const [options, setOptions] = useState(null)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  const filters = {
    status: params.get('status') || '',
    district: params.get('district') || '',
    document_type: params.get('document_type') || '',
    page: Number(params.get('page') || 1),
  }

  useEffect(() => {
    api.options().then(setOptions).catch(() => {})
  }, [])

  useEffect(() => {
    setData(null)
    api
      .listRecords({ ...filters, page_size: PAGE_SIZE })
      .then(setData)
      .catch((e) => setError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])

  function update(key, value) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== 'page') next.delete('page')
    setParams(next)
  }

  return (
    <>
      <PageHeader
        title="Uploaded Records"
        subtitle="All land records stored in the system."
        actions={<Link to="/upload" className="btn btn-primary">+ Upload Document</Link>}
      />
      <Alert>{error}</Alert>
      <section className="panel">
        <div className="filters">
          <select value={filters.status} onChange={(e) => update('status', e.target.value)}>
            <option value="">All statuses</option>
            {(options?.validation_statuses || []).map((s) => (
              <option key={s} value={s}>{STATUS_META[s]?.label || s}</option>
            ))}
          </select>
          <select value={filters.district} onChange={(e) => update('district', e.target.value)}>
            <option value="">All districts</option>
            {(options?.districts || []).map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
          <select value={filters.document_type} onChange={(e) => update('document_type', e.target.value)}>
            <option value="">All document types</option>
            {(options?.document_types || []).map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
          {(filters.status || filters.district || filters.document_type) && (
            <button className="btn btn-ghost" onClick={() => setParams({})}>Clear filters</button>
          )}
        </div>
        {!data ? (
          <Loading />
        ) : (
          <>
            <RecordsTable records={data.items} />
            <Pagination
              page={data.page}
              pageSize={data.page_size}
              total={data.total}
              onChange={(p) => update('page', String(p))}
            />
          </>
        )}
      </section>
    </>
  )
}
