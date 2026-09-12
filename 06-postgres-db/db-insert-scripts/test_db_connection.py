#!/usr/bin/env python3
"""Quick Postgres connectivity check (uses 05-imaging-ui/.env).

Usage:
  cd 06-postgres-db/db-insert-scripts
  python test_db_connection.py
"""

from __future__ import annotations

import os
import sys

from db_common import (
    bootstrap_env,
    configure_connection,
    db_schema,
    describe_dsn,
    psycopg_dsn,
    require_psycopg,
)


def main() -> None:
    bootstrap_env()
    url = psycopg_dsn(os.environ.get("DATABASE_URL", ""))
    if not url:
        print(
            "DATABASE_URL is not set. Put it in 05-imaging-ui/.env, e.g.\n"
            "  DATABASE_URL=postgresql+psycopg://aiuser:…@172.20.4.170:5432/imaging_outputs",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"DATABASE_URL → {describe_dsn(url)}")
    print(f"DB_SCHEMA    → {db_schema()}")

    psycopg = require_psycopg()
    try:
        with psycopg.connect(url, connect_timeout=10) as conn:
            schema = configure_connection(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_user, current_schema()")
                database, user, schema_now = cur.fetchone()
                print(f"connected: db={database} user={user} schema={schema_now}")

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
                print(f"tables in {schema}: {', '.join(tables) if tables else '(none)'}")

                if "chart_list" in tables:
                    cur.execute("SELECT COUNT(*) FROM chart_list")
                    (n,) = cur.fetchone()
                    print(f"chart_list rows: {n}")
                else:
                    print("chart_list: missing (run 001_schema.sql in DBeaver if needed)")
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    print("OK — Postgres connection works.")


if __name__ == "__main__":
    main()
