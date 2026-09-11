# Junk / blank page classification

Ported from `advantmed-document-processing` (`backend/app/adapters/junk/` + `JunkStage`).

Classifies each page as **Main**, **Blank**, **Invoice**, **Cover**, or **Duplicate**.

## Logic (priority order)

| Step | Rule | Label | Confidence |
|------|------|-------|------------|
| 1 | Image: grayscale ≤200×200 sample; pixels &lt; 245 (“ink”); ≤80 ink pixels | Blank | 0.95 |
| 2 | OCR text empty or &lt; 5 alphanumeric chars | Blank | 0.90 |
| 3 | OCR &lt; 100 chars and contains `intentionally blank` or `blank` | Blank | 0.90 |
| 4 | Invoice keywords (`invoice`, `amount due`, `superbill`, …) | Invoice | 0.85 |
| 5 | Cover/fax keywords, single-word `accept`/`summary`/`unaccept`, or EMR TOC markers | Cover | 0.85 |
| 6 | Duplicate SHA-256 fingerprint of normalized OCR (≥50 chars); first page stays Main | Duplicate | 0.99 |

Manifest / clinical “Main” pages are everything else.

## Run

```bash
cd 02-imaging-pipeline/junk-classification
pip install -r requirements.txt
python classify_junk.py
python classify_junk.py --no-image          # text rules only
python classify_junk.py --per-chart
```

Reads ``ocr/<chart>_prelim.txt`` only (preliminary / Tess). Skips charts with no prelim.
Optional ``pages/*.jpg`` for the image blank check.

## Output

```
02-imaging-pipeline/junk-classification/output/junk_classification.csv
```

```csv
chart_name,page_name,page_number,page_classification,page_classification_confidence,page_group,reason,ocr_source
52743839_44976074,1.jpg,1,Blank,0.95,junk,blank_image,prelim
52743839_44976074,2.jpg,2,Main,,main,,prelim
52743839_44976074,3.jpg,3,Cover,0.85,junk,cover,prelim
```

| Column | Notes |
|--------|-------|
| `page_classification` | `Main` / `Blank` / `Invoice` / `Cover` / `Duplicate` |
| `page_group` | `junk` (Blank/Invoice/Cover) · `duplicate` · `main` |
| `reason` | `blank_image` / `blank_ocr` / `declared_blank` / `invoice` / `cover` / `duplicate` |
| `ocr_source` | always `prelim` |

## Imaging UI (Page Classification)

Duplicate is **not** Blank/Junk — it can have valid content and only means
the OCR fingerprint matches an earlier page.

| CSV | Blank or Junk | Is Duplicate | Page Type |
|-----|---------------|--------------|-----------|
| Blank | Yes (Blank) | No | Not Available |
| Invoice / Cover | Yes (Junk) | No | Invoice / Cover |
| Duplicate | No | Yes | Not Available |
| Main | No | No | Not Available |
| (not run) | NA | NA | Not Available |

`page_group` in CSV: `junk` (Blank/Invoice/Cover) · `duplicate` · `main`

Copy into the UI drop folder:

```bash
cp output/junk_classification.csv ../../05-imaging-ui/data/pipeline/
```

Per-chart override:

`05-imaging-ui/data/folders/<chart>/imaging/<chart>_junk.csv`
