#!/usr/bin/env python3
"""Load CSVs from 05-imaging-ui/data into Postgres (bulk COPY + set SQL).

  data/metadata/metadata_R*_B*.csv  → manifest_member_list
  data/pipeline/dos_extraction.csv  → dos_extraction_results
  data/pipeline/hw_printed*.csv     → ocr_quality_results
  data/pipeline/rotation*.csv       → ocr_quality_results

Prerequisite: load_chart_info.py (chart_list / page_list).

Usage:
  python load_pipeline.py
  python load_pipeline.py --skip-manifest
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from datetime import datetime
from pathlib import Path

from db_common import (
    METADATA_FILE_RE,
    bootstrap_env,
    chart_blob_path,
    configure_connection,
    default_metadata_dir,
    default_pipeline_root,
    describe_dsn,
    psycopg_dsn,
    require_psycopg,
)

HW_NAMES = ("hw_printed_classification.csv", "hw_printed.csv")
ROTATION_NAMES = ("rotation_orientation.csv", "rotation.csv")
DOS_NAMES = ("dos_extraction.csv",)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
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
            if row:
                rows.append(row)
        return rows


def first_existing(dir_path: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        cand = dir_path / name
        if cand.is_file() and cand.stat().st_size > 0:
            return cand
    return None


def parse_dob_iso(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def parse_date_iso(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value or value.lower() in {"unknown", "null", "none"}:
        return ""
    return parse_dob_iso(value)


def parse_confidence_str(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    try:
        val = float(value)
    except ValueError:
        return ""
    if val > 1:
        val = val / 100.0
    return f"{round(val, 4)}"


def parse_float_str(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value or value.upper() in {"N/A", "NULL", "NONE"}:
        return ""
    try:
        return str(float(value))
    except ValueError:
        return ""


def parse_bool_str(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in {"1", "true", "t", "yes", "y", "mirrored"}:
        return "true"
    if value in {"0", "false", "f", "no", "n", "not mirrored", "not_mirrored"}:
        return "false"
    return ""


def copy_rows(cur: object, table: str, headers: list[str], rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    for row in rows:
        writer.writerow({h: row.get(h, "") for h in headers})
    buf.seek(0)
    cols = ", ".join(headers)
    with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv)") as copy:
        while True:
            chunk = buf.read(1024 * 1024)
            if not chunk:
                break
            copy.write(chunk)


def discover_metadata_csvs(metadata_dir: Path) -> list[Path]:
    found: list[tuple[int, int, Path]] = []
    if not metadata_dir.is_dir():
        return []
    for path in metadata_dir.iterdir():
        if not path.is_file() or path.name.startswith("._"):
            continue
        m = METADATA_FILE_RE.match(path.name)
        if not m:
            continue
        found.append((int(m.group(1)), int(m.group(2)), path))
    found.sort(key=lambda t: (t[0], t[1], t[2].name))
    return [p for _, _, p in found]


def load_manifest(
    conn: object,
    metadata_dir: Path,
    *,
    container_name: str,
    path_template: str,
) -> None:
    sources = discover_metadata_csvs(metadata_dir)
    if not sources:
        print(f"  No metadata_R*_B*.csv in {metadata_dir} — skip")
        return

    stg_rows: list[dict[str, str]] = []
    for path in sources:
        rows = read_csv_rows(path)
        print(f"  read {path.name}: {len(rows)} rows")
        for row in rows:
            record_id = (row.get("recordId") or "").strip()
            if not record_id:
                continue
            name = f"{row.get('DummyFirstName', '')} {row.get('DummyLastName', '')}".strip()
            if not name:
                continue
            stg_rows.append(
                {
                    "record_id": record_id,
                    "member_name": name,
                    "member_dob": parse_dob_iso(row.get("DummyDOB", "")),
                    "external_member_id": (row.get("MemberID") or "").strip(),
                    "path": chart_blob_path(path_template, record_id),
                    "blob_container_name": container_name or "",
                }
            )

    if not stg_rows:
        print("  No usable manifest rows — skip")
        return

    headers = [
        "record_id",
        "member_name",
        "member_dob",
        "external_member_id",
        "path",
        "blob_container_name",
    ]
    print(f"  Loading {len(stg_rows)} rows → manifest_member_list …")

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TEMP TABLE stg_manifest (
                record_id TEXT,
                member_name TEXT,
                member_dob TEXT,
                external_member_id TEXT,
                path TEXT,
                blob_container_name TEXT
            ) ON COMMIT DROP
            """
        )
        copy_rows(cur, "stg_manifest", headers, stg_rows)

        cur.execute(
            """
            INSERT INTO chart_list
                (chart_name, page_count, status, path, blob_container_name)
            SELECT DISTINCT
                s.record_id, 0, 'received',
                NULLIF(s.path, ''), NULLIF(s.blob_container_name, '')
            FROM stg_manifest s
            WHERE NOT EXISTS (
                SELECT 1 FROM chart_list c WHERE c.chart_name = s.record_id
            )
            """
        )
        cur.execute(
            """
            DELETE FROM manifest_member_list m
             WHERE m.chart_id IN (
                SELECT DISTINCT c.id
                FROM stg_manifest s
                JOIN chart_list c ON c.chart_name = s.record_id
             )
            """
        )
        cur.execute(
            """
            INSERT INTO manifest_member_list
                (chart_id, member_name, member_dob, external_member_id)
            SELECT
                c.id,
                s.member_name,
                NULLIF(s.member_dob, '')::DATE,
                NULLIF(s.external_member_id, '')
            FROM stg_manifest s
            JOIN (
                SELECT DISTINCT ON (chart_name) id, chart_name
                FROM chart_list
                ORDER BY chart_name, id
            ) c ON c.chart_name = s.record_id
            """
        )
        cur.execute("SELECT COUNT(*) FROM stg_manifest")
        n = int(cur.fetchone()[0])
    conn.commit()
    print(f"  Done — {n} manifest rows loaded")


