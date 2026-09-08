#!/usr/bin/env python3
"""
Basic helper: given a root folder, count page images in each subfolder and write a CSV.

Counts images inside <folder>/pages/ when that dir exists; otherwise counts images
directly in the subfolder.

Usage:
  python file_counter_mod.py /path/to/images
  python file_counter_mod.py /path/to/images --out counts.csv
  python file_counter_mod.py --images-root /path/to/images
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

IMAGE_RE = re.compile(r"\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)


def count_images(folder: Path) -> int:
    if not folder.is_dir():
        return 0
    n = 0
    for entry in folder.iterdir():
        if not entry.is_file() or entry.name.startswith("._"):
            continue
        if IMAGE_RE.search(entry.name):
            n += 1
    return n


def pages_in_folder(folder: Path) -> int:
    pages_dir = folder / "pages"
    if pages_dir.is_dir():
        return count_images(pages_dir)
    return count_images(folder)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count page images per subfolder and write a CSV."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=None,
        help="Root folder containing document subfolders",
    )
    parser.add_argument(
        "--images-root",
        default=None,
        help="Same as positional root (optional alias)",
    )
    parser.add_argument(
        "--out",
        "-o",
        default=None,
        metavar="PATH",
        help="CSV output path (default: <images-root>/file_counts.csv)",
    )
    args = parser.parse_args()

    raw = args.images_root or args.root
    if not raw:
        parser.print_help()
        return 1

    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: folder not found: {root}", file=sys.stderr)
        return 1

    rows: list[tuple[str, int]] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        rows.append((entry.name, pages_in_folder(entry)))

    out = Path(args.out).expanduser().resolve() if args.out else (root / "file_counts.csv")
    out.parent.mkdir(parents=True, exist_ok=True)

    total = sum(count for _, count in rows)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["folder", "page_count"])
        writer.writerows(rows)
        writer.writerow(["TOTAL", total])

    # Also print a short summary to the terminal
    print(f"folders: {len(rows)}")
    print(f"total pages: {total}")
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
