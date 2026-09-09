# Postgres DB pack (abridged imaging schema)

## Layouts

**Monorepo (AI Project POC on your laptop):**

```
AI Project POC/
  05-imaging-ui/                 ← UI app + .env + data/folders
  06-postgres-db/                ← this pack
    ddl-scripts/
    metadata/Metadata_R1_B1.csv
    db-insert-scripts/load_from_folders.py
```

**Nested (this standalone git repo):**

```
advantmed-imaging-ui/
  data/folders/
  postgres-db/                   ← same pack, nested
  .env
```

The insert script auto-detects either layout and loads `DATABASE_URL` from `05-imaging-ui/.env` when present.

## DATA_MODE

| Mode | Manifest | OCR |
|------|----------|-----|
| `local` | `06-postgres-db/metadata` (or nested `postgres-db/metadata`) | Local `ocr/` files |
| `postgres` | `manifest_member_list` | `ocr_results` |

## Quick start (Windows monorepo)

```bat
cd "c:\Projects\AI Project POC\06-postgres-db\db-insert-scripts"
pip install -r requirements.txt

REM Insert only (tables already created by DBA / prior DDL):
python load_from_folders.py

REM First-time schema create (needs CREATE on public — often fails for app users):
python load_from_folders.py --ddl
```

Uses `DATABASE_URL` from `05-imaging-ui\.env` (e.g. `…@172.20.4.170/imaging_outputs`).

## OCR mapping

| File / stage | `ocr_type` | UI kind |
|--------------|------------|---------|
| prelim (Tess) | `tesseract` | `preliminary` |
| final1 | `docling` | `final1` |
| final2 | `azuredocintel` | `final2` |

## Not loaded yet

- `ocr_quality_results`
- `dos_extraction_results`
- imaging verification / classification formats
