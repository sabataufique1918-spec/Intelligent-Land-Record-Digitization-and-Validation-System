"""Learning from officer corrections.

1. Field feedback: whenever a record with OCR suggestions is uploaded, edited or verified,
   each suggested value is compared with the value the officer saved (accepted / corrected).
   This gives the real accuracy of extraction on this office's documents.
2. Learned corrections: if officers corrected the same suggested value to the same final value
   at least MIN_CORRECTIONS times (and accepted it less often), later suggestions of that value
   are replaced automatically, with an explanation.
3. Line transcriptions (see services/training_lines.py) are the data for fine-tuning OCR.

Nothing here retrains a neural network by itself; fine-tuning Tesseract on exported lines is a
separate offline step (see backend/scripts/FINE_TUNING.md).
"""

import time
from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FieldFeedback, LandRecord
from .confidence import FIELDS, _norm, values_agree

MIN_CORRECTIONS = 2
_CACHE: dict = {"at": 0.0, "map": {}}
_CACHE_SECONDS = 20


def _value(record: LandRecord, field: str) -> str | None:
    value = getattr(record, field, None)
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def record_feedback(db: Session, record: LandRecord, event: str) -> int:
    """Store suggested-vs-final for every suggested field of this record. Returns rows written."""
    if record.ocr_status != "completed" or not record.ocr_text:
        return 0
    suggestions = record.ocr_suggestions
    if not suggestions:
        return 0
    existing = {f.field: f for f in db.scalars(select(FieldFeedback).where(FieldFeedback.record_id == record.id))}
    written = 0
    for field, s in suggestions.items():
        if field not in FIELDS:
            continue
        final = _value(record, field)
        accepted = final is not None and values_agree(field, s["value"], final)
        row = existing.get(field) or FieldFeedback(record_id=record.id, field=field)
        row.suggested_value = s["value"][:300]
        row.suggested_sources = "+".join(s.get("sources") or [])[:40]
        row.suggested_confidence = s.get("confidence")
        row.final_value = final[:300] if final else None
        row.accepted = accepted
        row.ocr_quality = record.ocr_quality
        row.event = event
        db.add(row)
        written += 1
    _CACHE["at"] = 0.0  # new evidence: rebuild learned corrections
    return written


def learned_corrections(db: Session) -> dict[tuple[str, str], dict]:
    """{(field, normalised wrong value): {"value": correct value, "count": n}}"""
    if time.time() - _CACHE["at"] < _CACHE_SECONDS:
        return _CACHE["map"]
    corrections: dict[tuple[str, str], Counter] = defaultdict(Counter)
    accepted: Counter = Counter()
    for row in db.scalars(select(FieldFeedback)):
        key = (row.field, _norm(row.suggested_value))
        if row.accepted:
            accepted[key] += 1
        elif row.final_value:
            corrections[key][row.final_value] += 1
    learned = {}
    for key, finals in corrections.items():
        value, count = finals.most_common(1)[0]
        if count >= MIN_CORRECTIONS and count > accepted[key]:
            learned[key] = {"value": value, "count": count}
    _CACHE.update(at=time.time(), map=learned)
    return learned


def apply_learned(suggestions: dict[str, dict], learned: dict | None) -> dict[str, dict]:
    if not learned:
        return suggestions
    for field, s in suggestions.items():
        hit = learned.get((field, _norm(s["value"])))
        if not hit or _norm(hit["value"]) == _norm(s["value"]):
            continue
        original = s["value"]
        s["value"] = hit["value"]
        s["sources"] = list(s.get("sources") or []) + ["learned"]
        s["confidence"] = max(s["confidence"], min(95, 60 + 10 * hit["count"]))
        s["level"] = "high" if s["confidence"] >= 80 else "medium" if s["confidence"] >= 55 else "low"
        s["reasons"] = list(s.get("reasons") or []) + [
            f"Changed from “{original}”: officers made this same correction {hit['count']} times"]
        s["alternatives"] = list(s.get("alternatives") or []) + [
            {"value": original, "method": "ocr (before learned correction)", "confidence": None}]
    return suggestions


def accuracy_stats(db: Session) -> dict:
    rows = db.scalars(select(FieldFeedback)).all()

    def rate(subset):
        n = len(subset)
        ok = sum(1 for r in subset if r.accepted)
        return {"checked": n, "accepted": ok, "accuracy": round(ok / n * 100, 1) if n else None}

    by_field = defaultdict(list)
    by_source = defaultdict(list)
    by_quality = defaultdict(list)
    for r in rows:
        by_field[r.field].append(r)
        by_source[r.suggested_sources or "unknown"].append(r)
        by_quality[r.ocr_quality or "unknown"].append(r)
    worst = Counter((r.field, r.suggested_value, r.final_value) for r in rows if not r.accepted and r.final_value)
    return {
        "overall": rate(rows),
        "records": len({r.record_id for r in rows}),
        "by_field": {k: rate(v) for k, v in sorted(by_field.items())},
        "by_source": {k: rate(v) for k, v in sorted(by_source.items())},
        "by_quality": {k: rate(v) for k, v in sorted(by_quality.items())},
        "frequent_corrections": [
            {"field": f, "suggested": s, "corrected_to": c, "times": n} for (f, s, c), n in worst.most_common(15)
        ],
        "learned": [{"field": f, "wrong": w, "correct": v["value"], "times": v["count"]}
                    for (f, w), v in learned_corrections(db).items()],
    }
