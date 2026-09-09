# Advantmed Imaging UI

Browse document folders with page images and OCR side-by-side (Preliminary Tess / Final OSS / Final AzDocInt).

## Features

- **Login** — username/password gate before History (`imaging-user` / `aipocpw2026`)
- **Landing (History)** — search, sort (filename / pages / last updated), OCR status (Queued / In Progress / Completed / Failed), OCR/Imaging icons, 15 per page with compact page numbers
- **Detail** — page viewer (left) + mode icons **OCR** / **Imaging**; OCR tabs: **Preliminary (Tess)** / **Final (OSS)** / **Final (AzDocInt)**; Imaging tabs: **Page Details** / **Doc Summary**; download OCR text or document imaging (CSV + JSON)
- **Data modes** via `.env`: `local` (default) or `postgres` (stubbed — imaging uses dummy rows until schema is wired)
- **Ad-hoc scripts** — see [`ad-hoc-scripts/ADHOC_README.md`](ad-hoc-scripts/ADHOC_README.md) to organize images + OCR into `pages/` / `ocr/`
- **Docker** — backend `:3000`, frontend `:3001` (nginx proxies `/api`)

## Local folder layout

```
data/folders/<folder_name>/
  pages/1.jpg
  pages/2.jpg
  ocr/<folder_name>_prelim.txt     # Preliminary (Tess)
  ocr/<folder_name>_final1.txt     # Final (OSS)
  ocr/<folder_name>_final2.json    # Final (AzDocInt) — pages[].content extracted for UI
  imaging/<folder_name>_imaging.json   # optional; dummy page rows if missing
```

OCR text files (prelim / final1) are one document each. Pages are split on filename markers that match the image name exactly:

```
===== 1.jpg =====
...page 1 text...
===== 2.jpg =====
...page 2 text...
```

AzDocInt `_final2.json` uses:

```json
{ "pages": [ { "fileName": "1.jpg", "content": "..." }, ... ] }
```

The API extracts `pages[].content` (falling back to `lines[].content`) and serves the same marker format to the UI.

Imaging JSON (optional) shape:

```json
{
  "manifest": {
    "member": "Gonzalez Stephen",
    "dob": "09/03/1942",
    "memberId": "MEM-DEMO-240315"
  },
  "pages": [
    {
      "pageNumber": 1,
      "fileName": "1.jpg",
      "memberName": "Gonzalez Stephen",
      "memberDob": "09/03/1942",
      "memberId": "MEM-DEMO-240315",
      "memberConfidence": 0.96,
      "handwrittenOrPrinted": "Printed",
      "orientationAngle": 0.64,
      "tiltAngle": 1.2,
      "mirrored": false,
      "pageQualityConfidence": 0.94,
      "dos": "01/03/2024",
      "dosConfidence": 0.91,
      "pageType": "Daily Note",
      "pageTypeConfidence": 0.88
    }
  ]
}
```

If `imaging/<folder>_imaging.json` is missing, the API returns **dummy backup rows** so the Imaging UI still works (pending Postgres).

Imaging downloads are **document-level only** (CSV + JSON).

## Docker (VM)

Backend listens on **3000**, UI on **3001**.

```bash
# From repo root — optionally point DATA_HOST_PATH at your folders
export DATA_HOST_PATH=./data/folders
docker compose up --build -d
```

- UI: `http://<vm-ip>:3001`
- API: `http://<vm-ip>:3000` (also available via UI at `/api`)

Stop:

```bash
docker compose down
```

Login: **imaging-user** / **aipocpw2026**

## Local setup (without Docker)

Open **http://127.0.0.1:5174** after both processes are running.

### macOS / Linux

```bash
# Backend (terminal 1)
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8002

# Frontend (terminal 2)
cd frontend
npm install
npm run dev
```

Subsequent runs:

```bash
# Backend
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8002

# Frontend
cd frontend && npm run dev
```

### Windows (PowerShell)

```powershell
# Backend (terminal 1)
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8002

# Frontend (terminal 2)
cd frontend
npm install
npm run dev
```

Subsequent runs:

```powershell
# Backend
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8002

# Frontend
cd frontend
npm run dev
```

If script activation is blocked, run once as Administrator:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Or use Command Prompt instead of PowerShell:

```bat
cd backend
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8002
```

## Environment

See root `.env`:

| Variable | Description |
|----------|-------------|
| `DATA_MODE` | `local` (CSV metadata + file OCR) or `postgres` (manifest + OCR from DB) |
| `DATA_ROOT` | Path to folders root (page images; Docker uses `/data/folders`) |
| `METADATA_ROOT` | Manifest CSVs when `DATA_MODE=local` (`../06-postgres-db/manifest` in monorepo, or `./postgres-db/manifest`) |
| `DATA_HOST_PATH` | Host path mounted into Docker backend (default `./data/folders`) |
| `METADATA_HOST_PATH` | Host Manifest CSV dir for Docker (default `./postgres-db/manifest`) |
| `DATABASE_URL` | Postgres URL (`DATA_MODE=postgres` reads `manifest_member_list` + `ocr_results`) |
| `ALLOWED_ORIGINS` | CORS origins for direct API access |
| `FILE_VIEWER_BLOB_ENABLED` | Show Local / Blob toggle in File Viewer |
| `BLOB_AUTH_MODE` | `entra` (default, Shared Key off OK) or legacy `sas` |
| `BLOB_ACCOUNT_URL` | Azure account URL (`https://….blob.core.windows.net`) |
| `BLOB_CONTAINER` | Blob container name |
| `BLOB_PATH_TEMPLATE` | Object key template (`{folder}`, `{filename}`, `{page}`) |
| `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` | App registration for Entra (or use Managed Identity / `az login`) |
| `BLOB_SAS_TOKEN` | Legacy only when `BLOB_AUTH_MODE=sas` |

## API

- `GET /api/folders` — list folders
- `GET /api/folders/{id}` — folder + pages
- `GET /api/folders/{id}/pages/{n}/image` — page image
- `GET /api/folders/{id}/ocr?kind=preliminary|final1|final2` — folder OCR (`*_prelim.txt` / `*_final1.txt` / `*_final2.json`)
- `GET /api/folders/{id}/imaging` — imaging page results (local JSON or dummy backup; Postgres later)
