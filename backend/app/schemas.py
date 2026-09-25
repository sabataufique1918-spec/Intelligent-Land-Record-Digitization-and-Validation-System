from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DOCUMENT_TYPES = [
    "Jamabandi / Record of Rights",
    "Khatauni",
    "Khasra / Field Book",
    "Mutation Register",
    "Sale Deed",
    "Cadastral Map",
    "Other",
]

AREA_UNITS = ["Acre", "Hectare", "Bigha", "Kanal", "Guntha", "Sq. Metre"]

# pending      -> uploaded, rule checks not run or no data yet
# flagged      -> automated rule checks found errors / conflicts
# rules_passed -> automated rule checks found no errors (still needs officer review)
# verified     -> officer approved
# rejected     -> officer rejected
VALIDATION_STATUSES = ["pending", "flagged", "rules_passed", "verified", "rejected"]
OFFICER_STATUSES = ["verified", "rejected", "pending"]


class ValidationIssue(BaseModel):
    code: str
    field: str | None = None
    severity: Literal["error", "warning", "info"]
    message: str
    related_record_ids: list[int] = []
    conflict_key: str | None = None


class RecordUpdate(BaseModel):
    document_type: str | None = None
    owner_name: str | None = None
    father_name: str | None = None
    document_date: date | None = None
    previous_owner: str | None = None
    survey_number: str | None = None
    khata_number: str | None = None
    village: str | None = None
    tehsil: str | None = None
    district: str | None = None
    state: str | None = None
    area_value: float | None = None
    area_unit: str | None = None
    language: str | None = None
    remarks: str | None = None


class StatusUpdate(BaseModel):
    status: Literal["verified", "rejected", "pending"]
    reviewed_by: str = Field(default="Officer", max_length=120)
    note: str | None = None


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    record_number: str | None
    document_type: str
    owner_name: str | None
    father_name: str | None
    document_date: date | None = None
    previous_owner: str | None = None
    survey_number: str | None
    khata_number: str | None
    village: str | None
    tehsil: str | None
    district: str | None
    state: str | None
    area_value: float | None
    area_unit: str | None
    language: str | None
    remarks: str | None
    original_filename: str | None
    file_type: str | None
    mime_type: str | None
    file_size: int | None
    has_file: bool = False
    ocr_status: str
    ocr_language: str | None = None
    ocr_confidence: float | None = None
    ocr_method: str | None = None
    ocr_pages: int | None = None
    ocr_error: str | None = None
    ocr_processed_at: datetime | None = None
    ocr_quality: str | None = None
    ocr_preprocessing: str | None = None
    validation_status: str
    validation_issues: list[ValidationIssue]
    reviewed_by: str | None
    review_note: str | None
    reviewed_at: datetime | None
    is_sample: bool
    created_at: datetime
    updated_at: datetime


class FieldSuggestion(BaseModel):
    value: str
    source: str
    confidence: int = 0
    level: str = "low"
    sources: list[str] = []
    reasons: list[str] = []
    alternatives: list[dict] = []


class RecordDetailOut(RecordOut):
    ocr_text: str | None = None
    ocr_words: list | None = None  # [[word, confidence 0-100], ...] in reading order
    ocr_suggestions: dict[str, FieldSuggestion] = {}
    extraction_confidence: float | None = None
    ai_model: str | None = None
    ai_error: str | None = None
    boundary: dict | None = None
    boundary_source: str | None = None


class OCRResult(BaseModel):
    text: str
    language: str
    confidence: float | None
    method: str
    pages_processed: int
    total_pages: int
    quality: str | None = None
    preprocessing: str | None = None
    suggestions: dict[str, FieldSuggestion]
    words: list | None = None  # [[word, confidence 0-100], ...] in reading order
    extraction_confidence: float | None = None
    ai_used: bool = False
    ai_model: str | None = None
    ai_error: str | None = None


class RecordPage(BaseModel):
    items: list[RecordOut]
    total: int
    page: int
    page_size: int


class DismissConflict(BaseModel):
    key: str = Field(max_length=80)
    note: str | None = Field(default=None, max_length=1000)
    reviewed_by: str = Field(default="Officer", max_length=120)
