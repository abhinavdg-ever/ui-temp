#!/usr/bin/env python3
"""Two steps only:

  1) Scan data/folders → write data/pipeline/chart_list.csv + page_list.csv
  2) Load those two CSVs into Postgres chart_list / page_list

Append rules for step 1:
  - Chart already in CSV with same page_count → skip
  - Otherwise add / refresh pages

Usage:
  python load_chart_info.py              # write CSVs, then load into DB
  python load_chart_info.py --csv-only   # write CSVs only
  python load_chart_info.py --db-only    # load existing CSVs into DB only
"""

from __future__ import annotations

import argparse
import csv
import io
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
        rows: list[dict[str, str]] = []
        for raw in csv.DictReader(f):
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
) -> tuple[Path, Path]:
    """Step 1: folders → chart_list.csv + page_list.csv."""
    chart_csv = pipeline_root / "chart_list.csv"
    page_csv = pipeline_root / "page_list.csv"

    by_chart: dict[str, dict[str, str]] = {
        r["chart_name"]: r for r in _read_csv(chart_csv) if r.get("chart_name")
    }
    pages_by_chart: dict[str, list[dict[str, str]]] = {}
    for r in _read_csv(page_csv):
        pages_by_chart.setdefault(r["chart_name"], []).append(r)

    folders = sorted(
        p for p in data_root.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    added = updated = skipped = 0

    for folder in folders:
        pages = list_page_files(folder)
        page_count = len(pages)
        existing = by_chart.get(folder.name)
        if existing is not None:
            try:
                existing_count = int(str(existing.get("page_count") or "0"))
            except ValueError:
                existing_count = -1
            if existing_count == page_count:
                skipped += 1
                continue
            updated += 1
        else:
            added += 1

        by_chart[folder.name] = {
            "chart_name": folder.name,
            "page_count": str(page_count),
            "status": (existing or {}).get("status") or "received",
            "path": chart_blob_path(path_template, folder.name),
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

    ordered = list(by_chart.keys())
    chart_rows = [by_chart[n] for n in ordered]
    page_rows: list[dict[str, str]] = []
    for name in ordered:
        page_rows.extend(pages_by_chart.get(name, []))

    _write_csv(chart_csv, CHART_HEADERS, chart_rows)
    _write_csv(page_csv, PAGE_HEADERS, page_rows)
    print(
        f"Wrote {chart_csv}: {len(chart_rows)} charts "
        f"(+{added} ~{updated} skip {skipped})"
    )
    print(f"Wrote {page_csv}: {len(page_rows)} pages")
    return chart_csv, page_csv


def _copy_csv(cur: object, table: str, headers: list[str], rows: list[dict[str, str]]) -> None:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    for row in rows:
        writer.writerow({h: row.get(h, "") for h in headers})
    buf.seek(0)
    with cur.copy(f"COPY {table} ({', '.join(headers)}) FROM STDIN WITH (FORMAT csv)") as copy:
        while True:
            chunk = buf.read(1024 * 1024)
            if not chunk:
                break
            copy.write(chunk)


def load_csvs_into_db(conn: object, *, chart_csv: Path, page_csv: Path) -> None:
    """Step 2: load chart_list.csv / page_list.csv into Postgres tables."""
    chart_rows = _read_csv(chart_csv)
    page_rows = _read_csv(page_csv)
    if not chart_rows:
        print(f"No rows in {chart_csv} — nothing to load")
        return

    print(f"Loading {chart_csv.name} ({len(chart_rows)} rows) → chart_list …")
    print(f"Loading {page_csv.name} ({len(page_rows)} rows) → page_list …")

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TEMP TABLE stg_chart (
                chart_name TEXT,
                page_count TEXT,
                status TEXT,
                path TEXT,
                blob_container_name TEXT,
                run_id TEXT,
                batch_id TEXT
            ) ON COMMIT DROP
            """
        )
        cur.execute(
            """
            CREATE TEMP TABLE stg_page (
                chart_name TEXT,
                page_name TEXT,
                page_number TEXT,
                ocr_prelim_status TEXT,
                ocr_final_status TEXT
            ) ON COMMIT DROP
            """
        )
        _copy_csv(cur, "stg_chart", CHART_HEADERS, chart_rows)
        if page_rows:
            _copy_csv(cur, "stg_page", PAGE_HEADERS, page_rows)

        # Update existing charts (keep lowest id if duplicates)
        cur.execute(
            """
            UPDATE chart_list c
               SET page_count = NULLIF(s.page_count, '')::INT,
                   status = COALESCE(NULLIF(s.status, ''), c.status),
                   path = COALESCE(NULLIF(s.path, ''), c.path),
                   blob_container_name = COALESCE(
                       NULLIF(s.blob_container_name, ''), c.blob_container_name
                   ),
                   run_id = COALESCE(NULLIF(s.run_id, ''), c.run_id),
                   batch_id = COALESCE(NULLIF(s.batch_id, ''), c.batch_id),
                   updated_at = now()
              FROM stg_chart s
             WHERE c.chart_name = s.chart_name
               AND c.id = (
                   SELECT MIN(c2.id) FROM chart_list c2
                    WHERE c2.chart_name = s.chart_name
               )
            """
        )
        cur.execute(
            """
            INSERT INTO chart_list
                (chart_name, page_count, status, path, blob_container_name, run_id, batch_id)
            SELECT
                s.chart_name,
                COALESCE(NULLIF(s.page_count, '')::INT, 0),
                COALESCE(NULLIF(s.status, ''), 'received'),
                NULLIF(s.path, ''),
                NULLIF(s.blob_container_name, ''),
                NULLIF(s.run_id, ''),
                NULLIF(s.batch_id, '')
            FROM stg_chart s
            WHERE NOT EXISTS (
                SELECT 1 FROM chart_list c WHERE c.chart_name = s.chart_name
            )
            """
        )

        # Update existing pages
        cur.execute(
            """
            UPDATE page_list p
               SET ocr_prelim_status = COALESCE(
                       NULLIF(s.ocr_prelim_status, ''), p.ocr_prelim_status
                   ),
                   ocr_final_status = COALESCE(
                       NULLIF(s.ocr_final_status, ''), p.ocr_final_status
                   ),
                   updated_at = now()
              FROM stg_page s
              JOIN (
                  SELECT DISTINCT ON (chart_name) id, chart_name
                  FROM chart_list
                  ORDER BY chart_name, id
              ) c ON c.chart_name = s.chart_name
             WHERE p.chart_id = c.id
               AND p.page_name = s.page_name
            """
        )
        cur.execute(
            """
            INSERT INTO page_list
                (chart_id, page_name, ocr_prelim_status, ocr_final_status)
            SELECT
                c.id,
                s.page_name,
                COALESCE(NULLIF(s.ocr_prelim_status, ''), 'pending'),
                COALESCE(NULLIF(s.ocr_final_status, ''), 'pending')
            FROM stg_page s
            JOIN (
                SELECT DISTINCT ON (chart_name) id, chart_name
                FROM chart_list
                ORDER BY chart_name, id
            ) c ON c.chart_name = s.chart_name
            WHERE s.page_name <> ''
              AND NOT EXISTS (
                  SELECT 1 FROM page_list p
                   WHERE p.chart_id = c.id AND p.page_name = s.page_name
              )
            """
        )

    conn.commit()
    print(
        f"Done — loaded {len(chart_rows)} charts and {len(page_rows)} pages "
        f"from CSV into chart_list / page_list"
    )


def main() -> None:
    ui_root = bootstrap_env()
    parser = argparse.ArgumentParser(
        description="Write chart/page CSVs, then load those CSVs into Postgres"
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--data-root", type=Path, default=default_data_root(ui_root))
    parser.add_argument(
        "--pipeline-root", type=Path, default=default_pipeline_root(ui_root)
    )
    parser.add_argument(
        "--container-name", default=os.environ.get("BLOB_CONTAINER", "")
    )
    parser.add_argument(
        "--path-template",
        default=os.environ.get("BLOB_PATH_TEMPLATE", "{folder}/pages/{filename}"),
    )
    parser.add_argument(
        "--csv-only", action="store_true", help="Write CSVs only (do not touch DB)"
    )
    parser.add_argument(
        "--db-only",
        action="store_true",
        help="Load existing pipeline CSVs into DB only",
    )
    parser.add_argument("--schema", default=None)
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
    print(f"pipeline_root: {pipeline_root}")

    chart_csv = pipeline_root / "chart_list.csv"
    page_csv = pipeline_root / "page_list.csv"

    if not args.db_only:
        print("\n=== 1) Write CSVs from data/folders ===")
        chart_csv, page_csv = sync_chart_csvs(
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
        print("DATABASE_URL is required to load CSVs into Postgres", file=sys.stderr)
        sys.exit(1)
    if not chart_csv.is_file():
        print(f"Missing {chart_csv}", file=sys.stderr)
        sys.exit(1)

    print("\n=== 2) Load CSVs into Postgres ===")
    print(f"database: {describe_dsn(database_url)}")
    psycopg = require_psycopg()
    with psycopg.connect(database_url) as conn:
        configure_connection(conn)
        load_csvs_into_db(conn, chart_csv=chart_csv, page_csv=page_csv)


if __name__ == "__main__":
    main()
