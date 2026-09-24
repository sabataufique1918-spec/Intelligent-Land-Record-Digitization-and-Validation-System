from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import LandRecord
from ..schemas import (
    AREA_UNITS,
    DOCUMENT_TYPES,
    VALIDATION_STATUSES,
    RecordDetailOut,
    RecordOut,
    RecordPage,
    RecordUpdate,
    StatusUpdate,
)
from ..services import ocr
from ..services.storage import file_path, save_upload
from ..services.validation import validate_with_related

router = APIRouter(prefix="/api", tags=["records"])


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def assign_record_number(record: LandRecord) -> None:
    year = (record.created_at or datetime.now(timezone.utc)).year
    record.record_number = f"LR-{year}-{record.id:05d}"


def get_record_or_404(db: Session, record_id: int) -> LandRecord:
    record = db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(404, "Record not found.")
    return record


@router.get("/meta/options")
def options(db: Session = Depends(get_db)):
    districts = db.scalars(
        select(LandRecord.district).where(LandRecord.district.is_not(None)).distinct().order_by(LandRecord.district)
    ).all()
    return {
        "document_types": DOCUMENT_TYPES,
        "area_units": AREA_UNITS,
        "validation_statuses": VALIDATION_STATUSES,
        "districts": districts,
    }


@router.get("/records", response_model=RecordPage)
def list_records(
    q: str | None = Query(None, description="Search owner, survey no, khata no, village, record no"),
    status: str | None = None,
    district: str | None = None,
    document_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = select(LandRecord)
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(LandRecord.owner_name).like(term),
                func.lower(LandRecord.father_name).like(term),
                func.lower(LandRecord.previous_owner).like(term),
                func.lower(LandRecord.survey_number).like(term),
                func.lower(LandRecord.khata_number).like(term),
                func.lower(LandRecord.village).like(term),
                func.lower(LandRecord.tehsil).like(term),
                func.lower(LandRecord.record_number).like(term),
                func.lower(LandRecord.original_filename).like(term),
                func.lower(LandRecord.ocr_text).like(term),
            )
        )
    if status:
        stmt = stmt.where(LandRecord.validation_status == status)
    if district:
        stmt = stmt.where(LandRecord.district == district)
    if document_type:
        stmt = stmt.where(LandRecord.document_type == document_type)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.order_by(LandRecord.created_at.desc(), LandRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/records/{record_id}", response_model=RecordDetailOut)
def get_record(record_id: int, db: Session = Depends(get_db)):
    return get_record_or_404(db, record_id)


@router.post("/records/upload", response_model=RecordDetailOut, status_code=201)
async def upload_record(
    file: UploadFile = File(...),
    document_type: str = Form("Other"),
    owner_name: str | None = Form(None),
    father_name: str | None = Form(None),
    document_date: date | None = Form(None),
    previous_owner: str | None = Form(None),
    survey_number: str | None = Form(None),
    khata_number: str | None = Form(None),
    village: str | None = Form(None),
    tehsil: str | None = Form(None),
    district: str | None = Form(None),
    state: str | None = Form(None),
    area_value: float | None = Form(None),
    area_unit: str | None = Form(None),
    language: str | None = Form(None),
    remarks: str | None = Form(None),
    run_ocr: bool = Form(False),
    ocr_language: str | None = Form(None),
    use_ai: bool = Form(True),
    db: Session = Depends(get_db),
):
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(400, "Unknown document type.")
    stored = await save_upload(file)

    record = LandRecord(
        document_type=document_type,
        owner_name=_clean(owner_name),
        father_name=_clean(father_name),
        document_date=document_date,
        previous_owner=_clean(previous_owner),
        survey_number=_clean(survey_number),
        khata_number=_clean(khata_number),
        village=_clean(village),
        tehsil=_clean(tehsil),
        district=_clean(district),
        state=_clean(state),
        area_value=area_value,
        area_unit=_clean(area_unit),
        language=_clean(language),
        remarks=_clean(remarks),
        ocr_status="not_run",
        **stored,
    )
    db.add(record)
    db.flush()
    assign_record_number(record)
    if run_ocr:
        await run_in_threadpool(ocr.apply_to_record, record, ocr_language or language or "English", use_ai)
    validate_with_related(db, record, keep_officer_decision=False)
    db.commit()
    db.refresh(record)
    return record


@router.patch("/records/{record_id}", response_model=RecordDetailOut)
def update_record(record_id: int, payload: RecordUpdate, db: Session = Depends(get_db)):
    record = get_record_or_404(db, record_id)
    data = payload.model_dump(exclude_unset=True)
    if "document_type" in data and data["document_type"] not in DOCUMENT_TYPES:
        raise HTTPException(400, "Unknown document type.")
    for key, value in data.items():
        setattr(record, key, _clean(value) if isinstance(value, str) else value)
    # Data changed, so any previous officer decision no longer applies.
    record.reviewed_by = record.review_note = record.reviewed_at = None
    validate_with_related(db, record, keep_officer_decision=False)
    db.commit()
    db.refresh(record)
    return record


@router.post("/records/{record_id}/validate", response_model=RecordDetailOut)
def revalidate(record_id: int, db: Session = Depends(get_db)):
    record = get_record_or_404(db, record_id)
    validate_with_related(db, record, keep_officer_decision=True)
    db.commit()
    db.refresh(record)
    return record


@router.patch("/records/{record_id}/status", response_model=RecordDetailOut)
def set_status(record_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    record = get_record_or_404(db, record_id)
    if payload.status == "pending":
        # Send back to the queue: recompute automated status.
        record.reviewed_by = record.review_note = record.reviewed_at = None
        record.validation_status = "pending"  # so a previously rejected record takes part in conflict checks
        validate_with_related(db, record, keep_officer_decision=False)
    else:
        record.validation_status = payload.status
        record.reviewed_by = _clean(payload.reviewed_by) or "Officer"
        record.review_note = _clean(payload.note)
        record.reviewed_at = datetime.now(timezone.utc)
        # A rejected record no longer takes part in conflicts; refresh it and its related records.
        validate_with_related(db, record, keep_officer_decision=True)
    db.commit()
    db.refresh(record)
    return record


class OCRRequest(BaseModel):
    language: str | None = None
    use_ai: bool = True


@router.post("/records/{record_id}/ocr", response_model=RecordDetailOut)
async def run_record_ocr(record_id: int, payload: OCRRequest, db: Session = Depends(get_db)):
    record = get_record_or_404(db, record_id)
    if not record.stored_filename:
        raise HTTPException(400, "This record has no document to read.")
    await run_in_threadpool(ocr.apply_to_record, record, payload.language or record.language or "English",
                            payload.use_ai)
    validate_with_related(db, record, keep_officer_decision=True)
    db.commit()
    db.refresh(record)
    return record


@router.get("/records/{record_id}/file")
def get_file(record_id: int, download: bool = False, db: Session = Depends(get_db)):
    record = get_record_or_404(db, record_id)
    if not record.stored_filename:
        raise HTTPException(404, "No document attached to this record.")
    path = file_path(record.stored_filename)
    if not path.exists():
        raise HTTPException(404, "Stored file is missing on the server.")
    return FileResponse(
        path,
        media_type=record.mime_type,
        filename=record.original_filename if download else None,
        content_disposition_type="attachment" if download else "inline",
    )
