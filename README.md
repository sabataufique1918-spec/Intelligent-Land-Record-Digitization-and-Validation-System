# Intelligent Land Record Digitization and Validation System (SIH26018)

A web application that helps land-revenue officers turn scanned land records (Khatauni, Jamabandi,
Khasra, 7/12 extracts, sale deeds, mutation registers) into checked, structured digital records. It
reads the document, suggests the details, scores how sure it is about each one, checks them against
other records and the cadastral map, and leaves the final decision to an officer.

Version 0.7 · React + FastAPI + PostgreSQL · all sample data in this repository is fictional.

## The problem

Land records are the backbone of land administration: property ownership, taxation, land acquisition,
dispute resolution and infrastructure planning. Across India, a large share of historical records still
exists as handwritten registers, scanned documents, maps, cadastral records and legacy PDF files.

Digitizing them by hand is slow and error-prone because the records suffer from poor image quality,
inconsistent formats, faded text, damaged pages, many regional languages and handwritten annotations.
Without standardized, accurate digital records it is hard to keep reliable databases, verify ownership,
connect records to modern land information systems and deliver citizen services. Manual data entry
also raises costs and introduces inconsistencies.

SIH26018 asks for an AI-powered platform that extracts structured information from scanned land records,
handwritten documents, maps and legacy PDFs in multiple Indian languages; classifies it into land-record
fields; validates it; scores its confidence; routes uncertain records to people; learns over time; and
integrates with LRMS, DILRMP, GIS platforms and government databases.

## What we built

Five core capabilities, each working end to end in this repository:

### 1. Multilingual OCR (with partial handwriting reading)
- Reads scanned PDFs, JPG and PNG in **12 languages**: English, Hindi, Marathi, Punjabi, Bengali,
  Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam and Urdu (Tesseract 5). PDFs that already contain text
  are read directly.
- **Cleans the image first** when needed: straightens tilted pages, removes yellowed paper, stains and
  shadows, erases table grid lines and recovers faded ink (OpenCV).
- A **Hindi model fine-tuned on land-record text** (`hin_landrec`) cut character errors from 11.2 % to
  1.0 % on held-out synthetic test lines.
- **Handwriting:** the reader is built for printed text, so on handwritten pages it reads only a small part
  (about 5 % of words clearly on our test documents). Instead of hiding this, every page shows **what
  share of the words was read clearly**, and each word is coloured by how sure the reader was.
- Reading runs in the **background**: an upload returns at once and the page updates itself when done.

### 2. AI field extraction + confidence scoring
- Finds **13 record fields** (owner, father's / husband's name, previous owner, document date, khasra /
  survey no., khata no., village, tehsil, district, state, area, area unit, document type) from their
  labels in Hindi or English (e.g. "खसरा संख्या", "Village", "जिल्हा").
- **Optional AI checking** compares the values with the page image and can correct OCR misreadings. It can
  run fully on-premise (a local vision model through Ollama) or through a cloud AI API; it is off by default.
- Every value gets a **0-100 confidence score with reasons** (how it was found, how clearly its words were
  read, whether its format is valid, whether two methods agree) and a plain label: *Looks right*,
  *Please check* or *Unsure*. Unsure values are never pre-selected.

### 3. Cross-record conflict detection
- Compares each record with all others: **the same parcel with different owners, possible duplicates,
  area mismatches (after unit conversion), khata mismatches and the same file uploaded twice**.
- Names are matched across scripts, so "सुरेश कुमार" and "Suresh Kumar" count as the same person.
- Officers can mark a conflict as "not a problem" with a note.

### 4. Cadastral map / GIS verification
- Imports a cadastral parcel layer (GeoJSON) and shows it on a map (Leaflet).
- Checks whether the record's survey number exists on the map, whether the recorded area matches the map
  area, whether a drawn or uploaded boundary matches the map parcel, and whether boundaries of different
  parcels overlap (Shapely).

### 5. Historical land-ownership timeline (digital twin)
- Brings together every record about one parcel, its map parcel and boundaries into a **dated ownership
  chain** and derives the current owner.
