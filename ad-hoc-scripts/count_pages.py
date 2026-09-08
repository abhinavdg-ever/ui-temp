#!/usr/bin/env python3
"""
Basic helper: given a root folder, print how many page images are in each subfolder.

Counts images inside <folder>/pages/ when that dir exists; otherwise counts images
directly in the subfolder.

Usage:
  python count_pages.py /path/to/images
  python count_pages.py --images-root /path/to/images
"""

from __future__ import annotations

import argparse
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
        description="Print number of page images in each subfolder."
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

    if not rows:
        print("No subfolders found.")
        return 0

    width = max(len(name) for name, _ in rows)
    total = 0
    for name, count in rows:
        print(f"{name.ljust(width)}  {count}")
        total += count
    print(f"{'-' * width}  -----")
    print(f"{'TOTAL'.ljust(width)}  {total}  ({len(rows)} folders)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
