"""Multilingual OCR for printed text using Tesseract.

- PDFs: pages with an embedded text layer are read directly; scanned pages are
  rendered to images and OCR'd in parallel.
- Images / scanned pages: Tesseract on the plain page first; pages that are skewed or poorly read
  are cleaned up (services/image_enhance.py) and the best reading is kept.
- Handwriting recognition is NOT supported by Tesseract: with AI enabled, Claude reads
  the page images instead (see run_ai).
"""

import hashlib
import os
import shutil
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image, ImageOps

from ..config import HINDI_OCR_MODEL, OCR_DPI, OCR_MAX_PAGES, TESSDATA_DIR, TESSERACT_CMD

# Display name -> Tesseract language code
LANGUAGES = {
    "English": "eng",
    "Hindi": "hin",
    "Marathi": "mar",
    "Punjabi": "pan",
    "Bengali": "ben",
    "Gujarati": "guj",
    "Odia": "ori",
    "Tamil": "tam",
    "Telugu": "tel",
    "Kannada": "kan",
    "Malayalam": "mal",
    "Urdu": "urd",
}

DEFAULT_WINDOWS_PATHS = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]

MIN_TEXT_LAYER_CHARS = 30
PAGE_TIMEOUT_SECONDS = 180
# One Tesseract process per CPU core at most. Each process is limited to one thread
# (OMP_THREAD_LIMIT=1): running variants and pages side by side is faster than letting several
# multi-threaded Tesseract processes fight over the same cores.
_TESSERACT_SLOTS = threading.BoundedSemaphore(os.cpu_count() or 2)


class OCRError(Exception):
    pass


def _find_tesseract() -> str | None:
    if TESSERACT_CMD:
        return TESSERACT_CMD if Path(TESSERACT_CMD).exists() else None
    found = shutil.which("tesseract")
    if found:
        return found
    for path in DEFAULT_WINDOWS_PATHS:
        if path.exists():
            return str(path)
    return None


def _configure() -> str | None:
    cmd = _find_tesseract()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
        os.environ.setdefault("OMP_THREAD_LIMIT", "1")
        # Use the project's language folder when it has models in it.
        if any(TESSDATA_DIR.glob("*.traineddata")):
            os.environ["TESSDATA_PREFIX"] = str(TESSDATA_DIR)
    return cmd


def installed_codes() -> set[str]:
    if not _configure():
        return set()
    try:
        return set(pytesseract.get_languages(config=""))
    except Exception:
        return set()


def status() -> dict:
    cmd = _configure()
    version = None
    if cmd:
        try:
            version = str(pytesseract.get_tesseract_version())
        except Exception:
            cmd = None
    codes = installed_codes() if cmd else set()
    return {
        "available": bool(cmd) and "eng" in codes,
        "engine": "Tesseract",
        "version": version,
        "handwriting_supported": False,
        "languages": [
            {"name": name, "code": code, "installed": code in codes}
            for name, code in LANGUAGES.items()
        ],
        "message": None if cmd else "Tesseract OCR is not installed on the server.",
    }


def resolve_languages(requested: str | None) -> str:
    """Turn 'hin', 'Hindi' or 'hin+eng' into a Tesseract language string that always includes English."""
    codes = installed_codes()
    if not codes:
        raise OCRError("Tesseract OCR is not installed on the server.")
    wanted: list[str] = []
    for part in (requested or "eng").replace(",", "+").split("+"):
        part = part.strip()
        if not part:
            continue
        code = LANGUAGES.get(part.title(), part.lower())
        if code not in LANGUAGES.values():
            raise OCRError(f"Unsupported OCR language: {part}")
        if code not in wanted:
            wanted.append(code)
    # English goes first: in testing, "eng+hin" kept Latin digits (e.g. "1.25") that
    # "hin+eng" dropped, while Devanagari text was read equally well.
    wanted = ["eng"] + [c for c in wanted if c != "eng"]
    if "hin" in wanted and HINDI_OCR_MODEL != "hin" and HINDI_OCR_MODEL in codes:
        wanted[wanted.index("hin")] = HINDI_OCR_MODEL
    missing = [c for c in wanted if c not in codes]
    if missing:
        raise OCRError(
            f"OCR language pack not installed: {', '.join(missing)}. "
            f"Run: python scripts/download_ocr_languages.py {' '.join(missing)}"
        )
    return "+".join(wanted)


def _prepare(image: Image.Image) -> Image.Image:
    image = ImageOps.grayscale(image)
    if image.width < 1200:
        image = image.resize((image.width * 2, image.height * 2), Image.LANCZOS)
    return ImageOps.autocontrast(image, cutoff=1)


