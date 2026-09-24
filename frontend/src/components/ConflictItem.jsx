import { useState } from 'react'
import { formatDate } from '../utils.js'

// One detected conflict with the officer's "not a conflict" / "restore" actions.
export default function ConflictItem({ conflict, onDismiss, onRestore, extra }) {
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState('')
  const [reviewer, setReviewer] = useState('Officer')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const d = conflict.details || {}

  async function act(fn) {
    setBusy(true)
    setError('')
    try {
      await fn()
      setOpen(false)
      setNote('')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className={`conflict conflict-${conflict.dismissed ? 'dismissed' : conflict.severity}`}>
      <div className="conflict-head">
        <span className="conflict-label">{conflict.label}</span>
        <span className={`sev sev-${conflict.severity}`}>{conflict.severity}</span>
        {conflict.dismissed && <span className="sev sev-dismissed">not a conflict</span>}
      </div>
      <p className="conflict-msg">{conflict.message}</p>
      {(d.match || d.notes?.length > 0) && (
        <p className="muted small">
          {d.match && <>Owner name match: {d.match}. </>}
          {d.notes?.length > 0 && <>{d.notes.join('; ')}.</>}
        </p>
      )}
      {extra}
      {conflict.dismissed && conflict.review && (
        <p className="review-line small">
          Reviewed by <strong>{conflict.review.reviewed_by}</strong> on {formatDate(conflict.review.created_at)}
          {conflict.review.note && <> — “{conflict.review.note}”</>}
        </p>
      )}
      {error && <p className="error-text small">{error}</p>}

      {conflict.dismissed ? (
        onRestore && (
          <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => act(() => onRestore(conflict))}>
            Restore as open conflict
          </button>
        )
      ) : open ? (
        <div className="dismiss-form">
          <textarea
            rows={2}
            placeholder="Reason (e.g. sale deed registered, joint ownership, data entry corrected)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="Reviewer name" />
          <div className="actions-row compact">
            <button
              className="btn btn-primary btn-sm"
              disabled={busy}
              onClick={() => act(() => onDismiss(conflict, note, reviewer))}
            >
              Confirm: not a conflict
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        onDismiss && (
          <button className="btn btn-ghost btn-sm" onClick={() => setOpen(true)}>
            Mark as not a conflict…
          </button>
        )
      )}
    </li>
  )
}
