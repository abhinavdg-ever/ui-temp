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

Creating the database and copying charts into it: `docs/CLIENT_INSTANCE.md` in the main
repository.
