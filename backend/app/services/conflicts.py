"""Cross-record conflict detection.

Compares records that refer to the same parcel (same normalised survey number,
village and district) and records that share the same uploaded file. All checks
are rule-based and explainable; they do not use AI, GIS or government databases.

Conflict types
- OWNER_CONFLICT      same parcel recorded under different owners          (error)
- OWNERSHIP_TRANSFER  different owners, but linked by dated transfer documents (info)
- POSSIBLE_DUPLICATE  same parcel and same owner (incl. spelling / script)  (warning)
- AREA_MISMATCH       same parcel, areas differ by more than 5 %            (warning)
- KHATA_MISMATCH      same parcel and owner, different khata numbers        (info)
- DUPLICATE_DOCUMENT  identical file uploaded for two records               (warning)

Rejected records are ignored. Officers can dismiss a conflict (ConflictReview).
"""

from collections import defaultdict

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import ConflictReview, LandRecord
from .matching import compare_areas, names_match, normalize_survey, places_match
from .twin import owners_linked_by_transfers
from .twin import same_parcel as records_same_parcel

CONFLICT_TYPES = {
    "OWNER_CONFLICT": {"label": "Owner conflict", "severity": "error"},
    "OWNERSHIP_TRANSFER": {"label": "Ownership transfer", "severity": "info"},
    "POSSIBLE_DUPLICATE": {"label": "Possible duplicate", "severity": "warning"},
    "AREA_MISMATCH": {"label": "Area mismatch", "severity": "warning"},
    "KHATA_MISMATCH": {"label": "Khata mismatch", "severity": "info"},
    "DUPLICATE_DOCUMENT": {"label": "Duplicate document", "severity": "warning"},
}


def conflict_key(conflict_type: str, a_id: int, b_id: int) -> str:
    low, high = sorted((a_id, b_id))
    return f"{conflict_type}:{low}-{high}"


def parse_conflict_key(key: str) -> tuple[str, int, int] | None:
    try:
        conflict_type, ids = key.split(":", 1)
        a, b = (int(x) for x in ids.split("-", 1))
    except ValueError:
        return None
    if conflict_type not in CONFLICT_TYPES or a == b:
        return None
    return conflict_type, a, b


def _ref(record: LandRecord) -> str:
    return record.record_number or f"#{record.id}"


def _same_parcel(a: LandRecord, b: LandRecord) -> tuple[bool, list[str]]:
    if not a.survey_key or a.survey_key != b.survey_key:
        return False, []
    village_ok, village_how = places_match(a.village, b.village)
    district_ok, district_how = places_match(a.district, b.district)
    if not (village_ok and district_ok):
        return False, []
    notes = [f"{name} matched across scripts" for name, how in
             (("village", village_how), ("district", district_how)) if how == "cross-script"]
    return True, notes


def compare_pair(a: LandRecord, b: LandRecord, group: list[LandRecord] | None = None) -> list[dict]:
    """All conflicts between two records (order-independent). `group` = other records of the
    same survey number, used to see whether transfer documents explain different owners."""
    if a.id == b.id or "rejected" in (a.validation_status, b.validation_status):
        return []
    if a.id > b.id:
        a, b = b, a
    found: list[dict] = []

    def add(conflict_type: str, message: str, **details):
        found.append({
            "key": conflict_key(conflict_type, a.id, b.id),
            "type": conflict_type,
            "label": CONFLICT_TYPES[conflict_type]["label"],
            "severity": CONFLICT_TYPES[conflict_type]["severity"],
            "record_ids": [a.id, b.id],
            "record_numbers": [_ref(a), _ref(b)],
            "message": message,
            "details": details,
        })

    if a.file_sha256 and a.file_sha256 == b.file_sha256:
        add("DUPLICATE_DOCUMENT", f"{_ref(a)} and {_ref(b)} have the identical document file attached.")

    same_parcel, notes = _same_parcel(a, b)
    if same_parcel:
        parcel = f"survey {a.survey_number} in {a.village}"
        same_owner, how = names_match(a.owner_name, b.owner_name)
        linked = None
        if a.owner_name and b.owner_name and not same_owner:
            parcel_records = [r for r in (group or []) if records_same_parcel(r, a)] + [a, b]
            parcel_records = list({r.id: r for r in parcel_records}.values())
            linked = owners_linked_by_transfers(parcel_records, a, b)
        if linked:
            refs = {r.id: _ref(r) for r in (group or []) + [a, b]}
            add("OWNERSHIP_TRANSFER",
                f"{parcel[:1].upper() + parcel[1:]} was '{a.owner_name}' in {_ref(a)} and '{b.owner_name}' in "
                f"{_ref(b)}; the change is explained by transfer document(s) "
                f"{', '.join(refs.get(i, f'#{i}') for i in linked)}. See the parcel history.",
                transfers=linked)
        elif a.owner_name and b.owner_name and not same_owner:
            add("OWNER_CONFLICT",
                f"{parcel[:1].upper() + parcel[1:]} is recorded under '{a.owner_name}' in {_ref(a)} and '{b.owner_name}' in {_ref(b)}. "
                "This may be a sale or mutation. Check which record is current.",
                notes=notes)
        elif same_owner:
            add("POSSIBLE_DUPLICATE",
                f"{_ref(a)} and {_ref(b)} describe the same parcel ({parcel}) and owner "
                f"('{a.owner_name}' / '{b.owner_name}', {how} match).",
                match=how, notes=notes)
            if a.khata_number and b.khata_number and normalize_survey(a.khata_number) != normalize_survey(b.khata_number):
                add("KHATA_MISMATCH",
                    f"Same parcel and owner, but khata no. {a.khata_number} in {_ref(a)} vs {b.khata_number} in {_ref(b)}.")

        area = compare_areas(a.area_value, a.area_unit, b.area_value, b.area_unit)
        if area:
            add("AREA_MISMATCH",
                f"Area of {parcel} differs by {area['difference_pct']}%: "
                f"{a.area_value} {a.area_unit} in {_ref(a)} vs {b.area_value} {b.area_unit} in {_ref(b)}.",
                **area)
    return found


