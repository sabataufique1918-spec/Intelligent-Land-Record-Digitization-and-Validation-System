"""Cadastral map (GIS) verification.

Parcel boundaries are stored as GeoJSON (WGS84 longitude/latitude) and computed
with Shapely in Python. Areas use a local equal-distance projection around the
parcel, which is accurate to well under 1 % for parcels of a few km. PostGIS is
not used yet (planned for large map layers).

Checks for a record (see gis_issues):
- MAP_PARCEL_NOT_FOUND       survey no. / village / district not on the loaded map
- AREA_MAP_MISMATCH          recorded area differs from the map parcel area by > 10 %
- INVALID_BOUNDARY           the record's own boundary is not a valid polygon
- BOUNDARY_DIFFERS_FROM_MAP  record boundary overlaps its map parcel by < 80 % (IoU)
- BOUNDARY_OVERLAP           record boundary overlaps another parcel's record boundary
"""

import math

from shapely.geometry import shape
from shapely.validation import explain_validity
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CadastralParcel, LandRecord
from .matching import TO_HECTARE, normalize_survey, places_match

EARTH_RADIUS_M = 6_371_008.8
AREA_TOLERANCE = 0.10          # 10 % (maps and records are both approximate)
BOUNDARY_MATCH_IOU = 0.80
OVERLAP_MIN_SHARE = 0.05       # ignore slivers below 5 % of the smaller parcel
MAX_VERTICES = 5000


class GeometryError(ValueError):
    pass


def parse_geometry(geojson: dict):
    """Validate a GeoJSON Polygon / MultiPolygon in lon/lat and return a Shapely geometry."""
    if not isinstance(geojson, dict) or geojson.get("type") not in ("Polygon", "MultiPolygon"):
        raise GeometryError("Boundary must be a GeoJSON Polygon or MultiPolygon.")
    try:
        geom = shape(geojson)
    except Exception as exc:  # malformed coordinates
        raise GeometryError(f"Invalid GeoJSON geometry: {exc}") from exc
    if geom.is_empty:
        raise GeometryError("Boundary is empty.")
    min_x, min_y, max_x, max_y = geom.bounds
    if not (-180 <= min_x <= max_x <= 180 and -90 <= min_y <= max_y <= 90):
        raise GeometryError("Coordinates must be longitude/latitude in degrees (WGS84).")
    if _vertex_count(geom) > MAX_VERTICES:
        raise GeometryError(f"Boundary has too many points (max {MAX_VERTICES}).")
    if not geom.is_valid:
        raise GeometryError(f"Boundary is not a valid polygon: {explain_validity(geom)}.")
    return geom


def _vertex_count(geom) -> int:
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    return sum(len(p.exterior.coords) + sum(len(i.coords) for i in p.interiors) for p in polys)


def _to_local_metres(geom, lat0: float, lon0: float):
    """Project lon/lat to metres around (lat0, lon0) - equirectangular, fine for small areas."""
    from shapely.ops import transform

    k = math.cos(math.radians(lat0))

    def fn(x, y, z=None):
        return ((x - lon0) * math.pi / 180 * EARTH_RADIUS_M * k, (y - lat0) * math.pi / 180 * EARTH_RADIUS_M)

    return transform(fn, geom)


def area_sqm(geom) -> float:
    c = geom.centroid
    return _to_local_metres(geom, c.y, c.x).area


def overlap_stats(a, b) -> dict:
    """Intersection area and IoU in square metres for two lon/lat geometries."""
    c = a.centroid
    pa, pb = _to_local_metres(a, c.y, c.x), _to_local_metres(b, c.y, c.x)
    inter = pa.intersection(pb).area if pa.intersects(pb) else 0.0
    union = pa.union(pb).area
    return {
        "intersection_sqm": inter,
        "iou": inter / union if union else 0.0,
        "share_of_smaller": inter / min(pa.area, pb.area) if min(pa.area, pb.area) else 0.0,
    }


def record_area_sqm(record: LandRecord) -> float | None:
    if record.area_value is None or record.area_unit not in TO_HECTARE:
        return None  # Bigha etc. vary by state and are not converted
    return float(record.area_value) * TO_HECTARE[record.area_unit] * 10_000


def format_area(sqm: float) -> str:
    return f"{sqm / 10_000:.3f} ha ({sqm:,.0f} m²)"


# ------------------------------------------------------------ map lookups

def layer_loaded(db: Session) -> bool:
    return db.scalar(select(CadastralParcel.id).limit(1)) is not None


def find_map_parcel(db: Session, record: LandRecord) -> CadastralParcel | None:
    key = record.survey_key or normalize_survey(record.survey_number)
    if not key or not record.village or not record.district:
        return None
    for parcel in db.scalars(select(CadastralParcel).where(CadastralParcel.survey_key == key)):
        if places_match(record.village, parcel.village)[0] and places_match(record.district, parcel.district)[0]:
            return parcel
    return None


