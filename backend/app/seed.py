"""Fictional sample records for demonstrating the dashboard.

Names, survey numbers and villages below are made up for testing and do not
represent real land holdings. Sample records have no attached document.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import LandRecord
from .routers.records import assign_record_number
from .services.validation import apply_validation

SAMPLE_RECORDS = [
    dict(document_type="Jamabandi / Record of Rights", owner_name="Ramesh Kumar", father_name="Shyam Lal",
         survey_number="112/3", khata_number="45", village="Rampur", tehsil="Sadar", district="Lucknow",
         state="Uttar Pradesh", area_value=2.5, area_unit="Acre", language="Hindi"),
    dict(document_type="Khatauni", owner_name="Sunita Devi", father_name="Mohan Singh",
         survey_number="87", khata_number="112", village="Rampur", tehsil="Sadar", district="Lucknow",
         state="Uttar Pradesh", area_value=1.2, area_unit="Hectare", language="Hindi"),
    # Deliberate conflict: same survey number + village as the first record, different owner.
    dict(document_type="Sale Deed", owner_name="Anil Verma", father_name="Prakash Verma",
         survey_number="112/3", khata_number="46", village="Rampur", tehsil="Sadar", district="Lucknow",
         state="Uttar Pradesh", area_value=2.5, area_unit="Acre", language="Hindi"),
    dict(document_type="Mutation Register", owner_name="Gurpreet Singh", father_name="Harbhajan Singh",
         survey_number="23/1", khata_number="9", village="Kheri", tehsil="Kharar", district="Mohali",
         state="Punjab", area_value=8, area_unit="Kanal", language="Punjabi"),
    dict(document_type="Khasra / Field Book", owner_name="Lakshmi Narayanan", father_name="Venkatesh",
         survey_number="301A", khata_number="77", village="Thirumalai", tehsil="Hosur", district="Krishnagiri",
         state="Tamil Nadu", area_value=0.8, area_unit="Hectare", language="Tamil"),
    # Missing owner name.
    dict(document_type="Jamabandi / Record of Rights", owner_name=None, father_name=None,
         survey_number="56", khata_number="14", village="Kheri", tehsil="Kharar", district="Mohali",
         state="Punjab", area_value=4, area_unit="Kanal", language="Punjabi"),
    dict(document_type="Cadastral Map", owner_name="Suresh Patil", father_name="Dattatray Patil",
         survey_number="19/2", khata_number="203", village="Wadgaon", tehsil="Haveli", district="Pune",
         state="Maharashtra", area_value=12, area_unit="Guntha", language="Marathi"),
    # Bad survey format and invalid area.
    dict(document_type="Khatauni", owner_name="Meena Kumari", father_name="Rajendra Prasad",
         survey_number="12-B?", khata_number="31", village="Chandpur", tehsil="Barh", district="Patna",
         state="Bihar", area_value=0, area_unit="Bigha", language="Hindi"),
    dict(document_type="Sale Deed", owner_name="Abdul Rahman", father_name="Iqbal Rahman",
         survey_number="402/7", khata_number="58", village="Wadgaon", tehsil="Haveli", district="Pune",
         state="Maharashtra", area_value=6, area_unit="Guntha", language="Marathi"),
    dict(document_type="Mutation Register", owner_name="Kavita Sharma", father_name="Om Prakash Sharma",
         survey_number="9", khata_number="3", village="Chandpur", tehsil="Barh", district="Patna",
         state="Bihar", area_value=3, area_unit="Bigha", language="Hindi"),
    dict(document_type="Jamabandi / Record of Rights", owner_name="Ravi Teja", father_name="Srinivas Rao",
         survey_number="215", khata_number="88", village="Thirumalai", tehsil="Hosur", district="Krishnagiri",
         state="Tamil Nadu", area_value=1.5, area_unit="Acre", language="Tamil"),
    dict(document_type="Khatauni", owner_name="Pooja Yadav", father_name="Mahesh Yadav",
         survey_number="64/2", khata_number="120", village="Rampur", tehsil="Sadar", district="Lucknow",
         state="Uttar Pradesh", area_value=0.6, area_unit="Hectare", language="Hindi"),
    # --- Conflict-detection examples (added in v0.3) ---
    # Same parcel and owner entered in Hindi and in English (cross-script duplicate).
    # 1.25 ha = 3.09 acre, so the areas agree after unit conversion.
    dict(document_type="Khatauni", owner_name="सुरेश कुमार", father_name="रामलाल",
         survey_number="२३८/२", khata_number="१४७", village="रामपुर", tehsil="सदर", district="लखनऊ",
         state="उत्तर प्रदेश", area_value=1.25, area_unit="Hectare", language="Hindi"),
    dict(document_type="Sale Deed", owner_name="Suresh Kumar", father_name="Ram Lal",
         survey_number="238/2", khata_number="147", village="Rampur", tehsil="Sadar", district="Lucknow",
         state="Uttar Pradesh", area_value=3.1, area_unit="Acre", language="English"),
    # Same owner and parcel as Gurpreet Singh's record above, but a different area.
    dict(document_type="Jamabandi / Record of Rights", owner_name="Gurpreet Singh", father_name="Harbhajan Singh",
         survey_number="23/1", khata_number="9", village="Kheri", tehsil="Kharar", district="Mohali",
         state="Punjab", area_value=12, area_unit="Kanal", language="Punjabi"),
    # Spelling variant of Lakshmi Narayanan with a different khata number.
    dict(document_type="Jamabandi / Record of Rights", owner_name="Laxmi Narayanan", father_name="Venkatesh",
         survey_number="301A", khata_number="78", village="Thirumalai", tehsil="Hosur", district="Krishnagiri",
         state="Tamil Nadu", area_value=0.8, area_unit="Hectare", language="Tamil"),
    # --- Ownership-history example (added in v0.6) ---
    # Sale of parcel 215 by Srinivas Rao, who is not the recorded owner (Ravi Teja since 2014): broken chain.
    dict(document_type="Sale Deed", owner_name="Priya Menon", father_name="K. Menon",
         survey_number="215", khata_number="88", village="Thirumalai", tehsil="Hosur", district="Krishnagiri",
         state="Tamil Nadu", area_value=1.5, area_unit="Acre", language="English"),
]

# (document date, previous owner / seller) per sample above, by position. Fictional.
SAMPLE_HISTORY = {
    0: (date(2018, 3, 10), None),            # Ramesh Kumar, Jamabandi 112/3
    1: (date(2019, 9, 9), None),
    2: (date(2023, 6, 15), "Ramesh Kumar"),  # sale 112/3 -> Anil Verma; Jamabandi not yet updated
    3: (date(2012, 8, 1), "Harbhajan Singh"),  # mutation (inheritance) 23/1
    4: (date(2015, 5, 5), None),
    5: (date(2019, 1, 20), None),
    6: (date(2017, 11, 30), None),
    7: (date(2021, 2, 14), None),
    8: (date(2024, 2, 11), "Vijay Kulkarni"),
    9: (date(2020, 10, 10), "Om Prakash Sharma"),
    10: (date(2014, 3, 3), None),             # Ravi Teja, Jamabandi 215
    11: (date(2022, 5, 18), None),
    12: (date(2021, 11, 2), None),            # Khatauni (Hindi) confirms the 2016 sale below
    13: (date(2016, 4, 20), "Mohan Lal"),     # sale 238/2 -> Suresh Kumar
    14: (date(2020, 1, 15), None),
    15: (date(2022, 7, 7), None),
    16: (date(2022, 9, 1), "Srinivas Rao"),   # broken chain
}

# Officer decisions applied to a few samples so every status appears on the dashboard.
OFFICER_DECISIONS = {
    1: ("verified", "Checked against physical register."),
    6: ("verified", "Verified during field visit."),
    9: ("rejected", "Illegible scan; resubmission requested."),
}


def _sample_key(owner, survey, village, document_type):
    return (owner or "", survey or "", village or "", document_type or "")


def seed_sample_data(db: Session) -> int:
    """Insert any sample records that are not in the database yet (existing data is never changed)."""
    existing = {
        _sample_key(r.owner_name, r.survey_number, r.village, r.document_type)
        for r in db.scalars(select(LandRecord).where(LandRecord.is_sample.is_(True)))
    }
    now = datetime.now(timezone.utc)
    created: dict[int, LandRecord] = {}
    for index, data in enumerate(SAMPLE_RECORDS):
        key = _sample_key(data["owner_name"], data["survey_number"], data["village"], data["document_type"])
        if key in existing:
            continue
        doc_date, previous_owner = SAMPLE_HISTORY.get(index, (None, None))
        record = LandRecord(
            **data,
            document_date=doc_date,
            previous_owner=previous_owner,
            is_sample=True,
            ocr_status="not_available",
            remarks="Sample record (fictional data, no document attached).",
            created_at=now - timedelta(days=len(SAMPLE_RECORDS) - index, hours=index),
        )
        db.add(record)
        db.flush()
        assign_record_number(record)
        created[index] = record

    for record in created.values():
        apply_validation(db, record, keep_officer_decision=False)

    for index, (status, note) in OFFICER_DECISIONS.items():
        record = created.get(index)
        if record is None:
            continue
        record.validation_status = status
        record.reviewed_by = "Demo Officer"
        record.review_note = note
        record.reviewed_at = now

    _backfill_history(db)
    db.commit()
    return len(created)


def _backfill_history(db: Session) -> None:
    """Give sample records created by older versions their (fictional) dates and sellers."""
    by_key = {
        _sample_key(d["owner_name"], d["survey_number"], d["village"], d["document_type"]): SAMPLE_HISTORY.get(i)
        for i, d in enumerate(SAMPLE_RECORDS)
    }
    for r in db.scalars(select(LandRecord).where(LandRecord.is_sample.is_(True), LandRecord.document_date.is_(None))):
        history = by_key.get(_sample_key(r.owner_name, r.survey_number, r.village, r.document_type))
        if history:
            r.document_date, r.previous_owner = history[0], r.previous_owner or history[1]
