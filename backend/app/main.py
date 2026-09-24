import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import CORS_ORIGINS, RECHECK_ON_STARTUP, SEED_SAMPLE_DATA
from .database import Base, SessionLocal, add_missing_columns, engine
from .routers import conflicts, dashboard, gis, ocr, parcels, records
from .seed import seed_sample_data
from .services.gis_layer import seed_sample_layer
from .services.validation import recheck_all

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    added = add_missing_columns()
    if added:
        logger.info("Added database columns: %s", ", ".join(added))
    if SEED_SAMPLE_DATA:
        with SessionLocal() as db:
            count = seed_sample_data(db)
            if count:
                logger.info("Inserted %d sample land records.", count)
            parcels = seed_sample_layer(db)
            if parcels:
                logger.info("Loaded %d fictional sample map parcels.", parcels)
    if RECHECK_ON_STARTUP:
        # Brings existing records up to date with the current rules (e.g. after an upgrade).
        with SessionLocal() as db:
            logger.info("Re-checked %d records for conflicts.", recheck_all(db))
    yield


app = FastAPI(
    title="Land Record Digitization & Validation API",
    description="SIH26018. Upload, storage, Tesseract OCR for printed text, pattern-based field "
                "suggestions, confidence scoring, optional Claude AI extraction, rule-based checks, "
                "cross-record conflict detection, cadastral map (GIS) checks, parcel ownership timelines "
                "(digital twin) and officer review. "
                "Handwriting recognition and government database / real cadastral map integration "
                "are not implemented yet.",
    version="0.6.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(records.router)
app.include_router(ocr.router)
app.include_router(conflicts.router)
app.include_router(gis.router)
app.include_router(parcels.router)


@app.get("/api/health", tags=["system"])
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": engine.dialect.name}
