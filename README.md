# Advantmed Imaging UI

Browse document folders with page images and OCR side-by-side (Preliminary Tess / Final OSS / Final AzDocInt).

## Features

- **Login** — username/password gate before History (`imaging-user` / `aipocpw2026`)
- **Landing (History)** — search, sort (filename / pages / last updated), OCR status (Queued / In Progress / Completed / Failed), OCR/Imaging icons (Imaging disabled), 10 per page with compact page numbers
- **Detail** — page viewer (left) + mode icons **OCR** / **Imaging** (Imaging disabled); OCR tabs: **Preliminary (Tess)** / **Final (OSS)** / **Final (AzDocInt)**; download page/full OCR
- **Data modes** via `.env`: `local` (default) or `postgres` (stubbed)
- **Ad-hoc scripts** — see [`ad-hoc-scripts/ADHOC_README.md`](ad-hoc-scripts/ADHOC_README.md) to organize images + OCR into `pages/` / `ocr/`
- **Docker** — backend `:3000`, frontend `:3001` (nginx proxies `/api`)

## Local folder layout

```
data/folders/<folder_name>/
  pages/1.jpg
  pages/2.jpg
  ocr/<folder_name>_prelim.txt     # Preliminary (Tess)
  ocr/<folder_name>_final1.txt     # Final (OSS)
  ocr/<folder_name>_final2.txt     # Final (AzDocInt)
```

OCR files are one document each. Pages are split on filename markers that match the image name exactly:

```
===== 1.jpg =====
...page 1 text...
===== 2.jpg =====
...page 2 text...
```

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
| `DATA_MODE` | `local` or `postgres` |
| `DATA_ROOT` | Path to folders root (local mode; Docker uses `/data/folders`) |
| `DATA_HOST_PATH` | Host path mounted into Docker backend (default `./data/folders`) |
| `DATABASE_URL` | Postgres URL (postgres mode — not implemented yet) |
| `ALLOWED_ORIGINS` | CORS origins for direct API access |

## API

- `GET /api/folders` — list folders
- `GET /api/folders/{id}` — folder + pages
- `GET /api/folders/{id}/pages/{n}/image` — page image
- `GET /api/folders/{id}/ocr?kind=preliminary|final1|final2` — folder OCR (`*_prelim.txt` / `*_final1.txt` / `*_final2.txt`)
