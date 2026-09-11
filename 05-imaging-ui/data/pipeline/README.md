# Pipeline CSV drop folder (local + Docker `/data/pipeline`)

Copy imaging pipeline outputs **and** Manifest metadata here. The UI and
`06-postgres-db/db-insert-scripts` read from this folder.

## Required files (flat — drop directly here)

### Status / imaging overlays (the “4 outputs”)

History status ignores Manifest:

| File | Role |
|------|------|
| **`hw_printed_classification.csv`** | HW/Printed (or `hw_printed.csv`) |
| **`rotation_orientation.csv`** | Rotation/tilt/mirrored (or `rotation.csv`) |
| **`dos_extraction.csv`** | DOS |
| **`member_extraction_results.csv`** and/or **`member_verification_summary.csv`** | Member (counts as **one** of the four) |

- **Imaging Completed** — chart present in **all 4** above  
- **Imaging in Progress** — chart present in **any 1+** of the four  

### Manifest (needed for Manifest Details — not used for status)

| File | Role |
|------|------|
| **`metadata_R1_B1.csv`** (and other `metadata_R*_B*.csv`) | Manifest member / DOB / MemberID |

```
05-imaging-ui/data/pipeline/
  hw_printed_classification.csv
  rotation_orientation.csv
  dos_extraction.csv
  member_extraction_results.csv
  member_verification_summary.csv
  metadata_R1_B1.csv
```

### Expected columns

**hw_printed_classification.csv**  
`chart_name,page_name,page_num,handwritten,confidence,method`

**rotation_orientation.csv**  
`folder,filename,rotation_deg,tilt_angle,mirrored`  
(`rotation_di` / `tilt_angle_c` truncated headers also accepted; mirrored = Yes/No)

**dos_extraction.csv**  
`chart_name,page_name,page_number,dos_from,dos_to,…,doc_dos_from,doc_dos_to` (ISO columns optional)

**member_*** — as produced by member-verification.

**metadata_R*_B*.csv** — `recordId,DummyFirstName,DummyLastName,DummyDOB,MemberID,…`

## Copy from pack outputs

```bash
cd 05-imaging-ui
cp ../01-ocr-extraction/output/hw_printed_classification.csv data/pipeline/ \
  2>/dev/null || cp ../01-ocr-extraction/output/hw_printed.csv data/pipeline/
cp ../02-imaging-pipeline/rotation-orientation/output/rotation_orientation.csv data/pipeline/ \
  2>/dev/null || cp ../02-imaging-pipeline/rotation-orientation/output/rotation.csv data/pipeline/
cp ../02-imaging-pipeline/dos-extraction/output/dos_extraction.csv data/pipeline/
cp ../02-imaging-pipeline/member-verification/output/member_*.csv data/pipeline/
cp ../06-postgres-db/manifest/metadata_R*.csv data/pipeline/
```

## Docker

`docker-compose.yml` mounts `./data/pipeline` → `/data/pipeline` and sets
`PIPELINE_ROOT` / `METADATA_ROOT` to that folder.
