import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Alert, Loading, PageHeader } from '../components/common.jsx'
import { FIELD_LABELS } from '../utils.js'

const SOURCE_LABEL = { label: 'Label match', ai: 'AI', 'label+ai': 'Label match + AI agree', learned: 'Learned correction' }

function Pct({ value }) {
  if (value === null || value === undefined) return <span className="muted">—</span>
  const tone = value >= 90 ? 'high' : value >= 70 ? 'medium' : 'low'
  return <strong className={`pct pct-${tone}`}>{value}%</strong>
}

function RateTable({ title, rows, labels = {} }) {
  const entries = Object.entries(rows || {})
  return (
    <section className="panel">
      <h2>{title}</h2>
      {entries.length === 0 ? (
        <p className="muted">No data yet.</p>
      ) : (
        <table className="table compact-table">
          <thead>
            <tr><th /><th>Checked</th><th>Accepted as suggested</th><th>Accuracy</th></tr>
          </thead>
          <tbody>
            {entries.map(([k, v]) => (
              <tr key={k}>
                <td>{labels[k] || k}</td>
                <td>{v.checked}</td>
                <td>{v.accepted}</td>
                <td><Pct value={v.accuracy} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

export default function TrainingPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.trainingStats().then(setData).catch((e) => setError(e.message))
  }, [])

  if (error) return <Alert>{error}</Alert>
  if (!data) return <Loading />
  const f = data.fields
  const l = data.lines
  const progress = Math.min(100, (l.lines_verified / l.recommended_minimum_lines) * 100)

  return (
    <>
      <PageHeader
        title="Training Data"
        subtitle="How accurate extraction really is on your documents, what the system has learned from officers, and data for fine-tuning OCR."
      />

      <div className="cards">
        <div className="summary-card">
          <div className="card-label">Suggestion accuracy</div>
          <div className="card-value"><Pct value={f.overall.accuracy} /></div>
          <div className="card-hint">{f.overall.checked} suggested values checked on {f.records} records</div>
        </div>
        <div className="summary-card tone-success">
          <div className="card-label">Learned corrections</div>
          <div className="card-value">{f.learned.length}</div>
          <div className="card-hint">Applied automatically to new documents</div>
        </div>
        <div className="summary-card tone-warning">
          <div className="card-label">Lines transcribed</div>
          <div className="card-value">{l.lines_verified}</div>
          <div className="card-hint">{l.handwritten_verified} handwritten · {l.lines_pending} waiting</div>
        </div>
        <div className="summary-card tone-danger">
          <div className="card-label">OCR error on your lines</div>
          <div className="card-value area-value">
            {l.current_ocr_cer_printed ?? '—'}{l.current_ocr_cer_printed !== null && '%'}
            <span className="muted small"> printed</span>
          </div>
          <div className="card-hint">
            Handwritten: {l.current_ocr_cer_handwritten !== null ? `${l.current_ocr_cer_handwritten}%` : '—'} (character error rate)
          </div>
        </div>
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2>OCR fine-tuning data</h2>
          <a className={`btn ${l.lines_verified ? 'btn-primary' : 'btn-ghost'}`} href={api.trainingExportUrl()}>
            ⇩ Download training data (ZIP)
          </a>
        </div>
        <p>
          <strong>{l.lines_verified}</strong> of about <strong>{l.recommended_minimum_lines}</strong> verified lines
          recommended before a first fine-tuning run ({l.characters_verified.toLocaleString('en-IN')} characters).
        </p>
        <div className="progress big"><div style={{ width: `${progress}%` }} /></div>
        <p className="muted small">
          Open any record → “Transcribe lines” to add data. The ZIP contains line images with their verified text in
          the format used by Tesseract’s <code>tesstrain</code>; the steps are in <code>backend/scripts/FINE_TUNING.md</code>.
          Fine-tuning runs outside this app (Linux / WSL, several hours of CPU). Handwriting needs thousands of lines to
          become reliable.
        </p>
        <Alert tone="warning">The export contains real names and survey numbers. Keep it inside your organisation.</Alert>
      </section>

      <div className="grid-2">
        <RateTable title="Accuracy by field" rows={f.by_field} labels={FIELD_LABELS} />
        <div>
          <RateTable title="Accuracy by method" rows={f.by_source} labels={SOURCE_LABEL} />
          <RateTable title="Accuracy by page quality" rows={f.by_quality} />
        </div>
      </div>

      <div className="grid-2">
        <section className="panel">
          <h2>Learned corrections</h2>
          {f.learned.length === 0 ? (
            <p className="muted">
              None yet. When officers correct the same OCR value to the same text at least twice, it appears here and is
              fixed automatically in future suggestions.
            </p>
          ) : (
            <table className="table compact-table">
              <thead><tr><th>Field</th><th>OCR reads</th><th>Corrected to</th><th>Times</th></tr></thead>
              <tbody>
                {f.learned.map((x) => (
                  <tr key={`${x.field}-${x.wrong}`}>
                    <td>{FIELD_LABELS[x.field] || x.field}</td><td className="muted">{x.wrong}</td>
                    <td><strong>{x.correct}</strong></td><td>{x.times}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
        <section className="panel">
          <h2>Most frequent corrections</h2>
          {f.frequent_corrections.length === 0 ? (
            <p className="muted">No corrections recorded yet.</p>
          ) : (
            <table className="table compact-table">
              <thead><tr><th>Field</th><th>Suggested</th><th>Officer saved</th><th>Times</th></tr></thead>
              <tbody>
                {f.frequent_corrections.map((x, i) => (
                  <tr key={i}>
                    <td>{FIELD_LABELS[x.field] || x.field}</td><td className="muted">{x.suggested}</td>
                    <td>{x.corrected_to}</td><td>{x.times}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </>
  )
}