- Flags broken chains (the seller was not the recorded owner), owner changes without a transfer document,
  pending mutations and undated records.

Around these: document upload, an officer review workflow (verify / reject / send back with a note), a
dashboard, search, a validation queue, and a **learning loop**: officers' corrections measure accuracy per
field and fix repeated errors automatically, and lines they type in become training data for fine-tuning
the OCR.

## What happens to a document

```mermaid
flowchart TD
    A[Officer uploads a scan<br/>PDF / JPG / PNG] --> B[Stored with a SHA-256 fingerprint<br/>record created, reading queued]
    B --> C{PDF with a text layer?}
    C -- yes --> E[Text taken directly]
    C -- no --> D[Image clean-up if needed<br/>deskew · stains · table lines · faded ink]
    D --> F[OCR in 12 languages<br/>text + confidence of every word]
    E --> G[Field extraction<br/>13 fields from Hindi / English labels<br/>+ optional AI check against the image]
    F --> G
    G --> H[Confidence engine<br/>0-100 per field + reasons<br/>share of words read clearly]
    H --> I[Validation<br/>rules · cross-record conflicts · GIS map checks]
    I --> J[Digital twin<br/>parcel ownership timeline]
    J --> K[Officer review<br/>copy values · verify / reject]
    K --> L[Learning<br/>accuracy per field · auto-corrections · OCR training data]
```

1. **Upload.** The file is checked (type, content, size up to 20 MB), stored, and fingerprinted so the same
   document uploaded twice is caught. The upload returns immediately.
2. **Read.** A background worker reads the pages (in parallel), cleaning up poor scans first. The text and
   the confidence of every word are saved.
3. **Extract and score.** Field values are found and scored; the page shows a verdict such as
   "9 details found: all look right" or "Handwritten or unclear page: 5 % of the words read clearly".
4. **Validate.** Rule checks, conflict detection and map checks run; problems are listed on the record.
5. **Review.** The officer sees each suggested value with its certainty, the text coloured by confidence and
   the document side by side, copies the values they accept, and verifies or rejects the record.
6. **Learn.** The officer's corrections are stored to measure accuracy and improve later suggestions.

## Expected solution vs this project

| Expected in SIH26018 | Status | In this project |
|---|---|---|
| Multilingual document recognition | Built | 12 Indian languages for printed text; fine-tuned Hindi model |
| Printed **and handwritten** text | Partial | Printed text works; handwriting is read only partly, and the share read clearly is shown. Real handwriting recognition is future work |
| Extraction from scanned PDFs, images, historical documents | Built | Scanned and text PDFs (up to 10 pages) and images, with image clean-up |
| Classification into predefined fields | Partial | 13 fields incl. owner, khasra / survey no., khata no., area, village, tehsil, district. Land classification, mutation and registration details are not extracted yet |
| Validation: business rules, duplicate detection | Built | Required fields, formats, area range, duplicates, owner / area / khata conflicts, identical files |
| Cross-database verification | Not yet | Checks run against records inside this system; no government database connection |
| Confidence scoring, uncertain fields flagged | Built | 0-100 per field with reasons; "Unsure" values not pre-selected |
| Human-assisted verification for low-confidence records | Built | Review workflow, validation queue, side-by-side view with the document |
| Learning that improves accuracy over time | Partial | Accuracy per field, automatic correction of repeated errors, OCR training data export and fine-tuning script; retraining is a manual step |
| Integration with GIS platforms and cadastral maps | Partial | GeoJSON cadastral layers with map checks; a fictional sample layer is included |
| Integration with LRMS / DILRMP | Not yet | A REST API exists that such systems could call |
| Secure repository with metadata and audit trail | Partial | Documents stored with type, size and fingerprint; reviewer, time and note recorded for each decision. No full audit log yet |
| Dashboards: documents processed, validation status, pending verification, errors, district-wise progress | Partial | Summary cards, status breakdown, records by district and document type, conflicts, extraction accuracy per field. State-wise progress not yet |
| APIs for government applications | Built | REST API with interactive documentation at `/docs` |
| Role-based access control | Not yet | No login or roles yet |

