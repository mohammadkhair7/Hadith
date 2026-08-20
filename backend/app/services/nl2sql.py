"""NL2SQL (§8.2): question → guarded read-only SELECT against the unified
schema. Prompt = schema summary (from information_schema, cached) + semantic
view YAML + few-shots + grounded book entities resolved from the catalog.
Auto-repair on execution failure AND on wrong-but-valid zero results."""
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import settings
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


# genitive kunya / patronymic variants normalize to the canonical alias forms
_TOKEN_CANON = {"ابي": "ابو", "ابا": "ابو", "وابي": "ابو", "وابو": "ابو", "ابن": "بن"}


def ground_narrators(conn, question: str) -> str:
    """Resolve narrator names in the question to narrator_ids via the aliases
    table (exact n-gram match on alias_norm, else trigram similarity on
    canonical_norm). Grounded ids let the model filter isnad_links.narrator_id
    directly instead of guessing (or transliterating) name strings."""
    toks = normalize_arabic(question).split()
    canon = [_TOKEN_CANON.get(t, t) for t in toks]
    grams: set[str] = set()
    for seq in (toks, canon):
        for n in (2, 3, 4):
            for i in range(len(seq) - n + 1):
                grams.add(" ".join(seq[i:i + n]))
        grams |= {t for t in seq if len(t) >= 4}
    if not grams:
        return ""
    rows = conn.execute("""
        SELECT n.narrator_id, n.canonical_ar, n.canonical_norm,
               count(il.chain_id) AS mentions
        FROM narrator_aliases a
        JOIN narrators n USING (narrator_id)
        LEFT JOIN isnad_links il ON il.narrator_id = n.narrator_id
        WHERE a.alias_norm = ANY(%s)
        GROUP BY 1, 2, 3
        ORDER BY mentions DESC LIMIT 5
    """, (list(grams),)).fetchall()
    if not rows:
        qnorm = " ".join(canon)
        rows = conn.execute("""
            SELECT narrator_id, canonical_ar, canonical_norm,
                   0 AS mentions, word_similarity(canonical_norm, %s) AS sim
            FROM narrators
            WHERE word_similarity(canonical_norm, %s) > 0.6
            ORDER BY sim DESC LIMIT 3
        """, (qnorm, qnorm)).fetchall()
    if not rows:
        return ""
    lines = [f"- narrator_id={r['narrator_id']} «{r['canonical_ar']}» "
             f"(canonical_norm='{r['canonical_norm']}', isnad mentions={r['mentions']})"
             for r in rows]
    return ("## Narrators referenced in the question (resolved from the aliases table)\n"
            + "\n".join(lines)
            + "\nFilter with isnad_links.narrator_id (join isnad_chains for the passage). "
            "Do NOT compare name strings when a grounded id exists. If several ids are "
            "clearly name variants of the same person (e.g. ابو هريره / ابي هريره), use "
            "narrator_id IN (all variant ids).")


_ARABIC_CHARS = re.compile(r"[\u0600-\u06FF]")


def _arabic_form(question: str) -> str | None:
    """For non-Arabic questions, get an Arabic rendering (names in standard
    Arabic spelling) so entity grounding can match the Arabic-only data."""
    letters = re.findall(r"[A-Za-z\u0600-\u06FF]", question)
    if not letters or len(_ARABIC_CHARS.findall(question)) / len(letters) >= 0.5:
        return None
    try:
        out = generate_json(
            "Translate this question about a hadith corpus into Arabic. Render any "
            "transliterated person or book names in their standard Arabic spelling "
            "(e.g. Abu Hurayrah → أبو هريرة). "
            'Respond with JSON: {"arabic": "<the question in Arabic>"}\n\n'
            f"Question: {question}")
        return out.get("arabic") or None
    except Exception:
        return None


def _prompt(conn, question: str, error: str | None = None,
            prev_sql: str | None = None, arabic: str | None = None) -> str:
    parts = [
        "You translate Arabic/English questions about a hadith corpus into a single PostgreSQL SELECT query.",
        "## Schema\n" + schema_summary(conn),
        "## Semantic view\n" + semantic_view(),
        'Respond with JSON: {"enhanced": "<restated question>", "sql": "<one SELECT>"}.',
        "Rules: one statement, SELECT/WITH only, always LIMIT, use text_norm for Arabic text matching "
        "(strip tashkeel, unify alef). Match book titles with LIKE on works.title_norm "
        "(titles often embed the author's name) or, better, by grounded ids when provided. "
        "A hadith = passages row with kind='unit'.",
        "CRITICAL — the data content is ARABIC: every string literal that is compared "
        "against Arabic columns (canonical_norm, alias_norm, title_norm, text_norm, "
        "mention_norm, grade_norm...) MUST be written in normalized Arabic script "
        "(tashkeel stripped, أ/إ/آ→ا, ة→ه, ى→ي, e.g. 'ابو هريره', 'عايشه'). "
        "NEVER transliterate names into Latin letters ('abu hurayra' matches nothing). "
        "If the question is in English, translate names/titles into Arabic before writing "
        "the literal. When a grounded narrator_id or work_id/edition_id is provided above, "
        "always prefer filtering by that id over any string comparison.",
        f"## Question\n{question}"
        + (f"\n(Arabic form: {arabic})" if arabic else ""),
    ]
    ground_q = f"{question} {arabic}" if arabic else question
    for grounded in (ground_books(conn, ground_q), ground_narrators(conn, ground_q)):
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
    arabic = _arabic_form(question)
    model = settings.nl_query_model
    out = generate_json(_prompt(conn, question, arabic=arabic), model=model)
    sql = validate_sql(out.get("sql", ""))
    try:
        rows = _execute_readonly(conn, sql)
    except Exception as e:
        conn.rollback()
        out = generate_json(_prompt(conn, question, error=str(e), prev_sql=sql,
                                    arabic=arabic), model=model)
        sql = validate_sql(out.get("sql", ""))
        rows = _execute_readonly(conn, sql)
    suspicion = _looks_wrong(rows)
    if suspicion:
        try:
            out2 = generate_json(_prompt(
                conn, question, prev_sql=sql, arabic=arabic,
                error=suspicion + ". Recheck joins and filters: book titles embed author "
                "names (use LIKE on title_norm or the grounded ids); hadith counting "
                "needs kind='unit' and an edition that actually has units; shamela "
                "editions of matn books contain pages, not units; Arabic-content "
                "literals must be normalized ARABIC script never Latin transliteration; "
                "prefer grounded narrator_id / work_id filters over name strings."),
                model=model)
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
