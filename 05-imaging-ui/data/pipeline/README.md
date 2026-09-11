# Pipeline CSV drop folder (local + Docker `/data/pipeline`)

Copy imaging pipeline outputs here. The UI **and** `06-postgres-db/db-insert-scripts`
read from this folder (no monorepo pack mounts required).

## Required CSVs (flat — drop directly here)

Prefer the **new** names; older aliases still work if present.

| File | Used by | Notes |
|------|---------|--------|
| **`hw_printed_classification.csv`** | UI + `load_quality_csvs.py` | replaces `hw_printed.csv` |
| **`rotation_orientation.csv`** | UI + `load_quality_csvs.py` | replaces `rotation.csv` |
| **`dos_extraction.csv`** | UI + `load_dos_csv.py` | |
| **`member_extraction_results.csv`** | UI overlays | |
| **`member_verification_summary.csv`** | UI overlays | |

```
05-imaging-ui/data/pipeline/
  hw_printed_classification.csv
  rotation_orientation.csv
  dos_extraction.csv
  member_extraction_results.csv
  member_verification_summary.csv
```

### Expected columns

**hw_printed_classification.csv**  
`chart_name,page_name,page_num,handwritten,confidence,method`

**rotation_orientation.csv**  
`folder,filename,rotation_deg,tilt_angle,mirrored`  
(`rotation_di` / `tilt_angle_c` truncated headers also accepted; mirrored = Yes/No)

**dos_extraction.csv**  
`chart_name,page_name,page_number,dos_from,dos_to,…,doc_dos_from,doc_dos_to` (ISO columns optional)

**member_extraction_results.csv** / **member_verification_summary.csv**  
As produced by member-verification.

## Copy from pack outputs

```bash
cd 05-imaging-ui
cp ../01-ocr-extraction/output/hw_printed_classification.csv data/pipeline/ \
  2>/dev/null || cp ../01-ocr-extraction/output/hw_printed.csv data/pipeline/
cp ../02-imaging-pipeline/rotation-orientation/output/rotation_orientation.csv data/pipeline/ \
  2>/dev/null || cp ../02-imaging-pipeline/rotation-orientation/output/rotation.csv data/pipeline/
cp ../02-imaging-pipeline/dos-extraction/output/dos_extraction.csv data/pipeline/
cp ../02-imaging-pipeline/member-verification/output/member_*.csv data/pipeline/
```

## Docker

`docker-compose.yml` mounts `./data/pipeline` → `/data/pipeline` and sets
`PIPELINE_ROOT=/data/pipeline`.
