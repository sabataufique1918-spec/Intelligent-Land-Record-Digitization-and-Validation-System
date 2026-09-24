import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { Alert, Loading, PageHeader, Pagination, RecordsTable } from '../components/common.jsx'

const PAGE_SIZE = 10

export default function SearchPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const page = Number(params.get('page') || 1)
  const [text, setText] = useState(q)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setText(q)
    if (!q) {
      setData(null)
      return
    }
    setLoading(true)
    setError('')
    api
      .listRecords({ q, page, page_size: PAGE_SIZE })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [q, page])

  function submit(e) {
    e.preventDefault()
    const term = text.trim()
    setParams(term ? { q: term } : {})
  }

  return (
    <>
      <PageHeader
        title="Record Search"
        subtitle="Search by owner name, father's name, survey / khasra number, khata number, village, tehsil, record number or file name."
      />
      <form className="search-bar" onSubmit={submit}>
        <input
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="e.g. Ramesh, 112/3, Rampur, LR-2026-00001"
        />
        <button className="btn btn-primary" type="submit">Search</button>
      </form>
      <Alert>{error}</Alert>

      {loading && <Loading text="Searching…" />}
      {!loading && data && (
        <section className="panel">
          <div className="panel-head">
            <h2>
              {data.total} result{data.total === 1 ? '' : 's'} for “{q}”
            </h2>
          </div>
          <RecordsTable records={data.items} />
          <Pagination
            page={data.page}
            pageSize={data.page_size}
            total={data.total}
            onChange={(p) => setParams({ q, page: String(p) })}
          />
        </section>
      )}
      {!q && <p className="muted">Enter a search term to find records.</p>}
    </>
  )
}
