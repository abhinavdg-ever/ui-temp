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

Windows (Git Bash): `source .venv/Scripts/activate` instead.

Creating the database and copying charts into it: `docs/CLIENT_INSTANCE.md` in the main
repository.
