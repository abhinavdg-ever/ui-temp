# Postgres DB pack (abridged imaging schema)

## DATA_MODE

| Mode | Manifest | OCR |
|------|----------|-----|
| `local` | `postgres-db/metadata/metadata_R*_B*.csv` | Local `ocr/` files |
| `postgres` | `manifest_member_list` | `ocr_results` |

## Data flow (db-insert **writes** to Postgres)

| Table | Written by insert script | Notes |
|-------|--------------------------|--------|
| `manifest_member_list` | **YES** | From stacked `metadata_R{n}_B{n}.csv` |
| `chart_list` | **YES** | Folder name = `chart_name`; `BLOB_CONTAINER` / `BLOB_PATH_TEMPLATE` |
| `page_list` | **YES** | Pages under each chart |
| `ocr_results` | **YES** | prelim→tesseract, final1→docling, final2→azuredocintel |

## OCR mapping

| File / stage | `ocr_type` | UI kind |
|--------------|------------|---------|
| prelim (Tess) | `tesseract` | `preliminary` |
| final1 | `docling` | `final1` |
| final2 | `azuredocintel` | `final2` |

`raw_text` may be plain text or JSON string.

## Quick start

```bash
cd postgres-db/db-insert-scripts
pip install -r requirements.txt
export DATABASE_URL=postgresql://USER:PASS@localhost:5432/imaging
export BLOB_CONTAINER=...
export BLOB_PATH_TEMPLATE='{folder}/pages/{filename}'

python load_from_folders.py --ddl

# Then in app .env:
# DATA_MODE=postgres
```

## Not loaded yet

- `ocr_quality_results`
- `dos_extraction_results`
- imaging verification / classification formats
