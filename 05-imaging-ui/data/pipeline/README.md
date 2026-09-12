# Pipeline CSV drop folder

Imaging exports live here. ETL (`load_chart_info` / `load_pipeline`) and the UI
read from this folder (`PIPELINE_ROOT=./data/pipeline`).

**Manifest metadata** lives in sibling **`../metadata/`** (`METADATA_ROOT`), not here.

## Files

| File | Role |
|------|------|
| `chart_list.csv` / `page_list.csv` | Written by `load_chart_info.py` from `data/folders` |
| `hw_printed_classification.csv` (or `hw_printed.csv`) | HW/Printed |
| `rotation_orientation.csv` (or `rotation.csv`) | Rotation / tilt / mirrored |
| `dos_extraction.csv` | DOS |
| `member_extraction_results.csv` / `member_verification_summary.csv` | Member (UI) |
| `junk_classification.csv` | Junk / blank (UI) |

## Copy from pack outputs

```bash
cd 05-imaging-ui
cp ../01-ocr-extraction/output/hw_printed_classification.csv data/pipeline/ \
  2>/dev/null || cp ../01-ocr-extraction/output/hw_printed.csv data/pipeline/
cp ../02-imaging-pipeline/rotation-orientation/output/rotation_orientation.csv data/pipeline/ \
  2>/dev/null || cp ../02-imaging-pipeline/rotation-orientation/output/rotation.csv data/pipeline/
cp ../02-imaging-pipeline/dos-extraction/output/dos_extraction.csv data/pipeline/
cp ../02-imaging-pipeline/member-verification/output/member_*.csv data/pipeline/
cp ../02-imaging-pipeline/junk-classification/output/junk_classification.csv data/pipeline/
```

Then:

```bash
cd ../06-postgres-db/db-insert-scripts
python load_chart_info.py
python load_pipeline.py
```
