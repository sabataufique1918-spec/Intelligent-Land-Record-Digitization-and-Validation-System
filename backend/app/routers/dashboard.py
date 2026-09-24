from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import LandRecord
from ..schemas import VALIDATION_STATUSES, RecordOut
from ..services import ai_extraction, conflicts, ocr
from ..services.pipeline import pipeline_status

router = APIRouter(prefix="/api", tags=["dashboard"])


def _grouped(db: Session, column):
    rows = db.execute(
        select(column, func.count()).group_by(column).order_by(func.count().desc())
    ).all()
    return [{"label": label or "Unspecified", "count": count} for label, count in rows]


@router.get("/dashboard/summary")
def summary(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(LandRecord.id))) or 0
    with_docs = db.scalar(
        select(func.count(LandRecord.id)).where(LandRecord.stored_filename.is_not(None))
    ) or 0
    status_counts = dict(
        db.execute(
            select(LandRecord.validation_status, func.count()).group_by(LandRecord.validation_status)
        ).all()
    )
    recent = db.scalars(
        select(LandRecord).order_by(LandRecord.created_at.desc(), LandRecord.id.desc()).limit(6)
    ).all()

    return {
        "total_records": total,
        "documents_uploaded": with_docs,
        "status_counts": {s: status_counts.get(s, 0) for s in VALIDATION_STATUSES},
        "by_district": _grouped(db, LandRecord.district),
        "by_document_type": _grouped(db, LandRecord.document_type),
        "recent_records": [RecordOut.model_validate(r) for r in recent],
        "ocr_completed": db.scalar(
            select(func.count(LandRecord.id)).where(LandRecord.ocr_status == "completed")
        ) or 0,
        "open_conflicts": sum(1 for c in conflicts.detect_all(db) if not c["dismissed"]),
        "pipeline": pipeline_status(ocr.status()["available"], ai_extraction.AI_EXTRACTION_ENABLED),
    }
