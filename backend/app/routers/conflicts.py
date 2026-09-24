from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ConflictReview, LandRecord
from ..schemas import DismissConflict, RecordOut
from ..services import conflicts as engine
from ..services.validation import recheck_all, validate_with_related

router = APIRouter(prefix="/api", tags=["conflicts"])


def _summary(items: list[dict]) -> dict:
    open_items = [c for c in items if not c["dismissed"]]
    counts = Counter(c["type"] for c in open_items)
    return {
        "open": len(open_items),
        "dismissed": len(items) - len(open_items),
        "records_involved": len({i for c in open_items for i in c["record_ids"]}),
        "by_type": {t: counts.get(t, 0) for t in engine.CONFLICT_TYPES},
    }


@router.get("/conflicts")
def list_conflicts(
    type: str | None = None,
    include_dismissed: bool = False,
    db: Session = Depends(get_db),
):
    items = engine.detect_all(db)
    summary = _summary(items)
    if not include_dismissed:
        items = [c for c in items if not c["dismissed"]]
    if type:
        items = [c for c in items if c["type"] == type]

    ids = {i for c in items for i in c["record_ids"]}
    records = {r.id: r for r in db.scalars(select(LandRecord).where(LandRecord.id.in_(ids)))} if ids else {}
    rank = {"error": 0, "warning": 1, "info": 2}

    groups = []
    for group in engine.group_conflicts(items):
        group.sort(key=lambda c: (c["dismissed"], rank[c["severity"]], c["type"]))
        record_ids = sorted({i for c in group for i in c["record_ids"]})
        first = records[record_ids[0]]
        parcel_based = any(c["type"] != "DUPLICATE_DOCUMENT" for c in group)
        groups.append({
            "key": f"g{record_ids[0]}",
            "title": (
                f"Survey {first.survey_number} · {first.village}, {first.district}"
                if parcel_based else f"Same file: {first.original_filename}"
            ),
            "worst_severity": min((c["severity"] for c in group if not c["dismissed"]),
                                  key=rank.get, default="info"),
            "records": [RecordOut.model_validate(records[i]) for i in record_ids],
            "conflicts": group,
        })
    groups.sort(key=lambda g: (rank[g["worst_severity"]], g["title"]))
    return {"summary": summary, "types": engine.CONFLICT_TYPES, "groups": groups}


@router.get("/records/{record_id}/conflicts")
def record_conflicts(record_id: int, db: Session = Depends(get_db)):
    record = db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(404, "Record not found.")
    items = engine.for_record(db, record)
    other_ids = {i for c in items for i in c["record_ids"]} - {record_id}
    others = {r.id: r for r in db.scalars(select(LandRecord).where(LandRecord.id.in_(other_ids)))} if other_ids else {}
    for c in items:
        other = others[next(i for i in c["record_ids"] if i != record_id)]
        c["other_record"] = RecordOut.model_validate(other)
    return {"items": items}


def _load_pair(db: Session, key: str) -> tuple[str, LandRecord, LandRecord]:
    parsed = engine.parse_conflict_key(key)
    if not parsed:
        raise HTTPException(400, "Invalid conflict key.")
    conflict_type, a_id, b_id = parsed
    a, b = db.get(LandRecord, a_id), db.get(LandRecord, b_id)
    if not a or not b:
        raise HTTPException(404, "Record not found.")
    return conflict_type, a, b


@router.post("/conflicts/dismiss")
def dismiss(payload: DismissConflict, db: Session = Depends(get_db)):
    conflict_type, a, b = _load_pair(db, payload.key)
    if payload.key not in {c["key"] for c in engine.compare_pair(a, b)}:
        raise HTTPException(409, "This conflict no longer exists. Refresh the page.")
    review = db.scalar(select(ConflictReview).where(ConflictReview.conflict_key == payload.key))
    if review is None:
        review = ConflictReview(conflict_key=payload.key, conflict_type=conflict_type,
                                record_a_id=min(a.id, b.id), record_b_id=max(a.id, b.id))
        db.add(review)
    review.note = (payload.note or "").strip() or None
    review.reviewed_by = payload.reviewed_by.strip() or "Officer"
    db.flush()
    validate_with_related(db, a, keep_officer_decision=True)
    validate_with_related(db, b, keep_officer_decision=True)
    db.commit()
    return {"ok": True}


@router.delete("/conflicts/dismiss/{key}")
def restore(key: str, db: Session = Depends(get_db)):
    _conflict_type, a, b = _load_pair(db, key)
    review = db.scalar(select(ConflictReview).where(ConflictReview.conflict_key == key))
    if review is None:
        raise HTTPException(404, "This conflict was not dismissed.")
    db.delete(review)
    db.flush()
    validate_with_related(db, a, keep_officer_decision=True)
    validate_with_related(db, b, keep_officer_decision=True)
    db.commit()
    return {"ok": True}


@router.post("/conflicts/rescan")
def rescan(db: Session = Depends(get_db)):
    checked = recheck_all(db)
    return {"records_checked": checked, "summary": _summary(engine.detect_all(db))}
