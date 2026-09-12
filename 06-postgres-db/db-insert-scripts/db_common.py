#!/usr/bin/env python3
"""Shared helpers for Postgres loaders (05-imaging-ui/data + DATABASE_URL)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PG_PACK_ROOT = SCRIPT_DIR.parent  # …/06-postgres-db or …/postgres-db

_IMAGING_UI_DIR_NAMES = (
    "05-imaging-ui",
    "advantmed-imaging-ui",
    "ui-temp",
    "imaging-ui",
)

IMAGE_RE = re.compile(r"\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)
PAGE_NUM_RE = re.compile(r"^(\d+)\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)
METADATA_FILE_RE = re.compile(r"^metadata_R(\d+)_B(\d+)\.csv$", re.IGNORECASE)

# Postgres COPY / upsert chunk size
BATCH_SIZE = 10_000


def iter_batches(rows: list, size: int = BATCH_SIZE):
    """Yield (1-based batch index, total_batches, slice)."""
    if not rows:
        return
    total = (len(rows) + size - 1) // size
    for i in range(0, len(rows), size):
        yield i // size + 1, total, rows[i : i + size]


def find_imaging_ui_root() -> Path | None:
    """Locate imaging-ui for DATA_ROOT / .env (sibling or parent of postgres-db pack)."""
    parent = PG_PACK_ROOT.parent
    for name in _IMAGING_UI_DIR_NAMES:
        cand = parent / name
        if (cand / ".env").is_file() or (cand / "data" / "folders").is_dir():
            return cand.resolve()
    if (parent / "data" / "folders").is_dir() or (parent / ".env").is_file():
        return parent.resolve()
    return None


def _load_env_file(path: Path) -> None:
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
    ui = find_imaging_ui_root()
    if ui:
        _load_env_file(ui / ".env")
    _load_env_file(PG_PACK_ROOT / ".env")
    return ui


def default_data_root(ui_root: Path | None) -> Path:
    env = (os.environ.get("DATA_ROOT") or "").strip()
    if env:
        path = Path(env)
        if path.is_absolute():
            return path
        if ui_root is not None:
            return (ui_root / path).resolve()
        return path.resolve()
    if ui_root is not None:
        return ui_root / "data" / "folders"
    return PG_PACK_ROOT.parent / "data" / "folders"


def default_pipeline_root(ui_root: Path | None) -> Path:
    env = (os.environ.get("PIPELINE_ROOT") or "").strip()
    if env:
        path = Path(env)
        if path.is_absolute():
            return path
        if ui_root is not None:
            return (ui_root / path).resolve()
        return path.resolve()
    if ui_root is not None:
        return ui_root / "data" / "pipeline"
    return PG_PACK_ROOT.parent / "data" / "pipeline"


def default_metadata_dir(ui_root: Path | None) -> Path:
    """Prefer 05-imaging-ui/data/metadata; fall back to pack manifest/."""
    env = (os.environ.get("METADATA_ROOT") or "").strip()
    if env:
        path = Path(env)
        if not path.is_absolute() and ui_root is not None:
            path = ui_root / path
        return path.resolve()
    if ui_root is not None:
        md = ui_root / "data" / "metadata"
        if md.is_dir():
            return md
    for name in ("manifest", "metadata"):
        cand = PG_PACK_ROOT / name
        if cand.is_dir():
            return cand
    if ui_root is not None:
        return ui_root / "data" / "metadata"
    return PG_PACK_ROOT / "manifest"


def psycopg_dsn(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    if url.startswith("postgres+psycopg://"):
        return "postgresql://" + url[len("postgres+psycopg://") :]
    return url


def db_schema() -> str:
    return (
        os.environ.get("DB_SCHEMA") or os.environ.get("PG_SCHEMA") or "public"
    ).strip() or "public"


def configure_connection(conn: object) -> str:
    schema = db_schema()
    with conn.cursor() as cur:  # type: ignore[attr-defined]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
            raise ValueError(f"Invalid DB_SCHEMA: {schema!r}")
        cur.execute(f"SET search_path TO {schema}")
    print(f"search_path: {schema}")
    return schema


def describe_dsn(url: str) -> str:
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


def require_psycopg():
    try:
        import psycopg
    except ImportError:
        print("Install psycopg: pip install 'psycopg[binary]>=3.2'", file=sys.stderr)
        sys.exit(1)
    return psycopg


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


def chart_blob_path(path_template: str, folder_name: str) -> str:
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


def upsert_chart(
    cur: object,
    chart_name: str,
    page_count: int,
    path: str,
    container_name: str | None = None,
    status: str = "received",
    run_id: str | None = None,
    batch_id: str | None = None,
) -> int:
    cur.execute(
        "SELECT id FROM chart_list WHERE chart_name = %s ORDER BY id LIMIT 1",
        (chart_name,),
    )
    row = cur.fetchone()
    if row:
        chart_id = int(row[0])
        cur.execute(
            """
            UPDATE chart_list
               SET page_count = %s,
                   path = %s,
                   blob_container_name = COALESCE(%s, blob_container_name),
                   status = COALESCE(NULLIF(%s, ''), status),
                   run_id = COALESCE(%s, run_id),
                   batch_id = COALESCE(%s, batch_id),
                   updated_at = now()
             WHERE id = %s
            """,
            (
                page_count,
                path,
                container_name or None,
                status or None,
                run_id or None,
                batch_id or None,
                chart_id,
            ),
        )
        return chart_id

    cur.execute(
        """
        INSERT INTO chart_list
            (chart_name, page_count, status, path, blob_container_name, run_id, batch_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            chart_name,
            page_count,
            status or "received",
            path,
            container_name or None,
            run_id or None,
            batch_id or None,
        ),
    )
    return int(cur.fetchone()[0])


def upsert_page(
    cur: object,
    chart_id: int,
    page_name: str,
    ocr_prelim_status: str = "pending",
    ocr_final_status: str = "pending",
) -> int:
    cur.execute(
        """
        SELECT id FROM page_list
         WHERE chart_id = %s AND page_name = %s
         ORDER BY id LIMIT 1
        """,
        (chart_id, page_name),
    )
    row = cur.fetchone()
    if row:
        page_id = int(row[0])
        cur.execute(
            """
            UPDATE page_list
               SET ocr_prelim_status = COALESCE(NULLIF(%s, ''), ocr_prelim_status),
                   ocr_final_status = COALESCE(NULLIF(%s, ''), ocr_final_status),
                   updated_at = now()
             WHERE id = %s
            """,
            (ocr_prelim_status, ocr_final_status, page_id),
        )
        return page_id

    cur.execute(
        """
        INSERT INTO page_list
            (chart_id, page_name, ocr_prelim_status, ocr_final_status)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (
            chart_id,
            page_name,
            ocr_prelim_status or "pending",
            ocr_final_status or "pending",
        ),
    )
    return int(cur.fetchone()[0])
