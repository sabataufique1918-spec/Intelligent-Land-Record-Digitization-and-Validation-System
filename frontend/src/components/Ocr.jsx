import { useEffect, useState } from 'react'
import { FIELD_LABELS } from '../utils.js'

const METHOD_LABEL = {
  tesseract: 'Tesseract OCR',
  pdf_text_layer: 'PDF text layer (no OCR needed)',
  mixed: 'PDF text layer + Tesseract OCR',
}

const SOURCE_LABEL = { label: 'Label match', ai: 'AI' }

export function OcrLanguageSelect({ status, value, onChange, disabled }) {
  const installed = (status?.languages || []).filter((l) => l.installed)
  return (
    <label className="field ocr-lang">
      <span>Document language</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
        {installed.map((l) => (
          <option key={l.code} value={l.name}>
            {l.name}
            {l.code !== 'eng' ? ' + English' : ''}
          </option>
        ))}
      </select>
    </label>
  )
}

// Shows whether AI extraction is on, and lets the user switch it off for one document.
export function AiToggle({ status, value, onChange, disabled }) {
  const ai = status?.ai
  if (!ai) return null
  if (!ai.enabled) {
    return (
      <p className="ai-note muted small">
        AI extraction: <strong>off</strong> — values are suggested by label matching only. (An
        administrator can enable Claude AI extraction in <code>backend/.env</code>.)
      </p>
    )
  }
  return (
    <label className="checkbox ai-note">
      <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} disabled={disabled} />
      <span>
        Also use AI ({ai.model}) to extract fields. <strong>The document text is sent to Anthropic’s
        API.</strong> Only use this for documents you are allowed to share.
      </span>
    </label>
  )
}

export function OcrMeta({ confidence, method, language, pages, totalPages, extractionConfidence, aiModel }) {
  return (
    <div className="ocr-meta">
      <span>
        <strong>Method:</strong> {METHOD_LABEL[method] || method}
      </span>
      {language && (
        <span>
          <strong>Languages:</strong> {language}
        </span>
      )}
      <span>
        <strong>OCR confidence:</strong>{' '}
        {confidence === null || confidence === undefined ? 'n/a' : `${confidence}%`}
      </span>
      {pages ? (
        <span>
          <strong>Pages:</strong> {pages}
          {totalPages && totalPages > pages ? ` of ${totalPages} (limit reached)` : ''}
        </span>
      ) : null}
      {extractionConfidence !== null && extractionConfidence !== undefined && (
        <span title="Average confidence of owner, survey no., village, district and area (missing fields count as 0)">
          <strong>Extraction confidence:</strong> {extractionConfidence}%
        </span>
      )}
      <span>
        <strong>AI:</strong> {aiModel ? `used (${aiModel})` : 'not used'}
      </span>
    </div>
  )
}

export function OcrText({ text }) {
  const [open, setOpen] = useState(false)
  if (!text) return <p className="muted">No text was found in the document.</p>
  return (
    <div className="ocr-text">
      <button type="button" className="link-btn" onClick={() => setOpen((v) => !v)}>
        {open ? '▾ Hide extracted text' : '▸ Show extracted text'}
      </button>
      {open && <pre>{text}</pre>}
    </div>
  )
}

export function ConfidenceBar({ value, level }) {
  return (
    <div className={`conf conf-${level}`} title={`${value}% (${level})`}>
      <div className="conf-track">
        <div className="conf-fill" style={{ width: `${value}%` }} />
      </div>
      <span className="conf-num">{value}%</span>
    </div>
  )
}

function isEmpty(field, current) {
  const v = current?.[field]
  if (field === 'document_type') return !v || v === 'Other'
  return v === '' || v === null || v === undefined
}

// Scored suggestions the user can choose to copy into the form.
export function OcrSuggestions({ suggestions, current, onApply, applyLabel = 'Apply selected to form' }) {
  const keys = Object.keys(FIELD_LABELS).filter((k) => suggestions?.[k])
  const [selected, setSelected] = useState({})
  const [openWhy, setOpenWhy] = useState(null)

  useEffect(() => {
    const initial = {}
    keys.forEach((k) => {
      initial[k] = isEmpty(k, current) && suggestions[k].level !== 'low'
    })
    setSelected(initial)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggestions])

  if (!keys.length) {
    return (
      <p className="muted small">
        No field values could be found in the text, so nothing can be suggested. Please fill the form
        manually.
      </p>
    )
  }

  function apply() {
    const values = {}
    keys.forEach((k) => {
      if (selected[k]) values[k] = suggestions[k].value
    })
    onApply(values)
  }

  return (
    <div className="suggestions">
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th />
              <th>Field</th>
              <th>Suggested value</th>
              <th>Confidence</th>
              <th>Current</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => {
              const s = suggestions[k]
              return (
                <tr key={k} className={s.level === 'low' ? 'row-low' : ''}>
                  <td>
                    <input
                      type="checkbox"
                      checked={!!selected[k]}
                      onChange={(e) => setSelected({ ...selected, [k]: e.target.checked })}
                      aria-label={`Use suggested ${FIELD_LABELS[k]}`}
                    />
                  </td>
                  <td>{FIELD_LABELS[k]}</td>
                  <td>
                    <strong>{s.value}</strong>
                    <div className="source-chips">
                      {(s.sources || []).map((src) => (
                        <span key={src} className={`src src-${src}`}>{SOURCE_LABEL[src] || src}</span>
                      ))}
                    </div>
                    {s.alternatives?.map((a) => (
                      <div key={a.value} className="alt small">
                        Other reading ({SOURCE_LABEL[a.method] || a.method}): <strong>{a.value}</strong> · {a.confidence}%
                      </div>
                    ))}
                  </td>
                  <td>
                    <ConfidenceBar value={s.confidence} level={s.level} />
                    <button type="button" className="link-btn small" onClick={() => setOpenWhy(openWhy === k ? null : k)}>
                      {openWhy === k ? 'Hide' : 'Why?'}
                    </button>
                    {openWhy === k && (
                      <ul className="why small">
                        {s.reasons.map((r) => (
                          <li key={r}>{r}</li>
                        ))}
                        <li className="muted">Source: “{s.source}”</li>
                      </ul>
                    )}
                  </td>
                  <td className="muted">{isEmpty(k, current) ? '—' : current[k]}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        Confidence combines OCR quality of the words, how the value was found, format checks and whether
        label matching and AI agree. Low-confidence values are not pre-selected. Always check values
        against the document before saving.
      </p>
      <button type="button" className="btn btn-primary" onClick={apply}>
        {applyLabel}
      </button>
    </div>
  )
}
