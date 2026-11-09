# Client review UI

The review UI for the client: charts, Page Details, ground truth, Accuracy and Manual
Review, served on **port 5001** (API on 5000). It reads its own Postgres database,
`imaging_outputs_client`, which holds a copy of the pipeline's outputs and our users,
and only the client's ground truth.

Page Details shows one result column, **Algorithm** (our Final values), with no
Extracted column: `CLIENT_VIEW=true`, set in `docker-compose.yml` and `.env.example`.

`backend/` and `frontend/` are copied from `review-ui/` in the main repository by
`utilities/sync_client_ui.sh`. Make changes there, not here.

## Deploy on the VM

The client UI runs on the VM in Docker beside ours: API **5000**, web **5001**, project name
`client-review` (its containers never replace our review-ui on 4000 / 4001). It reads its own
database, `imaging_outputs_client`, on the Postgres container `postgres-db`
(172.20.4.170:5432).

**First time** (in this folder on the VM):

```bash
cp .env.example .env
# fill in section 1 DATABASE_URL=postgresql+psycopg://aiuser:<password>@172.20.4.170:5432/imaging_outputs_client
#         section 2 Azure Blob (as our review-ui/.env), section 4 AUTH_SECRET
mkdir -p data/empty
docker compose up -d --build
curl -fsS localhost:5000/health && echo OK
```

**Each release**:

1. Windows (Command Prompt): github.com/abhinavdg-ever/ui-temp → Code → Download ZIP, and
   copy it into this folder's Azure DevOps working copy (keep its `.env` and `data\`):

   ```bat
   cd /d %USERPROFILE%\Downloads
   rmdir /s /q ui-temp-main 2>nul
   tar -xf ui-temp-main.zip
   robocopy "%USERPROFILE%\Downloads\ui-temp-main" "C:\work\client-ui-devops" /MIR /NFL /NDL /NP /XF .env .env.bak-* ._* /XD .git node_modules .venv "%USERPROFILE%\Downloads\ui-temp-main\data" "C:\work\client-ui-devops\data"
   ```

   then push `C:\work\client-ui-devops` to Azure DevOps as usual.

2. VM (bash), in this folder:

   ```bash
   git pull
   python3 ~/advantmed-imaging-pipeline/utilities/env_sync.py .     # .env in the example's order, values kept
   docker cp ~/advantmed-imaging-pipeline/schema postgres-db:/tmp/schema
   docker exec postgres-db psql -U postgres -d imaging_outputs_client -v ON_ERROR_STOP=1 -f /tmp/schema/migrate.sql
   docker compose up -d --build
   curl -fsS localhost:5000/health && echo OK
   ```

Open `http://172.20.4.170:5001` and sign in with the usual username and password.

| Command (VM, this folder) | Does |
|---|---|
| `docker compose logs -f backend` | API logs |
| `docker compose down` | stop it (ours keeps running) |

## Run it locally (no Docker)

Ports **8003** (API) and **5175** (web), so it runs beside our review-ui (8002 / 5174).
`.env` sets them for the dev server (`DEV_FRONTEND_PORT`, `DEV_BACKEND_PORT`); the API port is given to uvicorn.

```bash
cp .env.example .env                        # DATABASE_URL = the client database
cd backend && python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8003 --reload

cd frontend && npm install && npm run dev   # second terminal: http://localhost:5175
```

## Run it on Windows

Install once: **Python 3.12** (`winget install Python.Python.3.12`; not 3.13, a
dependency fails there) and **Node 20+** (`winget install OpenJS.NodeJS.LTS`).
Ports are the same: API 8003, web 5175 (`DEV_*_PORT` in `.env`).

**Command Prompt**, two windows, both started in this folder:

```bat
:: Window 1: the API
copy .env.example .env
:: then set DATABASE_URL in .env (notepad .env)
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8003 --reload

:: Window 2: the web page
cd frontend
npm install
npm run dev
:: open http://localhost:5175
```


| Problem | Fix |
|---|---|
| `No matching distribution` on `pip install` | Python 3.13+: make the venv with `py -3.12` |
| The page loads but every request fails | uvicorn is not on 8003, or `.env` has no usable `DATABASE_URL` |
| Port 5175 or 8003 in use | `netstat -ano \| findstr :8003`, then end that process, or change `DEV_*_PORT` in `.env` |
