#!/usr/bin/env python3
"""Load chart folders + metadata + OCR into Postgres (abridged schema).

  Monorepo (AI Project POC):
    05-imaging-ui/          ← DATA_ROOT, .env
    06-postgres-db/         ← this pack (ddl, manifest/, db-insert-scripts)

  Nested (standalone imaging-ui repo):
    imaging-ui/
      data/folders/
      postgres-db/          ← this pack (manifest/)
      .env

db-insert writes:
  - chart_list / page_list   ← <imaging-ui>/data/folders/<chart>/pages
  - manifest_member_list     ← stacked metadata_R{n}_B{n}.csv under manifest/
  - ocr_results              ← ocr/*_prelim / *_final1 / *_final2

Usage (from either layout; .env is auto-loaded from 05-imaging-ui when present):
  python load_from_folders.py
  python load_from_folders.py --metadata-dir ../manifest
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

# psycopg imported lazily in apply_ddl / load paths so --help works without it

SCRIPT_DIR = Path(__file__).resolve().parent
PG_PACK_ROOT = SCRIPT_DIR.parent  # …/06-postgres-db or …/postgres-db
DDL_PATH = PG_PACK_ROOT / "ddl-scripts" / "001_schema.sql"


def default_manifest_dir() -> Path:
    """Prefer manifest/; fall back to legacy metadata/."""
    for name in ("manifest", "metadata"):
        cand = PG_PACK_ROOT / name
        if cand.is_dir():
            return cand
    return PG_PACK_ROOT / "manifest"


DEFAULT_METADATA_DIR = default_manifest_dir()

# Sibling UI folder names under the monorepo root
_IMAGING_UI_DIR_NAMES = (
    "05-imaging-ui",
    "advantmed-imaging-ui",
    "ui-temp",
    "imaging-ui",
)


def find_imaging_ui_root() -> Path | None:
    """Locate imaging-ui for DATA_ROOT / .env (sibling or parent of postgres-db pack)."""
    parent = PG_PACK_ROOT.parent
    for name in _IMAGING_UI_DIR_NAMES:
        cand = parent / name
        if (cand / ".env").is_file() or (cand / "data" / "folders").is_dir():
            return cand.resolve()
    # Nested: postgres-db lives inside the imaging-ui repo
    if (parent / "data" / "folders").is_dir() or (parent / ".env").is_file():
        return parent.resolve()
    return None


def _load_env_file(path: Path) -> None:
    """Minimal .env loader (does not override existing os.environ keys)."""
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


def bootstrap_env() -> Path | None:
    """Load .env from imaging-ui (sibling 05-imaging-ui or nested parent)."""
    ui = find_imaging_ui_root()
    if ui:
        _load_env_file(ui / ".env")
    _load_env_file(PG_PACK_ROOT / ".env")
    return ui


def default_data_root(ui_root: Path | None) -> Path:
    """Resolve DATA_ROOT; relative paths are relative to imaging-ui, not cwd."""
    env = (os.environ.get("DATA_ROOT") or "").strip()
    if env:
        path = Path(env)
        if path.is_absolute():
            return path
        # .env often has DATA_ROOT=./data/folders — that means under imaging-ui
        if ui_root is not None:
            return (ui_root / path).resolve()
        return path.resolve()
    if ui_root is not None:
        return ui_root / "data" / "folders"
    return PG_PACK_ROOT.parent / "data" / "folders"


def psycopg_dsn(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    if url.startswith("postgres+psycopg://"):
        return "postgresql://" + url[len("postgres+psycopg://") :]
    return url


IMAGE_RE = re.compile(r"\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)
PAGE_NUM_RE = re.compile(r"^(\d+)\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)
OCR_MARKER_RE = re.compile(r"^=====\s*(.+?)\s*=====\s*$", re.MULTILINE)
# metadata_R1_B1.csv / Metadata_R1_B1.csv
METADATA_FILE_RE = re.compile(r"^metadata_R(\d+)_B(\d+)\.csv$", re.IGNORECASE)

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


def discover_metadata_csvs(metadata_dir: Path) -> list[Path]:
    """Find metadata_R{n}_B{n}.csv files, sorted by R then B (stack order)."""
    found: list[tuple[int, int, Path]] = []
    for path in metadata_dir.iterdir():
        if not path.is_file() or path.name.startswith("._"):
            continue
        m = METADATA_FILE_RE.match(path.name)
        if not m:
            continue
        found.append((int(m.group(1)), int(m.group(2)), path))
    found.sort(key=lambda t: (t[0], t[1], t[2].name))
    return [p for _, _, p in found]


def load_stacked_metadata_rows(
    metadata_dir: Path | None = None,
    metadata_csv: Path | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    """
    Load metadata rows stacked one below the other from metadata_Rn_Bn CSVs
    (or a single --metadata-csv override). Writes later go to manifest_member_list.
    """
    sources: list[Path] = []
    if metadata_csv is not None:
        sources = [metadata_csv]
    elif metadata_dir is not None:
        sources = discover_metadata_csvs(metadata_dir)
    if not sources:
        return [], []

    stacked: list[dict[str, str]] = []
    for path in sources:
        rows = read_metadata_rows(path)
        print(f"  metadata {path.name}: {len(rows)} rows")
        stacked.extend(rows)
    return stacked, sources


def _require_psycopg():
    try:
        import psycopg
    except ImportError:
        print("Install psycopg: pip install 'psycopg[binary]>=3.2'", file=sys.stderr)
        sys.exit(1)
    return psycopg


def apply_ddl(conn: object, ddl_path: Path) -> None:
    sql = ddl_path.read_text(encoding="utf-8")
    try:
        with conn.cursor() as cur:  # type: ignore[attr-defined]
            cur.execute(sql)
        conn.commit()  # type: ignore[attr-defined]
    except Exception as exc:
        conn.rollback()  # type: ignore[attr-defined]
        print(
            f"DDL failed ({exc}).\n"
            "  If tables already exist, re-run without --ddl (insert only).",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    print(f"Applied DDL: {ddl_path}")


def describe_dsn(url: str) -> str:
    """Host/db only (no credentials) for logs."""
    try:
        from urllib.parse import urlparse

        p = urlparse(url)
        host = p.hostname or "?"
        port = f":{p.port}" if p.port else ""
        db = (p.path or "/").lstrip("/") or "?"
        user = p.username or "?"
        return f"{user}@{host}{port}/{db}"
    except Exception:
        return "(unparsed)"


def upsert_chart(
    cur: object,
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


def upsert_page(cur: object, chart_id: int, page_name: str) -> int:
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
    cur: object,
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
    cur: object,
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
    tmpl = (path_template or "{folder}").strip()
    if "{folder}" not in tmpl and "{filename}" not in tmpl:
        base = tmpl.rstrip("/")
        return f"{base}/{folder_name}" if base else folder_name
    path = (
        tmpl.replace("{folder}", folder_name)
        .replace("{filename}", "")
        .replace("{page}", "")
    )
    return re.sub(r"/+", "/", path).strip("/")


def load_folders(
    conn: object,
    data_root: Path,
    metadata_rows: list[dict[str, str]],
    container_name: str,
    path_template: str,
) -> None:
    """Write chart_list, page_list, manifest_member_list, ocr_results to Postgres."""
    by_record: dict[str, list[dict[str, str]]] = {}
    for row in metadata_rows:
        by_record.setdefault(row["recordId"], []).append(row)
    print(
        f"Metadata stacked → {len(metadata_rows)} rows, "
        f"{len(by_record)} recordIds → manifest_member_list"
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
    ui_root = bootstrap_env()

    parser = argparse.ArgumentParser(
        description="db-insert: write charts, pages, metadata_Rn_Bn → manifest, OCR to Postgres"
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="Postgres URL (or set DATABASE_URL / imaging-ui .env)",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=default_data_root(ui_root),
        help="Path to data/folders (default: <05-imaging-ui>/data/folders)",
    )
    parser.add_argument(
        "--ddl",
        action="store_true",
        help="Apply ddl-scripts/001_schema.sql before load",
    )
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        default=DEFAULT_METADATA_DIR,
        help="Directory of metadata_R{n}_B{n}.csv files (default: ../manifest)",
    )
    parser.add_argument(
        "--metadata-csv",
        type=Path,
        default=None,
        help="Optional single CSV override (skips directory stack)",
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

    database_url = psycopg_dsn(args.database_url)
    if not database_url:
        print(
            "DATABASE_URL is required "
            "(set env, or put it in 05-imaging-ui/.env next to 06-postgres-db)",
            file=sys.stderr,
        )
        sys.exit(1)

    data_root = args.data_root.resolve()
    if not data_root.is_dir() and ui_root is not None:
        # Fallback if relative DATA_ROOT was resolved against the wrong cwd
        alt = (ui_root / "data" / "folders").resolve()
        if alt.is_dir():
            data_root = alt
    if not data_root.is_dir():
        print(f"DATA_ROOT not found: {data_root}", file=sys.stderr)
        if ui_root:
            print(f"  imaging-ui root detected: {ui_root}", file=sys.stderr)
            print(f"  expected folders at: {ui_root / 'data' / 'folders'}", file=sys.stderr)
            print("  or pass: --data-root \"…\\05-imaging-ui\\data\\folders\"", file=sys.stderr)
        else:
            print(
                "  Could not find 05-imaging-ui sibling; pass --data-root explicitly",
                file=sys.stderr,
            )
        sys.exit(1)

    metadata_dir = args.metadata_dir.resolve() if args.metadata_dir else None
    metadata_csv = args.metadata_csv.resolve() if args.metadata_csv else None
    if metadata_csv and not metadata_csv.is_file():
        print(f"Metadata CSV not found: {metadata_csv}", file=sys.stderr)
        sys.exit(1)
    if metadata_csv is None and (metadata_dir is None or not metadata_dir.is_dir()):
        print(f"Metadata dir not found: {metadata_dir}", file=sys.stderr)
        sys.exit(1)

    if ui_root:
        print(f"imaging-ui: {ui_root}")
    print(f"postgres-db pack: {PG_PACK_ROOT}")
    print(f"database: {describe_dsn(database_url)}")
    print("Loading stacked metadata_Rn_Bn CSVs…")
    metadata_rows, sources = load_stacked_metadata_rows(metadata_dir, metadata_csv)
    if not sources:
        print(
            f"No metadata_R*_B*.csv files in {metadata_dir}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"Stacked {len(sources)} file(s) → {len(metadata_rows)} total rows (write to DB)")

    psycopg = _require_psycopg()
    with psycopg.connect(database_url) as conn:
        if args.ddl:
            apply_ddl(conn, DDL_PATH)
        print(f"Loading folders from {data_root}")
        if args.container_name:
            print(f"BLOB_CONTAINER={args.container_name}")
        print(f"BLOB_PATH_TEMPLATE={args.path_template}")
        load_folders(
            conn,
            data_root,
            metadata_rows,
            args.container_name,
            args.path_template,
        )
        print("Done — chart_list, page_list, manifest_member_list, ocr_results written.")


if __name__ == "__main__":
    main()
