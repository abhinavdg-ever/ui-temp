# OCR Extraction — Printed / Handwritten

Ported from `advantmed-autocoderai-new` (`classify_image_type` + RandomForest `.pkl`).

## Layout

```
01-ocr-extraction/
  models/image_type_classification.pkl   ← RF model (from autocoder)
  hw_printed.py                          ← feature extract + classify
  classify_hw_printed.py                 ← walk data/folders → CSV
  requirements.txt
  output/hw_printed.csv                  ← combined output
```

## Prerequisites

- Python 3.10+
- System **Tesseract** installed (`tesseract` on PATH)
- `pip install -r requirements.txt`

## Run

```bat
cd 01-ocr-extraction
pip install -r requirements.txt
python classify_hw_printed.py
python classify_hw_printed.py --per-chart
```

Output CSV columns:

```csv
chart_name,page_name,page_number,handwritten_or_printed,confidence,method
```

Preprocess (same as autocoder): crop top 5% + bottom 2.5%, Sauvola binarize, then classify.

`method` is `ml` when the `.pkl` loads, else `heuristic` (avg Tesseract conf &lt; 50 → Handwritten).

## Imaging UI

The Imaging panel shows a **Printed / Handwritten** block. With `DATA_MODE=local`,
values overlay from `imaging/<chart>_hw_printed.csv` or `output/hw_printed.csv` when present.
