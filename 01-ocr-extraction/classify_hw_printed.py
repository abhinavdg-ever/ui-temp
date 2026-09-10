#!/usr/bin/env python3
"""
Classify each page image as Printed or Handwritten → CSV.

Uses models/image_type_classification.pkl (from advantmed-autocoderai-new).

Usage:
  cd 01-ocr-extraction
  pip install -r requirements.txt
  python classify_hw_printed.py
  python classify_hw_printed.py --per-chart
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MONOREPO_ROOT = SCRIPT_DIR.parent
IMAGING_UI_CANDIDATES = (
    MONOREPO_ROOT / "05-imaging-ui",
    SCRIPT_DIR.parent / "05-imaging-ui",
)

IMAGE_RE = re.compile(r"\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)
PAGE_NUM_RE = re.compile(r"^(\d+)\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)
PAGE_NAMED_RE = re.compile(r"^page_(\d+)\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)

CSV_COLUMNS = [
    "chart_name",
    "page_name",
    "page_number",
    "handwritten_or_printed",
    "confidence",
    "method",
]


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def find_imaging_ui() -> Path | None:
    for cand in IMAGING_UI_CANDIDATES:
        if (cand / ".env").is_file() or (cand / "data" / "folders").is_dir():
            return cand.resolve()
    return None


def bootstrap_env() -> Path | None:
    ui = find_imaging_ui()
    if ui:
        _load_env_file(ui / ".env")
    _load_env_file(SCRIPT_DIR / ".env")
    return ui


def default_data_root(ui: Path | None) -> Path:
    env = (os.environ.get("DATA_ROOT") or "").strip()
    if env:
        path = Path(env)
        if not path.is_absolute() and ui is not None:
            return (ui / path).resolve()
        return path.resolve()
    if ui is not None:
        return (ui / "data" / "folders").resolve()
    return (MONOREPO_ROOT / "05-imaging-ui" / "data" / "folders").resolve()


def list_page_files(folder: Path) -> list[tuple[int, Path]]:
    pages_dir = folder / "pages"
    if not pages_dir.is_dir():
        return []
    numbered: list[tuple[int, Path]] = []
    other: list[Path] = []
    for entry in pages_dir.iterdir():
        if not entry.is_file() or entry.name.startswith("._"):
            continue
        if not IMAGE_RE.search(entry.name):
            continue
        m = PAGE_NUM_RE.match(entry.name) or PAGE_NAMED_RE.match(entry.name)
        if m:
            numbered.append((int(m.group(1)), entry))
        else:
            other.append(entry)
    numbered.sort(key=lambda x: x[0])
    next_num = (numbered[-1][0] + 1) if numbered else 1
    for path in sorted(other, key=lambda p: p.name.lower()):
        numbered.append((next_num, path))
        next_num += 1
    return numbered


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    ui = bootstrap_env()

    parser = argparse.ArgumentParser(
        description="Classify page images as Printed / Handwritten → CSV"
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=default_data_root(ui),
        help="Path to data/folders",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=SCRIPT_DIR / "models" / "image_type_classification.pkl",
        help="Path to image_type_classification.pkl",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=SCRIPT_DIR / "output" / "hw_printed.csv",
        help="Combined CSV path",
    )
    parser.add_argument(
        "--per-chart",
        action="store_true",
        help="Also write imaging/<chart>_hw_printed.csv under each folder",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N folders (0 = all)",
    )
    args = parser.parse_args()

    from hw_printed import classify_image_path, load_model

    data_root = args.data_root.resolve()
    if not data_root.is_dir():
        print(f"DATA_ROOT not found: {data_root}", file=sys.stderr)
        sys.exit(1)

    model = load_model(args.model.resolve())
    folders = sorted(
        p for p in data_root.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    if args.limit and args.limit > 0:
        folders = folders[: args.limit]

    print(f"data_root: {data_root}")
    print(f"folders: {len(folders)}")
    print(f"out: {args.out.resolve()}")

    all_rows: list[dict[str, str]] = []
    for folder in folders:
        pages = list_page_files(folder)
        if not pages:
            print(f"  skip {folder.name}: no pages/")
            continue
        rows: list[dict[str, str]] = []
        for num, path in pages:
            label, conf, method = classify_image_path(path, model=model)
            rows.append(
                {
                    "chart_name": folder.name,
                    "page_name": path.name,
                    "page_number": str(num),
                    "handwritten_or_printed": label,
                    "confidence": "" if conf is None else f"{conf:.4f}",
                    "method": method,
                }
            )
        all_rows.extend(rows)
        print(f"  {folder.name}: pages={len(rows)}")
        if args.per_chart:
            chart_csv = folder / "imaging" / f"{folder.name}_hw_printed.csv"
            write_csv(chart_csv, rows)
            print(f"    → {chart_csv}")

    write_csv(args.out.resolve(), all_rows)
    print(f"wrote {len(all_rows)} rows → {args.out.resolve()}")


if __name__ == "__main__":
    main()