def _tesseract(image: Image.Image, lang: str) -> dict:
    with _TESSERACT_SLOTS:
        data = pytesseract.image_to_data(
            image,
            lang=lang,
            config="--oem 1 --psm 3",
            output_type=pytesseract.Output.DICT,
            timeout=PAGE_TIMEOUT_SECONDS,
        )
    lines: OrderedDict[tuple, list[str]] = OrderedDict()
    confidences = []
    words = []
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        if not word:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
        conf = float(data["conf"][i])
        if conf >= 0:
            confidences.append(conf)
            words.append([word, round(conf, 1)])

    out, previous_block = [], None
    for (block, _par, _line), line_words in lines.items():
        if previous_block is not None and block != previous_block:
            out.append("")
        out.append(" ".join(line_words))
        previous_block = block
    mean_conf = round(sum(confidences) / len(confidences), 1) if confidences else None
    # How much text was read confidently: characters of words with >= 60 % confidence, weighted.
    score = sum(len(w) * c / 100 for w, c in words if c >= 60)
    return {"text": "\n".join(out).strip(), "confidence": mean_conf, "words": words, "score": score}


FAST_PATH_CONFIDENCE = 88.0  # clean, straight pages skip the (slower) clean-up variants


def _ocr_image(image: Image.Image, lang: str) -> tuple[str, float | None, list, str]:
    """OCR one page. Tries the plain image first, then cleaned-up variants (deskew, background
    removal, denoising, binarisation) when the page is skewed or poorly read; keeps the best."""
    from .image_enhance import enhanced_variants, quick_skew

    image = ImageOps.exif_transpose(image)
    best = {**_tesseract(_prepare(image), lang), "preprocessing": "basic"}
    skew = quick_skew(image)
    if (best["confidence"] or 0) >= FAST_PATH_CONFIDENCE and abs(skew) < 0.5:
        return best["text"], best["confidence"], best["words"], best["preprocessing"]
    variants = enhanced_variants(image, skew)
    # Tesseract runs as a separate process per call, so the variants can be read in parallel.
    with ThreadPoolExecutor(max_workers=len(variants)) as pool:
        results = pool.map(lambda item: (item[0], _tesseract(item[1], lang)), variants.items())
        for name, result in results:
            if result["score"] > best["score"]:
                best = {**result, "preprocessing": name}
    return best["text"], best["confidence"], best["words"], best["preprocessing"]


def quality_label(confidence: float | None) -> str:
    """good >= 75, fair 50-75, poor < 50 (handwritten, damaged or very poor scans)."""
    if confidence is None:
        return "poor"
    return "good" if confidence >= 75 else "fair" if confidence >= 50 else "poor"


def run_ocr(path: Path, mime_type: str, language: str | None) -> dict:
    lang = resolve_languages(language)
    pages: list[dict] = []

    try:
        if mime_type == "application/pdf":
            scans: dict[int, Image.Image] = {}
            with pymupdf.open(path) as doc:
                total_pages = doc.page_count
                for index, page in enumerate(doc):
                    if index >= OCR_MAX_PAGES:
                        break
                    embedded = page.get_text().strip()
                    if len(embedded) >= MIN_TEXT_LAYER_CHARS:
                        pages.append({"page": index + 1, "method": "pdf_text_layer", "text": embedded,
                                      "confidence": None, "words": [[w, 100.0] for w in embedded.split()]})
                        continue
                    pix = page.get_pixmap(dpi=OCR_DPI, colorspace=pymupdf.csGRAY)
                    scans[index + 1] = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            # Scanned pages are OCR'd side by side (_TESSERACT_SLOTS keeps the CPU from being oversubscribed).
            if scans:
                with ThreadPoolExecutor(max_workers=min(len(scans), os.cpu_count() or 2)) as pool:
                    for number, (text, conf, words, pre) in zip(scans, pool.map(lambda im: _ocr_image(im, lang),
                                                                                 scans.values())):
                        pages.append({"page": number, "method": "tesseract", "text": text,
                                      "confidence": conf, "words": words, "preprocessing": pre})
                pages.sort(key=lambda p: p["page"])
        else:
            total_pages = 1
            with Image.open(path) as image:
                text, conf, words, pre = _ocr_image(image, lang)
            pages.append({"page": 1, "method": "tesseract", "text": text, "confidence": conf, "words": words,
                          "preprocessing": pre})
    except RuntimeError as exc:  # pytesseract timeout
        raise OCRError(f"OCR timed out or failed: {exc}") from exc
    except pytesseract.TesseractError as exc:
        raise OCRError(f"Tesseract error: {exc.message}") from exc
    except (pymupdf.FileDataError, OSError) as exc:
        raise OCRError(f"Could not open the document: {exc}") from exc

    text = "\n\n".join(
        (f"--- Page {p['page']} ---\n" if len(pages) > 1 else "") + p["text"] for p in pages
    ).strip()
    ocr_confs = [p["confidence"] for p in pages if p["confidence"] is not None]
    methods = {p["method"] for p in pages}
    return {
        "text": text,
        "language": lang,
        "confidence": round(sum(ocr_confs) / len(ocr_confs), 1) if ocr_confs else None,
        "quality": "good" if not ocr_confs and pages and all(p["method"] == "pdf_text_layer" for p in pages)
        else quality_label(round(sum(ocr_confs) / len(ocr_confs), 1) if ocr_confs else None),
        "method": "mixed" if len(methods) > 1 else (methods.pop() if methods else "tesseract"),
        "pages_processed": len(pages),
        "preprocessing": "; ".join(dict.fromkeys(p.get("preprocessing", "text layer") for p in pages)),
        "words": [w for p in pages for w in p["words"]],
        "total_pages": total_pages,
        "processed_at": datetime.now(timezone.utc),
    }


