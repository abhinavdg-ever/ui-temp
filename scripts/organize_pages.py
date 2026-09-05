#!/usr/bin/env python3
"""
Organize loose page images into pages/ under each document folder.

Expected input layout:
  <images_root>/
    <folder_name>/
      1.jpg
      2.jpg
      ...

Result:
  <images_root>/
    <folder_name>/
      pages/
        1.jpg
        2.jpg
        ...

Usage:
  python organize_pages.py --images-root "/path/to/images"
  python organize_pages.py --images-root "/path/to/images" --dry-run
  python organize_pages.py --images-root "/path/to/images" --copy
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

IMAGE_RE = re.compile(r"\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)
SKIP_DIRS = {"pages", "ocr"}


def iter_image_files(folder: Path) -> list[Path]:
    files: list[Path] = []
    for entry in folder.iterdir():
        if not entry.is_file() or entry.name.startswith("._"):
            continue
        if IMAGE_RE.search(entry.name):
            files.append(entry)
    return sorted(files, key=lambda p: p.name.lower())


def organize_folder(folder: Path, *, copy: bool, dry_run: bool) -> int:
    images = iter_image_files(folder)
    if not images:
        return 0

    pages_dir = folder / "pages"
    moved = 0
    for src in images:
        dest = pages_dir / src.name
        if dest.resolve() == src.resolve():
            continue
        print(f"  {'COPY' if copy else 'MOVE'} {src.name} -> pages/{src.name}")
        if dry_run:
            moved += 1
            continue
        pages_dir.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            print(f"  SKIP exists: pages/{src.name}")
            continue
        if copy:
            shutil.copy2(src, dest)
        else:
            shutil.move(str(src), str(dest))
        moved += 1
    return moved


def main() -> int:
    parser = argparse.ArgumentParser(description="Move/copy images into pages/ per folder.")
    parser.add_argument(
        "--images-root",
        required=True,
        help="Root folder containing document subfolders with images",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy instead of move (default: move)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without changing files",
    )
    args = parser.parse_args()

    images_root = Path(args.images_root).expanduser().resolve()
    if not images_root.is_dir():
        print(f"ERROR: images root not found: {images_root}")
        return 1

    total = 0
    folders = sorted(
        [p for p in images_root.iterdir() if p.is_dir() and not p.name.startswith(".") and p.name not in SKIP_DIRS],
        key=lambda p: p.name.lower(),
    )
    if not folders:
        print(f"No document folders under {images_root}")
        return 0

    for folder in folders:
        print(f"[{folder.name}]")
        total += organize_folder(folder, copy=args.copy, dry_run=args.dry_run)

    print(f"Done. {'Would process' if args.dry_run else 'Processed'} {total} image(s) across {len(folders)} folder(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
