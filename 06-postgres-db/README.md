# Postgres DB pack (abridged imaging schema)

## Layouts

**Monorepo (this repo / AI Project POC):**

```
…
  02-imaging-pipeline/dos-extraction/   ← DOS CSV producer
  05-imaging-ui/                        ← UI app + .env + data/folders
  06-postgres-db/                       ← this pack
    ddl-scripts/
    manifest/metadata_R1_B1.csv
    db-insert-scripts/load_from_folders.py
```

The insert script auto-detects this layout and loads `DATABASE_URL` from `05-imaging-ui/.env` when present.

## DATA_MODE

| Mode | Manifest | OCR |
|------|----------|-----|
| `local` | `06-postgres-db/manifest` | Local `ocr/` files |
| `postgres` | `manifest_member_list` | `ocr_results` |

## What gets written to Postgres

| Table | Source | Writer |
|-------|--------|--------|
| `chart_list` / `page_list` | `05-imaging-ui/data/folders/<chart>/pages` | `db-insert-scripts/load_from_folders.py` |
| `manifest_member_list` | `06-postgres-db/manifest/metadata_R*_B*.csv` | `load_from_folders.py` |
| `ocr_results` | `ocr/*_prelim` / `*_final1` / `*_final2` | `load_from_folders.py` |
| **`dos_extraction_results`** | **`05-imaging-ui/data/pipeline/dos_extraction.csv`** | `load_dos_csv.py` (skip if missing) |
| **`ocr_quality_results`** | **`data/pipeline/hw_printed_classification.csv` + `rotation_orientation.csv`** | `load_quality_csvs.py` (skip if missing) |

## Pipeline CSV drop folder

Put imaging exports in **`05-imaging-ui/data/pipeline/`** (see that folder’s README):

| CSV | Loader / consumer |
|-----|-------------------|
| `hw_printed_classification.csv` (or `hw_printed.csv`) | `load_quality_csvs.py` + UI |
| `rotation_orientation.csv` (or `rotation.csv`) | `load_quality_csvs.py` + UI |
| `dos_extraction.csv` | `load_dos_csv.py` + UI |
| `member_extraction_results.csv` | UI only (for now) |
| `member_verification_summary.csv` | UI only (for now) |

## `dos_extraction_results` ← DOS CSV

**Prerequisite:** run `load_from_folders.py` first so `chart_list` / `page_list` rows exist.

**Flow:**

1. `load_from_folders.py` → charts, pages, manifest, OCR  
2. Copy pipeline CSVs into `05-imaging-ui/data/pipeline/`  
3. `load_dos_csv.py` → `dos_extraction_results`  
4. `load_quality_csvs.py` → `ocr_quality_results` (HW + rotation)

```bat
cd 06-postgres-db\db-insert-scripts
python load_from_folders.py
python load_dos_csv.py
python load_quality_csvs.py
```

## Quick start (Windows monorepo)

```bat
cd "c:\Projects\AI Project POC\06-postgres-db\db-insert-scripts"
pip install -r requirements.txt

REM Insert charts / pages / manifest / OCR (tables already created):
python load_from_folders.py

REM After CSVs are in 05-imaging-ui\data\pipeline\:
python load_dos_csv.py
python load_quality_csvs.py
```

Uses `DATABASE_URL` from `05-imaging-ui\.env`:

```
postgresql+psycopg://aiuser:…@172.20.4.170:5432/imaging_outputs
```

- **Database** name: `imaging_outputs`
- **Schema**: `public` (`DB_SCHEMA=public`, default)
- Tables: `chart_list`, `page_list`, `manifest_member_list`, `ocr_results`, `ocr_quality_results`, `dos_extraction_results`

Loaders set `search_path` to `public` and upsert charts **without** `ON CONFLICT (chart_name)`.

### Postgres permission errors

If you see `permission denied for table chart_list`, the **user in `DATABASE_URL`** (usually `aiuser`)
lacks grants on `public` tables:

```sql
GRANT USAGE ON SCHEMA public TO aiuser;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aiuser;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aiuser;
```

## OCR mapping

| File / stage | `ocr_type` | UI kind |
|--------------|------------|---------|
| prelim (Tess) | `tesseract` | `preliminary` |
| final1 | `docling` | `final1` |
| final2 | `azuredocintel` | `final2` |

## Not loaded to Postgres yet

- `member_extraction_results` / `member_verification_summary` (UI reads from `data/pipeline` only)