# Small in-memory cache so that a preview OCR followed by the actual upload
# of the same file does not run Tesseract twice.
_CACHE: OrderedDict[tuple[str, str], dict] = OrderedDict()
_CACHE_SIZE = 16


def run_ocr_cached(path: Path, mime_type: str, language: str | None) -> dict:
    lang = resolve_languages(language)
    key = (hashlib.sha256(path.read_bytes()).hexdigest(), lang)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return dict(_CACHE[key])
    # Pass the requested language, not `lang`: resolving "eng+hin_landrec" again would reject the model name.
    result = run_ocr(path, mime_type, language)
    _CACHE[key] = result
    if len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return dict(result)


def apply_to_record(record, language: str | None, use_ai: bool = True) -> None:
    """Run OCR (and optionally AI extraction) on a record's stored document and save the results."""
    from .storage import file_path

    if not record.stored_filename:
        record.ocr_status = "not_available"
        return
    try:
        result = run_ocr_cached(file_path(record.stored_filename), record.mime_type, language)
    except OCRError as exc:
        record.ocr_status = "failed"
        record.ocr_error = str(exc)
        record.ocr_processed_at = datetime.now(timezone.utc)
        return
    result = {**result, **run_ai(file_path(record.stored_filename), record.mime_type, result, use_ai)}
    record.ocr_text = result["text"]
    record.ocr_language = result["language"]
    record.ocr_confidence = result["confidence"]
    record.ocr_method = result["method"]
    record.ocr_pages = result["pages_processed"]
    record.ocr_words = result["words"]
    record.ocr_quality = result.get("quality")
    record.ocr_preprocessing = (result.get("preprocessing") or "")[:200] or None
    record.ocr_error = None
    record.ocr_processed_at = result["processed_at"]
    record.ocr_status = "completed" if result["text"].strip() else "no_text"
    record.ai_fields, record.ai_model, record.ai_error = result["ai_fields"], result["ai_model"], result["ai_error"]


def page_images(path: Path, mime_type: str) -> list:
    """The document's pages as images (for AI reading of handwriting)."""
    if mime_type != "application/pdf":
        with Image.open(path) as image:
            return [ImageOps.exif_transpose(image).convert("RGB")]
    images = []
    with pymupdf.open(path) as doc:
        for index, page in enumerate(doc):
            if index >= OCR_MAX_PAGES:
                break
            pix = page.get_pixmap(dpi=200)
            images.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    return images


def run_ai(path: Path, mime_type: str, result: dict, use_ai: bool) -> dict:
    """Optional AI step after OCR. Returns fields to merge into the OCR result.
    - Poor pages (handwritten / damaged): Claude reads the page images directly, and its
      transcription replaces the unusable OCR text.
    - Other scanned pages: Claude gets the page images AND the OCR text (AI_SEND_IMAGES), so it can
      correct OCR misreadings while extracting fields; with AI_SEND_IMAGES off, only the text.
    - PDFs with a real text layer: text only (the text is already exact)."""
    from . import ai_extraction

    out = {"ai_fields": None, "ai_model": None, "ai_error": None}
    if not (use_ai and ai_extraction.AI_EXTRACTION_ENABLED):
        return out
    if result.get("quality") == "poor" and ai_extraction.LOCAL:
        # Tested with qwen3-vl:4b on handwritten records: it keeps repeating itself until stopped (~15 min
        # of GPU time) whether asked for a transcription or only the fields. Skip it; the OCR reading is kept.
        return out
    try:
        if result.get("quality") == "poor":
            ai = ai_extraction.extract_from_images(page_images(path, mime_type))
            out.update(ai_fields=ai["fields"], ai_model=ai["model"])
            if ai["transcription"]:
                out.update(text=ai["transcription"], method="ai_vision", words=None)
        elif result["text"].strip():
            if ai_extraction.AI_SEND_IMAGES and result.get("method") != "pdf_text_layer":
                ai = ai_extraction.extract_with_images(result["text"], page_images(path, mime_type))
            else:
                ai = ai_extraction.extract(result["text"])
            out.update(ai_fields=ai["fields"], ai_model=ai["model"])
    except ai_extraction.AIExtractionError as exc:
        out["ai_error"] = str(exc)
    return out