def load_dos(conn: object, pipeline_root: Path) -> None:
    path = first_existing(pipeline_root, DOS_NAMES)
    if path is None:
        print(f"  No {DOS_NAMES[0]} — skip")
        return
    raw_rows = read_csv_rows(path)
    print(f"  read {path.name}: {len(raw_rows)} rows")
    if not raw_rows:
        return

    stg_rows: list[dict[str, str]] = []
    for row in raw_rows:
        chart = (row.get("chart_name") or "").strip()
        if not chart:
            continue
        dos_from = parse_date_iso(
            row.get("dos_from_iso") or row.get("dos_from") or row.get("dos")
        )
        dos_to = parse_date_iso(row.get("dos_to_iso") or row.get("dos_to") or "")
        if dos_from and not dos_to and (
            row.get("dos_from") or row.get("dos_from_iso") or row.get("dos")
        ):
            dos_to = dos_from
        stg_rows.append(
            {
                "chart_name": chart,
                "page_name": (
                    row.get("page_name") or row.get("filename") or ""
                ).strip(),
                "page_number": (
                    row.get("page_number") or row.get("page_num") or ""
                ).strip(),
                "dos_from": dos_from,
                "dos_to": dos_to,
                "doc_dos_from": parse_date_iso(
                    row.get("doc_dos_from_iso") or row.get("doc_dos_from") or ""
                ),
                "doc_dos_to": parse_date_iso(
                    row.get("doc_dos_to_iso") or row.get("doc_dos_to") or ""
                ),
                "confidence": parse_confidence_str(row.get("confidence")),
            }
        )

    headers = [
        "chart_name",
        "page_name",
        "page_number",
        "dos_from",
        "dos_to",
        "doc_dos_from",
        "doc_dos_to",
        "confidence",
    ]
    print(f"  Loading {len(stg_rows)} rows → dos_extraction_results …")

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TEMP TABLE stg_dos (
                chart_name TEXT,
                page_name TEXT,
                page_number TEXT,
                dos_from TEXT,
                dos_to TEXT,
                doc_dos_from TEXT,
                doc_dos_to TEXT,
                confidence TEXT
            ) ON COMMIT DROP
            """
        )
        copy_rows(cur, "stg_dos", headers, stg_rows)

        cur.execute(
            """
            CREATE TEMP TABLE stg_dos_resolved ON COMMIT DROP AS
            SELECT
                c.id AS chart_id,
                p.id AS page_id,
                NULLIF(s.dos_from, '')::DATE AS dos_from,
                NULLIF(s.dos_to, '')::DATE AS dos_to,
                NULLIF(s.doc_dos_from, '')::DATE AS doc_dos_from,
                NULLIF(s.doc_dos_to, '')::DATE AS doc_dos_to,
                NULLIF(s.confidence, '')::NUMERIC(5,4) AS confidence
            FROM stg_dos s
            JOIN LATERAL (
                SELECT id
                FROM chart_list
                WHERE chart_name = s.chart_name
                   OR chart_name LIKE s.chart_name || '_%'
                   OR s.chart_name LIKE chart_name || '_%'
                ORDER BY CASE WHEN chart_name = s.chart_name THEN 0 ELSE 1 END, id
                LIMIT 1
            ) c ON TRUE
            JOIN LATERAL (
                SELECT id
                FROM page_list
                WHERE chart_id = c.id
                  AND (
                    page_name = s.page_name
                    OR page_name = regexp_replace(s.page_name, '^.*/', '')
                    OR (
                        s.page_number ~ '^[0-9]+$'
                        AND regexp_replace(page_name, '\\.[^.]+$', '') = s.page_number
                    )
                  )
                ORDER BY id
                LIMIT 1
            ) p ON TRUE
            """
        )
        cur.execute(
            """
            DELETE FROM dos_extraction_results d
             WHERE d.page_id IN (SELECT DISTINCT page_id FROM stg_dos_resolved)
            """
        )
        cur.execute(
            """
            INSERT INTO dos_extraction_results (
                chart_id, page_id, dos_from, dos_to,
                doc_dos_from, doc_dos_to, confidence
            )
            SELECT chart_id, page_id, dos_from, dos_to,
                   doc_dos_from, doc_dos_to, confidence
            FROM stg_dos_resolved
            """
        )
        cur.execute("SELECT COUNT(*) FROM stg_dos_resolved")
        n = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM stg_dos")
        total = int(cur.fetchone()[0])
    conn.commit()
    print(f"  Done — inserted={n} (unmatched={total - n})")


def load_quality(conn: object, pipeline_root: Path) -> None:
    hw_path = first_existing(pipeline_root, HW_NAMES)
    rot_path = first_existing(pipeline_root, ROTATION_NAMES)
    if hw_path is None and rot_path is None:
        print("  No HW/rotation CSVs — skip")
        return

    hw_rows = read_csv_rows(hw_path) if hw_path else []
    rot_rows = read_csv_rows(rot_path) if rot_path else []
    if hw_path:
        print(f"  read {hw_path.name}: {len(hw_rows)} rows")
    if rot_path:
        print(f"  read {rot_path.name}: {len(rot_rows)} rows")

    stg_hw: list[dict[str, str]] = []
    for row in hw_rows:
        chart = (
            row.get("chart_name") or row.get("chart_id") or row.get("folder") or ""
        ).strip()
        label = (
            row.get("handwritten")
            or row.get("handwritten_or_printed")
            or row.get("type")
            or ""
        ).strip()
        if not chart or not label or label.upper() == "N/A":
            continue
        stg_hw.append(
            {
                "chart_name": chart,
                "page_name": (
                    row.get("page_name") or row.get("filename") or row.get("page") or ""
                ).strip(),
                "page_number": (
                    row.get("page_number") or row.get("page_num") or ""
                ).strip(),
                "handwritten_label": label,
                "handwritten_flag": "true" if "handwritten" in label.lower() else "false",
                "handwritten_confidence": parse_confidence_str(row.get("confidence")),
            }
        )

    stg_rot: list[dict[str, str]] = []
    for row in rot_rows:
        chart = (
            row.get("folder") or row.get("chart_name") or row.get("chart_id") or ""
        ).strip()
        if not chart:
            continue
        rotation = parse_float_str(
            row.get("rotation_deg")
            or row.get("rotation_degree")
            or row.get("rotation_di")
            or row.get("orientation_angle")
            or row.get("rotation")
        )
        tilt = parse_float_str(
            row.get("tilt_angle_deg")
            or row.get("tilt_angle")
            or row.get("tilt_angle_c")
            or row.get("tilt")
        )
        mirrored = parse_bool_str(row.get("mirrored"))
        if not rotation and not tilt and not mirrored:
            continue
        orientation = ""
        if rotation:
            try:
                r = float(rotation)
                orientation = str(int(r)) if r.is_integer() else f"{r:g}"
            except ValueError:
                orientation = rotation
        stg_rot.append(
            {
                "chart_name": chart,
                "page_name": (
                    row.get("page_name") or row.get("filename") or row.get("page") or ""
                ).strip(),
                "page_number": (
                    row.get("page_number") or row.get("page_num") or ""
                ).strip(),
                "orientation": orientation,
                "rotation_deg": rotation,
                "tilt_angle": tilt,
                "mirrored": mirrored,
            }
        )

    print(
        f"  Loading HW={len(stg_hw)} rotation={len(stg_rot)} → ocr_quality_results …"
    )

    with conn.cursor() as cur:
        for sql in (
            "ALTER TABLE ocr_quality_results ADD COLUMN IF NOT EXISTS handwritten_label VARCHAR(30)",
            "ALTER TABLE ocr_quality_results ADD COLUMN IF NOT EXISTS handwritten_confidence NUMERIC(5,4)",
            "ALTER TABLE ocr_quality_results ADD COLUMN IF NOT EXISTS rotation_deg NUMERIC(8,2)",
            "ALTER TABLE ocr_quality_results ADD COLUMN IF NOT EXISTS mirrored BOOLEAN",
        ):
            try:
                cur.execute(sql)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc).lower()
                if "already exists" not in msg and "duplicate" not in msg:
                    raise

        cur.execute(
            """
            CREATE TEMP TABLE stg_hw (
                chart_name TEXT,
                page_name TEXT,
                page_number TEXT,
                handwritten_label TEXT,
                handwritten_flag TEXT,
                handwritten_confidence TEXT
            ) ON COMMIT DROP
            """
        )
        cur.execute(
            """
            CREATE TEMP TABLE stg_rot (
                chart_name TEXT,
                page_name TEXT,
                page_number TEXT,
                orientation TEXT,
                rotation_deg TEXT,
                tilt_angle TEXT,
                mirrored TEXT
            ) ON COMMIT DROP
            """
        )
        copy_rows(
            cur,
            "stg_hw",
            [
                "chart_name",
                "page_name",
                "page_number",
                "handwritten_label",
                "handwritten_flag",
                "handwritten_confidence",
            ],
            stg_hw,
        )
        copy_rows(
            cur,
            "stg_rot",
            [
                "chart_name",
                "page_name",
                "page_number",
                "orientation",
                "rotation_deg",
                "tilt_angle",
                "mirrored",
            ],
            stg_rot,
        )

        # Resolve pages once, merge HW + rotation by page_id
        cur.execute(
            """
            CREATE TEMP TABLE stg_quality ON COMMIT DROP AS
            WITH charts AS (
                SELECT DISTINCT ON (chart_name) id, chart_name
                FROM chart_list
                ORDER BY chart_name, id
            ),
            hw AS (
                SELECT
                    c.id AS chart_id,
                    p.id AS page_id,
                    s.handwritten_label,
                    s.handwritten_flag = 'true' AS handwritten_flag,
                    NULLIF(s.handwritten_confidence, '')::NUMERIC(5,4)
                        AS handwritten_confidence
                FROM stg_hw s
                JOIN LATERAL (
                    SELECT id FROM chart_list
                    WHERE chart_name = s.chart_name
                       OR chart_name LIKE s.chart_name || '_%'
                       OR s.chart_name LIKE chart_name || '_%'
                    ORDER BY CASE WHEN chart_name = s.chart_name THEN 0 ELSE 1 END, id
                    LIMIT 1
                ) c ON TRUE
                JOIN LATERAL (
                    SELECT id FROM page_list
                    WHERE chart_id = c.id
                      AND (
                        page_name = s.page_name
                        OR page_name = regexp_replace(s.page_name, '^.*/', '')
                        OR (
                            s.page_number ~ '^[0-9]+$'
                            AND regexp_replace(page_name, '\\.[^.]+$', '') = s.page_number
                        )
                      )
                    ORDER BY id LIMIT 1
                ) p ON TRUE
            ),
            rot AS (
                SELECT
                    c.id AS chart_id,
                    p.id AS page_id,
                    NULLIF(s.orientation, '') AS orientation,
                    NULLIF(s.rotation_deg, '')::NUMERIC(8,2) AS rotation_deg,
                    NULLIF(s.tilt_angle, '')::NUMERIC(6,2) AS tilt_angle,
                    CASE
                        WHEN s.mirrored = 'true' THEN TRUE
                        WHEN s.mirrored = 'false' THEN FALSE
                        ELSE NULL
                    END AS mirrored
                FROM stg_rot s
                JOIN LATERAL (
                    SELECT id FROM chart_list
                    WHERE chart_name = s.chart_name
                       OR chart_name LIKE s.chart_name || '_%'
                       OR s.chart_name LIKE chart_name || '_%'
                    ORDER BY CASE WHEN chart_name = s.chart_name THEN 0 ELSE 1 END, id
                    LIMIT 1
                ) c ON TRUE
                JOIN LATERAL (
                    SELECT id FROM page_list
                    WHERE chart_id = c.id
                      AND (
                        page_name = s.page_name
                        OR page_name = regexp_replace(s.page_name, '^.*/', '')
                        OR (
                            s.page_number ~ '^[0-9]+$'
                            AND regexp_replace(page_name, '\\.[^.]+$', '') = s.page_number
                        )
                      )
                    ORDER BY id LIMIT 1
                ) p ON TRUE
            ),
            pages AS (
                SELECT page_id, MAX(chart_id) AS chart_id FROM (
                    SELECT page_id, chart_id FROM hw
                    UNION ALL
                    SELECT page_id, chart_id FROM rot
                ) u
                GROUP BY page_id
            )
            SELECT
                pages.chart_id,
                pages.page_id,
                COALESCE(hw.handwritten_flag, FALSE) AS handwritten_flag,
                hw.handwritten_label,
                hw.handwritten_confidence,
                rot.orientation,
                rot.rotation_deg,
                rot.tilt_angle,
                rot.mirrored
            FROM pages
            LEFT JOIN hw ON hw.page_id = pages.page_id
            LEFT JOIN rot ON rot.page_id = pages.page_id
            """
        )
        cur.execute(
            """
            DELETE FROM ocr_quality_results q
             WHERE q.page_id IN (SELECT page_id FROM stg_quality)
            """
        )
        cur.execute(
            """
            INSERT INTO ocr_quality_results (
                chart_id, page_id, handwritten_flag, handwritten_label,
                handwritten_confidence, orientation, rotation_deg,
                tilt_angle, mirrored
            )
            SELECT
                chart_id, page_id, handwritten_flag, handwritten_label,
                handwritten_confidence, orientation, rotation_deg,
                tilt_angle, mirrored
            FROM stg_quality
            """
        )
        cur.execute("SELECT COUNT(*) FROM stg_quality")
        n = int(cur.fetchone()[0])
    conn.commit()
    print(f"  Done — inserted={n}")


def main() -> None:
    ui_root = bootstrap_env()
    parser = argparse.ArgumentParser(
        description="Bulk-load metadata + pipeline CSVs into Postgres"
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument(
        "--pipeline-root", type=Path, default=default_pipeline_root(ui_root)
    )
    parser.add_argument(
        "--metadata-dir", type=Path, default=default_metadata_dir(ui_root)
    )
    parser.add_argument(
        "--container-name", default=os.environ.get("BLOB_CONTAINER", "")
    )
    parser.add_argument(
        "--path-template",
        default=os.environ.get("BLOB_PATH_TEMPLATE", "{folder}/pages/{filename}"),
    )
    parser.add_argument("--skip-manifest", action="store_true")
    parser.add_argument("--skip-dos", action="store_true")
    parser.add_argument("--skip-quality", action="store_true")
    parser.add_argument("--schema", default=None)
    args = parser.parse_args()

    if args.schema:
        os.environ["DB_SCHEMA"] = args.schema

    database_url = psycopg_dsn(args.database_url)
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        sys.exit(1)

    pipeline_root = args.pipeline_root.resolve()
    metadata_dir = args.metadata_dir.resolve()

    if ui_root:
        print(f"imaging-ui: {ui_root}")
    print(f"database: {describe_dsn(database_url)}")
    print(f"pipeline: {pipeline_root}")
    print(f"metadata: {metadata_dir}")

    psycopg = require_psycopg()
    with psycopg.connect(database_url) as conn:
        configure_connection(conn)
        if not args.skip_manifest:
            print("\n=== manifest_member_list ===")
            load_manifest(
                conn,
                metadata_dir,
                container_name=args.container_name,
                path_template=args.path_template,
            )
        if not args.skip_dos:
            print("\n=== dos_extraction_results ===")
            load_dos(conn, pipeline_root)
        if not args.skip_quality:
            print("\n=== ocr_quality_results ===")
            load_quality(conn, pipeline_root)

    print("\nOK — pipeline load finished.")


if __name__ == "__main__":
    main()
