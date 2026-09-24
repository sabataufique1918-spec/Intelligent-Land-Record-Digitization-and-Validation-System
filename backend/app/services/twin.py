"""Parcel digital twin: every record about one parcel, on one ownership timeline.

Records are grouped into a parcel when they have the same survey number, village and
district (Hindi / English spellings matched, see matching.py). Dated records are put
in order and turned into an ownership chain:

- a record with previous_owner (sale deed, mutation, ...) is a TRANSFER from
  previous_owner to owner_name on document_date;
- any other record (Jamabandi, Khatauni, ...) STATES who the owner was on that date.

History checks:
- CHAIN_BREAK                    transfer from someone who was not the recorded owner then
- OWNER_CHANGE_WITHOUT_TRANSFER  owner changes with no transfer document on file
- MUTATION_PENDING               record of rights still shows the old owner after a transfer
- UNDATED_RECORD                 record cannot be placed on the timeline (no date)

This is rule-based reasoning over the records in this system only; it does not consult
registration or revenue department databases.
"""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LandRecord
from .matching import names_match, places_match

RECORD_OF_RIGHTS_TYPES = {"Jamabandi / Record of Rights", "Khatauni", "Khasra / Field Book"}


def _ref(r: LandRecord) -> str:
    return r.record_number or f"#{r.id}"


def _d(value) -> str:
    return value.isoformat() if value else "undated"


def same_person(a: str | None, b: str | None) -> bool:
    return names_match(a, b)[0]


def same_parcel(a: LandRecord, b: LandRecord) -> bool:
    return (bool(a.survey_key) and a.survey_key == b.survey_key
            and places_match(a.village, b.village)[0] and places_match(a.district, b.district)[0])


def is_transfer(r: LandRecord) -> bool:
    return bool(r.previous_owner and r.previous_owner.strip())


# ------------------------------------------------------------ grouping

def parcel_group(db: Session, record: LandRecord) -> list[LandRecord]:
    """All records (including rejected) about the same parcel as `record`."""
    if not record.survey_key:
        return [record]
    candidates = db.scalars(select(LandRecord).where(LandRecord.survey_key == record.survey_key)).all()
    group = [r for r in candidates if r.id == record.id or same_parcel(record, r)]
    if record.id is None or all(r.id != record.id for r in group):
        group.append(record)
    return group


def all_parcel_groups(db: Session) -> list[list[LandRecord]]:
    blocks: dict[str, list[LandRecord]] = defaultdict(list)
    singles = []
    for r in db.scalars(select(LandRecord).order_by(LandRecord.id)):
        (blocks[r.survey_key].append(r) if r.survey_key else singles.append([r]))
    groups = []
    for block in blocks.values():
        remaining = list(block)
        while remaining:
            seed = remaining.pop(0)
            group, rest = [seed], []
            for r in remaining:
                (group if any(same_parcel(g, r) for g in group) else rest).append(r)
            remaining = rest
            groups.append(group)
    return groups + singles


# ------------------------------------------------------------ timeline

