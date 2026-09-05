# Ad-hoc organize scripts

Two small scripts that prepare document folders for the Imaging UI.

They assume:

1. **Images root** — one subfolder per document, containing page images  
2. **OCR root** — one subfolder per document (same names), containing OCR `.txt` files  

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
    <folder_name>_final2.txt     # Final (AzDocInt)
```

OCR file body pages are marked as:

```
===== 1.jpg =====
...text...
===== 2.jpg =====
...text...
```

## 1) Organize page images → `pages/`

```bash
# Preview
python scripts/organize_pages.py --images-root "/path/to/images" --dry-run

# Move images into pages/ (default)
python scripts/organize_pages.py --images-root "/path/to/images"

# Or copy instead of move
python scripts/organize_pages.py --images-root "/path/to/images" --copy
```

**Windows (PowerShell):**

```powershell
python scripts\organize_pages.py --images-root "D:\path\to\images" --dry-run
python scripts\organize_pages.py --images-root "D:\path\to\images"
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

```bash
# Preview
python scripts/organize_ocr.py \
  --images-root "/path/to/images" \
  --ocr-root "/path/to/ocr_outputs" \
  --dry-run

# Copy OCR files into matching image folders
python scripts/organize_ocr.py \
  --images-root "/path/to/images" \
  --ocr-root "/path/to/ocr_outputs"
```

**Windows (PowerShell):**

```powershell
python scripts\organize_ocr.py --images-root "D:\path\to\images" --ocr-root "D:\path\to\ocr_outputs" --dry-run
python scripts\organize_ocr.py --images-root "D:\path\to\images" --ocr-root "D:\path\to\ocr_outputs"
```

OCR source files are classified by name:

| Kind | Matches (examples) | Written as |
|------|--------------------|------------|
| Tess prelim | `*_prelim.txt`, `*preliminary*` | `<folder>_prelim.txt` |
| Final OSS | `*_final1.txt`, `*final1*`, `*oss*` | `<folder>_final1.txt` |
| Final AzDocInt | `*_final2.txt`, `*final2*`, `*azdoc*`, `*azure*` | `<folder>_final2.txt` |

Folder names under `--ocr-root` must match folder names under `--images-root`.

## Typical full prep

```bash
python scripts/organize_pages.py --images-root "/data/charts"
python scripts/organize_ocr.py --images-root "/data/charts" --ocr-root "/data/ocr_outputs"
```

Then point the app at that tree:

```env
DATA_MODE=local
DATA_ROOT=/data/charts
```
