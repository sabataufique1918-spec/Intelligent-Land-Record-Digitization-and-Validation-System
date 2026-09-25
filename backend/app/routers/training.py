from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import LandRecord, TrainingLine
from ..services import learning, training_lines
from ..services.ocr import OCRError

router = APIRouter(prefix="/api", tags=["training"])


class LineUpdate(BaseModel):
    text: str | None = Field(default=None, max_length=2000)
    status: str = Field(default="verified", pattern="^(verified|skipped|pending)$")
    verified_by: str = Field(default="Officer", max_length=120)


class CutRequest(BaseModel):
    language: str | None = None


def _line_out(line: TrainingLine) -> dict:
    return {
        "id": line.id, "record_id": line.record_id, "page": line.page, "line_no": line.line_no,
        "image_url": f"/api/training/lines/{line.id}/image", "ocr_text": line.ocr_text,
        "ocr_confidence": line.ocr_confidence, "ground_truth": line.ground_truth, "status": line.status,
        "handwritten": line.handwritten, "verified_by": line.verified_by,
    }


@router.get("/training/stats")
def stats(db: Session = Depends(get_db)):
    return {"fields": learning.accuracy_stats(db), "lines": training_lines.training_stats(db)}


@router.get("/records/{record_id}/lines")
def list_lines(record_id: int, db: Session = Depends(get_db)):
    lines = db.scalars(select(TrainingLine).where(TrainingLine.record_id == record_id)
                       .order_by(TrainingLine.page, TrainingLine.line_no)).all()
    return {"items": [_line_out(line) for line in lines]}


@router.post("/records/{record_id}/lines")
async def cut_lines(record_id: int, payload: CutRequest, db: Session = Depends(get_db)):
    record = db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(404, "Record not found.")
    try:
        lines = await run_in_threadpool(training_lines.create_lines, db, record, payload.language)
    except (ValueError, OCRError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"items": [_line_out(line) for line in lines]}


@router.get("/training/lines/{line_id}/image")
def line_image(line_id: int, db: Session = Depends(get_db)):
    line = db.get(TrainingLine, line_id)
    if not line or not training_lines.line_image_path(line).exists():
        raise HTTPException(404, "Line image not found.")
    return FileResponse(training_lines.line_image_path(line), media_type="image/png")


@router.put("/training/lines/{line_id}")
def update_line(line_id: int, payload: LineUpdate, db: Session = Depends(get_db)):
    line = db.get(TrainingLine, line_id)
    if not line:
        raise HTTPException(404, "Line not found.")
    if payload.status == "verified":
        text = (payload.text or "").strip()
        if not text:
            raise HTTPException(400, "Type the correct text of the line, or skip it.")
        line.ground_truth = text
        line.verified_by = payload.verified_by.strip() or "Officer"
    line.status = payload.status
    db.commit()
    return _line_out(line)


@router.get("/training/export")
def export(db: Session = Depends(get_db)):
    data = training_lines.export_zip(db)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="ocr_training_ground_truth.zip"'})
