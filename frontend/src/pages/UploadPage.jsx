import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { Alert, IssueList, PageHeader, StatusBadge } from '../components/common.jsx'
import RecordFields, { EMPTY_FIELDS } from '../components/RecordFields.jsx'
import { ExtractionResult, ReadControls, ReadingProgress, fromPreview } from '../components/Ocr.jsx'
import { formatBytes } from '../utils.js'

const ACCEPT = '.pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg'
const MAX_MB = 20

export default function UploadPage() {
  const [options, setOptions] = useState(null)
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState('')
  const [fields, setFields] = useState(EMPTY_FIELDS)
  const [dragging, setDragging] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [ocrStatus, setOcrStatus] = useState(null)
  const [ocrLang, setOcrLang] = useState('Hindi')
  const [ocrResult, setOcrResult] = useState(null)
  const [ocrBusy, setOcrBusy] = useState(false)
  const [ocrError, setOcrError] = useState('')
  const [saveOcr, setSaveOcr] = useState(true)
  const [useAi, setUseAi] = useState(true)
  const inputRef = useRef(null)

  useEffect(() => {
    api.options().then(setOptions).catch((e) => setError(e.message))
    api
      .ocrStatus()
      .then((s) => {
        setOcrStatus(s)
        const installed = s.languages.filter((l) => l.installed).map((l) => l.name)
        if (installed.length && !installed.includes('Hindi')) setOcrLang(installed[0])
      })
      .catch(() => setOcrStatus({ available: false, message: 'Could not check OCR status.' }))
  }, [])

  const ocrReady = !!ocrStatus?.available

  useEffect(() => () => preview && URL.revokeObjectURL(preview), [preview])

  function pickFile(f) {
    setError('')
    if (!f) return
    const ok = /\.(pdf|png|jpe?g)$/i.test(f.name)
    if (!ok) return setError('Only PDF, JPG and PNG files are allowed.')
    if (f.size > MAX_MB * 1024 * 1024) return setError(`File is larger than ${MAX_MB} MB.`)
    setFile(f)
    setPreview(URL.createObjectURL(f))
    setOcrResult(null)
    setOcrError('')
  }

  async function runOcr() {
    if (!file) return
    setOcrBusy(true)
    setOcrError('')
    setOcrResult(null)
    const form = new FormData()
    form.append('file', file)
    form.append('language', ocrLang)
    form.append('use_ai', ocrStatus?.ai?.enabled && useAi ? 'true' : 'false')
    try {
      setOcrResult(await api.ocrExtract(form))
    } catch (err) {
      setOcrError(err.message)
    } finally {
      setOcrBusy(false)
    }
  }

  function applySuggestions(values) {
    setFields((f) => ({ ...f, ...values, language: f.language || ocrLang }))
  }

  async function submit(e) {
    e.preventDefault()
    if (!file) return setError('Please choose a PDF or image to upload.')
    setSubmitting(true)
    setError('')
    const form = new FormData()
    form.append('file', file)
    Object.entries(fields).forEach(([k, v]) => {
      if (v !== '' && v !== null) form.append(k, v)
    })
    if (ocrReady && saveOcr) {
      form.append('run_ocr', 'true')
      form.append('ocr_language', ocrLang)
      form.append('use_ai', ocrStatus?.ai?.enabled && useAi ? 'true' : 'false')
    }
    try {
      setResult(await api.uploadRecord(form))
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  function reset() {
    setFile(null)
    setPreview('')
    setFields(EMPTY_FIELDS)
    setResult(null)
    setError('')
    setOcrResult(null)
    setOcrError('')
  }

  if (result) {
    return (
      <>
        <PageHeader title="Upload complete" subtitle="The document was stored and rule checks were run on the details you entered." />
        <section className="panel">
          <div className="result-head">
            <div>
              <div className="muted small">Record number</div>
              <div className="result-number">{result.record_number}</div>
            </div>
            <StatusBadge status={result.validation_status} />
          </div>
          {result.ocr_status !== 'not_run' && (
            <p className="x-note">
              The document’s text is being read in the background. Open the record to see what was found;
              the rule checks are run again when reading finishes.
            </p>
          )}
          <h3>Rule check results</h3>
          <IssueList issues={result.validation_issues} />
          <div className="actions-row">
            <Link to={`/records/${result.id}`} className="btn btn-primary">Open record</Link>
            <button className="btn btn-ghost" onClick={reset}>Upload another</button>
          </div>
        </section>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Upload Document"
        subtitle="Upload a scanned land record (PDF, JPG or PNG) and enter its details."
      />
      {ocrStatus && !ocrReady && (
        <Alert tone="info">
          OCR is not available on the server ({ocrStatus.message || 'language files missing'}), so
          record details must be typed in manually.
        </Alert>
      )}
      <Alert>{error}</Alert>

      <form onSubmit={submit} className="upload-layout">
        <section className="panel">
          <h2>1. Document</h2>
          <div
            className={`dropzone ${dragging ? 'dragging' : ''}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              pickFile(e.dataTransfer.files?.[0])
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              hidden
              onChange={(e) => pickFile(e.target.files?.[0])}
            />
            {file ? (
              <div>
                <div className="file-name">{file.name}</div>
                <div className="muted small">{formatBytes(file.size)} · click to change</div>
              </div>
            ) : (
              <div>
                <div className="drop-icon">⇪</div>
                <div>Drag &amp; drop a file here, or click to browse</div>
                <div className="muted small">PDF, JPG, PNG · up to {MAX_MB} MB</div>
              </div>
            )}
          </div>
          {file && preview && (
            <div className="preview">
              {file.type === 'application/pdf' || /\.pdf$/i.test(file.name) ? (
                <iframe src={preview} title="PDF preview" />
              ) : (
                <img src={preview} alt="Selected document preview" />
              )}
            </div>
          )}

          {file && ocrReady && (
            <div className="ocr-box">
              <h3>Fill in the details automatically (optional)</h3>
              <p className="muted small">
                The system can read the printed text of this document and suggest values for the record
                details. You choose which ones to copy into the form, and check them before uploading.
              </p>
              {ocrBusy && <ReadingProgress status="processing" />}
              {ocrError && (
                <div className="x-summary x-summary-poor">
                  <span className="x-icon" aria-hidden="true">✗</span>
                  <div>
                    <div className="x-title">The document could not be read</div>
                    <div className="x-body">{ocrError}</div>
                  </div>
                </div>
              )}
              {ocrResult && !ocrBusy && (
                <ExtractionResult
                  result={fromPreview(ocrResult)}
                  current={fields}
                  onApply={applySuggestions}
                  applyLabel="Copy into the form"
                  documentUrl={preview}
                  documentIsPdf={file.type === 'application/pdf' || /\.pdf$/i.test(file.name)}
                />
              )}
              {!ocrBusy && (
                <ReadControls
                  status={ocrStatus}
                  lang={ocrLang}
                  onLangChange={setOcrLang}
                  useAi={useAi}
                  onUseAiChange={setUseAi}
                  onRun={runOcr}
                  busy={ocrBusy}
                  runLabel={ocrResult ? 'Read again' : 'Read document'}
                  collapsed={!!ocrResult}
                />
              )}
            </div>
          )}
        </section>

        <section className="panel">
          <h2>2. Record details</h2>
          <p className="muted small">Fields marked * are checked by the validation rules.</p>
          <RecordFields values={fields} onChange={setFields} options={options} />
          {ocrReady && (
            <label className="checkbox">
              <input type="checkbox" checked={saveOcr} onChange={(e) => setSaveOcr(e.target.checked)} />
              Also read and keep the document’s text with the record (so it can be searched and the numbers
              you enter can be checked against it)
            </label>
          )}
          <div className="actions-row">
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Uploading…' : 'Upload & run rule checks'}
            </button>
            <button type="button" className="btn btn-ghost" onClick={reset} disabled={submitting}>
              Clear
            </button>
          </div>
        </section>
      </form>
    </>
  )
}
