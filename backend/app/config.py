import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres@localhost:5432/land_records",  # set the real URL in backend/.env
)

UPLOAD_DIR = BASE_DIR / os.getenv("UPLOAD_DIR", "uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

SEED_SAMPLE_DATA = _bool(os.getenv("SEED_SAMPLE_DATA"), True)

# Re-run validation and conflict checks on all records when the server starts.
RECHECK_ON_STARTUP = _bool(os.getenv("RECHECK_ON_STARTUP"), True)

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

# --- OCR (Tesseract) ---
# Path to tesseract.exe; left empty, it is looked up on PATH and in the default install folder.
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "").strip()
# Folder holding *.traineddata language files (see scripts/download_ocr_languages.py).
TESSDATA_DIR = BASE_DIR / os.getenv("TESSDATA_DIR", "tessdata")
OCR_MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "10"))
OCR_DPI = int(os.getenv("OCR_DPI", "300"))
# Model used for Hindi. "hin_landrec" is the stock model fine-tuned on land-record text (see
# scripts/FINE_TUNING.md); if its file is not in TESSDATA_DIR the stock "hin" model is used.
HINDI_OCR_MODEL = os.getenv("HINDI_OCR_MODEL", "hin_landrec").strip() or "hin"
# Background OCR jobs that may run at the same time (each job can use several CPU cores).
OCR_WORKERS = max(1, int(os.getenv("OCR_WORKERS", "2")))

# --- AI field extraction (Claude API) ---
# Off by default: when on, the OCR text of a document is sent to Anthropic's API.
# Credentials come from ANTHROPIC_API_KEY (or another source the Anthropic SDK supports).
AI_EXTRACTION_ENABLED = _bool(os.getenv("AI_EXTRACTION_ENABLED"), False)
AI_MODEL = os.getenv("AI_MODEL", "claude-opus-5").strip()
# Reasoning effort: low | medium | high | xhigh | max. Field extraction is a simple task,
# so "low" keeps cost and latency down; raise it if accuracy on messy documents is poor.
AI_EFFORT = os.getenv("AI_EFFORT", "low").strip()
AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "120"))
# Where the AI runs: "anthropic" (Claude API, needs ANTHROPIC_API_KEY; data leaves this computer) or
# "ollama" (a vision model running locally in Ollama; free, nothing leaves this computer, less accurate).
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic").strip().lower()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").strip().rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-vl:4b").strip()
# Local models are slow on a small GPU (about 10 minutes for a printed page and longer for a handwritten
# one on a 4 GB GTX 1650), so they get a long timeout; reading runs in the background.
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "1800"))
# Send the page images together with the OCR text, so Claude can check and correct the OCR while
# extracting fields. Off: only the OCR text is sent (images are then sent only for unreadable pages).
AI_SEND_IMAGES = _bool(os.getenv("AI_SEND_IMAGES"), True)
