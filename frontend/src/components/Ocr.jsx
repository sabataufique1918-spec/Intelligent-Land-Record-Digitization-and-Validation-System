import { useEffect, useMemo, useState } from 'react'
import { FIELD_LABELS, formatDate } from '../utils.js'

// Plain-language names for the certainty levels computed by the backend confidence engine.
const CERTAINTY = {
  high: { label: 'Looks right', hint: 'Found clearly in the document' },
  medium: { label: 'Please check', hint: 'Probably right, but compare it with the document' },
  low: { label: 'Unsure', hint: 'Likely to be wrong: check it carefully' },
}

const LANGUAGE_NAMES = {
  eng: 'English', hin: 'Hindi', mar: 'Marathi', pan: 'Punjabi', ben: 'Bengali', guj: 'Gujarati',
  ori: 'Odia', tam: 'Tamil', tel: 'Telugu', kan: 'Kannada', mal: 'Malayalam', urd: 'Urdu',
}

const METHOD_LABEL = {
  ai_vision: 'AI read the page image (handwriting / poor scan)',
  tesseract: 'Tesseract OCR',
  pdf_text_layer: 'Text taken directly from the PDF (no OCR needed)',
  mixed: 'PDF text + Tesseract OCR',
}

// "eng+hin_landrec" -> "Hindi + English"
function languageNames(codes) {
  if (!codes) return ''
  const names = codes.split('+').map((c) => LANGUAGE_NAMES[c.split('_')[0]] || c)
  const main = names.filter((n) => n !== 'English')
  return [...new Set([...main, ...(names.includes('English') ? ['English'] : [])])].join(' + ')
}

// ---------------------------------------------------------------- normalising API results

export function fromPreview(r) {
  return {
    status: 'completed',
    text: r.text,
    quality: r.quality,
    method: r.method,
    confidence: r.confidence,
    pages: r.pages_processed,
    totalPages: r.total_pages,
    language: r.language,
    preprocessing: r.preprocessing,
    suggestions: r.suggestions || {},
    words: r.words,
    aiModel: r.ai_model,
    aiError: r.ai_error,
  }
}

export function fromRecord(rec) {
  return {
    status: rec.ocr_status,
    text: rec.ocr_text,
    quality: rec.ocr_quality,
    method: rec.ocr_method,
    confidence: rec.ocr_confidence,
    pages: rec.ocr_pages,
    language: rec.ocr_language,
    preprocessing: rec.ocr_preprocessing,
    suggestions: rec.ocr_suggestions || {},
    words: rec.ocr_words,
    aiModel: rec.ai_model,
    aiError: rec.ai_error,
    processedAt: rec.ocr_processed_at,
  }
}

// ---------------------------------------------------------------- controls

