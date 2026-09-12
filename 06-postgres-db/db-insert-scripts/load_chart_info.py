#!/usr/bin/env python3
"""Two steps (+ optional OCR):

  1) Scan data/folders → write data/pipeline/chart_list.csv + page_list.csv
  2) Load those two CSVs into Postgres chart_list / page_list
  3) Read data/folders/<chart>/ocr/* → ocr_results (raw text)

Append rules for step 1:
  - Chart already in CSV with same page_count → skip
  - Otherwise add / refresh pages

Usage:
  python load_chart_info.py              # write CSVs, load charts/pages + OCR
  python load_chart_info.py --csv-only   # write CSVs only
  python load_chart_info.py --db-only    # load existing CSVs + OCR into DB
  python load_chart_info.py --skip-ocr   # skip ocr_results load
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from pathlib import Path

from db_common import (
    BATCH_SIZE,
    PG_PACK_ROOT,
    bootstrap_env,
    chart_blob_path,
    configure_connection,
    default_data_root,
    default_pipeline_root,
    describe_dsn,
    iter_batches,
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

OCR_HEADERS = ["chart_name", "page_name", "ocr_type", "raw_text"]

# file suffix → ocr_results.ocr_type
OCR_FILE_MAP: list[tuple[str, str, tuple[str, ...]]] = [
    ("prelim", "tesseract", (".txt",)),
    ("final1", "docling", (".txt",)),
    ("final2", "azuredocintel", (".json", ".txt")),
]
OCR_MARKER_RE = re.compile(r"^=====\s*(.+?)\s*=====\s*$", re.MULTILINE)


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
    if not rows:
        return
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


def _apply_chart_batch(cur: object) -> None:
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


def _apply_page_batch(cur: object) -> None:
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


def load_csvs_into_db(conn: object, *, chart_csv: Path, page_csv: Path) -> None:
    """Step 2: load chart_list.csv / page_list.csv into Postgres in batches of 10k."""
    chart_rows = _read_csv(chart_csv)
    page_rows = _read_csv(page_csv)
    if not chart_rows:
        print(f"No rows in {chart_csv} — nothing to load")
        return

    print(
        f"Loading {chart_csv.name} ({len(chart_rows)} rows) → chart_list "
        f"in batches of {BATCH_SIZE} …"
    )
    print(
        f"Loading {page_csv.name} ({len(page_rows)} rows) → page_list "
        f"in batches of {BATCH_SIZE} …"
    )

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
            ) ON COMMIT DELETE ROWS
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
            ) ON COMMIT DELETE ROWS
            """
        )

        for batch_i, batch_n, batch in iter_batches(chart_rows):
            _copy_csv(cur, "stg_chart", CHART_HEADERS, batch)
            _apply_chart_batch(cur)
            conn.commit()
            print(f"  chart_list batch {batch_i}/{batch_n}: {len(batch)} rows")

        for batch_i, batch_n, batch in iter_batches(page_rows):
            _copy_csv(cur, "stg_page", PAGE_HEADERS, batch)
            _apply_page_batch(cur)
            conn.commit()
            print(f"  page_list batch {batch_i}/{batch_n}: {len(batch)} rows")

    print(
        f"Done — loaded {len(chart_rows)} charts and {len(page_rows)} pages "
        f"from CSV into chart_list / page_list"
    )


def find_ocr_file(folder: Path, suffix: str, exts: tuple[str, ...]) -> Path | None:
    ocr_dir = folder / "ocr"
    if not ocr_dir.is_dir():
        return None
    base = f"{folder.name}_{suffix}"
    for ext in exts:
        path = ocr_dir / f"{base}{ext}"
        if path.is_file():
            return path
    for ext in exts:
        matches = sorted(
            p
            for p in ocr_dir.iterdir()
            if p.is_file()
            and p.name.endswith(f"_{suffix}{ext}")
            and not p.name.startswith("._")
        )
        if matches:
            return matches[0]
    return None


