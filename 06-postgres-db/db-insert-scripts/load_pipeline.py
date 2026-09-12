#!/usr/bin/env python3
"""Load CSVs from 05-imaging-ui/data into Postgres imaging tables.

Reads:
  data/metadata/metadata_R*_B*.csv  → manifest_member_list
  data/pipeline/dos_extraction.csv  → dos_extraction_results
  data/pipeline/hw_printed*.csv     → ocr_quality_results
  data/pipeline/rotation*.csv       → ocr_quality_results

Prerequisite: run load_chart_info.py first (chart_list / page_list).

Usage:
  cd 06-postgres-db/db-insert-scripts
  python load_pipeline.py
  python load_pipeline.py --skip-manifest
  python load_pipeline.py --skip-dos --skip-quality
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from db_common import (
    METADATA_FILE_RE,
    PG_PACK_ROOT,
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


def parse_dob(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_date(raw: str | None) -> date | None:
    value = (raw or "").strip()
    if not value or value.lower() in {"unknown", "null", "none"}:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    iso = parse_dob(value)
    return date.fromisoformat(iso) if iso else None


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


def load_chart_page_maps(
    cur: object,
) -> tuple[dict[str, int], dict[tuple[str, str], int], dict[tuple[str, int], int]]:
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
        stem = Path(pname).stem
        if stem.isdigit():
            by_num[(cname, int(stem))] = int(page_id)
    return charts, by_name, by_num


def resolve_page_id(
    chart_name: str,
    row: dict[str, str],
    by_name: dict[tuple[str, str], int],
    by_num: dict[tuple[str, int], int],
) -> int | None:
    page_name = (
        row.get("page_name") or row.get("filename") or row.get("page") or ""
    ).strip()
    if page_name:
        pid = by_name.get((chart_name, page_name)) or by_name.get(
            (chart_name, Path(page_name).name)
        )
        if pid is not None:
            return pid
    raw_num = (row.get("page_number") or row.get("page_num") or "").strip()
    if raw_num.isdigit():
        return by_num.get((chart_name, int(raw_num)))
    if page_name:
        stem = Path(page_name).stem
        if stem.isdigit():
            return by_num.get((chart_name, int(stem)))
    return None


def match_chart(charts: dict[str, int], name: str) -> str | None:
    if not name:
        return None
    if name in charts:
        return name
    for cname in charts:
        if cname.startswith(name + "_") or name.startswith(cname + "_"):
            return cname
    return None


# ----- manifest -----


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
        print(f"  No metadata_R*_B*.csv in {metadata_dir} — skip manifest")
        return

    stacked: list[dict[str, str]] = []
    for path in sources:
        rows = read_csv_rows(path)
        print(f"  metadata {path.name}: {len(rows)} rows")
        stacked.extend(r for r in rows if r.get("recordId"))

    by_record: dict[str, list[dict[str, str]]] = {}
    for row in stacked:
        by_record.setdefault(row["recordId"], []).append(row)

    with conn.cursor() as cur:
        for record_id, rows in sorted(by_record.items()):
            chart_path = chart_blob_path(path_template, record_id)
            cur.execute(
                "SELECT id FROM chart_list WHERE chart_name = %s ORDER BY id LIMIT 1",
                (record_id,),
            )
            crow = cur.fetchone()
            if crow:
                chart_id = int(crow[0])
            else:
                cur.execute(
                    """
                    INSERT INTO chart_list
                        (chart_name, page_count, status, path, blob_container_name)
                    VALUES (%s, 0, 'received', %s, %s)
                    RETURNING id
                    """,
                    (record_id, chart_path, container_name or None),
                )
                chart_id = int(cur.fetchone()[0])

            cur.execute(
                "DELETE FROM manifest_member_list WHERE chart_id = %s", (chart_id,)
            )
            n = 0
            for row in rows:
                name = f"{row.get('DummyFirstName', '')} {row.get('DummyLastName', '')}".strip()
                if not name:
                    continue
                cur.execute(
                    """
                    INSERT INTO manifest_member_list
                        (chart_id, member_name, member_dob, external_member_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        chart_id,
                        name,
                        parse_dob(row.get("DummyDOB", "")),
                        row.get("MemberID") or None,
                    ),
                )
                n += 1
            print(f"  {record_id}: chart_id={chart_id} manifest={n}")
    conn.commit()
    print(f"  → manifest_member_list ({len(by_record)} charts)")


# ----- DOS -----


