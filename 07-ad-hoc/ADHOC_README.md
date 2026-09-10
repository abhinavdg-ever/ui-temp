# Ad-hoc organize scripts

Small scripts that prepare or inspect document folders for the Imaging UI.

They assume:

1. **Images root** — one subfolder per document, containing page images  
2. **OCR roots** — separate trees (or one combined tree) with the same folder names  

The scripts write `pages/` and `ocr/` **inside** each folder under the images root (so that tree can be pointed at by `DATA_ROOT`).

## Target layout

```
<images_root>/<folder_name>/
  pages/
    1.jpg
    2.jpg
  ocr/
    <folder_name>_prelim.txt     # Preliminary (Tess)
    <folder_name>_final1.txt     # Final (OSS)
    <folder_name>_final2.json    # Final (AzDocInt)
```

OCR text file body pages (prelim / final1) are marked as:

```
===== 1.jpg =====
...text...
===== 2.jpg =====
...text...
```

AzDocInt `_final2.json` looks like:

```json
{
  "pages": [
    { "pageNumber": 1, "fileName": "1.jpg", "content": "..." }
  ]
}
```

The UI extracts `pages[].content` (or `lines[].content` if needed).

## 0) Count pages per folder → CSV

```bash
python ad-hoc-scripts/file_counter_mod.py /path/to/images
# or choose the output path
python ad-hoc-scripts/file_counter_mod.py /path/to/images --out counts.csv
```

Writes a CSV with columns `folder,page_count` (plus a `TOTAL` row). Default output: `<images-root>/file_counts.csv`. Counts `pages/` when present, otherwise images in the folder.

## 1) Organize page images → `pages/`

```bash
# Preview
python ad-hoc-scripts/organize_pages.py --images-root "/path/to/images" --dry-run

# Move images into pages/ (default)
python ad-hoc-scripts/organize_pages.py --images-root "/path/to/images"

# Or copy instead of move
python ad-hoc-scripts/organize_pages.py --images-root "/path/to/images" --copy
```

**Windows (PowerShell):**

```powershell
python ad-hoc-scripts\organize_pages.py --images-root "D:\path\to\images" --dry-run
python ad-hoc-scripts\organize_pages.py --images-root "D:\path\to\images"
```

Before:

```
images/
  53688890_250126_0933/
    1.jpg
    2.jpg
```

After:

```
images/
  53688890_250126_0933/
    pages/
      1.jpg
      2.jpg
```

## 2) Organize OCR outputs → `ocr/`

Pass **separate** roots for each OCR kind. Folder names under each root must match the images folders. If a source file is not already named `*_prelim.txt` / `*_final1.txt` / `*_final2.json`, the script **adds the suffix** on the destination file.

```bash
# Preview
python ad-hoc-scripts/organize_ocr.py \
  --images-root "/path/to/images" \
  --prelim "/path/to/prelim_outputs" \
  --final1 "/path/to/final1_outputs" \
  --final2 "/path/to/final2_outputs" \
  --dry-run

# Copy
python ad-hoc-scripts/organize_ocr.py \
  --images-root "/path/to/images" \
  --prelim "/path/to/prelim_outputs" \
  --final1 "/path/to/final1_outputs" \
  --final2 "/path/to/final2_outputs"
```

**Windows (PowerShell):**

```powershell
python ad-hoc-scripts\organize_ocr.py `
  --images-root "D:\path\to\images" `
  --prelim "D:\path\to\prelim" `
  --final1 "D:\path\to\final1" `
  --final2 "D:\path\to\final2"
```

### Accepted source layouts per kind root

```
<prelim_root>/
  <folder_name>/
    anything.txt          # → images/<folder>/ocr/<folder>_prelim.txt
  # or a loose file:
  <folder_name>.txt       # → images/<folder>/ocr/<folder>_prelim.txt
```

Same for `--final1`. For `--final2`, prefer `.json` (`.txt` still accepted).

| Flag | Kind | Destination name |
|------|------|------------------|
| `--prelim` | Tess | `<folder>_prelim.txt` |
| `--final1` | OSS | `<folder>_final1.txt` |
| `--final2` | AzDocInt | `<folder>_final2.json` |

You can pass any subset of the three flags (e.g. only `--prelim`).

### Legacy combined OCR root

Still supported if all kinds live under one tree:

```bash
python ad-hoc-scripts/organize_ocr.py \
  --images-root "/path/to/images" \
  --ocr-root "/path/to/ocr_outputs"
```

## Typical full prep

```bash
python ad-hoc-scripts/organize_pages.py --images-root "/data/charts"
python ad-hoc-scripts/organize_ocr.py \
  --images-root "/data/charts" \
  --prelim "/data/ocr/prelim" \
  --final1 "/data/ocr/final1" \
  --final2 "/data/ocr/final2"
```

Then point the app at that tree:

```env
DATA_MODE=local
DATA_ROOT=/data/charts
```
