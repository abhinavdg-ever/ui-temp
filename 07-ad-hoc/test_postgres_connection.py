#!/usr/bin/env python3
"""Ad-hoc Postgres connectivity check for imaging_outputs.

Loads DATABASE_URL / DB_SCHEMA from 05-imaging-ui/.env (or env / --url).

Usage:
  cd 07-ad-hoc
  python test_postgres_connection.py
  python test_postgres_connection.py --url "postgresql://aiuser:…@172.20.4.170:5432/imaging_outputs"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

SCRIPT_DIR = Path(__file__).resolve().parent
MONOREPO = SCRIPT_DIR.parent
UI_ROOT = MONOREPO / "05-imaging-ui"
DEFAULT_ENV = UI_ROOT / ".env"


def load_env_file(path: Path) -> None:
    """Minimal .env loader — does not override existing os.environ keys."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


def to_psycopg_dsn(url: str) -> str:
    """Accept sqlalchemy-style postgresql+psycopg://… or plain postgresql://…"""
    url = (url or "").strip()
    if not url:
        return ""
    url = re.sub(r"^postgresql\+psycopg2?://", "postgresql://", url, flags=re.I)
    url = re.sub(r"^postgres://", "postgresql://", url, flags=re.I)
    return url


def redact_dsn(url: str) -> str:
    try:
        p = urlparse(url)
        if p.password:
            netloc = p.netloc.replace(f":{p.password}@", ":***@")
            return urlunparse(p._replace(netloc=netloc))
    except Exception:
        pass
    return url


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Postgres connection (ad-hoc)")
    parser.add_argument(
        "--env",
        type=Path,
        default=DEFAULT_ENV,
        help=f".env path (default: {DEFAULT_ENV})",
    )
    parser.add_argument("--url", default="", help="Override DATABASE_URL")
    parser.add_argument(
        "--schema",
        default="",
        help="Override DB_SCHEMA (default from env or public)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Connect timeout seconds (default 10)",
    )
    args = parser.parse_args()

    load_env_file(args.env)

    raw_url = args.url.strip() or os.environ.get("DATABASE_URL", "")
    url = to_psycopg_dsn(raw_url)
    schema = (args.schema or os.environ.get("DB_SCHEMA") or "public").strip()

    if not url:
        print(
            "DATABASE_URL is not set.\n"
            f"  Put it in {args.env} or pass --url\n"
            "  Example:\n"
            "  DATABASE_URL=postgresql+psycopg://aiuser:…@172.20.4.170:5432/imaging_outputs",
            file=sys.stderr,
        )
        return 1

    print(f"env file     → {args.env} ({'found' if args.env.is_file() else 'missing'})", flush=True)
    print(f"DATABASE_URL → {redact_dsn(url)}", flush=True)
    print(f"DB_SCHEMA    → {schema}", flush=True)

    try:
        import psycopg
    except ImportError:
        print(
            "psycopg is not installed. Try:\n  pip install 'psycopg[binary]'",
            file=sys.stderr,
        )
        return 1

    try:
        with psycopg.connect(url, connect_timeout=args.timeout) as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET search_path TO {schema}")
                cur.execute(
                    "SELECT current_database(), current_user, current_schema(), version()"
                )
                database, user, schema_now, version = cur.fetchone()
                print(f"connected    → db={database} user={user} schema={schema_now}", flush=True)
                print(f"server       → {version.split(',')[0]}", flush=True)

                cur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    ORDER BY table_name
                    """,
                    (schema,),
                )
                tables = [r[0] for r in cur.fetchall()]
                print(
                    f"tables ({schema}) → "
                    + (", ".join(tables) if tables else "(none)"),
                    flush=True,
                )

                for t in ("chart_list", "page_list", "manifest_member_list", "dos_extraction_results"):
                    if t in tables:
                        cur.execute(f"SELECT COUNT(*) FROM {t}")
                        (n,) = cur.fetchone()
                        print(f"  {t}: {n} rows", flush=True)
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1

    print("OK — Postgres connection works.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
