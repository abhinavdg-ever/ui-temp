# DOS extraction (imaging pipeline)

One **CSV row per page**.

## Page vs document DOS

| Fields | When filled |
|--------|-------------|
| `dos_from` / `dos_to` | Only if DOS extracted **on that page**; else blank |
| `doc_dos_from` / `doc_dos_to` | Document-level: carry forward last encounter; before first DOS or immunization-like pages → `02-02-2022` |

Single extracted date → from == to.

## Schema (`dos_extraction_results`)

```sql
dos_from DATE,       -- page-level (nullable)
dos_to DATE,         -- page-level (nullable)
doc_dos_from DATE,   -- document effective from
doc_dos_to DATE,     -- document effective to
```

See `06-postgres-db/ddl-scripts/001_schema.sql`.

## CSV columns

```csv
chart_name,page_name,page_number,dos_from,dos_to,dos_from_iso,dos_to_iso,doc_dos_from,doc_dos_to,doc_dos_from_iso,doc_dos_to_iso
```

## Run

```bash
cd 02-imaging-pipeline/dos-extraction
python extract_dos.py
python extract_dos.py --llm
```
