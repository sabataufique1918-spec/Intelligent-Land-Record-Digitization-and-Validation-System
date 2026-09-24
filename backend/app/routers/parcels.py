from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import LandRecord
from ..schemas import RecordOut
from ..services import gis, twin
from ..services.matching import normalize_text

router = APIRouter(prefix="/api/parcels", tags=["parcels"])
SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}


def _display_record(group: list[LandRecord]) -> LandRecord:
    """Record whose survey no. / village / district are shown as the parcel's name (prefer Latin script)."""
    active = [r for r in group if r.validation_status != "rejected"] or group
    latin = [r for r in active if (r.village or "").isascii()]
    return min(latin or active, key=lambda r: r.id)


def _event(r: LandRecord, current_owner: dict | None) -> dict:
    kind = "transfer" if twin.is_transfer(r) else (
        "record_of_rights" if r.document_type in twin.RECORD_OF_RIGHTS_TYPES else "other")
    return {
        "record_id": r.id, "record_number": r.record_number, "date": r.document_date,
        "document_type": r.document_type, "kind": kind, "owner_name": r.owner_name,
        "previous_owner": r.previous_owner, "area_value": r.area_value, "area_unit": r.area_unit,
        "area_sqm": gis.record_area_sqm(r), "validation_status": r.validation_status, "is_sample": r.is_sample,
        "is_current_owner": bool(current_owner and r.owner_name and twin.same_person(r.owner_name, current_owner["name"])),
    }


def _summary(group: list[LandRecord]) -> dict:
    timeline = twin.build_timeline(group)
    head = _display_record(group)
    dates = [r.document_date for r in group if r.document_date]
    worst = min((i["severity"] for i in timeline["issues"] if i["severity"] != "info"),
                key=SEVERITY_RANK.get, default=None)
    return {
        "id": min(r.id for r in group),
        "survey_number": head.survey_number, "village": head.village, "district": head.district,
        "current_owner": timeline["current_owner"],
        "records": len(group),
        "transfers": sum(1 for r in group if twin.is_transfer(r) and r.validation_status != "rejected"),
        "first_date": min(dates) if dates else None, "last_date": max(dates) if dates else None,
        "issue_count": sum(1 for i in timeline["issues"] if i["severity"] != "info"),
        "worst_severity": worst,
    }


@router.get("")
def list_parcels(q: str | None = None, db: Session = Depends(get_db)):
    groups = twin.all_parcel_groups(db)
    items = [_summary(g) for g in groups]
    if q and q.strip():
        term = normalize_text(q)
        items = [
            i for i, g in zip(items, groups)
            if any(term in normalize_text(" ".join(filter(None, [r.survey_number, r.village, r.district, r.owner_name,
                                                                   r.previous_owner, r.record_number])))
                   for r in g)
        ]
    items.sort(key=lambda i: (SEVERITY_RANK.get(i["worst_severity"], 3), -(i["records"]), i["id"]))
    return {"items": items, "total": len(items)}


@router.get("/by-record/{record_id}")
def parcel_twin(record_id: int, db: Session = Depends(get_db)):
    record = db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(404, "Record not found.")
    group = twin.parcel_group(db, record)
    timeline = twin.build_timeline(group)
    head = _display_record(group)
    active = [r for r in group if r.validation_status != "rejected"]

    map_parcel = None
    for r in active or group:
        parcel = gis.find_map_parcel(db, r)
        if parcel:
            map_parcel = {"id": parcel.id, "survey_number": parcel.survey_number, "area_sqm": round(parcel.area_sqm, 1),
                          "geometry": parcel.geometry, "source": parcel.source}
            break

    events = sorted((_event(r, timeline["current_owner"]) for r in group),
                    key=lambda e: (e["date"] is None, e["date"] or "", e["record_id"]))
    refs = {r.id: r.record_number for r in group}
    for i in timeline["issues"]:
        i["record_numbers"] = [refs.get(x, f"#{x}") for x in i["record_ids"]]
    for p in timeline["chain"]:
        p["record_numbers"] = [refs.get(x, f"#{x}") for x in p["record_ids"]]

    return {
        **_summary(group),
        "map_parcel": map_parcel,
        "boundaries": [{"record_id": r.id, "record_number": r.record_number, "geometry": r.boundary}
                       for r in active if r.boundary],
        "chain": timeline["chain"],
        "events": events,
        "issues": sorted(timeline["issues"], key=lambda i: SEVERITY_RANK[i["severity"]]),
        "records_detail": [RecordOut.model_validate(r) for r in sorted(group, key=lambda r: r.id)],
        "focus_record_id": record_id,
    }
