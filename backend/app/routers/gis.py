import json
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from shapely.geometry import mapping
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CadastralParcel, LandRecord
from ..schemas import RecordDetailOut
from ..services import gis
from ..services.gis_layer import import_feature_collection
from ..services.matching import places_match
from ..services.validation import validate_with_related

router = APIRouter(prefix="/api", tags=["gis"])

MAX_GEOJSON_BYTES = 20 * 1024 * 1024
MAP_ISSUE_CODES = {"MAP_PARCEL_NOT_FOUND", "AREA_MAP_MISMATCH", "INVALID_BOUNDARY",
                   "BOUNDARY_DIFFERS_FROM_MAP", "BOUNDARY_OVERLAP"}


class BoundaryIn(BaseModel):
    geometry: dict
    source: str = "drawn"


def _record_or_404(db: Session, record_id: int) -> LandRecord:
    record = db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(404, "Record not found.")
    return record


def _map_status(records: list[LandRecord]) -> str:
    active = [r for r in records if r.validation_status != "rejected"]
    if not active:
        return "unlinked"
    codes = {i["code"] for r in active for i in (r.validation_issues or [])}
    if codes & {"BOUNDARY_OVERLAP", "OWNER_CONFLICT", "INVALID_BOUNDARY"}:
        return "conflict"
    if codes & {"AREA_MAP_MISMATCH", "BOUNDARY_DIFFERS_FROM_MAP"} or any(r.validation_status == "flagged" for r in active):
        return "issue"
    if all(r.validation_status == "verified" for r in active):
        return "verified"
    return "linked"


@router.get("/gis/summary")
def gis_summary(db: Session = Depends(get_db)):
    records = db.scalars(select(LandRecord)).all()
    with_map_issue = [r for r in records if any(i["code"] in MAP_ISSUE_CODES and i["code"] != "MAP_PARCEL_NOT_FOUND"
                                                  for i in (r.validation_issues or []))]
    not_on_map = [r for r in records if any(i["code"] == "MAP_PARCEL_NOT_FOUND" for i in (r.validation_issues or []))]
    sources = db.execute(select(CadastralParcel.source, func.count()).group_by(CadastralParcel.source)).all()
    return {
        "parcels": sum(c for _, c in sources),
        "sources": [{"source": s, "parcels": c} for s, c in sources],
        "records_with_boundary": sum(1 for r in records if r.boundary),
        "records_with_map_issues": len(with_map_issue),
        "records_not_on_map": len(not_on_map),
    }


@router.get("/gis/layer")
def gis_layer(district: str | None = None, db: Session = Depends(get_db)):
    """Cadastral parcels as GeoJSON, each with the records linked to it and a map status."""
    parcels = db.scalars(select(CadastralParcel)).all()
    if district:
        parcels = [p for p in parcels if places_match(p.district, district)[0]]
    by_key: dict[str, list[LandRecord]] = defaultdict(list)
    keys = {p.survey_key for p in parcels}
    if keys:
        for r in db.scalars(select(LandRecord).where(LandRecord.survey_key.in_(keys))):
            by_key[r.survey_key].append(r)

    features = []
    for p in parcels:
        linked = [r for r in by_key.get(p.survey_key, [])
                  if places_match(r.village, p.village)[0] and places_match(r.district, p.district)[0]]
        features.append({
            "type": "Feature",
            "geometry": p.geometry,
            "properties": {
                "id": p.id, "survey_number": p.survey_number, "village": p.village, "district": p.district,
                "area_sqm": round(p.area_sqm, 1), "source": p.source, "map_status": _map_status(linked),
                "records": [{"id": r.id, "record_number": r.record_number, "owner_name": r.owner_name,
                             "validation_status": r.validation_status, "area_value": r.area_value,
                             "area_unit": r.area_unit} for r in linked],
            },
        })
    return {"type": "FeatureCollection", "features": features}


@router.get("/gis/boundaries")
def record_boundaries(db: Session = Depends(get_db)):
    """Boundaries drawn or uploaded for individual records."""
    features = []
    for r in db.scalars(select(LandRecord).where(LandRecord.boundary.is_not(None))):
        features.append({
            "type": "Feature", "geometry": r.boundary,
            "properties": {
                "record_id": r.id, "record_number": r.record_number, "owner_name": r.owner_name,
                "survey_number": r.survey_number, "validation_status": r.validation_status,
                "overlap": any(i["code"] == "BOUNDARY_OVERLAP" for i in (r.validation_issues or [])),
            },
        })
    return {"type": "FeatureCollection", "features": features}


@router.post("/gis/import")
async def import_layer(file: UploadFile = File(...), replace: bool = Form(True), db: Session = Depends(get_db)):
    name = Path(file.filename or "map.geojson").name
    if not name.lower().endswith((".geojson", ".json")):
        raise HTTPException(400, "Upload a GeoJSON file (.geojson or .json).")
    raw = await file.read(MAX_GEOJSON_BYTES + 1)
    if len(raw) > MAX_GEOJSON_BYTES:
        raise HTTPException(413, "Map file is larger than 20 MB.")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
        result = import_feature_collection(db, data, source=name, replace=replace)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "The file is not valid JSON.") from exc
    except gis.GeometryError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    from ..services.validation import recheck_all

    recheck_all(db)  # every record is checked against the new map
    return result


@router.get("/records/{record_id}/gis")
def record_gis(record_id: int, db: Session = Depends(get_db)):
    record = _record_or_404(db, record_id)
    report = gis.gis_report(db, record)
    report["record_boundary"] = record.boundary
    report["record_area_sqm"] = gis.record_area_sqm(record)
    return report


@router.put("/records/{record_id}/boundary", response_model=RecordDetailOut)
def set_boundary(record_id: int, payload: BoundaryIn, db: Session = Depends(get_db)):
    record = _record_or_404(db, record_id)
    try:
        geom = gis.parse_geometry(payload.geometry)
    except gis.GeometryError as exc:
        raise HTTPException(400, str(exc)) from exc
    record.boundary = mapping(geom)
    record.boundary_source = payload.source[:40] if payload.source in ("drawn", "uploaded", "map") else "drawn"
    validate_with_related(db, record, keep_officer_decision=True)
    db.commit()
    db.refresh(record)
    return record


@router.post("/records/{record_id}/boundary/from-map", response_model=RecordDetailOut)
def boundary_from_map(record_id: int, db: Session = Depends(get_db)):
    record = _record_or_404(db, record_id)
    parcel = gis.find_map_parcel(db, record)
    if parcel is None:
        raise HTTPException(404, "This record's parcel was not found on the cadastral map.")
    record.boundary, record.boundary_source = parcel.geometry, "map"
    validate_with_related(db, record, keep_officer_decision=True)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/records/{record_id}/boundary", response_model=RecordDetailOut)
def delete_boundary(record_id: int, db: Session = Depends(get_db)):
    record = _record_or_404(db, record_id)
    record.boundary = record.boundary_source = None
    validate_with_related(db, record, keep_officer_decision=True)
    db.commit()
    db.refresh(record)
    return record