## Component-wise technology

| Component | Technology | What it does here |
|---|---|---|
| Web interface | React 19, React Router 7, Vite 7 | Upload, review, dashboard, conflicts, map, parcel history, training pages |
| Maps | Leaflet, Leaflet-Geoman, OpenStreetMap | Cadastral map view; drawing and editing parcel boundaries |
| API | Python, FastAPI, Uvicorn | REST endpoints for records, OCR, conflicts, GIS, parcels, training, dashboard |
| Background processing | Python thread-pool job queue | Reads documents after upload without blocking the user |
| Database | PostgreSQL, SQLAlchemy 2, psycopg 3 | Records, text and word confidences, issues, feedback, map layers |
| Document storage | File system + SHA-256 | Uploaded files and duplicate-file detection |
| OCR | Tesseract 5 (LSTM), pytesseract, PyMuPDF | Reading scanned pages in 12 languages; reading PDF text layers |
| OCR fine-tuning | tesstrain / lstmtraining | Land-record Hindi model `hin_landrec` |
| Image processing | OpenCV, NumPy, Pillow | Deskew, background and stain removal, table-line removal, faded ink |
| Field extraction | Label matching (Python), optional vision-language AI (Ollama or cloud API) | 13 record fields; AI checks values against the page image |
| Confidence engine | Python rules | 0-100 score with reasons per field; share of words read clearly |
| Conflict detection and name matching | Python, difflib, phonetic key | Duplicates and conflicts; Hindi-English name matching |
| GIS checks | Shapely, GeoJSON | Area, boundary and overlap checks against the cadastral map |
| Learning | Feedback store, training-line export | Accuracy tracking, automatic corrections, OCR training data |

More detail on the approach and architecture: [docs/SIH26018_Technical_Approach.pdf](docs/SIH26018_Technical_Approach.pdf).

## Known limitations

- Handwritten pages are read only partly; officers type those details in.
- Only a **fictional** sample cadastral layer is included; real Bhu-Naksha / survey data must be imported
  as GeoJSON (WGS84). Shapefile, KML and DXF are not supported yet.
- No connection to LRMS, DILRMP, registration (IGRS) or revenue-department databases; ownership history
  uses only records in this system.
- Hindi-English name matching covers Devanagari (Hindi, Marathi) only.
- No user login or roles yet.
- Geometry is checked in Python (Shapely); state-scale map layers would need PostGIS spatial indexes.

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
| `OCR_WORKERS` | `2` | Documents OCR'd at the same time in the background |
| `AI_EXTRACTION_ENABLED` | `false` | Turn on Claude AI extraction (sends OCR text to Anthropic) |
| `AI_SEND_IMAGES` | `true` | With AI on, also send the page images so Claude can correct OCR misreadings |
| `AI_PROVIDER` | `anthropic` | `anthropic` (Claude API) or `ollama` (vision model on this computer, see "Local AI") |
| `OLLAMA_MODEL` | `qwen3-vl:4b` | Ollama model used when `AI_PROVIDER=ollama` |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama server address |
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
| POST | `/api/records/upload` | Multipart upload (`file` + record fields; `run_ocr=true` and `ocr_language` queue OCR in the background; the record returns with `ocr_status` `queued`) |
| GET | `/api/records/{id}` | Record detail |
| PATCH | `/api/records/{id}` | Edit details (re-runs rule checks) |
| POST | `/api/records/{id}/validate` | Re-run rule checks |
| PATCH | `/api/records/{id}/status` | Officer decision: `verified`, `rejected` or `pending` |
| GET | `/api/records/{id}/file` | View / download the stored document |
| POST | `/api/records/{id}/ocr` | Queue OCR of the stored document (`{"language": "Hindi"}`); returns 202, poll the record until `ocr_status` is no longer `queued` / `processing` |
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
Anthropic's API, and with `AI_SEND_IMAGES=true` (default) also the scanned page images (up to 5 pages). Only enable it for data you are permitted to share. Users can untick "Also use AI"
per document. If the API call fails, the app falls back to label matching and shows the error.

### Local AI (no API key, nothing leaves the computer)

