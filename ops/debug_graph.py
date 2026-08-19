import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import pool

pool.open()
with pool.connection() as conn:
    try:
        r = conn.execute(
            "SELECT count(*) AS n FROM ag_catalog.ag_graph WHERE name=%s",
            ("hadith_graph",)).fetchone()
        print("ag_graph count:", r)
    except Exception:
        traceback.print_exc()

with pool.connection() as conn:
    from app.services.nl2cypher import graph_exists, _execute_cypher
    print("graph_exists:", graph_exists(conn))
    try:
        rows = _execute_cypher(conn,
            "MATCH (s:Narrator)-[:NARRATED_FROM]->(t:Narrator) "
            "WHERE t.name CONTAINS 'ابو هريره' RETURN s.name LIMIT 5")
        print("cypher rows:", rows)
    except Exception:
        traceback.print_exc()
pool.close()