def _dismissed(db: Session, keys: list[str]) -> dict[str, ConflictReview]:
    if not keys:
        return {}
    rows = db.scalars(select(ConflictReview).where(ConflictReview.conflict_key.in_(keys)))
    return {r.conflict_key: r for r in rows}


def _attach_reviews(db: Session, conflicts: list[dict]) -> list[dict]:
    reviews = _dismissed(db, [c["key"] for c in conflicts])
    for c in conflicts:
        review = reviews.get(c["key"])
        c["dismissed"] = review is not None
        c["review"] = (
            {"note": review.note, "reviewed_by": review.reviewed_by, "created_at": review.created_at}
            if review else None
        )
    return conflicts


def for_record(db: Session, record: LandRecord) -> list[dict]:
    """Conflicts between one record and all other records."""
    if record.validation_status == "rejected":
        return []
    conditions = []
    if record.survey_key:
        conditions.append(LandRecord.survey_key == record.survey_key)
    if record.file_sha256:
        conditions.append(LandRecord.file_sha256 == record.file_sha256)
    if not conditions:
        return []

    stmt = select(LandRecord).where(or_(*conditions), LandRecord.validation_status != "rejected")
    if record.id is not None:
        stmt = stmt.where(LandRecord.id != record.id)
    others = db.scalars(stmt).all()
    conflicts = [c for other in others for c in compare_pair(record, other, others)]
    return _attach_reviews(db, conflicts)


def detect_all(db: Session) -> list[dict]:
    """Every conflict in the database (blocked by survey key and file hash, then pairwise)."""
    records = db.scalars(select(LandRecord).where(LandRecord.validation_status != "rejected")).all()
    blocks: dict[str, list[LandRecord]] = defaultdict(list)
    for r in records:
        if r.survey_key:
            blocks[f"s:{r.survey_key}"].append(r)
        if r.file_sha256:
            blocks[f"f:{r.file_sha256}"].append(r)

    seen: dict[str, dict] = {}
    for group in blocks.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                for c in compare_pair(a, b, group):
                    seen.setdefault(c["key"], c)
    return _attach_reviews(db, list(seen.values()))


def group_conflicts(conflicts: list[dict]) -> list[list[dict]]:
    """Group conflicts whose records are connected (e.g. three records about one parcel)."""
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for c in conflicts:
        a, b = c["record_ids"]
        parent[find(a)] = find(b)
    groups: dict[int, list[dict]] = defaultdict(list)
    for c in conflicts:
        groups[find(c["record_ids"][0])].append(c)
    return list(groups.values())


def as_issues(conflicts: list[dict], record_id: int) -> list[dict]:
    """Turn a record's conflicts into validation issues."""
    issues = []
    for c in conflicts:
        other = next(i for i in c["record_ids"] if i != record_id)
        if c["dismissed"]:
            issues.append({
                "code": f"{c['type']}_DISMISSED", "field": None, "severity": "info",
                "message": f"{c['label']} with record #{other} was reviewed and marked as not a problem"
                           f"{': ' + c['review']['note'] if c['review'] and c['review']['note'] else ''}.",
                "related_record_ids": [other], "conflict_key": c["key"],
            })
        else:
            issues.append({
                "code": c["type"], "field": None, "severity": c["severity"], "message": c["message"],
                "related_record_ids": [other], "conflict_key": c["key"],
            })
    return issues
