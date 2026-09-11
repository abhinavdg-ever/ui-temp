#!/usr/bin/env python3
"""Load HW + rotation/orientation CSVs → ocr_quality_results.

Preferred filenames (replace older hw_printed.csv / rotation.csv):
  - hw_printed_classification.csv
  - rotation_orientation.csv

Discovery order:
  1) --hw-csv / --rotation-csv (optional)
  2) 05-imaging-ui/data/pipeline/ (flat or mirrored packs)
  3) monorepo 01-ocr-extraction / 02-imaging-pipeline outputs
  4) optional per-chart imaging/<chart>_hw_printed.csv / *_rotation.csv

If neither file type is found → skip (exit 0). Charts/pages must already exist
(run load_from_folders.py first).

Usage:
  python load_quality_csvs.py
  python load_quality_csvs.py --per-chart
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from load_dos_csv import load_chart_page_maps, resolve_page_id
from load_from_folders import (
    bootstrap_env,
    configure_connection,
    default_data_root,
    describe_dsn,
    psycopg_dsn,
    _require_psycopg,
)
from pipeline_paths import (
    HW_FILENAMES,
    HW_PACK_RELS,
    ROTATION_FILENAMES,
    ROTATION_PACK_RELS,
    discover_named_csvs,
    pipeline_drop_dirs,
    read_csv_rows,
)

# Widen NUMERIC for tilt/rotation if needed; ensure new columns on older DBs
_ENSURE_COLUMNS_SQL = (
    "ALTER TABLE ocr_quality_results ADD COLUMN IF NOT EXISTS handwritten_label VARCHAR(30)",
    "ALTER TABLE ocr_quality_results ADD COLUMN IF NOT EXISTS handwritten_confidence NUMERIC(5,4)",
    "ALTER TABLE ocr_quality_results ADD COLUMN IF NOT EXISTS rotation_deg NUMERIC(8,2)",
    "ALTER TABLE ocr_quality_results ADD COLUMN IF NOT EXISTS mirrored BOOLEAN",
)


def parse_confidence(raw: str | None) -> float | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        val = float(value)
    except ValueError:
        return None
    if val > 1:
        val = val / 100.0
    return round(val, 4)


def parse_float(raw: str | None) -> float | None:
    value = (raw or "").strip()
    if not value or value.upper() in {"N/A", "NULL", "NONE"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_bool(raw: str | None) -> bool | None:
    value = (raw or "").strip().lower()
    if not value:
        return None
    if value in {"1", "true", "t", "yes", "y", "mirrored"}:
        return True
    if value in {"0", "false", "f", "no", "n", "not mirrored", "not_mirrored"}:
        return False
    return None


def chart_key(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        val = (row.get(key) or "").strip()
        if val:
            return val
    return ""


def page_row_for_resolve(row: dict[str, str]) -> dict[str, str]:
    """Normalize HW / rotation column aliases for resolve_page_id."""
    page_name = (
        row.get("page_name")
        or row.get("filename")
        or row.get("page")
        or ""
    ).strip()
    page_number = (
        row.get("page_number")
        or row.get("page_num")
        or ""
    ).strip()
    if not page_number and page_name:
        stem = Path(page_name).stem
        if stem.isdigit():
            page_number = stem
    return {"page_name": page_name, "page_number": page_number}


def hw_fields(row: dict[str, str]) -> dict[str, Any] | None:
    label = (
        row.get("handwritten")
        or row.get("handwritten_or_printed")
        or row.get("type")
        or ""
    ).strip()
    if not label or label.upper() == "N/A":
        return None
    flag = "handwritten" in label.lower()
    return {
        "handwritten_flag": flag,
        "handwritten_label": label,
        "handwritten_confidence": parse_confidence(row.get("confidence")),
    }


def rotation_fields(row: dict[str, str]) -> dict[str, Any] | None:
    rotation = parse_float(
        row.get("rotation_deg")
        or row.get("rotation_degree")
        or row.get("rotation_di")
        or row.get("orientation_angle")
        or row.get("rotation")
    )
    tilt = parse_float(
        row.get("tilt_angle_deg")
        or row.get("tilt_angle")
        or row.get("tilt_angle_c")
        or row.get("tilt")
    )
    mirrored = parse_bool(row.get("mirrored"))
    if rotation is None and tilt is None and mirrored is None:
        return None
    orientation = None
    if rotation is not None:
        # Store compact degree string for legacy orientation column
        orientation = (
            str(int(rotation)) if float(rotation).is_integer() else f"{rotation:g}"
        )
    return {
        "orientation": orientation,
        "rotation_deg": rotation,
        "tilt_angle": tilt,
        "mirrored": mirrored,
    }


def merge_quality(
    target: dict[str, Any], patch: dict[str, Any]
) -> None:
    for key, value in patch.items():
        if value is not None:
            target[key] = value


def discover_hw_paths(
    explicit: Path | None,
    data_root: Path,
    include_per_chart: bool,
) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    if explicit is not None:
        from pipeline_paths import add_existing

        add_existing(explicit, found, seen)
    for path in discover_named_csvs(
        filenames=HW_FILENAMES,
        pack_rels=HW_PACK_RELS,
        data_root=data_root if include_per_chart else None,
        per_chart_suffix="hw_printed" if include_per_chart else None,
    ):
        if path.resolve() not in seen:
            seen.add(path.resolve())
            found.append(path)
    return found


def discover_rotation_paths(
    explicit: Path | None,
    data_root: Path,
    include_per_chart: bool,
) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    if explicit is not None:
        from pipeline_paths import add_existing

        add_existing(explicit, found, seen)
    for path in discover_named_csvs(
        filenames=ROTATION_FILENAMES,
        pack_rels=ROTATION_PACK_RELS,
        data_root=data_root if include_per_chart else None,
        per_chart_suffix="rotation" if include_per_chart else None,
    ):
        if path.resolve() not in seen:
            seen.add(path.resolve())
            found.append(path)
    return found


def ensure_quality_columns(cur: object) -> None:
    for sql in _ENSURE_COLUMNS_SQL:
        try:
            cur.execute(sql)
        except Exception as exc:  # noqa: BLE001 — older PG without IF NOT EXISTS
            # Ignore duplicate_column; re-raise anything else
            msg = str(exc).lower()
            if "already exists" not in msg and "duplicate" not in msg:
                raise


def load_quality_rows(
    conn: object,
    hw_rows: list[dict[str, str]],
    rotation_rows: list[dict[str, str]],
) -> tuple[int, int, int]:
    """Merge HW + rotation by page; replace ocr_quality_results for those pages."""
    inserted = 0
    skip_chart = 0
    skip_page = 0
    by_page: dict[int, dict[str, Any]] = {}

    with conn.cursor() as cur:
        ensure_quality_columns(cur)
        charts, by_name, by_num = load_chart_page_maps(cur)

        def resolve(row: dict[str, str], chart_keys: tuple[str, ...]) -> tuple[int, int] | None:
            nonlocal skip_chart, skip_page
            chart_name = chart_key(row, *chart_keys)
            if not chart_name or chart_name not in charts:
                # try fuzzy: chart may be prefix of folder name
                match = None
                if chart_name:
                    for name in charts:
                        if name == chart_name or name.startswith(chart_name + "_") or chart_name.startswith(name + "_"):
                            match = name
                            break
                if match is None:
                    skip_chart += 1
                    return None
                chart_name = match
            page_id = resolve_page_id(chart_name, page_row_for_resolve(row), by_name, by_num)
            if page_id is None:
                skip_page += 1
                return None
            return charts[chart_name], page_id

        for row in hw_rows:
            resolved = resolve(row, ("chart_name", "chart_id", "folder"))
            if resolved is None:
                continue
            chart_id, page_id = resolved
            fields = hw_fields(row)
            if not fields:
                continue
            bucket = by_page.setdefault(
                page_id,
                {
                    "chart_id": chart_id,
                    "page_id": page_id,
                    "handwritten_flag": False,
                },
            )
            merge_quality(bucket, fields)

        for row in rotation_rows:
            resolved = resolve(row, ("folder", "chart_name", "chart_id"))
            if resolved is None:
                continue
            chart_id, page_id = resolved
            fields = rotation_fields(row)
            if not fields:
                continue
            bucket = by_page.setdefault(
                page_id,
                {
                    "chart_id": chart_id,
                    "page_id": page_id,
                    "handwritten_flag": False,
                },
            )
            merge_quality(bucket, fields)

        if by_page:
            cur.execute(
                "DELETE FROM ocr_quality_results WHERE page_id = ANY(%s)",
                (list(by_page.keys()),),
            )

        for row in by_page.values():
            cur.execute(
                """
                INSERT INTO ocr_quality_results (
                    chart_id, page_id, handwritten_flag, handwritten_label,
                    handwritten_confidence, orientation, rotation_deg,
                    tilt_angle, mirrored
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row["chart_id"],
                    row["page_id"],
                    bool(row.get("handwritten_flag", False)),
                    row.get("handwritten_label"),
                    row.get("handwritten_confidence"),
                    row.get("orientation"),
                    row.get("rotation_deg"),
                    row.get("tilt_angle"),
                    row.get("mirrored"),
                ),
            )
            inserted += 1

    conn.commit()
    return inserted, skip_chart, skip_page


