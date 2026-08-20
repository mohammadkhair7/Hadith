"""NL2SQL (§8.2): question → guarded read-only SELECT against the unified
schema. Prompt = schema summary (from information_schema, cached) + semantic
view YAML + few-shots + grounded book entities resolved from the catalog.
Auto-repair on execution failure AND on wrong-but-valid zero results."""
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .llm import generate_json
from .normalize import normalize_arabic

_SEMANTIC_VIEW = Path(__file__).resolve().parents[3] / "docs" / "semantic_view.yaml"

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|copy|"
    r"vacuum|analyze|comment|do|call|execute|set|reset|listen|notify)\b", re.I)
MAX_LIMIT = 200
STATEMENT_TIMEOUT_MS = 10_000


@lru_cache(maxsize=1)
def semantic_view() -> str:
    try:
        return _SEMANTIC_VIEW.read_text(encoding="utf-8")
    except OSError:
        return ""


@lru_cache(maxsize=1)
def schema_summary_cached() -> str:
    # filled lazily on first request (needs a live connection) — see schema_summary
    return ""


_schema_cache: str | None = None


def schema_summary(conn) -> str:
    global _schema_cache
    if _schema_cache is None:
        rows = conn.execute("""
            SELECT table_name, string_agg(column_name || ' ' || data_type, ', '
                                          ORDER BY ordinal_position) AS cols
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name IN ('works','editions','passages','toc_nodes',
                                 'subjects','subject_links','narrators',
                                 'narrator_aliases','translations',
                                 'isnad_chains','isnad_links','hadith_grades')
            GROUP BY table_name ORDER BY table_name
        """).fetchall()
        _schema_cache = "\n".join(f"{r['table_name']}({r['cols']})" for r in rows)
    return _schema_cache


def validate_sql(sql: str) -> str:
    """Guardrails: single SELECT/WITH statement, no DDL/DML, LIMIT enforced."""
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        raise ValueError("multiple statements are not allowed")
    if not re.match(r"^\s*(select|with)\b", s, re.I):
        raise ValueError("only SELECT/WITH queries are allowed")
    if FORBIDDEN.search(s):
        raise ValueError("forbidden keyword in query")
    m = re.search(r"\blimit\s+(\d+)\b", s, re.I)
    if m:
        if int(m.group(1)) > MAX_LIMIT:
            s = re.sub(r"\blimit\s+\d+\b", f"LIMIT {MAX_LIMIT}", s, flags=re.I)
    else:
        s = f"{s} LIMIT {MAX_LIMIT}"
    return s


_catalog_cache: list[dict] | None = None


def _catalog(conn) -> list[dict]:
    """Compact works/editions catalog with hadith-unit counts, cached."""
    global _catalog_cache
    if _catalog_cache is None:
        _catalog_cache = conn.execute("""
            SELECT w.work_id, w.title_ar, w.title_norm, w.kind AS work_kind,
                   e.edition_id, e.source,
                   count(p.passage_id) FILTER (WHERE p.kind='unit') AS units,
                   count(p.passage_id) AS total
            FROM works w
            JOIN editions e USING (work_id)
            LEFT JOIN passages p USING (edition_id)
            GROUP BY 1, 2, 3, 4, 5, 6
        """).fetchall()
    return _catalog_cache


def ground_books(conn, question: str) -> str:
    """Resolve book references in the question against the catalog (exact
    containment of the normalized title, else trigram word-similarity). The
    grounded ids let the model filter precisely instead of guessing titles."""
    qnorm = normalize_arabic(question)
    cat = _catalog(conn)
    hits = [r for r in cat if r["title_norm"] and r["title_norm"] in qnorm]
    if not hits:
        rows = conn.execute("""
            SELECT work_id, max(word_similarity(title_norm, %s)) AS sim
            FROM works GROUP BY work_id
            HAVING max(word_similarity(title_norm, %s)) > 0.55
            ORDER BY sim DESC LIMIT 3
        """, (qnorm, qnorm)).fetchall()
        ids = {r["work_id"] for r in rows}
        hits = [r for r in cat if r["work_id"] in ids]
    if not hits:
        return ""
    lines = []
    for r in hits[:8]:
        note = "أحاديث مفردة kind='unit'" if r["units"] else "صفحات فقط (لا يوجد kind='unit')"
        lines.append(f"- work_id={r['work_id']} «{r['title_ar']}» → edition_id={r['edition_id']} "
                     f"(source={r['source']}, units={r['units']}, passages={r['total']}, {note})")
    return ("## Books referenced in the question (resolved from the catalog — "
            "filter by these ids, prefer editions with units>0 when counting hadiths)\n"
            + "\n".join(lines))


def _prompt(conn, question: str, error: str | None = None,
            prev_sql: str | None = None) -> str:
    parts = [
        "You translate Arabic/English questions about a hadith corpus into a single PostgreSQL SELECT query.",
        "## Schema\n" + schema_summary(conn),
        "## Semantic view\n" + semantic_view(),
        'Respond with JSON: {"enhanced": "<restated question>", "sql": "<one SELECT>"}.',
        "Rules: one statement, SELECT/WITH only, always LIMIT, use text_norm for Arabic text matching "
        "(strip tashkeel, unify alef). Match book titles with LIKE on works.title_norm "
        "(titles often embed the author's name) or, better, by grounded ids when provided. "
        "A hadith = passages row with kind='unit'.",
        f"## Question\n{question}",
    ]
    grounded = ground_books(conn, question)
    if grounded:
        parts.insert(3, grounded)
    if error:
        parts.append(f"## Previous attempt failed\nSQL: {prev_sql}\nError: {error}\nFix the query.")
    return "\n\n".join(parts)


def _looks_wrong(rows: list) -> str | None:
    """Detect wrong-but-valid results worth one repair round."""
    if not rows:
        return "the query executed but returned no rows"
    if len(rows) == 1:
        vals = list(rows[0].values())
        if len(vals) == 1 and (vals[0] in (0, None)):
            return "the query executed but the count/value is 0 — the filter almost certainly missed"
    return None


def run_nl2sql(conn, question: str) -> dict[str, Any]:
    out = generate_json(_prompt(conn, question))
    sql = validate_sql(out.get("sql", ""))
    try:
        rows = _execute_readonly(conn, sql)
    except Exception as e:
        conn.rollback()
        out = generate_json(_prompt(conn, question, error=str(e), prev_sql=sql))
        sql = validate_sql(out.get("sql", ""))
        rows = _execute_readonly(conn, sql)
    suspicion = _looks_wrong(rows)
    if suspicion:
        try:
            out2 = generate_json(_prompt(
                conn, question, prev_sql=sql,
                error=suspicion + ". Recheck joins and filters: book titles embed author "
                "names (use LIKE on title_norm or the grounded ids); hadith counting "
                "needs kind='unit' and an edition that actually has units; shamela "
                "editions of matn books contain pages, not units."))
            sql2 = validate_sql(out2.get("sql", ""))
            rows2 = _execute_readonly(conn, sql2)
            if not _looks_wrong(rows2):
                out, sql, rows = out2, sql2, rows2
        except Exception:
            conn.rollback()                      # keep the first (valid) result
    return {"enhanced": out.get("enhanced", question), "sql": sql,
            "rows": rows, "row_count": len(rows)}


def _execute_readonly(conn, sql: str):
    with conn.transaction():
        conn.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
        conn.execute("SET LOCAL transaction_read_only = on")
        return conn.execute(sql).fetchall()