def _same_parcel(a: LandRecord, b: LandRecord) -> bool:
    return (bool(a.survey_key) and a.survey_key == b.survey_key
            and places_match(a.village, b.village)[0] and places_match(a.district, b.district)[0])


def boundary_overlaps(db: Session, record: LandRecord, geom) -> list[dict]:
    """Other (non-rejected) records whose boundary overlaps this one but describe a different parcel."""
    min_x, min_y, max_x, max_y = geom.bounds
    found = []
    stmt = select(LandRecord).where(LandRecord.boundary.is_not(None), LandRecord.validation_status != "rejected")
    if record.id is not None:
        stmt = stmt.where(LandRecord.id != record.id)
    for other in db.scalars(stmt):
        if _same_parcel(record, other):
            continue  # records about the same parcel are expected to overlap
        try:
            other_geom = parse_geometry(other.boundary)
        except GeometryError:
            continue
        ox1, oy1, ox2, oy2 = other_geom.bounds
        if ox1 > max_x or ox2 < min_x or oy1 > max_y or oy2 < min_y:
            continue  # bounding boxes do not touch
        stats = overlap_stats(geom, other_geom)
        if stats["share_of_smaller"] >= OVERLAP_MIN_SHARE:
            found.append({"record": other, **stats})
    return found


# ------------------------------------------------------------ checks

def gis_report(db: Session, record: LandRecord) -> dict:
    """Everything the record page's map panel shows, plus the issues."""
    issues: list[dict] = []
    report = {"layer_loaded": layer_loaded(db), "map_parcel": None, "boundary": None, "issues": issues}

    def add(code, field, severity, message, related=None):
        issue = {"code": code, "field": field, "severity": severity, "message": message}
        if related:
            issue["related_record_ids"] = related
        issues.append(issue)

    parcel = find_map_parcel(db, record) if report["layer_loaded"] else None
    rec_area = record_area_sqm(record)
    if parcel:
        report["map_parcel"] = {
            "id": parcel.id, "survey_number": parcel.survey_number, "village": parcel.village,
            "district": parcel.district, "area_sqm": round(parcel.area_sqm, 1), "source": parcel.source,
            "geometry": parcel.geometry,
        }
        if rec_area:
            diff = abs(rec_area - parcel.area_sqm) / max(rec_area, parcel.area_sqm)
            report["map_parcel"]["area_difference_pct"] = round(diff * 100, 1)
            if diff > AREA_TOLERANCE:
                add("AREA_MAP_MISMATCH", "area_value", "warning",
                    f"Recorded area {record.area_value} {record.area_unit} = {format_area(rec_area)} differs by "
                    f"{diff * 100:.0f}% from the cadastral map parcel ({format_area(parcel.area_sqm)}).")
    elif report["layer_loaded"] and record.survey_number and record.village and record.district:
        add("MAP_PARCEL_NOT_FOUND", "survey_number", "info",
            f"Survey {record.survey_number} in {record.village}, {record.district} was not found on the cadastral map.")

    if record.boundary:
        try:
            geom = parse_geometry(record.boundary)
        except GeometryError as exc:
            add("INVALID_BOUNDARY", None, "error", f"The record's boundary is invalid: {exc}")
            return report
        b_area = area_sqm(geom)
        report["boundary"] = {"area_sqm": round(b_area, 1), "source": record.boundary_source}
        if parcel:
            stats = overlap_stats(geom, shape(parcel.geometry))
            report["boundary"]["iou_with_map"] = round(stats["iou"] * 100, 1)
            if stats["iou"] < BOUNDARY_MATCH_IOU:
                add("BOUNDARY_DIFFERS_FROM_MAP", None, "warning",
                    f"The record's boundary matches the cadastral map parcel only {stats['iou'] * 100:.0f}% "
                    f"(intersection over union; {BOUNDARY_MATCH_IOU * 100:.0f}% expected).")
        overlaps = boundary_overlaps(db, record, geom)
        report["boundary"]["overlaps"] = [
            {"record_id": o["record"].id, "record_number": o["record"].record_number,
             "owner_name": o["record"].owner_name, "survey_number": o["record"].survey_number,
             "overlap_sqm": round(o["intersection_sqm"], 1)} for o in overlaps
        ]
        for o in overlaps:
            other = o["record"]
            add("BOUNDARY_OVERLAP", None, "error",
                f"Boundary overlaps {other.record_number} (survey {other.survey_number}, "
                f"{other.owner_name or 'unknown owner'}) by {o['intersection_sqm']:,.0f} m² "
                f"({o['share_of_smaller'] * 100:.0f}% of the smaller parcel).",
                related=[other.id])
    return report


def gis_issues(db: Session, record: LandRecord) -> list[dict]:
    return gis_report(db, record)["issues"]
