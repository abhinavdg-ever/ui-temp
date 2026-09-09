# Postgres DB pack (abridged imaging schema)

Scaffold for DDL + seed/load scripts. **Loaded now:** metadata (`manifest_member_list`) from a **single CSV**, and `ocr_results`. Quality / DOS / imaging result formats come next.

## Layout

```
postgres-db/
  ddl-scripts/
    001_schema.sql          # abridged schema (chart/page/manifest/ocr/…)
  metadata/
    B1_R1_DummyMetadata.csv # single metadata CSV (Excel format) — not split per folder
    README.md
  db-insert-scripts/
    load_from_folders.py    # load charts, pages, metadata, OCR
    requirements.txt
```

## Metadata format

One file: `metadata/B1_R1_DummyMetadata.csv`

Columns: `recordId,DummyFirstName,DummyLastName,DummyDOB,MemberID`

`recordId` matches `data/folders/<recordId>/` when a folder exists.

## OCR mapping

| File | `ocr_results.ocr_type` |
|------|------------------------|
| `*_prelim.txt` | `tesseract` |
| `*_final1.txt` | `docling` |
| `*_final2.json` / `.txt` | `azuredocintel` |

Page text is split on `===== 1.jpg =====` markers (same as the UI).

## Quick start

```bash
cd postgres-db/db-insert-scripts
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL=postgresql://USER:PASS@localhost:5432/imaging
export DATA_ROOT=../../data/folders   # optional; default is repo data/folders

python load_from_folders.py --ddl
# defaults to ../metadata/B1_R1_DummyMetadata.csv
python load_from_folders.py --metadata-csv ../metadata/B1_R1_DummyMetadata.csv
```

## Not loaded yet

Schema includes but loaders wait on formats:

- `ocr_quality_results`
- `dos_extraction_results`
- imaging JSON → future tables (verification / classification / …)
