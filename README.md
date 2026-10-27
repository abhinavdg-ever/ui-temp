# Client review UI

The review UI for the client: charts, Page Details, ground truth, Accuracy and Manual
Review, served on **port 5001** (API on 5000). It reads its own Postgres database,
`imaging_outputs_client`, which holds a copy of the pipeline's outputs and our users,
and only the client's ground truth.

`backend/` and `frontend/` are copied from `review-ui/` in the main repository by
`utilities/sync_client_ui.sh`. Make changes there, not here.

## Run it

```bash
cp .env.example .env          # set DATABASE_URL, ALLOWED_ORIGINS, AUTH_SECRET, Azure Blob
mkdir -p data/empty
docker compose up -d --build  # project "client-review": never touches our review-ui
curl -fsS localhost:5000/health && echo OK
```

Open `http://<VM IP>:5001` and sign in with the usual username and password.

| Command | Does |
|---|---|
| `git pull && docker compose up -d --build` | update the screens |
| `docker compose logs -f backend` | API logs |
| `docker compose down` | stop it (ours keeps running) |

## Run it locally (no Docker)

Ports **8003** (API) and **5175** (web), so it runs beside our review-ui (8002 / 5174).
`.env.development` sets them for the dev server; the API port is given to uvicorn.

```bash
cp .env.example .env                        # DATABASE_URL = the client database
cd backend && python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8003 --reload

cd frontend && npm install && npm run dev   # second terminal: http://localhost:5175
```

## Run it on Windows

Install once: **Python 3.12** (`winget install Python.Python.3.12`; not 3.13, a
dependency fails there), **Node 20+** (`winget install OpenJS.NodeJS.LTS`) and **Git**.
Ports are the same: API 8003, web 5175.

**PowerShell**, two windows, both started in this folder:

```powershell
# Window 1: the API
Copy-Item .env.example .env          # then set DATABASE_URL in .env (Notepad)
cd backend
py -3.12 -m venv .venv               # -3.12: plain `py` picks your newest Python
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8003 --reload

# Window 2: the web page
cd frontend
npm install
npm run dev                          # open http://localhost:5175
```

If `Activate.ps1` is blocked, run this once:
`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`.

**Git Bash** (VS Code's bash terminal), the same with Unix-style commands:

```bash
cp .env.example .env
cd backend && py -3.12 -m venv .venv && source .venv/Scripts/activate   # Scripts, not bin
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8003 --reload

cd frontend && npm install && npm run dev                               # second terminal
```

Next time only the activate line, `uvicorn …`, and `npm run dev` are needed. Check the API
at <http://localhost:8003/docs>; `curl.exe` (not `curl`) in PowerShell.

**Docker Desktop on Windows** runs the same as on the VM: `docker compose up -d --build` in
this folder, then <http://localhost:5001>.

| Problem | Fix |
|---|---|
| `No matching distribution` on `pip install` | Python 3.13+: make the venv with `py -3.12` |
| The page loads but every request fails | uvicorn is not on 8003, or `.env` has no usable `DATABASE_URL` |
| Port 5175 or 8003 in use | `netstat -ano \| findstr :8003`, then end that process, or change `.env.development` |

Creating the database and copying charts into it: `docs/CLIENT_INSTANCE.md` in the main
repository.
