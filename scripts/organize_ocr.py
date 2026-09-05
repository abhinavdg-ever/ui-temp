#!/usr/bin/env python3
"""
Copy OCR output files into ocr/ under each matching document folder in the images root.

Expected input layouts:

  <images_root>/
    <folder_name>/
      pages/…          # (or images already organized)

  <ocr_root>/
    <folder_name>/
      <folder_name>_prelim.txt     # or any *prelim* file
      <folder_name>_final1.txt     # or *final1* / *oss*
      <folder_name>_final2.txt     # or *final2* / *azdoc* / *azure*

Result (written into the images tree):
  <images_root>/
    <folder_name>/
      pages/…
      ocr/
        <folder_name>_prelim.txt
        <folder_name>_final1.txt
        <folder_name>_final2.txt

Usage:
  python organize_ocr.py --images-root "/path/to/images" --ocr-root "/path/to/ocr_outputs"
  python organize_ocr.py --images-root "/path/to/images" --ocr-root "/path/to/ocr_outputs" --dry-run
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

# Target suffixes used by the Imaging UI
KIND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("prelim", re.compile(r"(^|[_\-.])prelim(inary)?([_\-.]|$)", re.I)),
    ("final1", re.compile(r"(^|[_\-.])(final1|final_?oss|oss)([_\-.]|$)", re.I)),
    ("final2", re.compile(r"(^|[_\-.])(final2|final_?(az|azure|azdoc|azdocint)|azdocint|azure)([_\-.]|$)", re.I)),
]


def classify_ocr_file(path: Path) -> str | None:
    name = path.name
    # Prefer exact suffix matches first
    lower = name.lower()
    for suffix in ("_prelim.txt", "_final1.txt", "_final2.txt"):
        if lower.endswith(suffix):
            return suffix[1:-4]  # prelim / final1 / final2
    for suffix, pattern in KIND_PATTERNS:
        if pattern.search(path.stem):
            return suffix
    return None


def collect_ocr_files(folder: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for entry in folder.rglob("*"):
        if not entry.is_file() or entry.name.startswith("._"):
            continue
        if entry.suffix.lower() != ".txt":
            continue
        kind = classify_ocr_file(entry)
        if kind and kind not in found:
            found[kind] = entry
    return found


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy OCR outputs into images/<folder>/ocr/ as _prelim/_final1/_final2."
    )
    parser.add_argument(
        "--images-root",
        required=True,
        help="Root folder containing document subfolders (destination)",
    )
    parser.add_argument(
        "--ocr-root",
        required=True,
        help="Root folder containing OCR output subfolders (source)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without changing files",
    )
    args = parser.parse_args()

    images_root = Path(args.images_root).expanduser().resolve()
    ocr_root = Path(args.ocr_root).expanduser().resolve()

    if not images_root.is_dir():
        print(f"ERROR: images root not found: {images_root}")
        return 1
    if not ocr_root.is_dir():
        print(f"ERROR: OCR root not found: {ocr_root}")
        return 1

    ocr_folders = {
        p.name: p
        for p in ocr_root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    }
    if not ocr_folders:
        print(f"No OCR folders under {ocr_root}")
        return 0

    copied = 0
    skipped = 0
    for name, src_folder in sorted(ocr_folders.items(), key=lambda x: x[0].lower()):
        dest_folder = images_root / name
        if not dest_folder.is_dir():
            print(f"[{name}] SKIP — no matching folder under images root")
            skipped += 1
            continue

        mapping = collect_ocr_files(src_folder)
        if not mapping:
            print(f"[{name}] SKIP — no recognizable OCR txt files")
            skipped += 1
            continue

        ocr_dir = dest_folder / "ocr"
        print(f"[{name}]")
        for kind, src in sorted(mapping.items()):
            dest = ocr_dir / f"{name}_{kind}.txt"
            print(f"  COPY {src.name} -> ocr/{dest.name}")
            if args.dry_run:
                copied += 1
                continue
            ocr_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied += 1

    print(
        f"Done. {'Would copy' if args.dry_run else 'Copied'} {copied} file(s); "
        f"skipped {skipped} folder(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
