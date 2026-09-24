# Intelligent Land Record Digitization and Validation System (SIH26018)

Version 0.6 of an officer dashboard for digitizing and validating land records.

- **Frontend:** React 19 + Vite 7 (`frontend/`)
- **Backend:** Python + FastAPI + SQLAlchemy (`backend/`)
- **Database:** PostgreSQL

## What works in this version

| Feature | Status |
|---|---|
| Upload PDF / JPG / PNG (type, content and size checks, stored on disk) | Working |
| Manual entry of record details (owner, survey no., khata, village, district, area, …) | Working |
| **Multilingual OCR** of printed text (Tesseract 5) in English, Hindi, Marathi, Punjabi, Bengali, Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam, Urdu. PDFs with a text layer are read directly; scanned PDFs (up to 10 pages) and images are OCR'd | Basic |
| Field suggestions from OCR text by label matching (e.g. "खसरा संख्या", "Village", "जिल्हा"); the user reviews and applies them | Basic |
| Survey / khata numbers entered by the user checked against the OCR text | Basic |
| Search inside OCR text | Working |
| **Confidence engine**: 0-100 score and "Why?" explanation for every extracted field (OCR word confidence, how the value was found, format check, label/AI agreement). Entered values that differ from a high-confidence document value are flagged | Basic |
| **Cadastral map (GIS) verification** (Cadastral Map page + map on each record): import a GeoJSON parcel layer; checks whether the survey no. is on the map, recorded area vs map area (>10 % = warning), drawn/uploaded record boundary vs map parcel (<80 % overlap = warning) and boundary overlaps between records of different parcels (error). Draw / edit / upload boundaries on the map | Basic |
| **Parcel history / digital twin** (Parcel History page): all records of a parcel (Hindi/English matched), its map parcel and boundaries, a dated ownership chain and the derived current owner. Flags broken chains (seller was not the recorded owner), owner changes without a transfer, pending mutations and undated records. Different owners linked by valid transfers become an "Ownership transfer" (info) instead of an owner conflict | Basic |
| **AI field extraction with Claude** (Anthropic API), incl. document-type suggestion. Every AI value is checked against the document text; values not found there score low. **Off by default**, needs an API key | Built, off by default |
| Uploaded records list with filters and pagination | Working |
| Record search (owner, father's name, survey no., khata no., village, tehsil, record no., file name) | Working |
| Rule-based validation: required fields, survey-number format, area range | Basic |
| **Cross-record conflict detection** (Conflicts page): owner conflicts, possible duplicates (exact, spelling variant, or Hindi↔English name match), area mismatch after unit conversion, khata mismatch, identical document uploaded twice. Both records are updated, and officers can mark a conflict as "not a conflict" with a note | Basic |
| Validation status page and officer review (verify / reject / send back, with note) | Working |
| Dashboard with summary cards, status breakdown, records by district and document type | Working |
| 12 fictional sample records seeded on first start | Working |

## Not implemented yet

These modules from the target architecture **do not work yet**. The dashboard marks them as "Planned".

- Document classifier (document type is picked manually)
- Image quality enhancement beyond grayscale / auto-contrast / upscaling (no OpenCV deskew, denoise or super-resolution)
- Handwriting recognition (Tesseract only handles printed text)
- Layout understanding (tables / regions are not detected; text is read line by line)
- AI extraction has only been tested against a simulated API response, because no Anthropic API key was available during development
- Confidence engine
- Real cadastral maps: only a **fictional sample layer** is included; real state Bhu-Naksha / survey data must be obtained and imported as GeoJSON (WGS84). Other formats (Shapefile, KML, DXF) and map projections are not supported yet
- PostGIS: geometry is stored as GeoJSON and checked in Python (Shapely); fine for thousands of parcels, PostGIS spatial indexes are needed for state-scale layers
- Government database integration
- Ownership history uses only records in this system; it does not query registration (IGRS) or revenue department databases, and partitions / joint ownership shares are not modelled yet
- Hindi↔English name matching covers Devanagari only (Hindi, Marathi); Tamil, Bengali and other scripts are compared only exactly or by spelling
- User login and roles

## Project structure

```
backend/
  app/
    main.py              FastAPI app, startup (creates tables, seeds sample data)
    config.py            Settings read from backend/.env
    database.py          SQLAlchemy engine/session
    models.py            LandRecord table
    schemas.py           API schemas, document types, statuses
    seed.py              Fictional sample records
    routers/records.py   Upload, list/search, detail, edit, validate, review, file download
    routers/dashboard.py Dashboard summary
    services/validation.py  Rule-based checks (+ refreshes related records)
    services/conflicts.py   Cross-record conflict detection
    services/matching.py    Survey-number / name / place normalisation, unit conversion
    routers/conflicts.py    Conflict list, dismiss / restore, re-check
    services/gis.py         Geometry validation, areas, map checks, overlaps
    services/gis_layer.py   GeoJSON import and the fictional sample map
    routers/gis.py          Map layer, boundaries, import, per-record GIS report
    services/twin.py        Parcel grouping, ownership chain and history checks
    routers/parcels.py      Parcel list and digital-twin view
    services/ocr.py         Tesseract OCR (images, scanned and text PDFs)
    services/extraction.py  Label-matching field suggestions from OCR text
    services/ai_extraction.py  Optional Claude field extraction
    services/confidence.py  Per-field confidence scores
    routers/ocr.py          OCR status and preview endpoints
    services/storage.py     Upload checks and file storage
    services/pipeline.py    Honest status of each architecture stage
  uploads/               Uploaded files (created automatically)
  tessdata/              OCR language models (downloaded, not in git)
  scripts/download_ocr_languages.py
  requirements.txt
  .env.example
frontend/
  src/pages/             Dashboard, Upload, Records, RecordDetail, Validation, Search
  src/components/        Layout, shared UI, record form
  src/api.js             API client
  vite.config.js         Dev server + /api proxy to the backend
docker-compose.yml       Optional PostgreSQL container
samples/                 Fictional test documents for OCR and a fictional sample cadastral map (GeoJSON)
```

## Setup (Windows)

### 1. Install prerequisites

- **Python 3.11 or newer** (tested with 3.14)
- **Node.js 22 LTS or newer** from https://nodejs.org (includes `npm`). Close and reopen VS Code after installing.
- **PostgreSQL 16 or newer** from https://www.postgresql.org/download/windows/.
  During installation, set a password for the `postgres` user and keep port `5432`.
  (Alternative: if you have Docker Desktop, run `docker compose up -d` in the project root instead.)

- **Tesseract OCR 5** (for OCR). Install with:
  ```powershell
  winget install --id UB-Mannheim.TesseractOCR
  ```
  The backend finds it in `C:\Program Files\Tesseract-OCR` automatically (or set `TESSERACT_CMD` in `.env`).

### 2. Create the database (skip if using Docker)

Open **SQL Shell (psql)** from the Start menu, log in as `postgres`, then run:

```sql
CREATE DATABASE land_records;
```

The tables are created automatically when the backend starts.

### 3. Backend

In a VS Code terminal (PowerShell), from the project folder:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

If `Activate.ps1` is blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again.

Download the OCR language models (about 120 MB for all 12 languages) into `backend\tessdata`:

```powershell
python scripts\download_ocr_languages.py            # all languages
python scripts\download_ocr_languages.py hin mar    # or only some (English is always added)
```

Edit `backend\.env` and put your PostgreSQL password in `DATABASE_URL`:

```
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/land_records
```

Start the API:

```powershell
uvicorn app.main:app --reload --port 8000 --timeout-graceful-shutdown 3 --reload-dir app
```

Check http://127.0.0.1:8000/api/health. It should return `{"status":"ok","database":"postgresql"}`.
Interactive API docs: http://127.0.0.1:8000/docs

> **Port already in use?** If something else is using port 8000, start the backend on another port
> (e.g. `--port 8010`) and create `frontend\.env` containing `VITE_BACKEND_URL=http://127.0.0.1:8010`.

### 4. Frontend

In a **second** terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### Running again later

```powershell
# Terminal 1
cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000 --timeout-graceful-shutdown 3 --reload-dir app
# Terminal 2
cd frontend; npm run dev
```

## Configuration (`backend/.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/land_records` | Database connection |
| `UPLOAD_DIR` | `uploads` | Folder for uploaded files |
| `MAX_UPLOAD_MB` | `20` | Maximum upload size |
| `SEED_SAMPLE_DATA` | `true` | Insert sample records when the table is empty |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed frontend origins |
| `TESSERACT_CMD` | *(auto-detect)* | Path to `tesseract.exe` |
| `TESSDATA_DIR` | `tessdata` | Folder with `*.traineddata` language models |
| `OCR_MAX_PAGES` | `10` | Maximum PDF pages read per document |
| `OCR_DPI` | `300` | Resolution used to render scanned PDF pages |
| `AI_EXTRACTION_ENABLED` | `false` | Turn on Claude AI extraction (sends OCR text to Anthropic) |
| `ANTHROPIC_API_KEY` | *(not set)* | Anthropic API key used when AI extraction is on |
| `AI_MODEL` | `claude-opus-5` | Claude model used for extraction |
| `AI_EFFORT` | `low` | Reasoning effort (`low`/`medium`/`high`/`xhigh`/`max`); raise if messy documents are misread |
| `RECHECK_ON_STARTUP` | `true` | Re-run validation and conflict checks on all records at startup (turn off for very large databases) |

New columns added in later versions are created automatically on startup (existing data is kept).
To reset the sample data, drop and recreate the `land_records` database, then restart the backend.

## API overview

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | API + database check |
| GET | `/api/dashboard/summary` | Counts, breakdowns, recent records, pipeline status |
| GET | `/api/meta/options` | Document types, area units, statuses, districts |
| GET | `/api/records?q=&status=&district=&document_type=&page=&page_size=` | List / search records |
| POST | `/api/records/upload` | Multipart upload (`file` + record fields; `run_ocr=true` and `ocr_language` to OCR on upload) |
| GET | `/api/records/{id}` | Record detail |
| PATCH | `/api/records/{id}` | Edit details (re-runs rule checks) |
| POST | `/api/records/{id}/validate` | Re-run rule checks |
| PATCH | `/api/records/{id}/status` | Officer decision: `verified`, `rejected` or `pending` |
| GET | `/api/records/{id}/file` | View / download the stored document |
| POST | `/api/records/{id}/ocr` | Run / re-run OCR on the stored document (`{"language": "Hindi"}`) |
| GET | `/api/conflicts?type=&include_dismissed=` | All conflicts, grouped by parcel |
| GET | `/api/records/{id}/conflicts` | Conflicts involving one record |
| POST | `/api/conflicts/dismiss` | Mark a conflict as not a conflict (`{"key", "note", "reviewed_by"}`) |
| DELETE | `/api/conflicts/dismiss/{key}` | Restore a dismissed conflict |
| POST | `/api/conflicts/rescan` | Re-check every record |
| GET | `/api/gis/layer?district=` | Cadastral parcels (GeoJSON) with linked records and map status |
| GET | `/api/gis/boundaries` | Record boundaries (GeoJSON) |
| GET | `/api/gis/summary` | Map layer and map-check counts |
| POST | `/api/gis/import` | Import a GeoJSON FeatureCollection (`file`) |
| GET | `/api/records/{id}/gis` | Map parcel, areas, boundary match and overlaps for a record |
| PUT | `/api/records/{id}/boundary` | Set a record boundary (`{"geometry": GeoJSON, "source"}`) |
| POST | `/api/records/{id}/boundary/from-map` | Copy the map parcel as the record boundary |
| DELETE | `/api/records/{id}/boundary` | Remove the record boundary |
| GET | `/api/parcels?q=` | Parcels (digital twins) with current owner and history-check counts |
| GET | `/api/parcels/by-record/{id}` | Full digital twin of the parcel containing a record |
| GET | `/api/ocr/status` | Whether OCR is available and which languages are installed |
| POST | `/api/ocr/extract` | OCR a file without saving it; returns text + field suggestions |

## Validation statuses

- **Flagged**: rule checks found an error (missing required field, invalid area, owner conflict)
- **Rules Passed**: no rule errors; still needs officer review
- **Verified** / **Rejected**: officer decision
- **Pending**: not produced by this version; reserved for a future OCR processing queue

Sample data is fictional and has no attached documents.

## Trying OCR

1. Open **Upload Document** and choose `samples/sample_khatauni_hindi.png` (or the scanned PDF).
2. Keep the language as **Hindi + English** and click **Run OCR**.
3. Check the suggested values, tick the ones to use and click **Apply selected to form**.
4. Upload. Open the record to see the extracted text, and try searching for a Hindi word from it.

Results on the sample (printed, clean): all 9 fields suggested correctly from the PNG, about 92% OCR
confidence, about 5 seconds. OCR still makes mistakes (e.g. the scanned-PDF sample reads khata `147`
as `1470`), so suggestions must always be checked. Poor scans, stamps, tables with unusual layouts
and handwriting will give much weaker results.

## How conflict detection works

Two records are treated as the **same parcel** when their survey / khasra numbers match after
normalisation (Hindi digits converted, spaces removed, e.g. `२३८ / २` = `238/2`) **and** their village
and district match. Place names match exactly, or across scripts by sound (`रामपुर` = `Rampur`,
`लखनऊ` = `Lucknow`). Two Latin spellings such as `Rampur` and `Rampura` are kept separate.

| Conflict | When | Severity |
|---|---|---|
| Owner conflict | Same parcel, different owners | Error (record is Flagged) |
| Possible duplicate | Same parcel, same owner: exact, spelling variant (≥ 85 % similar) or Hindi↔English sound match | Warning |
| Area mismatch | Same parcel, areas differ by more than 5 % after converting acre / hectare / kanal / guntha / m² (Bigha only compared with Bigha, because its size varies by state) | Warning |
| Khata mismatch | Same parcel and owner, different khata numbers | Info |
| Duplicate document | The identical file (same SHA-256) is attached to two records | Warning |

Rejected records are left out. When a record is edited, reviewed or rejected, the records it conflicts
with are re-checked too. The sample data includes one example of each type. These are rule-based
checks: they can flag legitimate cases (e.g. after a sale), which is why officers can dismiss a conflict
with a reason.

## Field confidence and AI extraction

Every suggested field gets a **confidence score (0-100)** with a "Why?" list:

| Signal | Effect |
|---|---|
| How it was found | next to its label (strong), on the line below the label, by AI and found in the text, or by AI but **not** in the text (very weak) |
| OCR word confidence | Tesseract's confidence for the exact words of the value (PDF text layer = 100) |
| Format | e.g. survey no. like `45/2A`, area a plausible number, names without digits |
| Agreement | label matching and AI give the same value → higher; different → lower, and the other reading is shown |

High ≥ 80, medium 55-79, low < 55. Low-confidence values are not pre-selected in the form.

### Turning on AI extraction (optional)

1. Create an API key at https://console.anthropic.com (usage is billed by Anthropic).
2. In `backend\.env` set:
   ```
   AI_EXTRACTION_ENABLED=true
   ANTHROPIC_API_KEY=sk-ant-...
   ```
3. Restart the backend.

**Privacy:** with AI on, the OCR text of each document (names, survey numbers, etc.) is sent to
Anthropic's API. Only enable it for data you are permitted to share. Users can untick "Also use AI"
per document. If the API call fails, the app falls back to label matching and shows the error.

## Cadastral map (GIS) verification

On first start the backend loads a **fictional sample map** (18 rectangular parcels at placeholder
locations, sized to match the sample records) and two demo boundaries. It demonstrates:

- `LR-2026-00012` (Pooja Yadav, 64/2): area 0.6 ha vs 0.9 ha on the map, and a boundary drawn 40 m too
  far south that overlaps Ramesh Kumar's parcel 112/3 by 1,600 m².
- `LR-2026-00015` (Gurpreet Singh, 23/1): 12 kanal recorded vs 8 kanal on the map.
- `LR-2026-00008` (survey `12-B?`): not on the map.

**Importing a real layer:** the file must be a GeoJSON FeatureCollection in WGS84 longitude/latitude
(EPSG:4326) with polygon features and properties for the survey number (`survey_number`, `khasra_no`,
`gat_no`, `plot_no`, ...), `village` and `district`. Importing a file with the same name replaces its
earlier import; every record is then re-checked. `samples/sample_cadastral_map_fictional.geojson` shows
the format.

Areas are computed with a local projection around each parcel (accurate to well under 1 % for
village-sized areas). Bigha is not converted because its size differs by state. The background map
tiles come from OpenStreetMap and need an internet connection; parcels and checks work without it.

## Parcel history (digital twin)

Records get two optional fields: **document date** and **previous owner / seller**. A record with a
previous owner (sale deed, mutation, gift, inheritance) is a *transfer*; other records (Jamabandi,
Khatauni, Khasra) *state* the owner on their date. Records of one parcel are put in date order to build
the ownership chain and derive the current owner. OCR label matching and AI extraction also suggest
the date and seller (e.g. "Seller", "Vendor", "विक्रेता", "Date of Registration", "दिनांक").

| Check | Meaning |
|---|---|
| Broken chain (error) | A transfer's seller was not the recorded owner at that time |
| Owner change without transfer (warning) | A later record shows a new owner, but no transfer document is on file |
| Mutation pending (warning) | The record of rights still shows the old owner after the latest transfer |
| Undated record (info) | Record has no date, so it is not placed on the timeline |
| Future date (error) | Document date is in the future |

Sample data (fictional): parcel **112/3** was sold by Ramesh Kumar to Anil Verma in 2023 but the
Jamabandi was not updated (mutation pending); parcel **215** was "sold" in 2022 by Srinivas Rao although
Ravi Teja was the recorded owner (broken chain); parcel **238/2** shows a clean chain across Hindi and
English records.