def load_dos(conn: object, pipeline_root: Path) -> None:
    path = first_existing(pipeline_root, DOS_NAMES)
    if path is None:
        print(f"  No {DOS_NAMES[0]} in {pipeline_root} — skip DOS")
        return
    rows = read_csv_rows(path)
    print(f"  read {len(rows)} DOS rows from {path.name}")
    if not rows:
        return

    inserted = skip_chart = skip_page = 0
    with conn.cursor() as cur:
        charts, by_name, by_num = load_chart_page_maps(cur)
        page_ids: set[int] = set()
        prepared: list[tuple] = []
        for row in rows:
            chart_name = match_chart(
                charts, (row.get("chart_name") or "").strip()
            )
            if not chart_name:
                skip_chart += 1
                continue
            page_id = resolve_page_id(chart_name, row, by_name, by_num)
            if page_id is None:
                skip_page += 1
                continue
            dos_from = parse_date(
                row.get("dos_from_iso") or row.get("dos_from") or row.get("dos")
            )
            dos_to = parse_date(row.get("dos_to_iso") or row.get("dos_to") or "")
            if dos_from and not dos_to and (
                row.get("dos_from") or row.get("dos_from_iso") or row.get("dos")
            ):
                dos_to = dos_from
            doc_from = parse_date(
                row.get("doc_dos_from_iso") or row.get("doc_dos_from") or ""
            )
            doc_to = parse_date(
                row.get("doc_dos_to_iso") or row.get("doc_dos_to") or ""
            )
            conf = parse_confidence(row.get("confidence"))
            page_ids.add(page_id)
            prepared.append(
                (
                    charts[chart_name],
                    page_id,
                    dos_from,
                    dos_to,
                    doc_from,
                    doc_to,
                    conf,
                )
            )
        if page_ids:
            cur.execute(
                "DELETE FROM dos_extraction_results WHERE page_id = ANY(%s)",
                (list(page_ids),),
            )
        for vals in prepared:
            cur.execute(
                """
                INSERT INTO dos_extraction_results (
                    chart_id, page_id, dos_from, dos_to,
                    doc_dos_from, doc_dos_to, confidence
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                vals,
            )
            inserted += 1
    conn.commit()
    print(
        f"  → dos_extraction_results inserted={inserted} "
        f"skip_chart={skip_chart} skip_page={skip_page}"
    )


# ----- quality (HW + rotation) -----


def load_quality(conn: object, pipeline_root: Path) -> None:
    hw_path = first_existing(pipeline_root, HW_NAMES)
    rot_path = first_existing(pipeline_root, ROTATION_NAMES)
    if hw_path is None and rot_path is None:
        print(f"  No HW/rotation CSVs in {pipeline_root} — skip quality")
        return

    hw_rows = read_csv_rows(hw_path) if hw_path else []
    rot_rows = read_csv_rows(rot_path) if rot_path else []
    if hw_path:
        print(f"  HW read {len(hw_rows)} from {hw_path.name}")
    if rot_path:
        print(f"  rotation read {len(rot_rows)} from {rot_path.name}")

    inserted = skip_chart = skip_page = 0
    by_page: dict[int, dict[str, Any]] = {}

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

        charts, by_name, by_num = load_chart_page_maps(cur)

        def resolve(row: dict[str, str], keys: tuple[str, ...]) -> tuple[int, int] | None:
            nonlocal skip_chart, skip_page
            raw = ""
            for k in keys:
                raw = (row.get(k) or "").strip()
                if raw:
                    break
            chart_name = match_chart(charts, raw)
            if not chart_name:
                skip_chart += 1
                return None
            page_id = resolve_page_id(chart_name, row, by_name, by_num)
            if page_id is None:
                skip_page += 1
                return None
            return charts[chart_name], page_id

        for row in hw_rows:
            resolved = resolve(row, ("chart_name", "chart_id", "folder"))
            if not resolved:
                continue
            chart_id, page_id = resolved
            label = (
                row.get("handwritten")
                or row.get("handwritten_or_printed")
                or row.get("type")
                or ""
            ).strip()
            if not label or label.upper() == "N/A":
                continue
            bucket = by_page.setdefault(
                page_id, {"chart_id": chart_id, "page_id": page_id, "handwritten_flag": False}
            )
            bucket["handwritten_flag"] = "handwritten" in label.lower()
            bucket["handwritten_label"] = label
            bucket["handwritten_confidence"] = parse_confidence(row.get("confidence"))

        for row in rot_rows:
            resolved = resolve(row, ("folder", "chart_name", "chart_id"))
            if not resolved:
                continue
            chart_id, page_id = resolved
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
                continue
            bucket = by_page.setdefault(
                page_id, {"chart_id": chart_id, "page_id": page_id, "handwritten_flag": False}
            )
            if rotation is not None:
                bucket["orientation"] = (
                    str(int(rotation)) if float(rotation).is_integer() else f"{rotation:g}"
                )
                bucket["rotation_deg"] = rotation
            if tilt is not None:
                bucket["tilt_angle"] = tilt
            if mirrored is not None:
                bucket["mirrored"] = mirrored

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
    print(
        f"  → ocr_quality_results inserted={inserted} "
        f"skip_chart={skip_chart} skip_page={skip_page}"
    )


def main() -> None:
    ui_root = bootstrap_env()
    parser = argparse.ArgumentParser(
        description="Load data/metadata + data/pipeline CSVs into Postgres"
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument(
        "--pipeline-root",
        type=Path,
        default=default_pipeline_root(ui_root),
    )
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        default=default_metadata_dir(ui_root),
    )
    parser.add_argument(
        "--container-name",
        default=os.environ.get("BLOB_CONTAINER", ""),
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
    print(f"postgres-db pack: {PG_PACK_ROOT}")
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
