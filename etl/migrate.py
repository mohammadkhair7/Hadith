"""Apply etl/schema.sql to the target Postgres. Idempotent."""
from pathlib import Path

from db import connect

SCHEMA = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")


def main() -> None:
    with connect(autocommit=True) as conn:
        conn.execute(SCHEMA)
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' ORDER BY table_name"
        ).fetchall()
    print(f"schema applied — {len(rows)} tables:")
    print("  " + ", ".join(r[0] for r in rows))


if __name__ == "__main__":
    main()
