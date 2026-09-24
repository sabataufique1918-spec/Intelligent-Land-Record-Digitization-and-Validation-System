from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LandRecord(Base):
    __tablename__ = "land_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_number: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)

    # Record metadata (entered manually at upload time for now; OCR is not implemented yet)
    document_type: Mapped[str] = mapped_column(String(64), default="Other")
    owner_name: Mapped[str | None] = mapped_column(String(200), index=True)
    father_name: Mapped[str | None] = mapped_column(String(200))
    # Ownership history: date of the document / entry, and for transfers (sale deed, mutation)
    # the previous owner / seller. owner_name is then the new owner / buyer.
    document_date: Mapped[date | None] = mapped_column(Date, index=True)
    previous_owner: Mapped[str | None] = mapped_column(String(200))
    survey_number: Mapped[str | None] = mapped_column(String(64), index=True)
    # Normalised survey number used to find records about the same parcel.
    survey_key: Mapped[str | None] = mapped_column(String(64), index=True)
    khata_number: Mapped[str | None] = mapped_column(String(64), index=True)
    village: Mapped[str | None] = mapped_column(String(120), index=True)
    tehsil: Mapped[str | None] = mapped_column(String(120))
    district: Mapped[str | None] = mapped_column(String(120), index=True)
    state: Mapped[str | None] = mapped_column(String(120))
    area_value: Mapped[float | None] = mapped_column(Float)
    area_unit: Mapped[str | None] = mapped_column(String(32))
    language: Mapped[str | None] = mapped_column(String(64))
    remarks: Mapped[str | None] = mapped_column(Text)

    # Stored document
    original_filename: Mapped[str | None] = mapped_column(String(255))
    stored_filename: Mapped[str | None] = mapped_column(String(255))
    file_type: Mapped[str | None] = mapped_column(String(16))  # "pdf" | "image"
    mime_type: Mapped[str | None] = mapped_column(String(100))
    file_size: Mapped[int | None] = mapped_column(Integer)
    file_sha256: Mapped[str | None] = mapped_column(String(64), index=True)

    # Processing / validation
    # OCR: not_run | completed | no_text | failed | not_available (no document)
    ocr_status: Mapped[str] = mapped_column(String(32), default="not_run")
    ocr_text: Mapped[str | None] = mapped_column(Text)
    ocr_language: Mapped[str | None] = mapped_column(String(64))
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    ocr_method: Mapped[str | None] = mapped_column(String(32))
    ocr_pages: Mapped[int | None] = mapped_column(Integer)
    ocr_error: Mapped[str | None] = mapped_column(Text)
    ocr_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # [[word, confidence 0-100], ...] from Tesseract, used for per-field confidence scores.
    ocr_words: Mapped[list | None] = mapped_column(JSON)
    # AI (Claude) extraction result: {field: {"value": ..., "evidence": ...}}
    ai_fields: Mapped[dict | None] = mapped_column(JSON)
    ai_model: Mapped[str | None] = mapped_column(String(64))
    ai_error: Mapped[str | None] = mapped_column(Text)
    validation_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    validation_issues: Mapped[list] = mapped_column(JSON, default=list)
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Parcel boundary for this record (GeoJSON Polygon / MultiPolygon, WGS84 lon/lat), drawn or uploaded.
    boundary: Mapped[dict | None] = mapped_column(JSON)
    boundary_source: Mapped[str | None] = mapped_column(String(40))

    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    @property
    def has_file(self) -> bool:
        return bool(self.stored_filename)

    @property
    def ocr_suggestions(self) -> dict:
        from .services.confidence import build_suggestions

        return build_suggestions(self.ocr_text, self.ocr_words, self.ocr_method, self.ai_fields)

    @property
    def extraction_confidence(self) -> float | None:
        from .services.confidence import overall_confidence

        return overall_confidence(self.ocr_suggestions)


class ConflictReview(Base):
    """An officer's decision that a detected conflict between two records is not a real problem."""

    __tablename__ = "conflict_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conflict_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    conflict_type: Mapped[str] = mapped_column(String(40))
    record_a_id: Mapped[int] = mapped_column(Integer, index=True)
    record_b_id: Mapped[int] = mapped_column(Integer, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str] = mapped_column(String(120), default="Officer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CadastralParcel(Base):
    """A parcel from an imported cadastral map layer (the reference map records are checked against)."""

    __tablename__ = "cadastral_parcels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    survey_number: Mapped[str] = mapped_column(String(64))
    survey_key: Mapped[str] = mapped_column(String(64), index=True)
    village: Mapped[str | None] = mapped_column(String(120))
    district: Mapped[str | None] = mapped_column(String(120))
    geometry: Mapped[dict] = mapped_column(JSON)  # GeoJSON geometry, WGS84
    area_sqm: Mapped[float] = mapped_column(Float)
    min_lon: Mapped[float] = mapped_column(Float)
    min_lat: Mapped[float] = mapped_column(Float)
    max_lon: Mapped[float] = mapped_column(Float)
    max_lat: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(200), index=True)
    properties: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
