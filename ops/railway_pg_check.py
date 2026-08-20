"""Probe the Railway Postgres: version, AGE availability, existing contents.
Reads the connection URL from the RAILWAY_PG_URL env var (never printed)."""
import os
import sys

import psycopg

url = os.environ.get("RAILWAY_PG_URL")
if not url:
    sys.exit("RAILWAY_PG_URL not set")

with psycopg.connect(url, connect_timeout=15) as conn:
    ver = conn.execute("SHOW server_version").fetchone()[0]
    print("server_version:", ver)
    avail = conn.execute(
        "SELECT count(*) FROM pg_available_extensions WHERE name='age'"
    ).fetchone()[0]
    print("age available:", bool(avail))
    tables = conn.execute("""
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema='public'
    """).fetchone()[0]
    print("public tables:", tables)
    size = conn.execute(
        "SELECT pg_size_pretty(pg_database_size(current_database()))"
    ).fetchone()[0]
    print("db size:", size)
