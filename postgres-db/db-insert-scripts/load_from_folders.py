#!/usr/bin/env python3
"""Load chart folders + metadata + OCR into Postgres (abridged schema).

Loads for now:
  - chart_list / page_list   (from data/folders/<chart>/pages)
  - manifest_member_list     (from a single metadata CSV — B1_R1_DummyMetadata format)
  - ocr_results              (from ocr/*_prelim / *_final1 / *_final2)

Other result tables (quality, DOS, …) are deferred until formats are provided.

Usage:
  export DATABASE_URL=postgresql://user:pass@localhost:5432/imaging
  # optional: DATA_ROOT=/path/to/data/folders
  python load_from_folders.py --ddl
  python load_from_folders.py --metadata-csv ../metadata/B1_R1_DummyMetadata.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import psycopg
except ImportError:
    print("Install psycopg: pip install 'psycopg[binary]>=3.2'", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = Path(os.environ.get("DATA_ROOT", ROOT / "data" / "folders"))
DDL_PATH = Path(__file__).resolve().parents[1] / "ddl-scripts" / "001_schema.sql"

IMAGE_RE = re.compile(r"\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)
PAGE_NUM_RE = re.compile(r"^(\d+)\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)
OCR_MARKER_RE = re.compile(r"^=====\s*(.+?)\s*=====\s*$", re.MULTILINE)

# UI / file suffix → ocr_results.ocr_type
OCR_FILE_MAP: list[tuple[str, str, tuple[str, ...]]] = [
    ("prelim", "tesseract", (".txt",)),
    ("final1", "docling", (".txt",)),
    ("final2", "azuredocintel", (".json", ".txt")),
]


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


def member_name(first: str, last: str) -> str:
    return f"{(first or '').strip()} {(last or '').strip()}".strip()


def list_page_files(folder: Path) -> list[tuple[str, int]]:
    pages_dir = folder / "pages"
    if not pages_dir.is_dir():
        return []
    numbered: list[tuple[int, str]] = []
    other: list[str] = []
    for entry in pages_dir.iterdir():
        if not entry.is_file() or entry.name.startswith("._"):
            continue
        if not IMAGE_RE.search(entry.name):
            continue
        m = PAGE_NUM_RE.match(entry.name)
        if m:
            numbered.append((int(m.group(1)), entry.name))
        else:
            other.append(entry.name)
    numbered.sort(key=lambda x: x[0])
    result = [(name, num) for num, name in numbered]
    for i, name in enumerate(sorted(other), start=len(result) + 1):
        result.append((name, i))
    return result


def find_ocr_file(folder: Path, suffix: str, exts: tuple[str, ...]) -> Path | None:
    ocr_dir = folder / "ocr"
    if not ocr_dir.is_dir():
        return None
    base = f"{folder.name}_{suffix}"
    for ext in exts:
        path = ocr_dir / f"{base}{ext}"
        if path.is_file():
            return path
    # fallback: any file ending with _{suffix}{ext}
    for ext in exts:
        matches = sorted(
            p
            for p in ocr_dir.iterdir()
            if p.is_file() and p.name.endswith(f"_{suffix}{ext}") and not p.name.startswith("._")
        )
        if matches:
            return matches[0]
    return None


def azdoc_json_to_marker_text(raw: str) -> str:
    data = json.loads(raw)
    pages = data.get("pages") if isinstance(data, dict) else data
    if not isinstance(pages, list):
        return raw
    chunks: list[str] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        filename = page.get("fileName") or page.get("filename") or "page.jpg"
        body = page.get("content") or ""
        if not body and isinstance(page.get("lines"), list):
            body = "\n".join(
                str(line.get("content", ""))
                for line in page["lines"]
                if isinstance(line, dict)
            )
        chunks.append(f"===== {filename} =====\n{body}".rstrip())
    return "\n\n".join(chunks)


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


def read_metadata_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, str]] = []
        for row in reader:
            # normalize keys (trim BOM / spaces)
            norm = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            if not norm.get("recordId"):
                continue
            rows.append(norm)
        return rows


def apply_ddl(conn: psycopg.Connection, ddl_path: Path) -> None:
    sql = ddl_path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"Applied DDL: {ddl_path}")


def upsert_chart(
    cur: psycopg.Cursor,
    chart_name: str,
    page_count: int,
    path: str,
    container_name: str | None = None,
) -> int:
    cur.execute(
        """
        INSERT INTO chart_list (chart_name, page_count, status, path, blob_container_name)
        VALUES (%s, %s, 'received', %s, %s)
        ON CONFLICT (chart_name) DO UPDATE
            SET page_count = EXCLUDED.page_count,
                path = EXCLUDED.path,
                blob_container_name = COALESCE(EXCLUDED.blob_container_name, chart_list.blob_container_name),
                updated_at = now()
        RETURNING id
        """,
        (chart_name, page_count, path, container_name or None),
    )
    return int(cur.fetchone()[0])


def upsert_page(cur: psycopg.Cursor, chart_id: int, page_name: str) -> int:
    cur.execute(
        """
        INSERT INTO page_list (chart_id, page_name, ocr_prelim_status, ocr_final_status)
        VALUES (%s, %s, 'pending', 'pending')
        ON CONFLICT (chart_id, page_name) DO UPDATE SET updated_at = now()
        RETURNING id
        """,
        (chart_id, page_name),
    )
    return int(cur.fetchone()[0])


def load_metadata_for_chart(
    cur: psycopg.Cursor,
    chart_id: int,
    rows: list[dict[str, str]],
) -> int:
    cur.execute("DELETE FROM manifest_member_list WHERE chart_id = %s", (chart_id,))
    n = 0
    for row in rows:
        name = member_name(row.get("DummyFirstName", ""), row.get("DummyLastName", ""))
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
    return n


def load_ocr_for_chart(
    cur: psycopg.Cursor,
    chart_id: int,
    folder: Path,
    page_ids: dict[str, int],
) -> int:
    """Write ocr_results. raw_text is stored as-is (plain text or JSON string)."""
    cur.execute("DELETE FROM ocr_results WHERE chart_id = %s", (chart_id,))
    inserted = 0
    for suffix, ocr_type, exts in OCR_FILE_MAP:
        path = find_ocr_file(folder, suffix, exts)
        if not path:
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        # Keep JSON files as JSON text in raw_text; plain files stay plain text.
        # For page splitting only, derive a marker view when needed.
        if path.suffix.lower() == ".json":
            try:
                split_source = azdoc_json_to_marker_text(raw)
            except json.JSONDecodeError:
                split_source = raw
            store_raw = raw  # store original JSON string
        else:
            split_source = raw
            store_raw = raw

        by_page = split_ocr_by_page(split_source)
        if "__all__" in by_page or path.suffix.lower() == ".json":
            # Document-level JSON: one row per page with same JSON blob, or unsplit text
            payload = store_raw if path.suffix.lower() == ".json" else by_page.get("__all__", store_raw)
            if path.suffix.lower() == ".json" and "__all__" not in by_page:
                # Prefer per-page text extracted from JSON when markers exist; still allow JSON mix
                for page_name, page_id in page_ids.items():
                    chunk = by_page.get(page_name)
                    if chunk is None:
                        for key, val in by_page.items():
                            if key.lower() == page_name.lower():
                                chunk = val
                                break
                    # Store page text when available; otherwise full JSON string
                    text_value = chunk if chunk is not None else store_raw
                    cur.execute(
                        """
                        INSERT INTO ocr_results (chart_id, page_id, ocr_type, raw_text)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (chart_id, page_id, ocr_type, text_value),
                    )
                    inserted += 1
                    cur.execute(
                        "UPDATE page_list SET ocr_final_status = 'completed' WHERE id = %s",
                        (page_id,),
                    )
                continue
            for page_name, page_id in page_ids.items():
                cur.execute(
                    """
                    INSERT INTO ocr_results (chart_id, page_id, ocr_type, raw_text)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (chart_id, page_id, ocr_type, payload),
                )
                inserted += 1
                status_col = (
                    "ocr_prelim_status" if ocr_type == "tesseract" else "ocr_final_status"
                )
                cur.execute(
                    f"UPDATE page_list SET {status_col} = 'completed' WHERE id = %s",
                    (page_id,),
                )
            continue

        for page_name, page_id in page_ids.items():
            chunk = by_page.get(page_name)
            if chunk is None:
                for key, val in by_page.items():
                    if key.lower() == page_name.lower():
                        chunk = val
                        break
            if chunk is None:
                continue
            cur.execute(
                """
                INSERT INTO ocr_results (chart_id, page_id, ocr_type, raw_text)
                VALUES (%s, %s, %s, %s)
                """,
                (chart_id, page_id, ocr_type, chunk),
            )
            inserted += 1
            status_col = (
                "ocr_prelim_status" if ocr_type == "tesseract" else "ocr_final_status"
            )
            cur.execute(
                f"UPDATE page_list SET {status_col} = 'completed' WHERE id = %s",
                (page_id,),
            )
    return inserted


def chart_blob_path(path_template: str, folder_name: str) -> str:
    """Resolve chart_list.path from BLOB_PATH_TEMPLATE (folder name = chart)."""
    path = (
        (path_template or "{folder}")
        .replace("{folder}", folder_name)
        .replace("{filename}", "")
        .replace("{page}", "")
    )
    return re.sub(r"/+", "/", path).strip("/")


def load_folders(
    conn: psycopg.Connection,
    data_root: Path,
    metadata_csv: Path,
    container_name: str,
    path_template: str,
) -> None:
    by_record: dict[str, list[dict[str, str]]] = {}
    for row in read_metadata_rows(metadata_csv):
        by_record.setdefault(row["recordId"], []).append(row)
    print(
        f"Metadata: {sum(len(v) for v in by_record.values())} rows, "
        f"{len(by_record)} recordIds from {metadata_csv}"
    )

    folders = sorted(
        p for p in data_root.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    if not folders:
        print(f"No folders under {data_root}")

    with conn.cursor() as cur:
        for folder in folders:
            pages = list_page_files(folder)
            chart_path = chart_blob_path(path_template, folder.name)
            chart_id = upsert_chart(
                cur,
                folder.name,
                len(pages),
                chart_path,
                container_name=container_name or None,
            )
            page_ids: dict[str, int] = {}
            for page_name, _num in pages:
                page_ids[page_name] = upsert_page(cur, chart_id, page_name)

            meta_rows = by_record.get(folder.name, [])
            n_meta = load_metadata_for_chart(cur, chart_id, meta_rows) if meta_rows else 0
            n_ocr = load_ocr_for_chart(cur, chart_id, folder, page_ids) if page_ids else 0
            print(
                f"  {folder.name}: chart_id={chart_id} pages={len(pages)} "
                f"manifest={n_meta} ocr_rows={n_ocr} path={chart_path}"
            )

        existing = {f.name for f in folders}
        for record_id, rows in by_record.items():
            if record_id in existing:
                continue
            chart_path = chart_blob_path(path_template, record_id)
            chart_id = upsert_chart(
                cur,
                record_id,
                0,
                chart_path,
                container_name=container_name or None,
            )
            n_meta = load_metadata_for_chart(cur, chart_id, rows)
            print(f"  {record_id}: chart_id={chart_id} metadata-only manifest={n_meta}")

    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load folders + metadata + OCR into Postgres")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="Postgres URL (or set DATABASE_URL)",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help="Path to data/folders",
    )
    parser.add_argument(
        "--ddl",
        action="store_true",
        help="Apply ddl-scripts/001_schema.sql before load",
    )
    default_metadata = Path(__file__).resolve().parents[1] / "metadata" / "B1_R1_DummyMetadata.csv"
    parser.add_argument(
        "--metadata-csv",
        type=Path,
        default=default_metadata,
        help="Single metadata CSV (B1_R1_DummyMetadata format)",
    )
    parser.add_argument(
        "--container-name",
        default=os.environ.get("BLOB_CONTAINER", ""),
        help="chart_list.blob_container_name (env BLOB_CONTAINER)",
    )
    parser.add_argument(
        "--path-template",
        default=os.environ.get("BLOB_PATH_TEMPLATE", "{folder}/pages/{filename}"),
        help="Blob path template (env BLOB_PATH_TEMPLATE); {folder}=chart_name",
    )
    args = parser.parse_args()

    if not args.database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        sys.exit(1)

    data_root = args.data_root.resolve()
    if not data_root.is_dir():
        print(f"DATA_ROOT not found: {data_root}", file=sys.stderr)
        sys.exit(1)

    metadata_csv = args.metadata_csv.resolve()
    if not metadata_csv.is_file():
        print(f"Metadata CSV not found: {metadata_csv}", file=sys.stderr)
        sys.exit(1)

    with psycopg.connect(args.database_url) as conn:
        if args.ddl:
            apply_ddl(conn, DDL_PATH)
        print(f"Loading from {data_root}")
        if args.container_name:
            print(f"BLOB_CONTAINER={args.container_name}")
        print(f"BLOB_PATH_TEMPLATE={args.path_template}")
        load_folders(
            conn,
            data_root,
            metadata_csv,
            args.container_name,
            args.path_template,
        )
        print("Done.")


if __name__ == "__main__":
    main()