Instead of Claude, AI reading can use a vision-language model running on the same computer through
[Ollama](https://ollama.com). It is free and private, but much less accurate than Claude (especially on
handwriting) and slow on a small GPU (roughly a minute or more per page on a 4 GB GTX 1650).

```powershell
winget install Ollama.Ollama
ollama pull qwen3-vl:4b
```

Then in `backend/.env`: `AI_EXTRACTION_ENABLED=true` and `AI_PROVIDER=ollama`, and restart the backend.
The same prompts and JSON output format are used as with Claude, so the field suggestions, confidence
scores and review screens work the same way. Values read by the local model get the same "read by AI"
confidence limits, so officers are asked to check them.

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

## OCR accuracy and image clean-up

Before OCR, each page is checked for skew. Clean, straight pages are read directly (fast path). Other
pages are cleaned up with OpenCV and read in three versions in parallel:
background removed (yellowed paper, stains, shadows), background plus table grid lines removed, and
adaptive threshold for faded ink. The version with the most confidently read text is kept. Skew up to
±10° is corrected automatically.

Measured on the fictional sample Khatauni and five degraded copies (9 fields each):

| Scan condition | Fields correct before | After | Character error before → after |
|---|---|---|---|
| Clean | 9/9 | 9/9 | 17% → 17% |
| Tilted 4° | 0/9 | 9/9 | 65% → 17% |
| Yellowed paper, stain, shadow | 0/9 | 9/9 | 100% → 18% |
| Faded + blurry | 0/9 | 3/9 | 93% → 33% |
| Low-resolution phone photo | 1/9 | 7/9 | 54% → 48% |
| All of the above combined | 0/9 | 6/9 | 100% → 27% |
| **Total** | **10/54** | **43/54** | **72% → 27%** |

Degraded pages take about 2-5 s each (clean pages about 1-2 s). Denoising and CLAHE contrast boosting
were also tested and made results worse, so they are not used. These numbers come from synthetic
degradations of one printed sample; accuracy on real scans will differ.

**Handwritten pages:** Tesseract reads printed text only. Pages with average OCR confidence below 50 %
are marked *poor quality* (likely handwritten or badly damaged) and no field suggestions are made from
the unreadable text. If AI extraction is enabled, those pages are sent to Claude **as images**; its
transcription replaces the OCR text and every value it reads is shown with at most medium confidence,
because it cannot be cross-checked.

**AI with page images (printed pages):** with AI on and `AI_SEND_IMAGES=true`, Claude gets the page
images together with the OCR text and reads each value from the image, using the OCR text as a hint.
Values that match the OCR text are scored as grounded; values Claude read differently from the OCR
(likely OCR errors, e.g. a misread digit) are shown with medium confidence and the reason "the OCR text
reads it differently", and take precedence over a disagreeing label-matching value. PDFs with a real
text layer are sent as text only.

**Speed:** OCR runs in background worker threads (`OCR_WORKERS`), so uploads return immediately.
Scanned PDF pages are read in parallel, and each Tesseract process is limited to one thread
(`OMP_THREAD_LIMIT=1`) with at most one process per CPU core, which avoids the slowdown of several
multi-threaded Tesseract processes competing for the same cores. OCR jobs that were running when the
server stopped are marked *failed* at the next start and can be re-run.

**Second OCR engine (tested, not used):** RapidOCR (PaddleOCR PP-OCRv5 Devanagari models on ONNX Runtime)
was evaluated against this pipeline on held-out synthetic Hindi land-record text in fonts not used for
training. Its recognizer alone beat Tesseract on single cropped lines (5.3 % vs 8.0 % character error,
about 8x faster), but on full pages it did worse: 40 % vs 12 % on slightly tilted pages (its text
detector missed whole lines), and 8 % vs 6 % on straight pages even when Tesseract found the lines and
RapidOCR only read them. Choosing per page by confidence also made results worse, because the two
engines' confidence scores are not comparable. Surya 0.22 was also considered; it now needs a separate
vLLM / llama.cpp model server and conflicts with this project's Pillow and OpenCV versions.
