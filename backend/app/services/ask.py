"""/ask orchestrator (§8.1): route the question, run the right engine(s),
compose an answer with citations. Follows the Quran.chat LangGraph pattern as
a plain state pipeline (router -> engines -> composer)."""
import json
from typing import Any

from .llm import generate_json, generate_text
from .nl2cypher import run_nl2cypher
from .nl2sql import run_nl2sql
from .search import keyword_search
from .vector import hybrid_search

ROUTER_PROMPT = """Classify this question about a hadith corpus into exactly one route:
- "analytical": counting, aggregation, statistics, "how many", "which book has most", comparisons of numbers
- "graph": narrator chains, who narrated from whom, isnad relationships between people
- "lookup": find a specific known hadith by its wording or number
- "semantic": conceptual/thematic question needing meaning-based retrieval

Respond JSON: {"route": "...", "reason": "<short>"}

Question: %s"""

COMPOSER_SYSTEM = """أنت مساعد بحث في الحديث الشريف. أجب عن السؤال اعتماداً على المقاطع
والنتائج المرفقة فقط، بالعربية الفصحى الواضحة. استشهد بأرقام المصادر [1] [2] بين
النصوص. إن لم تكف النتائج فقل ذلك صراحة. لا تختلق أحاديث أو أرقاماً."""


def ask(conn, question: str, *, lang: str = "ar") -> dict[str, Any]:
    try:
        routed = generate_json(ROUTER_PROMPT % question)
        route = routed.get("route", "semantic")
    except Exception:
        route = "semantic"
    if route not in ("analytical", "graph", "lookup", "semantic"):
        route = "semantic"

    result: dict[str, Any] = {"question": question, "route": route}

    if route == "analytical":
        try:
            nl = run_nl2sql(conn, question)
            result["sql"] = nl["sql"]
            result["rows"] = nl["rows"]
            result["answer"] = _compose_from_rows(question, nl)
            return result
        except Exception as e:
            conn.rollback()
            result["engine_error"] = str(e)
            route = "semantic"                    # graceful fallback to retrieval

    if route == "graph":
        try:
            g = run_nl2cypher(conn, question)
            result["cypher"] = g.get("cypher")
            result["rows"] = g["rows"]
            if g.get("note"):
                result["note"] = g["note"]
            if g["row_count"]:
                result["answer"] = _compose_from_rows(question, g)
                return result
            # empty graph -> fall through to retrieval
        except Exception as e:
            conn.rollback()
            result["engine_error"] = str(e)

    # retrieval path (lookup uses keyword-first; semantic uses hybrid RRF)
    if route == "lookup":
        ret = keyword_search(conn, question, limit=8, offset=0)
        if ret["total"] == 0:
            ret = hybrid_search(conn, question, limit=8)
    else:
        ret = hybrid_search(conn, question, limit=8)

    citations = ret["items"]
    result["citations"] = citations
    if ret.get("coverage"):
        result["coverage"] = ret["coverage"]
    result["answer"] = _compose_from_passages(question, citations)
    return result


def _compose_from_passages(question: str, items: list[dict]) -> str:
    if not items:
        return "لم أعثر على نتائج كافية للإجابة عن هذا السؤال في المصادر المتاحة."
    ctx = "\n\n".join(
        f"[{i+1}] {it['work_title']}"
        + (f"، حديث رقم {it['hadith_num']}" if it.get("hadith_num") else "")
        + f":\n{_strip_marks(it.get('snippet') or '')[:600]}"
        for i, it in enumerate(items[:8]))
    return generate_text(
        f"السؤال: {question}\n\nالمقاطع:\n{ctx}\n\nالجواب:",
        system=COMPOSER_SYSTEM)


def _compose_from_rows(question: str, engine_out: dict) -> str:
    rows = engine_out.get("rows", [])
    if not rows:
        return "الاستعلام لم يُرجِع نتائج."
    preview = json.dumps(rows[:30], ensure_ascii=False, default=str)
    return generate_text(
        f"السؤال: {question}\n\nنتيجة الاستعلام (JSON):\n{preview}\n\n"
        "صِغ الجواب بالعربية في جملة أو جملتين اعتماداً على هذه النتيجة فقط.",
        system=COMPOSER_SYSTEM)


def _strip_marks(s: str) -> str:
    return s.replace("<mark>", "").replace("</mark>", "")
