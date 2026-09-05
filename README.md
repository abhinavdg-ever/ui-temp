# Advantmed Imaging UI

Browse document folders with page images and Preliminary / Final OCR side-by-side. Visual language matches `advantmed-document-processing`.

## Features

- **Landing** — History list with Number of pages, OCR Processed, Imaging Processed (hardcoded `0`), Last Updated At, and **View** (10 per page, paginated)
- **Detail** — page viewer (left) + OCR tabs: **Preliminary OCR** / **Final OCR** (right), synced page-by-page from the single OCR file
- **Data modes** via `.env`: `local` (default) or `postgres` (stubbed)

## Local folder layout

```
data/folders/<folder_name>/
  pages/1.jpg
  pages/2.jpg
  ocr/<folder_name>_prelim.txt
  ocr/<folder_name>_final.txt
```

OCR files are one document each. Pages are split on filename markers that match the image name exactly:

```
===== 1.jpg =====
...page 1 text...
===== 2.jpg =====
...page 2 text...
```

## Setup

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
| `DATA_MODE` | `local` or `postgres` |
| `DATA_ROOT` | Path to folders root (local mode) |
| `DATABASE_URL` | Postgres URL (postgres mode — not implemented yet) |

## API

- `GET /api/folders` — list folders
- `GET /api/folders/{id}` — folder + pages
- `GET /api/folders/{id}/pages/{n}/image` — page image
- `GET /api/folders/{id}/ocr?kind=preliminary|final` — folder OCR text (`*_prelim.txt` / `*_final.txt`)
