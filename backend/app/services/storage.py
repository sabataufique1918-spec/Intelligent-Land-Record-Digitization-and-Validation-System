import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from ..config import MAX_UPLOAD_BYTES, MAX_UPLOAD_MB, UPLOAD_DIR

ALLOWED = {
    ".pdf": ("pdf", "application/pdf"),
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
}

MAGIC = {
    "application/pdf": [b"%PDF"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff"],
}


async def read_upload(file: UploadFile) -> tuple[bytes, dict]:
    """Read and check an uploaded file. Returns its bytes and metadata (without storing it)."""
    original = Path(file.filename or "").name
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, "Only PDF, JPG, JPEG and PNG files are allowed.")
    file_type, mime = ALLOWED[ext]

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) == 0:
        raise HTTPException(400, "The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File is larger than {MAX_UPLOAD_MB} MB.")
    if not any(data.startswith(sig) for sig in MAGIC[mime]):
        raise HTTPException(400, "File content does not match its extension.")

    return data, {
        "original_filename": original,
        "file_sha256": hashlib.sha256(data).hexdigest(),
        "file_type": file_type,
        "mime_type": mime,
        "file_size": len(data),
        "extension": ext,
    }


async def save_upload(file: UploadFile) -> dict:
    data, meta = await read_upload(file)
    stored = f"{uuid.uuid4().hex}{meta.pop('extension')}"
    (UPLOAD_DIR / stored).write_bytes(data)
    return {**meta, "stored_filename": stored}


def file_path(stored_filename: str) -> Path:
    return UPLOAD_DIR / Path(stored_filename).name