def split_ocr_by_page(text: str) -> dict[str, str]:
    matches = list(OCR_MARKER_RE.finditer(text))
    if not matches:
        return {"__all__": text}
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[m.group(1).strip()] = text[start:end].strip()
    return out


def azdoc_json_page_texts(raw: str) -> dict[str, str]:
    """Map page filename → content from AzDocInt JSON; empty if not JSON pages."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    pages = data.get("pages") if isinstance(data, dict) else data
    if not isinstance(pages, list):
        return {}
    out: dict[str, str] = {}
    for i, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            continue
        filename = (
            page.get("fileName") or page.get("filename") or f"{i}.jpg"
        )
        body = page.get("content") or ""
        if not body and isinstance(page.get("lines"), list):
            body = "\n".join(
                str(line.get("content", ""))
                for line in page["lines"]
                if isinstance(line, dict)
            )
        out[str(filename).strip()] = body
    return out


def collect_ocr_rows(data_root: Path) -> list[dict[str, str]]:
    """Parse data/folders/<chart>/ocr/* into staging rows for ocr_results."""
    rows: list[dict[str, str]] = []
    folders = sorted(
        p for p in data_root.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    for folder in folders:
        page_names = [name for name, _ in list_page_files(folder)]
        for suffix, ocr_type, exts in OCR_FILE_MAP:
            path = find_ocr_file(folder, suffix, exts)
            if path is None:
                continue
            raw = path.read_text(encoding="utf-8", errors="replace")
            by_page: dict[str, str] = {}
            if path.suffix.lower() == ".json":
                by_page = azdoc_json_page_texts(raw)
                if not by_page:
                    # store full JSON on every page if structure unknown
                    for page_name in page_names:
                        rows.append(
                            {
                                "chart_name": folder.name,
                                "page_name": page_name,
                                "ocr_type": ocr_type,
                                "raw_text": raw,
                            }
                        )
                    continue
            else:
                by_page = split_ocr_by_page(raw)

            if "__all__" in by_page:
                payload = by_page["__all__"]
                targets = page_names or ["__document__"]
                for page_name in targets:
                    rows.append(
                        {
                            "chart_name": folder.name,
                            "page_name": page_name if page_names else "1.jpg",
                            "ocr_type": ocr_type,
                            "raw_text": payload,
                        }
                    )
                continue

            # Prefer known page files; also keep unmatched marker keys
            used: set[str] = set()
            for page_name in page_names:
                chunk = by_page.get(page_name)
                if chunk is None:
                    for key, val in by_page.items():
                        if key.lower() == page_name.lower():
                            chunk = val
                            break
                if chunk is None:
                    continue
                used.add(page_name)
                rows.append(
                    {
                        "chart_name": folder.name,
                        "page_name": page_name,
                        "ocr_type": ocr_type,
                        "raw_text": chunk,
                    }
                )
            for key, val in by_page.items():
                if key in used:
                    continue
                # skip if already matched case-insensitively
                if any(key.lower() == u.lower() for u in used):
                    continue
                rows.append(
                    {
                        "chart_name": folder.name,
                        "page_name": key,
                        "ocr_type": ocr_type,
                        "raw_text": val,
                    }
                )
    return rows


def load_ocr_into_db(conn: object, data_root: Path) -> None:
    """Load folder ocr/* files into ocr_results (batched COPY)."""
    rows = collect_ocr_rows(data_root)
    if not rows:
        print("No OCR files under data/folders/*/ocr — skip ocr_results")
        return

    print(
        f"Loading {len(rows)} OCR page-rows → ocr_results "
        f"in batches of {BATCH_SIZE} …"
    )
    charts = sorted({r["chart_name"] for r in rows})

    with conn.cursor() as cur:
        # Replace OCR for charts we are about to load
        cur.execute(
            """
            CREATE TEMP TABLE stg_ocr_charts (
                chart_name TEXT
            ) ON COMMIT DROP
            """
        )
        _copy_csv(cur, "stg_ocr_charts", ["chart_name"], [{"chart_name": c} for c in charts])
        cur.execute(
            """
            DELETE FROM ocr_results o
             WHERE o.chart_id IN (
                SELECT c.id FROM chart_list c
                JOIN stg_ocr_charts s ON s.chart_name = c.chart_name
             )
            """
        )
        conn.commit()
        print(f"  Cleared ocr_results for {len(charts)} charts")

        cur.execute(
            """
            CREATE TEMP TABLE stg_ocr (
                chart_name TEXT,
                page_name TEXT,
                ocr_type TEXT,
                raw_text TEXT
            ) ON COMMIT DELETE ROWS
            """
        )

        inserted = 0
        for batch_i, batch_n, batch in iter_batches(rows):
            _copy_csv(cur, "stg_ocr", OCR_HEADERS, batch)
            cur.execute(
                """
                WITH inserted AS (
                    INSERT INTO ocr_results (chart_id, page_id, ocr_type, raw_text)
                    SELECT
                        c.id,
                        p.id,
                        s.ocr_type,
                        s.raw_text
                    FROM stg_ocr s
                    JOIN (
                        SELECT DISTINCT ON (chart_name) id, chart_name
                        FROM chart_list
                        ORDER BY chart_name, id
                    ) c ON c.chart_name = s.chart_name
                    JOIN LATERAL (
                        SELECT id
                        FROM page_list
                        WHERE chart_id = c.id
                          AND (
                            page_name = s.page_name
                            OR lower(page_name) = lower(s.page_name)
                          )
                        ORDER BY id
                        LIMIT 1
                    ) p ON TRUE
                    WHERE s.ocr_type IN ('tesseract', 'docling', 'azuredocintel')
                    RETURNING 1
                )
                SELECT COUNT(*) FROM inserted
                """
            )
            n = int(cur.fetchone()[0])
            inserted += n

            # Update page OCR status flags for this batch
            cur.execute(
                """
                UPDATE page_list p
                   SET ocr_prelim_status = 'completed',
                       updated_at = now()
                  FROM stg_ocr s
                  JOIN (
                      SELECT DISTINCT ON (chart_name) id, chart_name
                      FROM chart_list
                      ORDER BY chart_name, id
                  ) c ON c.chart_name = s.chart_name
                 WHERE p.chart_id = c.id
                   AND p.page_name = s.page_name
                   AND s.ocr_type = 'tesseract'
                """
            )
            cur.execute(
                """
                UPDATE page_list p
                   SET ocr_final_status = 'completed',
                       updated_at = now()
                  FROM stg_ocr s
                  JOIN (
                      SELECT DISTINCT ON (chart_name) id, chart_name
                      FROM chart_list
                      ORDER BY chart_name, id
                  ) c ON c.chart_name = s.chart_name
                 WHERE p.chart_id = c.id
                   AND p.page_name = s.page_name
                   AND s.ocr_type IN ('docling', 'azuredocintel')
                """
            )
            conn.commit()
            print(
                f"  ocr_results batch {batch_i}/{batch_n}: "
                f"{len(batch)} staged, {n} inserted"
            )

    print(f"Done — inserted {inserted} OCR rows for {len(charts)} charts")


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
    parser.add_argument(
        "--skip-ocr",
        action="store_true",
        help="Skip loading data/folders/*/ocr into ocr_results",
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
        if not args.skip_ocr:
            print("\n=== 3) Load OCR files → ocr_results ===")
            if not data_root.is_dir():
                print(f"DATA_ROOT not found for OCR: {data_root}", file=sys.stderr)
            else:
                load_ocr_into_db(conn, data_root)
        else:
            print("\n=== 3) OCR skipped (--skip-ocr) ===")


if __name__ == "__main__":
    main()
