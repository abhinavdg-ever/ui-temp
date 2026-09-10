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
| **`dos_extraction_results`** | **`02-imaging-pipeline/dos-extraction/output/dos_extraction.csv`** | `db-insert-scripts/load_dos_csv.py` (skips if no CSV) |

## `dos_extraction_results` ← DOS CSV

Produced by:

```bash
cd 02-imaging-pipeline/dos-extraction
python extract_dos.py
# → output/dos_extraction.csv
```

CSV columns (one row **per page**):

```csv
chart_name,page_name,page_number,dos_from,dos_to,dos_from_iso,dos_to_iso,doc_dos_from,doc_dos_to,doc_dos_from_iso,doc_dos_to_iso
```

| CSV column | DB column | Notes |
|------------|-----------|--------|
| `chart_name` | → `chart_list.id` | |
| `page_name` | → `page_list.id` | |
| `dos_from` / `dos_to` | `dos_from` / `dos_to` | Page-level; blank if not on this page |
| `dos_from_iso` / `dos_to_iso` | (same, as DATE) | `YYYY-MM-DD` |
| `doc_dos_from` / `doc_dos_to` | `doc_dos_from` / `doc_dos_to` | Carry-forward; preamble/immunization → `2022-02-02` |

**Prerequisite:** run `load_from_folders.py` first so `chart_list` / `page_list` rows exist.

**Flow:**

1. `load_from_folders.py` → charts, pages, manifest, OCR  
2. `extract_dos.py` → `dos_extraction.csv`  
3. `load_dos_csv.py` → `dos_extraction_results` (exit 0 / skip if CSV missing)

```bat
cd 06-postgres-db\db-insert-scripts
python load_dos_csv.py
REM optional: python load_dos_csv.py --per-chart
```

## Quick start (Windows monorepo)

```bat
cd "c:\Projects\AI Project POC\06-postgres-db\db-insert-scripts"
pip install -r requirements.txt

REM Insert charts / pages / manifest / OCR (tables already created):
python load_from_folders.py

cd "..\..\02-imaging-pipeline\dos-extraction"
python extract_dos.py

cd "..\..\06-postgres-db\db-insert-scripts"
python load_dos_csv.py
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

## Not loaded yet

- `ocr_quality_results`
- `member_extraction_results`
- imaging verification / classification formats
