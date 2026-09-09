# Postgres DB pack (abridged imaging schema)

## Data flow

| Table | Direction | Notes |
|-------|-----------|--------|
| `manifest_member_list` | **READ** from Postgres | Seed via single metadata CSV / upstream |
| `chart_list` | **WRITE** | `blob_container_name` ← `BLOB_CONTAINER`, `path` ← `BLOB_PATH_TEMPLATE` with `{folder}` = chart name, `chart_name` ← folder name |
| `page_list` | **WRITE** | Pages under each chart |
| `ocr_results` | **WRITE** | See OCR mapping; `raw_text` holds plain text **or** JSON string |

## Layout

```
postgres-db/
  ddl-scripts/001_schema.sql
  metadata/B1_R1_DummyMetadata.csv
  db-insert-scripts/load_from_folders.py
```

## OCR mapping

| File / stage | `ocr_type` | `raw_text` |
|--------------|------------|------------|
| prelim (Tess) | `tesseract` | plain text |
| final1 (docling) | `docling` | plain text |
| final2 (AzDocInt) | `azuredocintel` | JSON and/or text — mix OK |

## Env (shared with File Viewer)

```bash
BLOB_CONTAINER=my-container
BLOB_PATH_TEMPLATE={folder}/pages/{filename}
DATABASE_URL=postgresql://...
```

## Quick start

```bash
cd postgres-db/db-insert-scripts
pip install -r requirements.txt
export DATABASE_URL=postgresql://USER:PASS@localhost:5432/imaging
export BLOB_CONTAINER=...
export BLOB_PATH_TEMPLATE='{folder}/pages/{filename}'
python load_from_folders.py --ddl
```

## Not loaded yet

- `ocr_quality_results`
- `dos_extraction_results`
- imaging verification / classification formats
