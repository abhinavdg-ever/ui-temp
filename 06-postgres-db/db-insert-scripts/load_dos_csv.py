#!/usr/bin/env python3
"""Load DOS extraction CSV → dos_extraction_results.

Sources (first found wins for combined; per-chart files are additive):
  1. --csv path (optional)
  2. 02-imaging-pipeline/dos-extraction/output/dos_extraction.csv
  3. <data-root>/<chart>/imaging/<chart>_dos.csv  (if --per-chart / auto-discover)

If no CSV files exist → skip (exit 0). Charts/pages must already be in Postgres
(run load_from_folders.py first).

Usage:
  python load_dos_csv.py
  python load_dos_csv.py --csv ../../02-imaging-pipeline/dos-extraction/output/dos_extraction.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import date, datetime
from pathlib import Path

from load_from_folders import (
    PG_PACK_ROOT,
    bootstrap_env,
    configure_connection,
    default_data_root,
    describe_dsn,
    parse_dob,
    psycopg_dsn,
    _require_psycopg,
)

MONOREPO_ROOT = PG_PACK_ROOT.parent
DEFAULT_COMBINED_CSV = (
    MONOREPO_ROOT / "02-imaging-pipeline" / "dos-extraction" / "output" / "dos_extraction.csv"
)


def parse_date(raw: str | None) -> date | None:
    """Prefer ISO YYYY-MM-DD; also accept MM/DD/YYYY and MM-DD-YYYY."""
    value = (raw or "").strip()
    if not value or value.lower() in {"unknown", "null", "none"}:
        return None
    # ISO first
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    # reuse folder loader helper (returns iso string)
    iso = parse_dob(value)
    if iso:
        return date.fromisoformat(iso)
    return None


def row_dates(row: dict[str, str]) -> tuple[date | None, date | None, date | None, date | None]:
    """Page + doc DOS; prefer *_iso columns when present."""
    dos_from = parse_date(row.get("dos_from_iso") or row.get("dos_from") or row.get("dos"))
    dos_to = parse_date(row.get("dos_to_iso") or row.get("dos_to") or "")
    if dos_from and not dos_to:
        # legacy single-dos CSV or single-date page
        dos_to = dos_from if (row.get("dos_from") or row.get("dos_from_iso") or row.get("dos")) else None

    doc_from = parse_date(row.get("doc_dos_from_iso") or row.get("doc_dos_from") or "")
    doc_to = parse_date(row.get("doc_dos_to_iso") or row.get("doc_dos_to") or "")
    return dos_from, dos_to, doc_from, doc_to


def read_dos_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, str]] = []
        for raw in reader:
            row = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k is not None}
            chart = row.get("chart_name") or ""
            if not chart:
                continue
            rows.append(row)
        return rows


def discover_csv_paths(
    combined: Path | None,
    data_root: Path,
    include_per_chart: bool,
) -> list[Path]:
    """Collect existing DOS CSV paths. Empty list → caller should skip."""
    found: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path | None) -> None:
        if path is None:
            return
        resolved = path.resolve()
        if resolved in seen or not resolved.is_file() or resolved.stat().st_size == 0:
            return
        seen.add(resolved)
        found.append(resolved)

    add(combined)

    if include_per_chart and data_root.is_dir():
        for folder in sorted(p for p in data_root.iterdir() if p.is_dir() and not p.name.startswith(".")):
            chart_csv = folder / "imaging" / f"{folder.name}_dos.csv"
            add(chart_csv)

    return found


def confidence_value(row: dict[str, str]) -> float | None:
    raw = (row.get("confidence") or "").strip()
    if not raw:
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    if val > 1:
        val = val / 100.0
    return round(val, 4)


def load_chart_page_maps(cur: object) -> tuple[dict[str, int], dict[tuple[str, str], int], dict[tuple[str, int], int]]:
    """chart_name → id; (chart_name, page_name) → page_id; (chart_name, page_number) → page_id."""
    cur.execute("SELECT id, chart_name FROM chart_list")
    charts = {str(name): int(cid) for cid, name in cur.fetchall()}

    cur.execute(
        """
        SELECT c.chart_name, p.id, p.page_name
        FROM page_list p
        JOIN chart_list c ON c.id = p.chart_id
        """
    )
    by_name: dict[tuple[str, str], int] = {}
    by_num: dict[tuple[str, int], int] = {}
    for chart_name, page_id, page_name in cur.fetchall():
        cname = str(chart_name)
        pname = str(page_name)
        by_name[(cname, pname)] = int(page_id)
        # also index stem / numeric basename (1.jpg → 1)
        stem = Path(pname).stem
        if stem.isdigit():
            by_num[(cname, int(stem))] = int(page_id)
        if pname.lower().startswith("page_") and stem[5:].isdigit():
            by_num[(cname, int(stem[5:]))] = int(page_id)
    return charts, by_name, by_num


def resolve_page_id(
    chart_name: str,
    row: dict[str, str],
    by_name: dict[tuple[str, str], int],
    by_num: dict[tuple[str, int], int],
) -> int | None:
    page_name = (row.get("page_name") or "").strip()
    if page_name:
        pid = by_name.get((chart_name, page_name))
        if pid is not None:
            return pid
        # try basename only
        base = Path(page_name).name
        pid = by_name.get((chart_name, base))
        if pid is not None:
            return pid

    raw_num = (row.get("page_number") or "").strip()
    if raw_num.isdigit():
        return by_num.get((chart_name, int(raw_num)))
    return None


def load_dos_rows(conn: object, rows: list[dict[str, str]]) -> tuple[int, int, int]:
    """Insert DOS rows. Returns (inserted, skipped_no_chart, skipped_no_page)."""
    inserted = 0
    skip_chart = 0
    skip_page = 0

    with conn.cursor() as cur:
        charts, by_name, by_num = load_chart_page_maps(cur)
        # Replace existing DOS rows for pages we are about to load (idempotent re-run)
        page_ids_to_replace: set[int] = set()
        prepared: list[tuple[int, int, date | None, date | None, date | None, date | None, float | None]] = []

        for row in rows:
            chart_name = (row.get("chart_name") or "").strip()
            if chart_name not in charts:
                skip_chart += 1
                continue
            chart_id = charts[chart_name]
            page_id = resolve_page_id(chart_name, row, by_name, by_num)
            if page_id is None:
                skip_page += 1
                continue
            dos_from, dos_to, doc_from, doc_to = row_dates(row)
            conf = confidence_value(row)
            page_ids_to_replace.add(page_id)
            prepared.append((chart_id, page_id, dos_from, dos_to, doc_from, doc_to, conf))

        if page_ids_to_replace:
            cur.execute(
                "DELETE FROM dos_extraction_results WHERE page_id = ANY(%s)",
                (list(page_ids_to_replace),),
            )

        for chart_id, page_id, dos_from, dos_to, doc_from, doc_to, conf in prepared:
            cur.execute(
                """
                INSERT INTO dos_extraction_results (
                    chart_id, page_id, dos_from, dos_to, doc_dos_from, doc_dos_to, confidence
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (chart_id, page_id, dos_from, dos_to, doc_from, doc_to, conf),
            )
            inserted += 1

    conn.commit()
    return inserted, skip_chart, skip_page


