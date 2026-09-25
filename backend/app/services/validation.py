"""Basic rule-based validation for land records.

This is deliberately simple: deterministic checks on the metadata fields that
are stored for a record, cross-record conflict detection (services/conflicts.py),
and an exact-match check of survey / khata numbers against the record's OCR text
when available. It is NOT AI validation and it
does not consult any government database or GIS layer.
"""

import re

import hashlib
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LandRecord
from . import conflicts, gis, twin
from .confidence import build_suggestions, values_agree
from .extraction import normalize_digits
from .matching import normalize_survey
from .storage import file_path

REQUIRED_FIELDS = {
    "owner_name": "Owner name",
    "survey_number": "Survey / Khasra number",
    "village": "Village",
    "district": "District",
}

# Fields compared with the value read from the document (survey / khata use NOT_IN_DOCUMENT).
DOCUMENT_COMPARE_FIELDS = {
    "owner_name": "Owner name",
    "father_name": "Father's / husband's name",
    "previous_owner": "Previous owner / seller",
    "village": "Village",
    "district": "District",
    "area_value": "Area",
}

# e.g. 123, 45/2, 45/2/1, 112A
SURVEY_NUMBER_PATTERN = re.compile(r"^\d+[A-Za-z]?(/\d+[A-Za-z]?)*$")
NAME_PATTERN = re.compile(r"^[^\d@#$%^&*=+<>{}\[\]|\\~`]+$")

MAX_REASONABLE_AREA = 10_000  # in the record's own unit


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def run_rule_checks(db: Session, record: LandRecord) -> list[dict]:
    issues: list[dict] = []

    def add(code, field, severity, message):
        issues.append({"code": code, "field": field, "severity": severity, "message": message})

    for field, label in REQUIRED_FIELDS.items():
        if _blank(getattr(record, field)):
            add("MISSING_FIELD", field, "error", f"{label} is missing.")

    if not _blank(record.survey_number) and not SURVEY_NUMBER_PATTERN.match(record.survey_number.strip()):
        add(
            "SURVEY_FORMAT",
            "survey_number",
            "warning",
            f"Survey number '{record.survey_number}' does not match the expected format (e.g. 123 or 45/2).",
        )

    if not _blank(record.owner_name) and not NAME_PATTERN.match(record.owner_name.strip()):
        add("NAME_FORMAT", "owner_name", "warning", "Owner name contains digits or unexpected symbols.")

    if record.area_value is None:
        add("MISSING_FIELD", "area_value", "warning", "Area is not recorded.")
    elif record.area_value <= 0:
        add("AREA_INVALID", "area_value", "error", "Area must be greater than zero.")
    elif record.area_value > MAX_REASONABLE_AREA:
        add("AREA_OUTLIER", "area_value", "warning", "Area is unusually large; please check the unit.")

    if record.area_value is not None and _blank(record.area_unit):
        add("MISSING_FIELD", "area_unit", "warning", "Area unit is not specified.")

    # Cross-record conflicts (same parcel / same file). See services/conflicts.py.
    issues.extend(conflicts.as_issues(conflicts.for_record(db, record), record.id))

    # Cadastral map checks (area vs map, boundary vs map, boundary overlaps). See services/gis.py.
    issues.extend(gis.gis_issues(db, record))

    # Ownership history checks (chain breaks, pending mutation). See services/twin.py.
    if record.document_date and record.document_date > date.today():
        add("FUTURE_DATE", "document_date", "error", "Document date is in the future.")
    elif record.document_date and record.document_date.year < 1850:
        add("DATE_OUTLIER", "document_date", "warning", "Document date is unusually old; please check it.")
    issues.extend(twin.record_issues(db, record))

    # Compare entered numbers with the text read from the document (exact token match).
    if record.ocr_status == "completed" and record.ocr_text:
        doc_text = re.sub(r"\s*/\s*", "/", normalize_digits(record.ocr_text))
        for field, label in (("survey_number", "Survey number"), ("khata_number", "Khata number")):
            value = getattr(record, field)
            if _blank(value):
                continue
            token = re.sub(r"\s+", "", normalize_digits(value))
            if not re.search(rf"(?<![\d/]){re.escape(token)}(?![\d/])", doc_text, re.IGNORECASE):
                add("NOT_IN_DOCUMENT", field, "warning",
                    f"{label} '{value}' was not found in the text read from the document.")
        # Entered values that disagree with a high-confidence value read from the document.
        suggestions = build_suggestions(record.ocr_text, record.ocr_words, record.ocr_method, record.ai_fields)
        for field, label in DOCUMENT_COMPARE_FIELDS.items():
            found, entered = suggestions.get(field), getattr(record, field)
            if not found or found["level"] != "high" or _blank(entered):
                continue
            if field == "area_value":
                same_unit = not record.area_unit or suggestions.get("area_unit", {}).get("value") in (None, record.area_unit)
                if not same_unit or values_agree(field, str(entered), found["value"]):
                    continue
            elif values_agree(field, str(entered), found["value"]):
                continue
            add("DIFFERS_FROM_DOCUMENT", field, "warning",
                f"{label} entered as '{entered}' but the document reads '{found['value']}' "
                f"({found['confidence']}% confidence).")
        if record.ocr_quality == "poor" and record.ocr_method != "ai_vision":
            words = record.ocr_words or []
            clear = sum(1 for _, conf in words if conf >= 80)  # same "read clearly" threshold as the record page
            share = f"only {round(100 * clear / len(words))}% of the words ({clear} of {len(words)}) were read clearly" \
                if words else f"the text was read with {record.ocr_confidence or 0:.0f}% confidence"
            add("OCR_POOR_QUALITY", None, "warning",
                f"Handwritten or unclear document: {share}. Enter the details from the document.")
        elif record.ocr_method == "ai_vision":
            add("AI_READ_HANDWRITING", None, "info",
                "The text was read by AI directly from the image (handwriting / poor scan). Check every "
                "value against the document.")
        elif record.ocr_confidence is not None and record.ocr_confidence < 60:
            add("LOW_OCR_CONFIDENCE", None, "info",
                f"OCR confidence is low ({record.ocr_confidence:.0f}%); compare the fields with the document manually.")
    elif record.ocr_status == "failed":
        add("OCR_FAILED", None, "info", f"OCR could not read the document: {record.ocr_error}")

    if not record.stored_filename:
        add("NO_DOCUMENT", None, "info", "No source document is attached to this record.")

    return issues


