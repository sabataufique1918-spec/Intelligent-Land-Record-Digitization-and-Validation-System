"""Background OCR jobs.

OCR of a scanned page takes seconds to minutes (more with AI reading), so uploading a document or
pressing "Run OCR" returns at once with ocr_status="queued". A small pool of worker threads
(OCR_WORKERS) reads the document and saves the result; the record page polls until the status is
no longer queued / processing.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import select

from ..config import OCR_WORKERS
from ..database import SessionLocal
from ..models import LandRecord
from . import ocr
from .learning import record_feedback
from .validation import validate_with_related

logger = logging.getLogger("uvicorn.error")

PENDING = ("queued", "processing")
_POOL = ThreadPoolExecutor(max_workers=OCR_WORKERS, thread_name_prefix="ocr")


def submit(record_id: int, language: str, use_ai: bool, after_upload: bool = False) -> None:
    """Queue OCR for a record whose ocr_status has already been set to "queued" and committed."""
    _POOL.submit(_run, record_id, language, use_ai, after_upload)


def _run(record_id: int, language: str, use_ai: bool, after_upload: bool) -> None:
    with SessionLocal() as db:
        record = db.get(LandRecord, record_id)
        if record is None:
            return
        try:
            record.ocr_status = "processing"
            db.commit()
            ocr.apply_to_record(record, language, use_ai)
            # A freshly uploaded record has no officer decision yet; a re-run keeps an existing one.
            validate_with_related(db, record, keep_officer_decision=not after_upload)
            if after_upload:
                record_feedback(db, record, "upload")
            db.commit()
        except Exception as exc:  # never leave a record stuck in "processing"
            logger.exception("OCR job for record %s failed", record_id)
            db.rollback()
            record = db.get(LandRecord, record_id)
            if record is not None:
                record.ocr_status = "failed"
                record.ocr_error = f"OCR failed unexpectedly: {exc}"
                record.ocr_processed_at = datetime.now(timezone.utc)
                db.commit()


def recover_interrupted(db) -> int:
    """Mark jobs that were queued or running when the server stopped as failed, so they can be re-run."""
    stuck = db.scalars(select(LandRecord).where(LandRecord.ocr_status.in_(PENDING))).all()
    for record in stuck:
        record.ocr_status = "failed"
        record.ocr_error = "OCR was interrupted by a server restart. Run it again."
    db.commit()
    return len(stuck)
