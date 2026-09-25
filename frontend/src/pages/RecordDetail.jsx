import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { Alert, IssueList, Loading, PageHeader, StatusBadge } from '../components/common.jsx'
import RecordFields, { EMPTY_FIELDS } from '../components/RecordFields.jsx'
import ConflictItem from '../components/ConflictItem.jsx'
import RecordMap from '../components/RecordMap.jsx'
import { ExtractionResult, ReadControls, ReadingProgress, fromRecord } from '../components/Ocr.jsx'
import { OCR_STATUS, display, formatArea, formatBytes, formatDate } from '../utils.js'

function toForm(record) {
  const values = {}
  Object.keys(EMPTY_FIELDS).forEach((k) => {
    values[k] = record[k] ?? ''
  })
  return values
}

function toPayload(values) {
  const payload = {}
  Object.entries(values).forEach(([k, v]) => {
    if (k === 'area_value') payload[k] = v === '' ? null : Number(v)
    else payload[k] = v === '' ? null : v
  })
  return payload
}

export default function RecordDetail() {
  const { id } = useParams()
  const [record, setRecord] = useState(null)
  const [options, setOptions] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(EMPTY_FIELDS)
  const [reviewer, setReviewer] = useState('Officer')
  const [note, setNote] = useState('')
  const [ocrStatus, setOcrStatus] = useState(null)
  const [ocrLang, setOcrLang] = useState('Hindi')
  const [conflicts, setConflicts] = useState(null)
  const [useAi, setUseAi] = useState(true)

  useEffect(() => {
    setRecord(null)
    api
      .getRecord(id)
      .then((r) => {
        setRecord(r)
        if (r.language) setOcrLang(r.language)
      })
      .catch((e) => setError(e.message))
    api.options().then(setOptions).catch(() => {})
    api.ocrStatus().then(setOcrStatus).catch(() => setOcrStatus({ available: false }))
  }, [id])

  // OCR runs in the background on the server: poll until it has finished.
  const ocrPending = ['queued', 'processing'].includes(record?.ocr_status)
  useEffect(() => {
    if (!ocrPending) return
    const timer = setInterval(() => {
      api
        .getRecord(id)
        .then((r) => {
          if (['queued', 'processing'].includes(r.ocr_status)) return
          setRecord(r)
          setNotice(r.ocr_status === 'failed' ? '' : 'The document has been read and the rule checks were re-run.')
        })
        .catch(() => {})
    }, 2000)
    return () => clearInterval(timer)
  }, [id, ocrPending])

  // Reload conflicts whenever the record changes (edit, review, OCR).
  useEffect(() => {
    if (!record) return
    api
      .recordConflicts(record.id)
      .then((r) => setConflicts(r.items))
      .catch(() => setConflicts([]))
  }, [record])

  async function dismissConflict(c, conflictNote, reviewedBy) {
    await api.dismissConflict({ key: c.key, note: conflictNote, reviewed_by: reviewedBy })
    setRecord(await api.getRecord(id))
    setNotice('Conflict marked as not a problem.')
  }

  async function restoreConflict(c) {
    await api.restoreConflict(c.key)
    setRecord(await api.getRecord(id))
    setNotice('Conflict restored.')
  }

  async function run(action, message) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const updated = await action()
      setRecord(updated)
      setNotice(message)
      return true
    } catch (e) {
      setError(e.message)
      return false
    } finally {
      setBusy(false)
    }
  }

  const decide = (status) =>
    run(
      () => api.setStatus(id, { status, reviewed_by: reviewer, note }),
      status === 'pending' ? 'Record sent back to the review queue.' : `Record marked as ${status}.`,
    ).then((ok) => ok && setNote(''))

  async function saveEdits(e) {
    e.preventDefault()
    const ok = await run(() => api.updateRecord(id, toPayload(form)), 'Changes saved and rule checks re-run.')
    if (ok) setEditing(false)
  }

  function applyOcrSuggestions(values) {
    setForm({ ...toForm(record), ...values })
    setEditing(true)
    const n = Object.keys(values).length
    setNotice(`${n} detail${n === 1 ? '' : 's'} copied into the edit form below. Check them against the document, then press Save.`)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const readDocument = () =>
    run(
      () => api.runOcr(id, ocrLang, !!ocrStatus?.ai?.enabled && useAi),
      'Reading started. The results will appear in “Text from the document” when it finishes.',
    )

  if (error && !record) return <Alert>{error}</Alert>
  if (!record) return <Loading />

  const decided = ['verified', 'rejected'].includes(record.validation_status)
  const rows = [
    ['Document type', record.document_type],
    ['Owner name', record.owner_name],
    ["Father's / husband's name", record.father_name],
    ['Document date', record.document_date],
    ['Previous owner / seller', record.previous_owner],
    ['Survey / Khasra no.', record.survey_number],
    ['Khata no.', record.khata_number],
    ['Village', record.village],
    ['Tehsil / Taluka', record.tehsil],
    ['District', record.district],
    ['State', record.state],
    ['Area', formatArea(record)],
    ['Language', record.language],
    ['Remarks', record.remarks],
  ]

  return (
    <>
      <PageHeader
        title={record.record_number}
        subtitle={
          <>
            <StatusBadge status={record.validation_status} />{' '}
            {record.is_sample && <span className="tag">Sample data</span>}{' '}
            <span className="muted">Created {formatDate(record.created_at)}</span>
          </>
        }
        actions={
          <>
            <Link to={`/parcels/record/${record.id}`} className="btn btn-ghost">Parcel history</Link>
            <Link to="/records" className="btn btn-ghost">← All records</Link>
          </>
        }
      />
      <Alert>{error}</Alert>
      <Alert tone="success">{notice}</Alert>

      <div className="detail-layout">
        <div>
          <section className="panel">
            <div className="panel-head">
              <h2>Record details</h2>
              {!editing && (
                <button
                  className="btn btn-ghost"
                  onClick={() => {
                    setForm(toForm(record))
                    setEditing(true)
                  }}
                >
                  Edit details
                </button>
              )}
            </div>
            {editing ? (
              <form onSubmit={saveEdits}>
                <RecordFields values={form} onChange={setForm} options={options} />
                <p className="muted small">
                  Saving re-runs the rule checks and clears any previous officer decision.
                </p>
                <div className="actions-row">
                  <button className="btn btn-primary" disabled={busy}>Save changes</button>
                  <button type="button" className="btn btn-ghost" onClick={() => setEditing(false)}>
                    Cancel
                  </button>
                </div>
              </form>
            ) : (
              <dl className="details">
                {rows.map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd>{display(value)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Validation results</h2>
              <button
                className="btn btn-ghost"
                disabled={busy}
                onClick={() => run(() => api.revalidate(id), 'Rule checks re-run.')}
              >
                Re-run rule checks
              </button>
            </div>
            <IssueList issues={record.validation_issues} />
            <p className="muted small">
              Rule-based checks: entered values vs the document text, other records and the imported
              cadastral map. Government-database checks are not implemented yet.
            </p>
          </section>

          {record.has_file && (
            <section className="panel">
              <div className="panel-head">
                <h2>Text from the document</h2>
              </div>
              {ocrPending && <ReadingProgress status={record.ocr_status} />}
              {record.ocr_status === 'not_run' && (
                <p className="x-empty">
                  The text of this document has not been read yet. Choose the language written on the document
                  and press <strong>Read document</strong>: the system reads the printed text and suggests values
                  for the record details.
                </p>
              )}
              {record.ocr_status === 'failed' && (
                <div className="x-summary x-summary-poor">
                  <span className="x-icon" aria-hidden="true">✗</span>
                  <div>
                    <div className="x-title">Reading the document failed</div>
                    <div className="x-body">{record.ocr_error} Try again below.</div>
                  </div>
                </div>
              )}
              {['completed', 'no_text'].includes(record.ocr_status) && (
                <ExtractionResult
                  result={fromRecord(record)}
                  current={toForm(record)}
                  onApply={applyOcrSuggestions}
                  applyLabel="Copy into the record"
                  documentUrl={api.fileUrl(record.id)}
                  documentIsPdf={record.file_type === 'pdf'}
                />
              )}
              {!ocrPending &&
                (ocrStatus?.available ? (
                  <ReadControls
                    status={ocrStatus}
                    lang={ocrLang}
                    onLangChange={setOcrLang}
                    useAi={useAi}
                    onUseAiChange={setUseAi}
                    onRun={readDocument}
                    busy={busy}
                    runLabel={record.ocr_status === 'not_run' ? 'Read document' : 'Read again'}
                    collapsed={['completed', 'no_text'].includes(record.ocr_status)}
                  >
                    <p className="small muted">
                      Text reading keeps making the same mistakes on your documents?{' '}
                      <Link to={`/records/${record.id}/transcribe`} className="link">
                        Type in a few lines to train it →
                      </Link>
                    </p>
                  </ReadControls>
                ) : (
                  ocrStatus && <p className="muted">Reading documents is not available on the server.</p>
                ))}
            </section>
          )}

          <RecordMap record={record} onRecordChange={setRecord} />
        </div>

        <div>
          <section className="panel">
            <h2>Officer review</h2>
            {decided && (
              <div className="review-box">
                <StatusBadge status={record.validation_status} /> by{' '}
                <strong>{display(record.reviewed_by)}</strong> on {formatDate(record.reviewed_at)}
                {record.review_note && <p className="review-note">“{record.review_note}”</p>}
              </div>
            )}
            <label className="field">
              <span>Reviewer name</span>
              <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
            </label>
            <label className="field">
              <span>Note</span>
              <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
            </label>
            <div className="actions-row">
              <button className="btn btn-success" disabled={busy} onClick={() => decide('verified')}>
                Verify
              </button>
              <button className="btn btn-danger" disabled={busy} onClick={() => decide('rejected')}>
                Reject
              </button>
              {decided && (
                <button className="btn btn-ghost" disabled={busy} onClick={() => decide('pending')}>
                  Send back to queue
                </button>
              )}
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Related records &amp; conflicts</h2>
              <Link to="/conflicts" className="link small">All conflicts →</Link>
            </div>
            {conflicts === null ? (
              <Loading />
            ) : conflicts.length === 0 ? (
              <p className="muted">
                No other record refers to this parcel or uses the same document file.
              </p>
            ) : (
              <ul className="conflict-list">
                {conflicts.map((c) => (
                  <ConflictItem
                    key={c.key}
                    conflict={c}
                    onDismiss={dismissConflict}
                    onRestore={restoreConflict}
                    extra={
                      <p className="small">
                        Other record:{' '}
                        <Link to={`/records/${c.other_record.id}`} className="record-link">
                          {c.other_record.record_number}
                        </Link>{' '}
                        · {display(c.other_record.owner_name)} · {c.other_record.document_type}{' '}
                        <StatusBadge status={c.other_record.validation_status} />
                      </p>
                    }
                  />
                ))}
              </ul>
            )}
          </section>

          <section className="panel">
            <h2>Source document</h2>
            {record.has_file ? (
              <>
                <div className="file-meta">
                  <div className="file-name">{record.original_filename}</div>
                  <div className="muted small">
                    {record.file_type?.toUpperCase()} · {formatBytes(record.file_size)} · Text: {OCR_STATUS[record.ocr_status] || record.ocr_status}
                  </div>
                </div>
                <div className="preview">
                  {record.file_type === 'pdf' ? (
                    <iframe src={api.fileUrl(record.id)} title="Document preview" />
                  ) : (
                    <img src={api.fileUrl(record.id)} alt={record.original_filename} />
                  )}
                </div>
                <div className="actions-row">
                  <a className="btn btn-ghost" href={api.fileUrl(record.id)} target="_blank" rel="noreferrer">
                    Open in new tab
                  </a>
                  <a className="btn btn-ghost" href={api.fileUrl(record.id, true)}>Download</a>
                </div>
              </>
            ) : (
              <p className="muted">No document attached to this record.</p>
            )}
          </section>
        </div>
      </div>
    </>
  )
}
