import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..schemas import OCRResult
from ..services import ai_extraction, ocr
from ..services.confidence import build_suggestions, overall_confidence
from ..services.storage import read_upload

router = APIRouter(prefix="/api/ocr", tags=["ocr"])


@router.get("/status")
def ocr_status():
    return {**ocr.status(), "ai": ai_extraction.status()}


@router.post("/extract", response_model=OCRResult)
async def extract(file: UploadFile = File(...), language: str = Form("Hindi"), use_ai: bool = Form(True)):
    """Run OCR (and AI extraction if enabled) on a file without saving it, to pre-fill the upload form."""
    data, meta = await read_upload(file)
    fd, tmp = tempfile.mkstemp(suffix=meta["extension"])
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        result = await run_in_threadpool(ocr.run_ocr_cached, Path(tmp), meta["mime_type"], language)
    except ocr.OCRError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        os.unlink(tmp)

    ai_fields = ai_model = ai_error = None
    if use_ai and ai_extraction.AI_EXTRACTION_ENABLED and result["text"].strip():
        try:
            ai = await run_in_threadpool(ai_extraction.extract, result["text"])
            ai_fields, ai_model = ai["fields"], ai["model"]
        except ai_extraction.AIExtractionError as exc:
            ai_error = str(exc)

    suggestions = build_suggestions(result["text"], result["words"], result["method"], ai_fields)
    return {
        **result,
        "suggestions": suggestions,
        "extraction_confidence": overall_confidence(suggestions),
        "ai_used": ai_fields is not None,
        "ai_model": ai_model,
        "ai_error": ai_error,
    }
