"""NL2SQL (§8.2): question → guarded read-only SELECT against the unified
schema. Prompt = schema summary (from information_schema, cached) + semantic
view YAML + few-shots. One auto-repair round on execution failure."""
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .llm import generate_json

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
                                 'narrator_aliases','translations')
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


def _prompt(conn, question: str, error: str | None = None,
            prev_sql: str | None = None) -> str:
    parts = [
        "You translate Arabic/English questions about a hadith corpus into a single PostgreSQL SELECT query.",
        "## Schema\n" + schema_summary(conn),
        "## Semantic view\n" + semantic_view(),
        'Respond with JSON: {"enhanced": "<restated question>", "sql": "<one SELECT>"}.',
        "Rules: one statement, SELECT/WITH only, always LIMIT, use text_norm for Arabic text matching (strip tashkeel, unify alef).",
        f"## Question\n{question}",
    ]
    if error:
        parts.append(f"## Previous attempt failed\nSQL: {prev_sql}\nError: {error}\nFix the query.")
    return "\n\n".join(parts)


def run_nl2sql(conn, question: str) -> dict[str, Any]:
    out = generate_json(_prompt(conn, question))
    sql = validate_sql(out.get("sql", ""))
    try:
        rows = _execute_readonly(conn, sql)
    except Exception as e:
        conn.rollback()
        out2 = generate_json(_prompt(conn, question, error=str(e), prev_sql=sql))
        sql = validate_sql(out2.get("sql", ""))
        rows = _execute_readonly(conn, sql)
        out = out2
    return {"enhanced": out.get("enhanced", question), "sql": sql,
            "rows": rows, "row_count": len(rows)}


def _execute_readonly(conn, sql: str):
    with conn.transaction():
        conn.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
        conn.execute("SET LOCAL transaction_read_only = on")
        return conn.execute(sql).fetchall()
