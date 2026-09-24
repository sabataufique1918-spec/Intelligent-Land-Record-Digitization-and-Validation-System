"""Confidence engine: a 0-100 score and explanation for every extracted field.

The score combines evidence that can be checked, not a model's own opinion:
  1. How the value was found: next to its label, on the line after the label,
     or by AI (Claude). AI values must be found in the OCR text ("grounded");
     values the AI produced that are not in the document score very low.
  2. OCR quality of the exact words that make up the value (Tesseract word
     confidence; 100 for PDFs with a real text layer).
  3. Whether the value has a plausible format for that field.
  4. Whether label matching and AI agree.

Levels: high >= 80, medium 55-79, low < 55.
"""

import re
import unicodedata

from ..schemas import AREA_UNITS, DOCUMENT_TYPES
from .extraction import UNITS, _collapse_repeated_marks, normalize_digits, parse_date, suggest_fields
from .matching import names_match, normalize_survey, places_match

FIELDS = [
    "document_type", "owner_name", "father_name", "previous_owner", "document_date", "survey_number", "khata_number",
    "village", "tehsil", "district", "state", "area_value", "area_unit",
]
CORE_FIELDS = ["owner_name", "survey_number", "village", "district", "area_value"]

METHOD_WEIGHT = {
    "label_same_line": 0.92,
    "label_next_line": 0.80,
    "ai_grounded": 0.90,
    "ai_ungrounded": 0.30,
    "ai_classification": 0.65,
}
METHOD_REASON = {
    "label_same_line": "Found right after the label “{label}”",
    "label_next_line": "Found on the line below the label “{label}”",
    "ai_grounded": "Extracted by AI and found in the document text",
    "ai_ungrounded": "Extracted by AI but NOT found in the document text (possible error)",
    "ai_classification": "Document type suggested by AI from the whole text",
}

