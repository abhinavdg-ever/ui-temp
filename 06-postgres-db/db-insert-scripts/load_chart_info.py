#!/usr/bin/env python3
"""Build chart_list / page_list CSVs under data/pipeline, then upsert into Postgres.

Source of truth for pages: 05-imaging-ui/data/folders/<chart>/pages
Intermediate CSVs:        05-imaging-ui/data/pipeline/chart_list.csv
                          05-imaging-ui/data/pipeline/page_list.csv

Append rules:
  - If chart already in chart_list.csv and page_count matches disk → skip
  - Otherwise append (or refresh pages when page_count changed)

Usage:
  cd 06-postgres-db/db-insert-scripts
  python load_chart_info.py
  python load_chart_info.py --csv-only          # write CSVs, skip Postgres
  python load_chart_info.py --db-only           # push existing CSVs to Postgres
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

from db_common import (
    PG_PACK_ROOT,
    bootstrap_env,
    chart_blob_path,
    configure_connection,
    default_data_root,
    default_pipeline_root,
    describe_dsn,
    list_page_files,
    psycopg_dsn,
    require_psycopg,
    upsert_chart,
    upsert_page,
)

CHART_HEADERS = [
    "chart_name",
    "page_count",
    "status",
    "path",
    "blob_container_name",
    "run_id",
    "batch_id",
]
PAGE_HEADERS = [
    "chart_name",
    "page_name",
    "page_number",
    "ocr_prelim_status",
    "ocr_final_status",
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, str]] = []
        for raw in reader:
            row = {
                (k or "").strip(): (v or "").strip()
                for k, v in raw.items()
                if k is not None
            }
            if row.get("chart_name"):
                rows.append(row)
        return rows


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in headers})


def sync_chart_csvs(
    *,
    data_root: Path,
    pipeline_root: Path,
    container_name: str,
    path_template: str,
) -> tuple[Path, Path, dict[str, int]]:
    """Scan folders → append/update pipeline chart_list.csv + page_list.csv."""
    chart_csv = pipeline_root / "chart_list.csv"
    page_csv = pipeline_root / "page_list.csv"

    chart_rows = _read_csv(chart_csv)
    page_rows = _read_csv(page_csv)

    by_chart: dict[str, dict[str, str]] = {
        r["chart_name"]: r for r in chart_rows if r.get("chart_name")
    }
    pages_by_chart: dict[str, list[dict[str, str]]] = {}
    for r in page_rows:
        pages_by_chart.setdefault(r["chart_name"], []).append(r)

    folders = sorted(
        p for p in data_root.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    stats = {"scanned": 0, "skipped": 0, "added": 0, "updated": 0}

    for folder in folders:
        stats["scanned"] += 1
        pages = list_page_files(folder)
        page_count = len(pages)
        existing = by_chart.get(folder.name)
        if existing is not None:
            try:
                existing_count = int(str(existing.get("page_count") or "0"))
            except ValueError:
                existing_count = -1
            if existing_count == page_count:
                stats["skipped"] += 1
                print(f"  skip {folder.name}: page_count={page_count} unchanged")
                continue
            stats["updated"] += 1
            action = "update"
        else:
            stats["added"] += 1
            action = "add"

        chart_path = chart_blob_path(path_template, folder.name)
        by_chart[folder.name] = {
            "chart_name": folder.name,
            "page_count": str(page_count),
            "status": (existing or {}).get("status") or "received",
            "path": chart_path,
            "blob_container_name": container_name
            or (existing or {}).get("blob_container_name")
            or "",
            "run_id": (existing or {}).get("run_id") or "",
            "batch_id": (existing or {}).get("batch_id") or "",
        }
        pages_by_chart[folder.name] = [
            {
                "chart_name": folder.name,
                "page_name": page_name,
                "page_number": str(num),
                "ocr_prelim_status": "pending",
                "ocr_final_status": "pending",
            }
            for page_name, num in pages
        ]
        print(f"  {action} {folder.name}: pages={page_count} path={chart_path}")

    # Stable order: existing chart names first (as previously written), then new
    ordered_names = list(by_chart.keys())
    new_chart_rows = [by_chart[n] for n in ordered_names]
    new_page_rows: list[dict[str, str]] = []
    for name in ordered_names:
        new_page_rows.extend(pages_by_chart.get(name, []))

    _write_csv(chart_csv, CHART_HEADERS, new_chart_rows)
    _write_csv(page_csv, PAGE_HEADERS, new_page_rows)
    print(
        f"Wrote {chart_csv.name}: {len(new_chart_rows)} charts "
        f"(+{stats['added']} ~{stats['updated']} skip {stats['skipped']})"
    )
    print(f"Wrote {page_csv.name}: {len(new_page_rows)} pages")
    return chart_csv, page_csv, stats


def push_chart_csvs_to_db(
    conn: object,
    *,
    chart_csv: Path,
    page_csv: Path,
) -> None:
    chart_rows = _read_csv(chart_csv)
    page_rows = _read_csv(page_csv)
    if not chart_rows:
        print(f"No chart rows in {chart_csv} — nothing to push")
        return

    pages_by_chart: dict[str, list[dict[str, str]]] = {}
    for r in page_rows:
        pages_by_chart.setdefault(r["chart_name"], []).append(r)

    with conn.cursor() as cur:
        for crow in chart_rows:
            name = crow["chart_name"]
            try:
                page_count = int(crow.get("page_count") or "0")
            except ValueError:
                page_count = 0
            chart_id = upsert_chart(
                cur,
                name,
                page_count,
                crow.get("path") or name,
                container_name=crow.get("blob_container_name") or None,
                status=crow.get("status") or "received",
                run_id=crow.get("run_id") or None,
                batch_id=crow.get("batch_id") or None,
            )
            for prow in pages_by_chart.get(name, []):
                upsert_page(
                    cur,
                    chart_id,
                    prow["page_name"],
                    ocr_prelim_status=prow.get("ocr_prelim_status") or "pending",
                    ocr_final_status=prow.get("ocr_final_status") or "pending",
                )
            print(
                f"  db {name}: chart_id={chart_id} "
                f"pages={len(pages_by_chart.get(name, []))}"
            )
    conn.commit()
    print(f"Pushed {len(chart_rows)} charts → chart_list / page_list")


def main() -> None:
    ui_root = bootstrap_env()
    parser = argparse.ArgumentParser(
        description="Scan data/folders → pipeline chart/page CSVs → Postgres"
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="Postgres URL (or DATABASE_URL / 05-imaging-ui .env)",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=default_data_root(ui_root),
        help="Path to data/folders",
    )
    parser.add_argument(
        "--pipeline-root",
        type=Path,
        default=default_pipeline_root(ui_root),
        help="Path to data/pipeline (chart_list.csv / page_list.csv)",
    )
    parser.add_argument(
        "--container-name",
        default=os.environ.get("BLOB_CONTAINER", ""),
        help="chart_list.blob_container_name",
    )
    parser.add_argument(
        "--path-template",
        default=os.environ.get("BLOB_PATH_TEMPLATE", "{folder}/pages/{filename}"),
        help="Blob path template; {folder}=chart_name",
    )
    parser.add_argument(
        "--csv-only",
        action="store_true",
        help="Only write/update pipeline CSVs (no Postgres)",
    )
    parser.add_argument(
        "--db-only",
        action="store_true",
        help="Only push existing pipeline CSVs to Postgres",
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="Postgres schema (default: DB_SCHEMA / public)",
    )
    args = parser.parse_args()

    if args.schema:
        os.environ["DB_SCHEMA"] = args.schema

    data_root = args.data_root.resolve()
    pipeline_root = args.pipeline_root.resolve()
    if not data_root.is_dir() and ui_root is not None:
        alt = (ui_root / "data" / "folders").resolve()
        if alt.is_dir():
            data_root = alt
    if not args.db_only and not data_root.is_dir():
        print(f"DATA_ROOT not found: {data_root}", file=sys.stderr)
        sys.exit(1)

    if ui_root:
        print(f"imaging-ui: {ui_root}")
    print(f"postgres-db pack: {PG_PACK_ROOT}")
    print(f"data_root: {data_root}")
    print(f"pipeline_root: {pipeline_root}")

    chart_csv = pipeline_root / "chart_list.csv"
    page_csv = pipeline_root / "page_list.csv"

    if not args.db_only:
        chart_csv, page_csv, _ = sync_chart_csvs(
            data_root=data_root,
            pipeline_root=pipeline_root,
            container_name=args.container_name,
            path_template=args.path_template,
        )

    if args.csv_only:
        print("Done (--csv-only).")
        return

    database_url = psycopg_dsn(args.database_url)
    if not database_url:
        print("DATABASE_URL is required to push CSVs to Postgres", file=sys.stderr)
        sys.exit(1)
    if not chart_csv.is_file():
        print(f"Missing {chart_csv} — run without --db-only first", file=sys.stderr)
        sys.exit(1)

    print(f"database: {describe_dsn(database_url)}")
    psycopg = require_psycopg()
    with psycopg.connect(database_url) as conn:
        configure_connection(conn)
        push_chart_csvs_to_db(conn, chart_csv=chart_csv, page_csv=page_csv)
    print("OK — chart_list / page_list updated.")


if __name__ == "__main__":
    main()
