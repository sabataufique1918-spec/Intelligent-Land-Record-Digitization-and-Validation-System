"""Cutting document pages into text-line images for transcription and OCR fine-tuning.

Lines are found with a horizontal projection profile on the cleaned-up page (works for printed
and handwritten lines that are roughly horizontal). Each line image gets Tesseract's current guess,
which the officer corrects. Verified lines are exported as tesstrain ground truth:
    <name>.png  +  <name>.gt.txt   (one line of text)
"""

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR
from ..models import LandRecord, TrainingLine
from . import ocr
from .image_enhance import estimate_skew, normalize_background, remove_table_lines, rotate, to_gray_array, upscale
from .storage import file_path

LINES_DIR = UPLOAD_DIR / "training_lines"
MIN_LINE_HEIGHT = 18
MAX_LINES_PER_PAGE = 60
PADDING = 8


def _segment_lines(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Return (x, y, w, h) boxes of text lines using a horizontal ink profile."""
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))  # drop specks
    h, w = ink.shape
    # Remove long rules (table lines, underlines) so they do not merge lines.
    rules = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, w // 6), 1)))
    ink = cv2.subtract(ink, rules)
    profile = ink.sum(axis=1) / 255
    threshold = max(3, 0.015 * w)
    rows = profile > threshold
    boxes, start = [], None
    for y, on in enumerate(list(rows) + [False]):
        if on and start is None:
            start = y
        elif not on and start is not None:
            if y - start >= MIN_LINE_HEIGHT:
                band = ink[start:y]
                cols = np.where(band.sum(axis=0) > 0)[0]
                if len(cols):
                    x0, x1 = int(cols[0]), int(cols[-1])
                    boxes.append((max(0, x0 - PADDING), max(0, start - PADDING),
                                  min(w, x1 + PADDING) - max(0, x0 - PADDING),
                                  min(h, y + PADDING) - max(0, start - PADDING)))
            start = None
    boxes = _split_columns(ink, _split_tall(ink, boxes))
    # Drop page-edge strips and fold marks: text lines are wider than they are tall.
    boxes = [b for b in boxes if b[2] >= 1.2 * b[3] and b[2] >= 3 * MIN_LINE_HEIGHT]
    # Whatever is still far taller than a line after splitting is a stamp, photo or seal, not text.
    if len(boxes) >= 3:
        typical = float(np.median([b[3] for b in boxes]))
        boxes = [b for b in boxes if b[3] <= 3 * typical]
    return boxes[:MAX_LINES_PER_PAGE]


def _split_tall(ink: np.ndarray, boxes: list) -> list:
    """Split boxes that contain several tightly spaced lines, cutting at the lowest-ink rows."""
    if len(boxes) < 3:
        return boxes
    typical = float(np.median([b[3] for b in boxes]))
    out = []
    for x, y, w, h in boxes:
        n = round(h / typical)
        if h < 1.6 * typical or n < 2:
            out.append((x, y, w, h))
            continue
        profile = ink[y:y + h, x:x + w].sum(axis=1).astype(float)
        busy = float(np.percentile(profile, 75)) or 1.0
        cuts, step = [], h / n
        for k in range(1, n):
            lo, hi = int(step * k - step * 0.35), int(step * k + step * 0.35)
            cut = lo + int(np.argmin(profile[lo:hi]))
            if profile[cut] < 0.25 * busy:  # only cut where there is a real gap (not inside big letters)
                cuts.append(cut)
        edges = [0] + cuts + [h]
        # Devanagari vowel marks above the headline leave a thin, almost empty band: never cut off a
        # piece much shorter than a normal line.
        if min(b - a for a, b in zip(edges, edges[1:])) < 0.7 * typical:
            out.append((x, y, w, h))
            continue
        for a, b in zip(edges, edges[1:]):
            out.append((x, y + a, w, b - a))
    return out


def _split_columns(ink: np.ndarray, boxes: list, min_gap_ratio: float = 0.06) -> list:
    """Split a line box into separate pieces where there is a wide empty vertical gap (two columns)."""
    out = []
    width = ink.shape[1]
    for x, y, w, h in boxes:
        cols = ink[y:y + h, x:x + w].sum(axis=0) > 0
        pieces, start, gap = [], None, 0
        for i, on in enumerate(list(cols) + [False] * int(width * min_gap_ratio + 1)):
            if on:
                if start is None:
                    start = i
                gap = 0
            elif start is not None:
                gap += 1
                if gap > width * min_gap_ratio:
                    pieces.append((start, i - gap + 1))
                    start, gap = None, 0
        if len(pieces) <= 1:
            out.append((x, y, w, h))
            continue
        for a, b in pieces:
            if b - a > 2 * MIN_LINE_HEIGHT:
                out.append((max(0, x + a - PADDING), y, min(w - a, b - a + 2 * PADDING), h))
    return out


def _guess(image: Image.Image, lang: str) -> tuple[str, float | None]:
    # Tesseract reads single lines better with a white margin and letters at least ~40 px high.
    if image.height < 60:
        f = 60 / image.height
        image = image.resize((int(image.width * f), 60), Image.LANCZOS)
    framed = Image.new("L", (image.width + 40, image.height + 40), 255)
    framed.paste(image.convert("L"), (20, 20))
    data = pytesseract.image_to_data(framed, lang=lang, config="--oem 1 --psm 7",
                                     output_type=pytesseract.Output.DICT, timeout=60)
    words = [(w.strip(), float(c)) for w, c in zip(data["text"], data["conf"]) if w.strip() and float(c) >= 0]
    text = " ".join(w for w, _ in words)
    conf = round(sum(c for _, c in words) / len(words), 1) if words else None
    return text, conf


def create_lines(db: Session, record: LandRecord, language: str | None) -> list[TrainingLine]:
    """Cut the record's pages into lines (once) and store them with Tesseract's guesses."""
    existing = db.scalars(select(TrainingLine).where(TrainingLine.record_id == record.id)
                          .order_by(TrainingLine.page, TrainingLine.line_no)).all()
    if existing:
        return existing
    if not record.stored_filename:
        raise ValueError("This record has no document.")
    lang = ocr.resolve_languages(language or record.language or "Hindi")
    LINES_DIR.mkdir(parents=True, exist_ok=True)
    handwritten = record.ocr_quality == "poor"

    jobs = []
    for page_no, page in enumerate(ocr.page_images(file_path(record.stored_filename), record.mime_type), start=1):
        flat = normalize_background(upscale(to_gray_array(page)))
        flat = rotate(flat, estimate_skew(flat))
        # Remove only page-long table borders; shorter strokes may be Devanagari headlines.
        clean = remove_table_lines(flat, min_fraction=1 / 4)
        for line_no, (x, y, w, h) in enumerate(_segment_lines(flat), start=1):
            crop = Image.fromarray(clean[y:y + h, x:x + w])
            name = f"r{record.id}_p{page_no}_l{line_no:03d}.png"
            crop.save(LINES_DIR / name)
            jobs.append((page_no, line_no, name, [x, y, w, h], crop))

    with ThreadPoolExecutor(max_workers=4) as pool:
        guesses = list(pool.map(lambda j: _guess(j[4], lang), jobs))

    lines = []
    for (page_no, line_no, name, bbox, _), (text, conf) in zip(jobs, guesses):
        line = TrainingLine(record_id=record.id, page=page_no, line_no=line_no, image_file=name, bbox=bbox,
                            language=lang, ocr_text=text, ocr_confidence=conf, handwritten=handwritten)
        db.add(line)
        lines.append(line)
    db.commit()
    return lines


def line_image_path(line: TrainingLine) -> Path:
    return LINES_DIR / Path(line.image_file).name


def cer(reference: str, hypothesis: str) -> float:
    a, b = "".join(reference.split()), "".join((hypothesis or "").split())
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / max(1, len(a))


def training_stats(db: Session) -> dict:
    lines = db.scalars(select(TrainingLine)).all()
    verified = [line for line in lines if line.status == "verified" and line.ground_truth]
    by_lang: dict[str, int] = {}
    for line in verified:
        by_lang[line.language or "?"] = by_lang.get(line.language or "?", 0) + 1

    def ocr_cer(subset):
        if not subset:
            return None
        total = sum(len("".join(line.ground_truth.split())) for line in subset)
        errors = sum(cer(line.ground_truth, line.ocr_text or "") * len("".join(line.ground_truth.split()))
                     for line in subset)
        return round(errors / max(1, total) * 100, 1)

    return {
        "lines_total": len(lines),
        "lines_verified": len(verified),
        "lines_pending": sum(1 for line in lines if line.status == "pending"),
        "lines_skipped": sum(1 for line in lines if line.status == "skipped"),
        "characters_verified": sum(len(line.ground_truth) for line in verified),
        "handwritten_verified": sum(1 for line in verified if line.handwritten),
        "records": len({line.record_id for line in lines}),
        "by_language": by_lang,
        # Measured on officer-verified lines: how wrong the current OCR model is on YOUR documents.
        "current_ocr_cer_printed": ocr_cer([line for line in verified if not line.handwritten]),
        "current_ocr_cer_handwritten": ocr_cer([line for line in verified if line.handwritten]),
        "recommended_minimum_lines": 400,
    }


def export_zip(db: Session) -> bytes:
    """Verified lines in tesstrain layout, plus a manifest. Contains real document content."""
    lines = db.scalars(select(TrainingLine).where(TrainingLine.status == "verified")).all()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        manifest = ["file\trecord_id\tpage\tline\tlanguage\thandwritten\tocr_confidence"]
        for line in lines:
            path = line_image_path(line)
            if not path.exists() or not line.ground_truth:
                continue
            stem = Path(line.image_file).stem
            z.write(path, f"ground-truth/{stem}.png")
            z.writestr(f"ground-truth/{stem}.gt.txt", line.ground_truth.strip() + "\n")
            manifest.append(f"{stem}\t{line.record_id}\t{line.page}\t{line.line_no}\t{line.language}\t"
                            f"{line.handwritten}\t{line.ocr_confidence}")
        z.writestr("manifest.tsv", "\n".join(manifest) + "\n")
        z.writestr("README.txt", (
            "Line images and verified transcriptions for fine-tuning Tesseract (tesstrain).\n"
            f"Exported {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Contains real document content: "
            "handle as confidential.\nSee backend/scripts/FINE_TUNING.md in the project for the steps.\n"))
    return buf.getvalue()
