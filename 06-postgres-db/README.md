# Postgres DB pack (abridged imaging schema)

## Layout

```
05-imaging-ui/
  data/
    folders/     ← chart page images + ocr/
    pipeline/    ← imaging CSVs (+ chart_list.csv / page_list.csv from loader)
    metadata/    ← metadata_R*_B*.csv (Manifest)
  .env           ← DATABASE_URL, DATA_ROOT, PIPELINE_ROOT, METADATA_ROOT
06-postgres-db/
  ddl-scripts/
  db-insert-scripts/
    load_chart_info.py   ← folders → pipeline chart/page CSVs → Postgres
    load_pipeline.py     ← metadata + pipeline CSVs → Postgres
    test_db_connection.py
    db_common.py
```

## Scripts

```bash
cd 06-postgres-db/db-insert-scripts
pip install -r requirements.txt

python test_db_connection.py   # optional connectivity check

# 1) Scan data/folders → write/append data/pipeline/chart_list.csv + page_list.csv → upsert DB
python load_chart_info.py

# 2) Load CSVs from data/metadata + data/pipeline into DB tables
python load_pipeline.py
```

| Script | Reads | Writes |
|--------|-------|--------|
| `load_chart_info.py` | `data/folders/<chart>/pages` | `data/pipeline/chart_list.csv`, `page_list.csv` → `chart_list`, `page_list` |
| `load_pipeline.py` | `data/metadata/metadata_R*_B*.csv`, `data/pipeline/*.csv` | `manifest_member_list`, `dos_extraction_results`, `ocr_quality_results` |

`load_chart_info` **skips** a folder when it already exists in `chart_list.csv` with the **same page_count**.

## DATA_MODE (UI)

| Mode | Manifest | OCR |
|------|----------|-----|
| `local` | `data/metadata` | Local `ocr/` files |
| `postgres` | `manifest_member_list` | `ocr_results` |

## Env (`05-imaging-ui/.env`)

```
DATA_ROOT=./data/folders
PIPELINE_ROOT=./data/pipeline
METADATA_ROOT=./data/metadata
DATABASE_URL=postgresql+psycopg://aiuser:…@172.20.4.170:5432/imaging_outputs
DB_SCHEMA=public
```

## Pipeline CSV drop (`data/pipeline/`)

| CSV | Table / consumer |
|-----|------------------|
| `chart_list.csv` / `page_list.csv` | written by `load_chart_info` |
| `dos_extraction.csv` | `dos_extraction_results` |
| `hw_printed_classification.csv` (or `hw_printed.csv`) | `ocr_quality_results` + UI |
| `rotation_orientation.csv` (or `rotation.csv`) | `ocr_quality_results` + UI |
| `member_*` / `junk_*` | UI overlays only |

## Metadata (`data/metadata/`)

`metadata_R1_B1.csv` (and other `metadata_R*_B*.csv`) → `manifest_member_list` via `load_pipeline.py`.

## Permissions

```sql
GRANT USAGE ON SCHEMA public TO aiuser;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aiuser;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aiuser;
```