def main() -> None:
    ui_root = bootstrap_env()

    parser = argparse.ArgumentParser(
        description="Load hw_printed_classification + rotation_orientation → ocr_quality_results"
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="Postgres URL (or DATABASE_URL / 05-imaging-ui .env)",
    )
    parser.add_argument("--hw-csv", type=Path, default=None, help="HW classification CSV")
    parser.add_argument(
        "--rotation-csv", type=Path, default=None, help="Rotation/orientation CSV"
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=default_data_root(ui_root),
        help="data/folders root (for optional per-chart overrides)",
    )
    parser.add_argument(
        "--per-chart",
        action="store_true",
        help="Also load <chart>/imaging/<chart>_hw_printed.csv and *_rotation.csv",
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="Postgres schema (default: DB_SCHEMA / PG_SCHEMA / public)",
    )
    args = parser.parse_args()

    if args.schema:
        os.environ["DB_SCHEMA"] = args.schema

    database_url = psycopg_dsn(args.database_url)
    if not database_url:
        print(
            "DATABASE_URL is required "
            "(set env, or put it in 05-imaging-ui/.env next to 06-postgres-db)",
            file=sys.stderr,
        )
        sys.exit(1)

    data_root = args.data_root.resolve()
    hw_paths = discover_hw_paths(args.hw_csv, data_root, include_per_chart=args.per_chart)
    rot_paths = discover_rotation_paths(
        args.rotation_csv, data_root, include_per_chart=args.per_chart
    )

    if not hw_paths and not rot_paths:
        print("No HW / rotation CSVs found — skip.")
        print(f"  preferred: {', '.join(HW_FILENAMES)} | {', '.join(ROTATION_FILENAMES)}")
        for drop in pipeline_drop_dirs():
            print(f"  looked under: {drop}")
        sys.exit(0)

    hw_rows: list[dict[str, str]] = []
    for path in hw_paths:
        rows = read_csv_rows(path)
        print(f"  HW read {len(rows)} rows from {path}")
        hw_rows.extend(rows)

    rotation_rows: list[dict[str, str]] = []
    for path in rot_paths:
        rows = read_csv_rows(path)
        print(f"  rotation read {len(rows)} rows from {path}")
        rotation_rows.extend(rows)

    if not hw_rows and not rotation_rows:
        print("HW / rotation CSV(s) empty — skip.")
        sys.exit(0)

    print(f"database: {describe_dsn(database_url)}")
    print(f"HW rows: {len(hw_rows)}  rotation rows: {len(rotation_rows)}")

    psycopg = _require_psycopg()
    with psycopg.connect(database_url) as conn:
        configure_connection(conn)
        inserted, skip_chart, skip_page = load_quality_rows(conn, hw_rows, rotation_rows)

    print(
        f"done: inserted={inserted} skipped_no_chart={skip_chart} "
        f"skipped_no_page={skip_page}"
    )


if __name__ == "__main__":
    main()
