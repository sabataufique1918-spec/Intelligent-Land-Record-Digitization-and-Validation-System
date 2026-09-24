"""Importing cadastral map layers (GeoJSON) and the fictional sample layer."""

import math

from shapely.geometry import mapping
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import CadastralParcel, LandRecord
from .gis import GeometryError, area_sqm, parse_geometry
from .matching import normalize_survey

SAMPLE_SOURCE = "Sample map (fictional)"

# Accepted property names (case-insensitive) in imported GeoJSON features.
SURVEY_KEYS = ["survey_number", "survey_no", "surveyno", "sy_no", "khasra", "khasra_no", "khasra_number",
               "plot_no", "gat_no", "dag_no", "parcel_no"]
VILLAGE_KEYS = ["village", "village_name", "mauza", "gram"]
DISTRICT_KEYS = ["district", "district_name", "dist"]
MAX_FEATURES = 20_000


def _prop(props: dict, keys: list[str]) -> str | None:
    lower = {str(k).lower(): v for k, v in props.items()}
    for key in keys:
        value = lower.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return None


def import_feature_collection(db: Session, data: dict, source: str, replace: bool = True) -> dict:
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise GeometryError("File must be a GeoJSON FeatureCollection.")
    features = data.get("features") or []
    if len(features) > MAX_FEATURES:
        raise GeometryError(f"Too many features ({len(features)}); the limit is {MAX_FEATURES}.")
    if replace:
        db.execute(delete(CadastralParcel).where(CadastralParcel.source == source))

    imported, skipped = 0, []
    for index, feature in enumerate(features):
        props = (feature or {}).get("properties") or {}
        survey = _prop(props, SURVEY_KEYS)
        if not survey:
            skipped.append({"feature": index, "reason": "no survey / khasra number property"})
            continue
        try:
            geom = parse_geometry((feature or {}).get("geometry"))
        except GeometryError as exc:
            skipped.append({"feature": index, "reason": str(exc)})
            continue
        min_x, min_y, max_x, max_y = geom.bounds
        db.add(CadastralParcel(
            survey_number=survey, survey_key=normalize_survey(survey),
            village=_prop(props, VILLAGE_KEYS), district=_prop(props, DISTRICT_KEYS),
            geometry=mapping(geom), area_sqm=area_sqm(geom),
            min_lon=min_x, min_lat=min_y, max_lon=max_x, max_lat=max_y,
            source=source, properties=props,
        ))
        imported += 1
    db.flush()
    return {"source": source, "imported": imported, "skipped": skipped[:50], "skipped_count": len(skipped)}


# ------------------------------------------------------------ sample layer

def _rect(lat0: float, lon0: float, x: float, y: float, w: float, h: float) -> dict:
    """Rectangle w x h metres whose south-west corner is x, y metres east / north of (lat0, lon0)."""
    m_per_deg_lat = math.pi / 180 * 6_371_008.8
    m_per_deg_lon = m_per_deg_lat * math.cos(math.radians(lat0))

    def pt(dx, dy):
        return [round(lon0 + dx / m_per_deg_lon, 7), round(lat0 + dy / m_per_deg_lat, 7)]

    return {"type": "Polygon", "coordinates": [[pt(x, y), pt(x + w, y), pt(x + w, y + h), pt(x, y + h), pt(x, y)]]}


# (village, district, origin lat, origin lon, [(survey, x, y, w, h), ...])
# Placeholder locations and sizes chosen to match the fictional sample records - not real parcels.
_SAMPLE_VILLAGES = [
    ("Rampur", "Lucknow", 26.7800, 80.9000, [
        ("110", 0, 0, 80, 100), ("111", 80, 0, 90, 100), ("112/3", 170, 0, 101.17, 100), ("113", 271.17, 0, 70, 100),
        ("87", 0, 100, 120, 100), ("64/2", 120, 100, 90, 100),  # 0.9 ha on the map vs 0.6 ha in the record
        ("238/2", 210, 100, 125, 100), ("239", 335, 100, 60, 100),
    ]),
    ("Kheri", "Mohali", 30.6500, 76.7000, [
        ("23/1", 0, 0, 63.6, 63.63), ("56", 63.6, 0, 45, 44.96), ("57", 108.6, 0, 50, 40),
    ]),
    ("Wadgaon", "Pune", 18.4700, 73.8000, [
        ("19/2", 0, 0, 35, 34.69), ("402/7", 35, 0, 25, 24.28), ("403", 60, 0, 30, 30),
    ]),
    ("Thirumalai", "Krishnagiri", 12.5200, 78.2100, [
        ("301A", 0, 0, 80, 100), ("215", 80, 0, 70, 86.71),
    ]),
    ("Chandpur", "Patna", 25.5000, 85.1000, [
        ("9", 0, 0, 80, 60), ("10", 80, 0, 60, 60),
    ]),
]


def sample_feature_collection() -> dict:
    features = []
    for village, district, lat0, lon0, parcels in _SAMPLE_VILLAGES:
        for survey, x, y, w, h in parcels:
            features.append({
                "type": "Feature",
                "properties": {"survey_number": survey, "village": village, "district": district,
                               "note": "Fictional sample parcel for testing"},
                "geometry": _rect(lat0, lon0, x, y, w, h),
            })
    return {"type": "FeatureCollection", "name": SAMPLE_SOURCE, "features": features}


def _demo_boundary(db: Session, owner: str, survey: str, geometry: dict) -> None:
    record = db.scalar(select(LandRecord).where(
        LandRecord.is_sample.is_(True), LandRecord.owner_name == owner, LandRecord.survey_number == survey))
    if record is not None and record.boundary is None:
        record.boundary, record.boundary_source = geometry, "sample"


def seed_sample_layer(db: Session) -> int:
    """Load the fictional map layer (and two demo boundaries) if no map layer exists yet."""
    if db.scalar(select(CadastralParcel.id).limit(1)) is not None:
        return 0
    result = import_feature_collection(db, sample_feature_collection(), SAMPLE_SOURCE)
    lat0, lon0 = 26.7800, 80.9000
    # Ramesh Kumar's boundary equals the map parcel 112/3.
    _demo_boundary(db, "Ramesh Kumar", "112/3", _rect(lat0, lon0, 170, 0, 101.17, 100))
    # Pooja Yadav's boundary is drawn 40 m too far south: it overlaps parcel 112/3.
    _demo_boundary(db, "Pooja Yadav", "64/2", _rect(lat0, lon0, 120, 60, 90, 100))
    db.commit()
    return result["imported"]
