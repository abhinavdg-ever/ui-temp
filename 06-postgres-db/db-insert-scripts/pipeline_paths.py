#!/usr/bin/env python3
"""Shared discovery for pipeline CSVs (pack paths + 05-imaging-ui/data/pipeline drop)."""

from __future__ import annotations

import csv
import os
from pathlib import Path

from load_from_folders import PG_PACK_ROOT, find_imaging_ui_root

_MONOREPO = PG_PACK_ROOT.parent


def imaging_ui_root() -> Path | None:
    return find_imaging_ui_root()


def pipeline_drop_dirs() -> list[Path]:
    """Candidate drop folders for flat / mirrored pipeline CSVs."""
    dirs: list[Path] = []
    ui = imaging_ui_root()
    env = (os.environ.get("PIPELINE_ROOT") or "").strip()
    if env:
        p = Path(env)
        if not p.is_absolute() and ui is not None:
            p = ui / p
        dirs.append(p)
    if ui is not None:
        dirs.append(ui / "data" / "pipeline")
    dirs.append(Path("/data/pipeline"))
    return dirs


def add_existing(path: Path | None, found: list[Path], seen: set[Path]) -> None:
    if path is None:
        return
    try:
        resolved = path.resolve()
    except OSError:
        return
    if resolved in seen or not resolved.is_file() or resolved.stat().st_size == 0:
        return
    seen.add(resolved)
    found.append(resolved)


def discover_named_csvs(
    *,
    filenames: tuple[str, ...],
    pack_rels: tuple[tuple[str, ...], ...] = (),
    data_root: Path | None = None,
    per_chart_suffix: str | None = None,
) -> list[Path]:
    """
    Find CSVs by preferred filenames (first in filenames wins for same location),
    pack relative paths, and optional per-chart imaging/<chart>_<suffix>.csv.
    """
    found: list[Path] = []
    seen: set[Path] = set()

    for drop in pipeline_drop_dirs():
        if not drop.is_dir():
            continue
        for name in filenames:
            add_existing(drop / name, found, seen)
            add_existing(drop / "output" / name, found, seen)
        for rel in pack_rels:
            add_existing(drop.joinpath(*rel), found, seen)

    for rel in pack_rels:
        add_existing(_MONOREPO.joinpath(*rel), found, seen)
        if len(rel) >= 2:
            out_dir = _MONOREPO.joinpath(*rel[:-1])
            for name in filenames:
                add_existing(out_dir / name, found, seen)

    if per_chart_suffix and data_root is not None and data_root.is_dir():
        for folder in sorted(
            p for p in data_root.iterdir() if p.is_dir() and not p.name.startswith(".")
        ):
            add_existing(
                folder / "imaging" / f"{folder.name}_{per_chart_suffix}.csv",
                found,
                seen,
            )

    return found


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, str]] = []
        for raw in reader:
            row = {
                (k or "").strip(): (v or "").strip()
                for k, v in raw.items()
                if k is not None
            }
            if row:
                rows.append(row)
        return rows


# Preferred export names replace older hw_printed.csv / rotation.csv
HW_FILENAMES = (
    "hw_printed_classification.csv",
    "hw_printed.csv",
)
HW_PACK_RELS = (
    ("01-ocr-extraction", "output", "hw_printed_classification.csv"),
    ("01-ocr-extraction", "output", "hw_printed.csv"),
)

ROTATION_FILENAMES = (
    "rotation_orientation.csv",
    "rotation.csv",
)
ROTATION_PACK_RELS = (
    (
        "02-imaging-pipeline",
        "rotation-orientation",
        "output",
        "rotation_orientation.csv",
    ),
    ("02-imaging-pipeline", "rotation-orientation", "output", "rotation.csv"),
)

DOS_FILENAMES = ("dos_extraction.csv",)
DOS_PACK_RELS = (
    ("02-imaging-pipeline", "dos-extraction", "output", "dos_extraction.csv"),
)
