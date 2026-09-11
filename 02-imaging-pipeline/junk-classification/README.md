# Junk / blank page classification

Classifies pages from **existing preliminary OCR** — it does **not** run Tesseract.

## Input (required)

For each chart under `DATA_ROOT` (default `05-imaging-ui/data/folders/`):

```
<data>/folders/<chart>/ocr/<chart>_prelim.txt
```

Prelim file is already OCR’d (page markers like `===== 1.jpg =====`).  
That text is the **only** default input for Blank / Junk / Duplicate.

## Logic (per page, on prelim text)

| Rule | Result |
|------|--------|
| Empty text, or &lt; 5 letters/digits after stripping punctuation | **Blank** |
| Short text (&lt; 100 chars) containing `blank` / `intentionally blank` | **Blank** |
| Invoice keywords (`invoice`, `amount due`, …) | **Invoice** (junk) |
| Cover/fax keywords | **Cover** (junk) |
| Same OCR fingerprint as an earlier page in the chart (≥50 chars) | **Duplicate** (not junk) |
| Otherwise | **Main** |

Optional `--image`: also mark near-white `pages/*.jpg` as Blank. Skip this when prelim exists.

## Run

```bash
cd 02-imaging-pipeline/junk-classification
python classify_junk.py
```

```bash
python classify_junk.py --limit 1          # one chart
python classify_junk.py --per-chart        # also imaging/<chart>_junk.csv
python classify_junk.py --image            # optional pixel blank (needs Pillow)
```

## Output

`output/junk_classification.csv`

```csv
chart_name,page_name,page_number,page_classification,page_classification_confidence,page_group,reason,ocr_source
…,1.jpg,1,Blank,0.90,junk,blank_ocr,prelim
…,2.jpg,2,Main,,main,,prelim
…,3.jpg,3,Cover,0.85,junk,cover,prelim
```

| `page_group` | Meaning |
|--------------|---------|
| `junk` | Blank / Invoice / Cover |
| `duplicate` | Duplicate of earlier page (content may be valid) |
| `main` | Keep |

Copy for UI:

```bash
cp output/junk_classification.csv ../../05-imaging-ui/data/pipeline/
```

## Imaging UI

| CSV | Blank or Junk | Is Duplicate | Page Type |
|-----|---------------|--------------|-----------|
| Blank | Yes (Blank) | No | Not Available |
| Invoice / Cover | Yes (Junk) | No | Invoice / Cover |
| Duplicate | No | Yes | Not Available |
| Main | No | No | Not Available |
| (not run) | NA | NA | Not Available |