SURVEY_RE = re.compile(r"^\d+[A-Z]?(/\d+[A-Z]?)*$")
KHATA_RE = re.compile(r"^\d+[A-Z/]*$")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", _collapse_repeated_marks(normalize_digits(text or "")))
    text = re.sub(r"\s*/\s*", "/", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _tokens(value: str) -> list[str]:
    return [t for t in re.split(r"[\s,;:()\-]+", _norm(value)) if t]


# ---------------------------------------------------------------- checks

def format_check(field: str, value: str) -> tuple[bool, str]:
    v = (value or "").strip()
    if field == "survey_number":
        ok = bool(SURVEY_RE.match(normalize_survey(v) or ""))
        return ok, "Valid survey number format" if ok else "Unusual survey number format"
    if field == "khata_number":
        ok = bool(KHATA_RE.match(normalize_survey(v) or ""))
        return ok, "Valid khata number format" if ok else "Unusual khata number format"
    if field == "area_value":
        try:
            n = float(normalize_digits(v))
        except ValueError:
            return False, "Area is not a number"
        ok = 0 < n < 10_000
        return ok, "Area is a plausible number" if ok else "Area is outside the plausible range"
    if field == "area_unit":
        ok = v in AREA_UNITS
        return ok, "Known area unit" if ok else "Unknown area unit"
    if field == "document_date":
        from datetime import date

        try:
            d = date.fromisoformat(v)
        except ValueError:
            return False, "Not a valid date"
        ok = date(1850, 1, 1) <= d <= date.today()
        return ok, "Valid date" if ok else "Date is in the future or implausibly old"
    if field == "document_type":
        ok = v in DOCUMENT_TYPES
        return ok, "Known document type" if ok else "Unknown document type"
    # names and places
    letters = sum(ch.isalpha() for ch in v)
    digits = sum(ch.isdigit() for ch in normalize_digits(v))
    ok = letters >= 2 and digits == 0 and len(v) <= 80
    return ok, "Looks like a valid name" if ok else "Contains digits or is too short/long for a name"


def ocr_word_confidence(value: str, words: list | None, ocr_method: str | None) -> tuple[float | None, str]:
    """Average Tesseract confidence of the OCR words that make up the value."""
    if ocr_method == "pdf_text_layer":
        return 100.0, "Text taken from the PDF's text layer (no OCR errors)"
    if not words:
        return None, "Word-level OCR confidence not available"
    index: dict[str, float] = {}
    for word, conf in words:
        for token in _tokens(word):
            index[token] = max(conf, index.get(token, 0))
    confs = []
    for token in _tokens(value):
        if token in index:
            confs.append(index[token])
        else:  # e.g. value "238/2" split differently by OCR
            partial = [c for t, c in index.items() if token in t or t in token]
            if partial:
                confs.append(max(partial))
    if not confs:
        return None, "Value's words were not matched to OCR words"
    avg = sum(confs) / len(confs)
    return avg, f"OCR read these words with {avg:.0f}% confidence"


def is_grounded(field: str, value: str, evidence: str, text: str) -> bool:
    """Can the AI's value be found in the document text?"""
    doc = _norm(text)
    if field == "area_unit":
        return any(re.search(p, text, re.IGNORECASE) for p, unit in UNITS if unit == value)
    if field == "document_date":
        return parse_date(evidence) == value and _norm(evidence) in doc
    if field in ("survey_number", "khata_number", "area_value"):
        token = re.escape(_norm(value).replace(" ", ""))
        return bool(re.search(rf"(?<![\d/.]){token}(?![\d/])", doc.replace(" / ", "/")))
    if _norm(value) in doc:
        return True
    ev = _norm(evidence)
    return bool(ev) and ev in doc and _norm(value) in ev


def values_agree(field: str, a: str, b: str) -> bool:
    if field in ("survey_number", "khata_number"):
        return normalize_survey(a) == normalize_survey(b)
    if field == "area_value":
        try:
            return abs(float(normalize_digits(a)) - float(normalize_digits(b))) < 1e-6
        except ValueError:
            return False
    if field in ("owner_name", "father_name", "previous_owner"):
        return names_match(a, b)[0]
    if field in ("village", "tehsil", "district", "state"):
        return places_match(a, b)[0]
    return _norm(a) == _norm(b)


# ---------------------------------------------------------------- scoring

def _level(score: int) -> str:
    return "high" if score >= 80 else "medium" if score >= 55 else "low"


def score_candidate(field: str, value: str, method: str, label: str | None,
                    words: list | None, ocr_method: str | None) -> tuple[float, list[str]]:
    reasons = [METHOD_REASON[method].format(label=label or "")]
    score = METHOD_WEIGHT[method]
    if method != "ai_classification" and field not in ("area_unit", "document_date"):
        word_conf, why = ocr_word_confidence(value, words, ocr_method)
        reasons.append(why)
        if word_conf is not None:
            score *= 0.5 + 0.5 * (word_conf / 100)
        else:
            score *= 0.85
    ok, why = format_check(field, value)
    reasons.append(why)
    if not ok:
        score *= 0.5
    return score, reasons


def build_suggestions(text: str | None, words: list | None, ocr_method: str | None,
                      ai_fields: dict | None) -> dict[str, dict]:
    """Merge label-matching and AI results into one scored suggestion per field."""
    if not text:
        return {}
    rule = suggest_fields(text)
    ai = ai_fields or {}
    out: dict[str, dict] = {}

    for field in FIELDS:
        candidates = []
        if field in rule:
            r = rule[field]
            s, reasons = score_candidate(field, r["value"], r.get("method", "label_same_line"),
                                         r.get("label"), words, ocr_method)
            candidates.append({"value": r["value"], "source": r["source"], "method": "label",
                               "score": s, "reasons": reasons})
        if field in ai:
            a = ai[field]
            if field == "document_type":
                method = "ai_classification"
            else:
                method = "ai_grounded" if is_grounded(field, a["value"], a.get("evidence", ""), text) else "ai_ungrounded"
            s, reasons = score_candidate(field, a["value"], method, None, words, ocr_method)
            candidates.append({"value": a["value"], "source": a.get("evidence") or "(AI)", "method": "ai",
                               "score": s, "reasons": reasons})
        if not candidates:
            continue

        best = max(candidates, key=lambda c: c["score"])
        score = best["score"]
        reasons = list(best["reasons"])
        sources = [best["method"]]
        alternatives = []
        if len(candidates) == 2:
            other = next(c for c in candidates if c is not best)
            if values_agree(field, best["value"], other["value"]):
                score = min(1.0, max(score, other["score"]) + 0.08)
                sources = ["label", "ai"]
                reasons.append("Label matching and AI agree")
            else:
                score *= 0.75
                reasons.append(f"Label matching and AI disagree (other reading: “{other['value']}”)")
                alternatives.append({"value": other["value"], "method": other["method"],
                                     "confidence": round(other["score"] * 100)})
        confidence = round(score * 100)
        out[field] = {
            "value": best["value"],
            "source": best["source"],
            "confidence": confidence,
            "level": _level(confidence),
            "sources": sources,
            "reasons": reasons,
            "alternatives": alternatives,
        }
    return out


def overall_confidence(suggestions: dict[str, dict]) -> float | None:
    """Average over the core fields; a missing core field counts as 0."""
    if not suggestions:
        return None
    scores = [suggestions[f]["confidence"] if f in suggestions else 0 for f in CORE_FIELDS]
    return round(sum(scores) / len(scores), 1)
