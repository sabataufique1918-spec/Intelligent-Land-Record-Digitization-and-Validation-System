import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { Alert, Loading, PageHeader } from '../components/common.jsx'

// Officers type the correct text of each line image; verified lines become OCR training data.
export default function TranscribePage() {
  const { id } = useParams()
  const [record, setRecord] = useState(null)
  const [lines, setLines] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [reviewer, setReviewer] = useState('Officer')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const inputs = useRef({})

  useEffect(() => {
    api.getRecord(id).then(setRecord).catch((e) => setError(e.message))
    api.recordLines(id).then((r) => setLines(r.items)).catch((e) => setError(e.message))
  }, [id])

  useEffect(() => {
    if (!lines) return
    const d = {}
    lines.forEach((l) => {
      // Pre-fill only guesses OCR was fairly sure about; handwriting guesses are mostly noise.
      d[l.id] = l.ground_truth ?? ((l.ocr_confidence ?? 0) >= 50 ? l.ocr_text || '' : '')
    })
    setDrafts(d)
  }, [lines])

  async function cut() {
    setBusy(true)
    setError('')
    try {
      const r = await api.cutLines(id, record?.language || 'Hindi')
      setLines(r.items)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function save(line, status, index) {
    setError('')
    try {
      const updated = await api.saveLine(line.id, { text: drafts[line.id], status, verified_by: reviewer })
      setLines((ls) => ls.map((l) => (l.id === line.id ? updated : l)))
      const next = lines[index + 1]
      if (next) inputs.current[next.id]?.focus()
    } catch (e) {
      setError(e.message)
    }
  }

  const done = lines ? lines.filter((l) => l.status !== 'pending').length : 0

  return (
    <>
      <PageHeader
        title={`Transcribe lines · ${record?.record_number || ''}`}
        subtitle="Type exactly what is written on each line. Verified lines are used to measure and fine-tune OCR on documents like this."
        actions={<Link to={`/records/${id}`} className="btn btn-ghost">← Back to record</Link>}
      />
      <Alert tone="info">
        Copy the text <strong>as written</strong> (same spelling, script and digits), not a corrected or
        translated version. Skip lines that are stamps, pictures or unreadable. For typing Hindi, use a Hindi
        keyboard such as Windows “Hindi Phonetic” or Google Input Tools. Press <kbd>Enter</kbd> to save and
        move to the next line.
      </Alert>
      <Alert>{error}</Alert>

      {!lines ? (
        <Loading />
      ) : lines.length === 0 ? (
        <section className="panel">
          <p>This document has not been cut into lines yet.</p>
          <button className="btn btn-primary" onClick={cut} disabled={busy || !record?.has_file}>
            {busy ? 'Cutting into lines…' : 'Cut the document into lines'}
          </button>
          {record && !record.has_file && <p className="muted small">This record has no document.</p>}
        </section>
      ) : (
        <>
          <div className="transcribe-bar">
            <span>
              <strong>{done}</strong> of {lines.length} lines done
            </span>
            <div className="progress"><div style={{ width: `${(done / lines.length) * 100}%` }} /></div>
            <label className="field inline-field">
              <span>Your name</span>
              <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
            </label>
          </div>
          <ol className="line-list">
            {lines.map((line, i) => (
              <li key={line.id} className={`line-item line-${line.status}`}>
                <div className="line-meta small">
                  Page {line.page}, line {line.line_no}
                  {line.handwritten && <span className="tag">handwritten</span>}
                  {line.status !== 'pending' && <span className={`tag tag-${line.status}`}>{line.status}</span>}
                </div>
                <img src={line.image_url} alt={`Line ${line.line_no}`} className="line-image" />
                <div className="line-edit">
                  <input
                    ref={(el) => {
                      inputs.current[line.id] = el
                    }}
                    lang="hi"
                    value={drafts[line.id] ?? ''}
                    onChange={(e) => setDrafts({ ...drafts, [line.id]: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        save(line, 'verified', i)
                      }
                    }}
                  />
                  <button className="btn btn-primary btn-sm" onClick={() => save(line, 'verified', i)}>Save</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => save(line, 'skipped', i)}>Skip</button>
                </div>
                <div className="muted small">
                  OCR read: “{line.ocr_text || '—'}”
                  {line.ocr_confidence !== null && ` (${line.ocr_confidence}%)`}
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
    </>
  )
}
