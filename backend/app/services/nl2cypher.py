"""NL2CYPHER (§8.3): question → guarded read-only Cypher against the Apache
AGE narrator graph. The graph is populated in Phase 6; until then queries run
against an empty graph and return no rows (with a coverage note)."""
import json
import re
from typing import Any

from .llm import generate_json

GRAPH_NAME = "hadith_graph"
MAX_LIMIT = 100
STATEMENT_TIMEOUT_MS = 10_000

FORBIDDEN = re.compile(
    r"\b(create|merge|delete|detach|set|remove|drop|load|call)\b", re.I)

GRAPH_SCHEMA = """
Node labels:
  Narrator {narrator_id, name, mentions}   -- name is normalized Arabic (no tashkeel, ابو not أبو)
Edge types:
  (:Narrator)-[:NARRATED_FROM {count}]->(:Narrator)   -- student -> teacher; count = joint narrations
(There are NO Passage/Work nodes in this graph — per-hadith questions belong to SQL.)
"""

FEW_SHOTS = """
Q: من روى عن أبي هريرة؟
Cypher: MATCH (s:Narrator)-[:NARRATED_FROM]->(t:Narrator) WHERE t.name CONTAINS 'ابو هريره' RETURN s.name, s.narrator_id LIMIT 50

Q: كم حديثاً يرويه نافع عن ابن عمر؟
Cypher: MATCH (a:Narrator)-[r:NARRATED_FROM]->(b:Narrator) WHERE a.name CONTAINS 'نافع' AND b.name CONTAINS 'ابن عمر' RETURN r.count LIMIT 10

Q: من أكثر شيوخ مالك بن أنس رواية؟
Cypher: MATCH (s:Narrator)-[r:NARRATED_FROM]->(t:Narrator) WHERE s.name CONTAINS 'مالك بن انس' RETURN t.name, r.count ORDER BY r.count DESC LIMIT 20
"""


def graph_exists(conn) -> bool:
    try:
        row = conn.execute(
            "SELECT count(*) AS n FROM ag_catalog.ag_graph WHERE name=%s",
            (GRAPH_NAME,)).fetchone()
        return bool(row and row["n"])
    except Exception:
        conn.rollback()
        return False


def validate_cypher(cy: str) -> str:
    s = cy.strip().rstrip(";").strip()
    if not re.match(r"^\s*match\b", s, re.I):
        raise ValueError("only MATCH...RETURN queries are allowed")
    if "return" not in s.lower():
        raise ValueError("query must have a RETURN clause")
    if FORBIDDEN.search(s):
        raise ValueError("forbidden keyword in cypher")
    if "$" in s or ";" in s:
        raise ValueError("parameters/semicolons are not allowed")
    m = re.search(r"\blimit\s+(\d+)\b", s, re.I)
    if m:
        if int(m.group(1)) > MAX_LIMIT:
            s = re.sub(r"\blimit\s+\d+\b", f"LIMIT {MAX_LIMIT}", s, flags=re.I)
    else:
        s = f"{s} LIMIT {MAX_LIMIT}"
    return s


def _prompt(question: str, error: str | None = None, prev: str | None = None,
            frame: dict | None = None) -> str:
    parts = [
        "You translate Arabic/English questions about hadith narrators into a single openCypher MATCH query for Apache AGE.",
        "## Graph schema\n" + GRAPH_SCHEMA,
        "## Examples\n" + FEW_SHOTS,
        'Respond with JSON: {"cypher": "<one MATCH...RETURN query>"}.',
        "Rules: MATCH/RETURN only, always LIMIT, normalize Arabic names (no tashkeel, unify alef: ابو not أبو).",
        f"## Question\n{question}",
    ]
    if frame:
        # linguistic frame (§12.3): pre-resolved entities let Cypher match by id
        parts.append(
            "## Linguistic frame (pre-resolved — prefer matching by narrator_id/work_id)\n"
            + json.dumps(frame, ensure_ascii=False))
    if error:
        parts.append(f"## Previous attempt failed\nCypher: {prev}\nError: {error}\nFix it.")
    return "\n\n".join(parts)


def _execute_cypher(conn, cypher: str):
    """Run bounded read-only cypher via AGE. Column count is derived from the
    RETURN clause; results come back as agtype -> parsed to python."""
    n_cols = len(re.split(r",(?![^()]*\))",
                          re.search(r"\breturn\b(.*?)(\blimit\b|$)", cypher,
                                    re.I | re.S).group(1)))
    cols = ", ".join(f"c{i} agtype" for i in range(n_cols))
    with conn.transaction():
        conn.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
        conn.execute("LOAD 'age'")
        conn.execute('SET LOCAL search_path = ag_catalog, "$user", public')
        # AGE requires the graph name as a literal constant (no bind params);
        # GRAPH_NAME is a fixed module constant, the cypher body is guarded.
        rows = conn.execute(
            f"SELECT * FROM cypher('{GRAPH_NAME}', $${cypher}$$) AS ({cols})"
        ).fetchall()
    out = []
    for r in rows:
        parsed = {}
        for k, v in r.items():
            s = str(v)
            s = re.sub(r"::(vertex|edge|path|numeric)$", "", s)
            try:
                parsed[k] = json.loads(s)
            except (ValueError, TypeError):
                parsed[k] = s
        out.append(parsed)
    return out


def run_nl2cypher(conn, question: str) -> dict[str, Any]:
    if not graph_exists(conn):
        return {"cypher": None, "rows": [], "row_count": 0,
                "note": "narrator graph not built yet (Phase 6)"}
    from .frames import build_frame
    try:
        frame = build_frame(conn, question)
    except Exception:
        conn.rollback()
        frame = None                       # frame is additive, never a gate (§12.3)
    out = generate_json(_prompt(question, frame=frame))
    cy = validate_cypher(out.get("cypher", ""))
    try:
        rows = _execute_cypher(conn, cy)
    except Exception as e:
        conn.rollback()
        out = generate_json(_prompt(question, error=str(e), prev=cy, frame=frame))
        cy = validate_cypher(out.get("cypher", ""))
        rows = _execute_cypher(conn, cy)
    if not rows:
        # wrong-but-valid repair: names in the graph are normalized substrings
        try:
            out2 = generate_json(_prompt(
                question, prev=cy, frame=frame,
                error="the query executed but matched nothing — use CONTAINS with a "
                "shorter normalized name fragment (no tashkeel, ابو not أبو, بن not ابن), "
                "or match by narrator_id from the frame"))
            cy2 = validate_cypher(out2.get("cypher", ""))
            rows2 = _execute_cypher(conn, cy2)
            if rows2:
                cy, rows = cy2, rows2
        except Exception:
            conn.rollback()
    return {"cypher": cy, "rows": rows, "row_count": len(rows), "frame": frame}
