import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import OCRResult
from ..services import ai_extraction, ocr
from ..services.confidence import build_suggestions, overall_confidence
from ..services.learning import apply_learned, learned_corrections
from ..services.storage import read_upload

router = APIRouter(prefix="/api/ocr", tags=["ocr"])


@router.get("/status")
def ocr_status():
    return {**ocr.status(), "ai": ai_extraction.status()}


@router.post("/extract", response_model=OCRResult)
async def extract(
    file: UploadFile = File(...),
    language: str = Form("Hindi"),
    use_ai: bool = Form(True),
    db: Session = Depends(get_db),
):
    """Run OCR (and AI extraction if enabled) on a file without saving it, to pre-fill the upload form."""
    data, meta = await read_upload(file)
    fd, tmp = tempfile.mkstemp(suffix=meta["extension"])
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        result = await run_in_threadpool(ocr.run_ocr_cached, Path(tmp), meta["mime_type"], language)
        result = {**result, **await run_in_threadpool(ocr.run_ai, Path(tmp), meta["mime_type"], result, use_ai)}
    except ocr.OCRError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        os.unlink(tmp)

    suggestions = apply_learned(
        build_suggestions(result["text"], result["words"], result["method"], result["ai_fields"]),
        learned_corrections(db),
    )
    return {
        **result,
        "suggestions": suggestions,
        "extraction_confidence": overall_confidence(suggestions),
        "ai_used": result["ai_fields"] is not None,
    }