def main() -> None:
    ui_root = bootstrap_env()

    parser = argparse.ArgumentParser(
        description="Load dos_extraction.csv → dos_extraction_results (skip if no files)"
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="Postgres URL (or DATABASE_URL / 05-imaging-ui .env)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Combined DOS CSV (default: 02-imaging-pipeline/.../dos_extraction.csv)",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=default_data_root(ui_root),
        help="data/folders root (for optional per-chart imaging/*_dos.csv)",
    )
    parser.add_argument(
        "--per-chart",
        action="store_true",
        help="Also load <chart>/imaging/<chart>_dos.csv when present",
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="Postgres schema (default: DB_SCHEMA / PG_SCHEMA / imaging_outputs)",
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

    combined = args.csv.resolve() if args.csv else DEFAULT_COMBINED_CSV
    data_root = args.data_root.resolve()
    # Auto-include per-chart when combined is missing (still skip if none exist)
    include_per_chart = bool(args.per_chart) or not combined.is_file()

    paths = discover_csv_paths(combined, data_root, include_per_chart=include_per_chart)
    if not paths:
        print("No DOS CSV found — skip.")
        print(f"  looked for: {combined}")
        if include_per_chart:
            print(f"  and: {data_root}/<chart>/imaging/<chart>_dos.csv")
        sys.exit(0)

    all_rows: list[dict[str, str]] = []
    for path in paths:
        rows = read_dos_rows(path)
        print(f"  read {len(rows)} rows from {path}")
        all_rows.extend(rows)

    if not all_rows:
        print("DOS CSV(s) empty — skip.")
        sys.exit(0)

    print(f"database: {describe_dsn(database_url)}")
    print(f"total CSV rows: {len(all_rows)}")

    psycopg = _require_psycopg()
    with psycopg.connect(database_url) as conn:
        configure_connection(conn)
        inserted, skip_chart, skip_page = load_dos_rows(conn, all_rows)

    print(
        f"done: inserted={inserted} skipped_no_chart={skip_chart} "
        f"skipped_no_page={skip_page}"
    )


if __name__ == "__main__":
    main()
