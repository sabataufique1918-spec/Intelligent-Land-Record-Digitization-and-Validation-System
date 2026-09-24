import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { Alert, IssueList, PageHeader, StatusBadge } from '../components/common.jsx'
import RecordFields, { EMPTY_FIELDS } from '../components/RecordFields.jsx'
import { AiToggle, OcrLanguageSelect, OcrMeta, OcrSuggestions, OcrText } from '../components/Ocr.jsx'
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
            <>
              <h3>OCR</h3>
              {result.ocr_status === 'failed' ? (
                <Alert>{result.ocr_error}</Alert>
              ) : (
                <OcrMeta
                  confidence={result.ocr_confidence}
                  method={result.ocr_method}
                  language={result.ocr_language}
                  pages={result.ocr_pages}
                  extractionConfidence={result.extraction_confidence}
                  aiModel={result.ai_model}
                />
              )}
            </>
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
              <h3>Read text from document (OCR)</h3>
              <p className="muted small">
                Works on printed text. Handwritten records are not supported yet.
              </p>
              <div className="ocr-controls">
                <OcrLanguageSelect status={ocrStatus} value={ocrLang} onChange={setOcrLang} disabled={ocrBusy} />
                <button type="button" className="btn btn-primary" onClick={runOcr} disabled={ocrBusy}>
                  {ocrBusy ? 'Reading document…' : 'Run OCR'}
                </button>
              </div>
              <AiToggle status={ocrStatus} value={useAi} onChange={setUseAi} disabled={ocrBusy} />
              {ocrBusy && <p className="muted small">This can take a few seconds per page (longer with AI).</p>}
              <Alert>{ocrError}</Alert>
              {ocrResult?.ai_error && <Alert tone="warning">AI extraction failed: {ocrResult.ai_error} Label matching was used instead.</Alert>}
              {ocrResult && (
                <>
                  <OcrMeta
                    confidence={ocrResult.confidence}
                    method={ocrResult.method}
                    language={ocrResult.language}
                    pages={ocrResult.pages_processed}
                    totalPages={ocrResult.total_pages}
                    extractionConfidence={ocrResult.extraction_confidence}
                    aiModel={ocrResult.ai_model}
                  />
                  <OcrSuggestions suggestions={ocrResult.suggestions} current={fields} onApply={applySuggestions} />
                  <OcrText text={ocrResult.text} />
                </>
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
              Save the document's OCR text with the record (used for search and number cross-checks)
            </label>
          )}
          <div className="actions-row">
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? (ocrReady && saveOcr ? 'Uploading & reading text…' : 'Uploading…') : 'Upload & run rule checks'}
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