def automated_status(issues: list[dict]) -> str:
    if any(i["severity"] == "error" for i in issues):
        return "flagged"
    return "rules_passed"


def apply_validation(db: Session, record: LandRecord, keep_officer_decision: bool = True) -> None:
    record.survey_key = normalize_survey(record.survey_number)
    record.validation_issues = run_rule_checks(db, record)
    if keep_officer_decision and record.validation_status in ("verified", "rejected"):
        return
    record.validation_status = automated_status(record.validation_issues)


def related_ids(record: LandRecord) -> set[int]:
    return {i for issue in (record.validation_issues or []) for i in issue.get("related_record_ids", [])}


def validate_with_related(db: Session, record: LandRecord, keep_officer_decision: bool = True) -> None:
    """Validate a record, then refresh every record it conflicted with before or after the change,
    so conflicts show up (and disappear) on both sides."""
    before = related_ids(record)
    apply_validation(db, record, keep_officer_decision)
    db.flush()
    for other_id in (before | related_ids(record)) - {record.id}:
        other = db.get(LandRecord, other_id)
        if other is not None:
            apply_validation(db, other, keep_officer_decision=True)
    db.flush()


def recheck_all(db: Session) -> int:
    """Recompute survey keys, file hashes and validation for every record."""
    records = db.scalars(select(LandRecord).order_by(LandRecord.id)).all()
    for record in records:
        record.survey_key = normalize_survey(record.survey_number)
        if record.stored_filename and not record.file_sha256:
            path = file_path(record.stored_filename)
            if path.exists():
                record.file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    db.flush()
    for record in records:
        apply_validation(db, record, keep_officer_decision=True)
    db.commit()
    return len(records)
