"""Download Tesseract language models into backend/tessdata.

Usage (from the backend folder, with the virtual environment active):
    python scripts/download_ocr_languages.py              # all supported languages
    python scripts/download_ocr_languages.py hin eng      # only the listed codes
    python scripts/download_ocr_languages.py --fast       # smaller, less accurate models
"""

import sys
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import TESSDATA_DIR  # noqa: E402
from app.services.ocr import LANGUAGES  # noqa: E402

URL = "https://github.com/tesseract-ocr/{repo}/raw/main/{code}.traineddata"


def main(argv: list[str]) -> int:
    repo = "tessdata_fast" if "--fast" in argv else "tessdata_best"
    codes = [a for a in argv if not a.startswith("--")] or list(LANGUAGES.values())
    if "eng" not in codes:
        codes.append("eng")  # English is always combined with the document language

    TESSDATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Saving {repo} models to {TESSDATA_DIR}")
    failed = []
    for code in codes:
        target = TESSDATA_DIR / f"{code}.traineddata"
        if target.exists() and target.stat().st_size > 0:
            print(f"  {code}: already present")
            continue
        try:
            tmp = target.with_suffix(".part")
            urllib.request.urlretrieve(URL.format(repo=repo, code=code), tmp)
            tmp.replace(target)
            print(f"  {code}: {target.stat().st_size / 1_048_576:.1f} MB")
        except Exception as exc:  # network errors, 404 for unknown codes
            failed.append(code)
            print(f"  {code}: FAILED ({exc})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