def build_timeline(records: list[LandRecord]) -> dict:
    active = [r for r in records if r.validation_status != "rejected"]
    dated = sorted((r for r in active if r.document_date), key=lambda r: (r.document_date, r.id))
    undated = [r for r in active if not r.document_date]
    chain: list[dict] = []
    issues: list[dict] = []
    current: dict | None = None

    def issue(code, severity, message, record_ids):
        issues.append({"code": code, "severity": severity, "message": message, "record_ids": record_ids})

    def close(period, until):
        period["to"] = until
        chain.append(period)

    for r in dated:
        if is_transfer(r):
            broken = False
            if current is None:
                # The seller is only known from this document.
                chain.append({"owner": r.previous_owner, "from": None, "to": r.document_date, "via": "named as seller",
                              "record_ids": [r.id], "broken": False})
            elif not same_person(r.previous_owner, current["owner"]):
                broken = True
                issue("CHAIN_BREAK", "error",
                      f"{_ref(r)} ({_d(r.document_date)}) records a transfer from '{r.previous_owner}', but the recorded "
                      f"owner at that time was '{current['owner']}' (since {_d(current['from'])}). The seller may not "
                      "have had the right to transfer this land.",
                      [r.id] + current["record_ids"])
                close(current, r.document_date)
            else:
                close(current, r.document_date)
            current = {"owner": r.owner_name, "from": r.document_date, "to": None, "via": "transfer",
                       "transfer_record_id": r.id, "document_type": r.document_type,
                       "record_ids": [r.id], "broken": broken}
        else:
            if current and same_person(r.owner_name, current["owner"]):
                current["record_ids"].append(r.id)  # confirms the current owner
                continue
            if current:
                issue("OWNER_CHANGE_WITHOUT_TRANSFER", "warning",
                      f"{_ref(r)} ({_d(r.document_date)}) shows '{r.owner_name}' as owner, but no transfer from "
                      f"'{current['owner']}' is on file.",
                      [r.id] + current["record_ids"])
                close(current, r.document_date)
            current = {"owner": r.owner_name, "from": r.document_date, "to": None, "via": "record",
                       "record_ids": [r.id], "broken": bool(current)}
    if current:
        chain.append(current)

    # Record of rights not updated after the latest transfer.
    if current and current["via"] == "transfer" and not current["broken"]:
        transfer_id = current["transfer_record_id"]
        confirmed = any(r.id in current["record_ids"] and r.document_type in RECORD_OF_RIGHTS_TYPES for r in dated)
        if not confirmed:
            transfer = next(r for r in dated if r.id == transfer_id)
            for r in active:
                if (r.document_type in RECORD_OF_RIGHTS_TYPES and r.id != transfer_id
                        and not same_person(r.owner_name, current["owner"])):
                    issue("MUTATION_PENDING", "warning",
                          f"Record of rights {_ref(r)} still shows '{r.owner_name}', but {_ref(transfer)} "
                          f"({transfer.document_type}, {_d(transfer.document_date)}) transferred the parcel to "
                          f"'{current['owner']}'. Mutation may be pending.",
                          [r.id, transfer_id])

    for r in undated:
        issue("UNDATED_RECORD", "info",
              f"{_ref(r)} has no document date, so it is not placed on the ownership timeline.", [r.id])

    owner = None
    if current:
        owner = {"name": current["owner"], "since": current["from"], "via": current["via"],
                 "record_ids": current["record_ids"], "broken_chain": any(p["broken"] for p in chain)}
    elif undated:
        names = {r.owner_name for r in undated if r.owner_name}
        if len(names) == 1 or all(same_person(n, next(iter(names))) for n in names):
            owner = {"name": undated[0].owner_name, "since": None, "via": "undated record",
                     "record_ids": [r.id for r in undated], "broken_chain": False}
    return {"chain": chain, "current_owner": owner, "issues": issues}


def owners_linked_by_transfers(records: list[LandRecord], a: LandRecord, b: LandRecord) -> list[int] | None:
    """If a's and b's owners are consecutive or connected through unbroken transfers, return the
    transfer record ids that link them (used to explain owner 'conflicts')."""
    chain = build_timeline(records)["chain"]

    def period_of(r):
        return next((i for i, p in enumerate(chain) if r.id in p["record_ids"]), None)

    ia, ib = period_of(a), period_of(b)
    if ia is None or ib is None or ia == ib:
        return None
    lo, hi = sorted((ia, ib))
    steps = chain[lo + 1:hi + 1]
    if all(p["via"] == "transfer" and not p["broken"] for p in steps):
        return [p["transfer_record_id"] for p in steps]
    return None


def record_issues(db: Session, record: LandRecord) -> list[dict]:
    """Timeline issues that involve this record, as validation issues."""
    if record.validation_status == "rejected":
        return []
    out = []
    for i in build_timeline(parcel_group(db, record))["issues"]:
        if record.id in i["record_ids"]:
            others = [x for x in i["record_ids"] if x != record.id]
            out.append({"code": i["code"], "field": "document_date" if i["code"] == "UNDATED_RECORD" else None,
                        "severity": i["severity"], "message": i["message"], "related_record_ids": others})
    return out