export function OcrLanguageSelect({ status, value, onChange, disabled }) {
  const installed = (status?.languages || []).filter((l) => l.installed)
  return (
    <label className="field ocr-lang">
      <span>Language written on the document</span>
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

// Per-document switch for AI checking, shown only when AI is switched on and ready.
export function AiToggle({ status, value, onChange, disabled }) {
  const ai = status?.ai
  if (!ai?.enabled) return null
  if (!ai.ready) {
    return <p className="ai-note muted small">AI checking is switched on but not set up yet. {ai.message}</p>
  }
  return (
    <label className="checkbox ai-note">
      <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} disabled={disabled} />
      <span>
        Also use AI to check the values against the page image.{' '}
        {ai.local ? (
          <>It runs on this computer, so nothing is sent outside. It can take up to about 10 minutes per page.</>
        ) : (
          <>
            <strong>The document is sent to an online AI service</strong>, so only use it for documents you are
            allowed to share.
          </>
        )}
      </span>
    </label>
  )
}

// Language + button (+ AI switch) to read a document. Collapsed into "Read again" once there is a result.
export function ReadControls({ status, lang, onLangChange, useAi, onUseAiChange, onRun, busy, runLabel, collapsed, children }) {
  const body = (
    <div className="read-controls">
      <div className="ocr-controls">
        <OcrLanguageSelect status={status} value={lang} onChange={onLangChange} disabled={busy} />
        <button type="button" className={`btn ${collapsed ? 'btn-ghost' : 'btn-primary'}`} onClick={onRun} disabled={busy}>
          {busy ? 'Reading…' : runLabel}
        </button>
      </div>
      <AiToggle status={status} value={useAi} onChange={onUseAiChange} disabled={busy} />
      {children}
    </div>
  )
  if (!collapsed) return body
  return (
    <details className="read-again">
      <summary>Read the document again (e.g. in a different language)</summary>
      {body}
    </details>
  )
}

// ---------------------------------------------------------------- progress

export function ReadingProgress({ status }) {
  return (
    <div className="x-progress" role="status">
      <span className="spinner" aria-hidden="true" />
      <div>
        <strong>{status === 'queued' ? 'Waiting to start reading…' : 'Reading the document…'}</strong>
        <div className="muted small">
          Usually 5 to 30 seconds per page (longer when AI checking is on). You can keep working; the results
          appear here by themselves.
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- how much was read

// How sure the text reader was about each word (its confidence, 0-100).
const WORD_BANDS = [
  { key: 'clear', min: 80, label: 'read clearly' },
  { key: 'unsure', min: 50, label: 'unsure' },
  { key: 'doubtful', min: -1, label: 'probably wrong' },
]

function band(conf) {
  return WORD_BANDS.find((b) => conf >= b.min).key
}

function wordStats(words) {
  if (!words?.length) return null
  const counts = { clear: 0, unsure: 0, doubtful: 0 }
  words.forEach(([, conf]) => {
    counts[band(conf)] += 1
  })
  const pct = (n) => Math.round((100 * n) / words.length)
  return {
    total: words.length,
    counts,
    pct: { clear: pct(counts.clear), unsure: pct(counts.unsure), doubtful: pct(counts.doubtful) },
  }
}

// Stacked bar: the share of words read clearly, uncertainly and probably wrongly.
function ReadingMeter({ stats }) {
  return (
    <div className="x-meter">
      <div className="x-meter-bar" role="img" aria-label={`${stats.pct.clear}% of the words read clearly`}>
        {WORD_BANDS.map((b) =>
          stats.counts[b.key] ? (
            <span key={b.key} className={`m-${b.key}`} style={{ width: `${(100 * stats.counts[b.key]) / stats.total}%` }} />
          ) : null,
        )}
      </div>
      <div className="x-meter-legend">
        {WORD_BANDS.map((b) => (
          <span key={b.key}>
            <i className={`dot m-${b.key}`} aria-hidden="true" /> <strong>{stats.pct[b.key]}%</strong> {b.label} (
            {stats.counts[b.key]})
          </span>
        ))}
        <span className="muted">of {stats.total} words</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- result

function summary(result, count, highCount, stats) {
  if (!result.text?.trim()) {
    return {
      tone: 'poor', icon: '!', title: 'No text was found on this document',
      body: 'The page may be blank, a photo or too faint. Check that the right file was uploaded, or type the details in yourself.',
    }
  }
  if (result.method === 'ai_vision') {
    return {
      tone: 'ai', icon: 'AI', title: 'This page was read by AI from the image',
      body: 'It is probably handwritten, and handwriting is hard to read: compare every detail with the document.',
    }
  }
  if (result.quality === 'poor') {
    return {
      tone: 'fair', icon: '!',
      title: stats ? `Handwritten or unclear page: ${stats.pct.clear}% of the words read clearly` : 'Handwritten or unclear page',
      body: 'The text reader is made for printed text, so it reads handwriting only partly. The words it read are shown below, coloured by how sure it is. Use them as a guide and type the details in from the document.',
    }
  }
  if (count === 0) {
    return {
      tone: 'fair', icon: '?', title: 'Text was read, but no details were recognised',
      body: 'The labels the system looks for (such as “खसरा संख्या” or “Village”) were not found. Look at the text read and fill in the form yourself.',
    }
  }
  const toCheck = count - highCount
  const found = `${count} detail${count === 1 ? '' : 's'} found`
  if (result.quality === 'fair') {
    return {
      tone: 'fair', icon: '!', title: `${found}, but the text was only partly clear`,
      body: 'Compare every value with the document before using it.',
    }
  }
  return {
    tone: 'good', icon: '✓',
    title: toCheck ? `${found}: ${highCount} look right, ${toCheck} need a check` : `${found}: all look right`,
    body: 'Tick the details you want, then copy them into the form. Always glance at the document before saving.',
  }
}

// The text read, each word coloured by how sure the reader was; words used for a detail are marked.
function ReadText({ text, words, suggestions }) {
  const lines = useMemo(() => {
    const used = new Set()
    Object.values(suggestions || {}).forEach((s) =>
      (s.value || '').split(/\s+/).forEach((t) => t.length > 1 && used.add(t)),
    )
    let next = 0 // `words` follow the text in reading order; page headings etc. have no entry
    return text.split('\n').map((line) =>
      line.split(/(\s+)/).map((token) => {
        if (!token.trim()) return { token }
        let conf = null
        for (let k = next; k < Math.min(next + 6, words?.length || 0); k += 1) {
          if (words[k][0] === token) {
            conf = words[k][1]
            next = k + 1
            break
          }
        }
        return { token, conf, band: conf === null ? null : band(conf), used: used.has(token) }
      }),
    )
  }, [text, words, suggestions])

  return (
    <pre className="x-text">
      {lines.map((parts, i) => (
        <span key={i}>
          {parts.map((p, j) =>
            p.band || p.used ? (
              <span
                key={j}
                className={[p.band && `w-${p.band}`, p.used && 'w-used'].filter(Boolean).join(' ')}
                title={p.conf === null ? undefined : `${Math.round(p.conf)}% sure`}
              >
                {p.token}
              </span>
            ) : (
              p.token
            ),
          )}
          {'\n'}
        </span>
      ))}
    </pre>
  )
}

function FullText({ result }) {
  const [copied, setCopied] = useState(false)
  const hasDetails = Object.keys(result.suggestions || {}).length > 0
  function copy() {
    navigator.clipboard?.writeText(result.text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  return (
    <div>
      <div className="x-text-head">
        <span className="muted small">
          {result.words?.length > 0 && (
            <>
              <span className="w-clear">read clearly</span> · <span className="w-unsure">unsure</span> ·{' '}
              <span className="w-doubtful">probably wrong</span>
              {hasDetails && (
                <>
                  {' '}· <span className="w-used">used for a detail</span>
                </>
              )}
              . Point at a word to see how sure the reader was.
            </>
          )}
        </span>
        <button type="button" className="btn btn-ghost btn-sm" onClick={copy}>
          {copied ? 'Copied ✓' : 'Copy text'}
        </button>
      </div>
      <ReadText text={result.text} words={result.words} suggestions={result.suggestions} />
    </div>
  )
}

function isEmpty(field, current) {
  const v = current?.[field]
  if (field === 'document_type') return !v || v === 'Other'
  return v === '' || v === null || v === undefined
}

function sameValue(a, b) {
  return String(a ?? '').trim().toLowerCase() === String(b ?? '').trim().toLowerCase()
}

function DetailRow({ field, s, current, checked, onToggle }) {
  const [open, setOpen] = useState(false)
  const certainty = CERTAINTY[s.level] || CERTAINTY.low
  const now = isEmpty(field, current) ? null : current[field]
  const differs = now !== null && !sameValue(now, s.value)
  const alreadySame = now !== null && !differs
  return (
    <li className={`x-row x-${s.level} ${checked ? 'x-checked' : ''}`}>
      <label className="x-pick">
        <input type="checkbox" checked={checked} onChange={onToggle} disabled={alreadySame} aria-label={`Use ${FIELD_LABELS[field]}`} />
      </label>
      <div className="x-main">
        <div className="x-field">{FIELD_LABELS[field]}</div>
        <div className="x-value">{s.value}</div>
        <div className="x-reason">{s.reasons?.[0]}</div>
        {s.alternatives?.map((a) => (
          <div key={a.value} className="x-alt">
            Another reading of the document: <strong>{a.value}</strong>
          </div>
        ))}
        {differs && (
          <div className="x-current">
            The record now has <strong>{now}</strong>{checked ? ': it will be replaced.' : '.'}
          </div>
        )}
        {alreadySame && <div className="x-current x-same">Already in the record ✓</div>}
        {open && (
          <ul className="x-why">
            {s.reasons?.map((r) => (
              <li key={r}>{r}</li>
            ))}
            <li>
              Read from: <span className="x-source">“{s.source}”</span>
            </li>
          </ul>
        )}
      </div>
      <div className="x-side">
        <span className={`x-pill x-pill-${s.level}`} title={certainty.hint}>
          {certainty.label}
        </span>
        <span className="x-score" title="Confidence score (0-100)">{s.confidence}/100</span>
        <button type="button" className="link-btn small" onClick={() => setOpen((v) => !v)}>
          {open ? 'Less' : 'How was this found?'}
        </button>
      </div>
    </li>
  )
}

function Details({ suggestions, current, onApply, applyLabel }) {
  const keys = Object.keys(FIELD_LABELS).filter((k) => suggestions?.[k])
  const missing = Object.keys(FIELD_LABELS).filter((k) => !suggestions?.[k] && k !== 'document_type')
  const [selected, setSelected] = useState({})
  const [applied, setApplied] = useState(0)

  useEffect(() => {
    const initial = {}
    keys.forEach((k) => {
      initial[k] = isEmpty(k, current) && suggestions[k].level !== 'low'
    })
    setSelected(initial)
    setApplied(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggestions])

  const count = keys.filter((k) => selected[k]).length

  function apply() {
    const values = {}
    keys.forEach((k) => {
      if (selected[k]) values[k] = suggestions[k].value
    })
    onApply(values)
    setApplied(count)
  }

  function selectAll() {
    setSelected(Object.fromEntries(keys.map((k) => [k, true])))
  }

  return (
    <div className="x-details">
      <div className="x-toolbar">
        <span className="muted small">
          Tick the details to copy. “Unsure” ones are not ticked for you.
        </span>
        <span className="x-toolbar-actions">
          <button type="button" className="link-btn small" onClick={selectAll}>Tick all</button>
          <button type="button" className="link-btn small" onClick={() => setSelected({})}>Untick all</button>
        </span>
      </div>
      <ul className="x-list">
        {keys.map((k) => (
          <DetailRow
            key={k}
            field={k}
            s={suggestions[k]}
            current={current}
            checked={!!selected[k]}
            onToggle={() => setSelected({ ...selected, [k]: !selected[k] })}
          />
        ))}
      </ul>
      {missing.length > 0 && (
        <p className="x-missing">
          <strong>Not found in the text:</strong> {missing.map((k) => FIELD_LABELS[k]).join(', ')}. Fill these in
          yourself if they are on the document.
        </p>
      )}
      <div className="x-apply">
        <button type="button" className="btn btn-primary" onClick={apply} disabled={!count}>
          {count ? `${applyLabel} (${count})` : 'Tick details to copy'}
        </button>
        {applied > 0 && (
          <span className="x-applied">
            ✓ {applied} detail{applied === 1 ? '' : 's'} copied. Check them in the form before saving.
          </span>
        )}
      </div>
    </div>
  )
}

function TechnicalDetails({ result }) {
  return (
    <details className="x-tech">
      <summary>Technical details</summary>
      <dl>
        <dt>How it was read</dt>
        <dd>{METHOD_LABEL[result.method] || result.method}</dd>
        {result.language && (
          <>
            <dt>Languages</dt>
            <dd>
              {languageNames(result.language)} <span className="muted">({result.language})</span>
            </dd>
          </>
        )}
        <dt>Reading confidence</dt>
        <dd>
          {result.confidence === null || result.confidence === undefined
            ? 'not applicable (exact PDF text)'
            : `${result.confidence}% average over all words`}
        </dd>
        {result.preprocessing && result.preprocessing !== 'basic' && (
          <>
            <dt>Image clean-up</dt>
            <dd>{result.preprocessing}</dd>
          </>
        )}
        <dt>AI checking</dt>
        <dd>{result.aiModel ? 'used' : 'not used'}</dd>
        {result.processedAt && (
          <>
            <dt>Read on</dt>
            <dd>{formatDate(result.processedAt)}</dd>
          </>
        )}
      </dl>
    </details>
  )
}

function DocumentView({ url, isPdf }) {
  return isPdf ? <iframe src={url} title="Document" className="x-doc" /> : <img src={url} alt="Document" className="x-doc" />
}

/**
 * Everything read from a document: a plain-language verdict with how much of the text was read
 * clearly, the details found (to copy into the form), the text itself and a side-by-side view.
 */
export function ExtractionResult({ result, current, onApply, applyLabel = 'Copy into the form', documentUrl, documentIsPdf }) {
  const suggestions = result.suggestions || {}
  const count = Object.keys(suggestions).length
  const highCount = Object.values(suggestions).filter((s) => s.level === 'high').length
  const stats = result.method === 'ai_vision' ? null : wordStats(result.words)
  const s = summary(result, count, highCount, stats)
  const hasText = !!result.text?.trim()
  const defaultTab = count ? 'details' : 'text'
  const [tab, setTab] = useState(defaultTab)

  useEffect(() => {
    setTab(defaultTab)
  }, [defaultTab, result.text])

  const tabs = [
    count > 0 && ['details', `Details found (${count})`],
    hasText && ['text', 'Text read'],
    hasText && documentUrl && ['compare', 'Side by side with document'],
  ].filter(Boolean)

  const facts = [
    result.pages && `${result.pages} page${result.pages === 1 ? '' : 's'} read${
      result.totalPages && result.totalPages > result.pages ? ` (of ${result.totalPages}; page limit reached)` : ''
    }`,
    result.language && languageNames(result.language),
  ].filter(Boolean)

  return (
    <div className="x-result">
      <div className={`x-summary x-summary-${s.tone}`}>
        <span className="x-icon" aria-hidden="true">{s.icon}</span>
        <div className="x-summary-main">
          <div className="x-title">{s.title}</div>
          <div className="x-body">{s.body}</div>
          {stats && <ReadingMeter stats={stats} />}
          {facts.length > 0 && <div className="x-facts">{facts.join(' · ')}</div>}
        </div>
      </div>

      {result.aiError && (
        <p className="x-note">AI checking did not work this time ({result.aiError}), so only the normal text reading was used.</p>
      )}

      {tabs.length > 0 && (
        <>
          <div className="x-tabs" role="tablist">
            {tabs.map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                className={`x-tab ${tab === key ? 'active' : ''}`}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="x-panel">
            {tab === 'details' && count > 0 && (
              <Details suggestions={suggestions} current={current} onApply={onApply} applyLabel={applyLabel} />
            )}
            {tab === 'text' && hasText && <FullText result={result} />}
            {tab === 'compare' && hasText && documentUrl && (
              <div className="x-compare">
                <DocumentView url={documentUrl} isPdf={documentIsPdf} />
                <ReadText text={result.text} words={result.words} suggestions={suggestions} />
              </div>
            )}
          </div>
        </>
      )}

      <TechnicalDetails result={result} />
    </div>
  )
}
