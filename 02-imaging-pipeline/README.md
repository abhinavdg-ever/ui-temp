# Imaging pipeline outputs → UI mapping

Drop real CSVs into these folders (header row required). The Imaging UI reads them
with **no dummy values** — missing fields show as `not found`.

| Pack | Combined CSV | UI block |
|------|--------------|----------|
| `01-ocr-extraction/output/hw_printed.csv` | Hand Written format | Page Quality & Orientation → Printed / Handwritten |
| `02-imaging-pipeline/dos-extraction/output/dos_extraction.csv` | DOS from/to | DOS Extraction |
| `02-imaging-pipeline/rotation-orientation/output/rotation.csv` | Rotation format | Page Quality & Orientation |
| `02-imaging-pipeline/member-verification/output/member_extraction_results.csv` | member_extraction_results | Extracted Name / DOB / ID (page + doc) |
| `02-imaging-pipeline/member-verification/output/member_verification_summary.csv` | member_verification_summary | Doc Summary → Rejection Rules |

Per-chart overrides also work under:

`05-imaging-ui/data/folders/<chart>/imaging/<chart>_*.csv`
