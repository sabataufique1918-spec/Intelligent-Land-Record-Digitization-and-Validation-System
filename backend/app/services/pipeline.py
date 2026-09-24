"""Honest status of each stage in the target architecture.

"available" = works in this build, "basic" = a simple version works,
"planned" = not implemented yet.
"""

PIPELINE_STAGES = [
    {"key": "upload", "name": "Document Upload", "status": "available",
     "detail": "PDF, JPG and PNG upload with type and size checks; files stored on disk."},
    {"key": "classifier", "name": "Document Classifier", "status": "planned",
     "detail": "Document type is selected manually by the uploader for now."},
    {"key": "enhancement", "name": "Image Quality Enhancement", "status": "planned",
     "detail": "Only grayscale, auto-contrast and upscaling of small images before OCR. "
               "OpenCV cleanup / super-resolution not implemented yet."},
    {"key": "ocr", "name": "Multilingual OCR / HTR", "status": "basic",
     "detail": "Tesseract OCR for printed text in English and 11 Indian languages; PDF text layers "
               "are read directly. Handwriting recognition is not supported yet."},
    {"key": "layout", "name": "Layout Understanding", "status": "planned",
     "detail": "Not implemented yet."},
    {"key": "extraction", "name": "Field Extraction", "status": "basic",
     "detail": "Label matching on OCR text. AI extraction with Claude is available but off "
               "(needs an Anthropic API key)."},
    {"key": "validation", "name": "Validation Engine", "status": "basic",
     "detail": "Rule checks (required fields, formats, area range, survey / khata numbers vs OCR text) "
               "and cross-record conflict detection: owner conflicts, duplicates incl. Hindi/English "
               "name matching, area (unit-converted) and khata mismatches, duplicate files. "
               "Cadastral map checks: parcel on map, area vs map, boundary vs map, boundary overlaps "
               "(against the imported map layer). No history or government DB checks."},
    {"key": "confidence", "name": "Confidence Engine", "status": "basic",
     "detail": "0-100 score per extracted field from OCR word confidence, extraction method, format "
               "checks and label/AI agreement; AI values not found in the document score low. "
               "Entered values that differ from high-confidence document values are flagged."},
    {"key": "review", "name": "Human Verification", "status": "available",
     "detail": "Officers can verify or reject a record and add a note."},
    {"key": "knowledge_graph", "name": "Knowledge Graph / Digital Twin", "status": "basic",
     "detail": "Each parcel's records, map parcel and boundaries combined into a dated ownership chain with "
               "current owner; flags broken chains, owner changes without a transfer and pending mutations. "
               "Uses records in this system only (no registration / revenue department data)."},
    {"key": "storage", "name": "PostgreSQL + GIS", "status": "basic",
     "detail": "Records and cadastral parcel boundaries (GeoJSON) stored in PostgreSQL; spatial checks "
               "done in Python with Shapely. PostGIS spatial indexing not added yet."},
    {"key": "dashboard", "name": "Officer Dashboard", "status": "basic",
     "detail": "Summary cards, records, search, validation queue, conflicts and a cadastral map view. "
               "Analytics planned."},
]


def pipeline_status(ocr_available: bool, ai_enabled: bool = False) -> list[dict]:
    stages = [dict(stage) for stage in PIPELINE_STAGES]
    for stage in stages:
        if ai_enabled and stage["key"] == "extraction":
            stage["detail"] = ("AI extraction with Claude (Anthropic API) plus label matching on OCR text. "
                               "Every value is checked against the document text; officers confirm before saving.")
        if ai_enabled and stage["key"] == "classifier":
            stage["status"] = "basic"
            stage["detail"] = "Claude suggests the document type from the OCR text; the uploader confirms it."
    if not ocr_available:
        for stage in stages:
            if stage["key"] == "ocr":
                stage["status"] = "setup"
                stage["detail"] = "OCR code is installed but Tesseract or its language files are missing on the server."
    return stages
