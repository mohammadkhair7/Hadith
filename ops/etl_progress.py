import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "etl"))
from db import connect  # noqa: E402

with connect() as pg:
    done = pg.execute("SELECT count(*) FROM etl_state WHERE status='done'").fetchone()[0]
    passages = pg.execute("SELECT count(*) FROM passages").fetchone()[0]
    toc = pg.execute("SELECT count(*) FROM toc_nodes").fetchone()[0]
    recent = pg.execute(
        "SELECT step, updated_at FROM etl_state ORDER BY updated_at DESC LIMIT 5"
    ).fetchall()
print(f"steps done: {done} | passages: {passages} | toc_nodes: {toc}")
for step, ts in recent:
    print(f"  {step}  {ts}")
