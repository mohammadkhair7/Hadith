"""Generate a TOC (الفهرس) for shamela editions from heading lines in the page
text itself (the crawl did not preserve the native Shamela titles table).

Heading grammar (line-start, short lines only):
  كتاب / أبواب / سورة / تفسير سورة  -> depth 1
  باب                               -> depth 2 (under the last كتاب)
  فصل / مقدمة / خاتمة / مسألة       -> child of the innermost open node
Pages are anchored (passages.toc_node_id) to the innermost node; a page that
introduces a heading anchors to the first node it introduces, so TOC clicks
land on the page where the section starts. Idempotent: --rebuild regenerates.
DATABASE_URL-driven (local + Railway)."""
import argparse
import os
import re
import sys

import psycopg

sys.stdout.reconfigure(encoding="utf-8")

_MARKS = re.compile(r"[\u064B-\u0652\u0670\u0640]")
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه"})
# leading decoration: numbers, dashes, brackets, stars, dots
_DECOR = re.compile(r"^[\s\d\u0660-\u0669\-–—=*.،:()\[\]«»_§]+")

_KIND1 = re.compile(r"^(كتاب|ابواب|سوره|تفسير سوره)\s+\S")
_KIND2 = re.compile(r"^باب\b")
_KIND3 = re.compile(r"^(فصل|مقدمه|خاتمه|مساله)\b")
# editor-added headings: a whole line wrapped in square brackets
_BRACKET = re.compile(r"^\[(.{2,120})\]$")
# bracketed lines that are NOT headings: poetry meters, page refs, numbers
_BRACKET_SKIP = re.compile(r"^(البحر\s|ص\s*[::]?\s*\d|\d|رقم\s)")
_STRIP_CHARS = " .،:-–—=*_«»()[]§"


def classify(line: str) -> tuple[int, str] | None:
    """Return (depth-kind 1/2/3, title) or None."""
    if len(line) > 160:
        return None
    br = _BRACKET.match(line)
    if br:
        inner = br.group(1).strip(_STRIP_CHARS)
        bare = _DECOR.sub("", _MARKS.sub("", inner).translate(_FOLD)).strip()
        if not bare or _BRACKET_SKIP.match(bare):
            return None
        if _KIND1.match(bare):
            return 1, inner
        if _KIND2.match(bare):
            return 2, inner
        return 3, inner
    bare = _MARKS.sub("", line).translate(_FOLD)
    bare = _DECOR.sub("", bare).strip()
    if not (3 <= len(bare) <= 95):
        return None
    title = _DECOR.sub("", line).strip(_STRIP_CHARS)
    if _KIND1.match(bare):
        return 1, title
    if _KIND2.match(bare):
        return 2, title
    if _KIND3.match(bare):
        return 3, title
    return None


def build_edition(conn, edition_id: int) -> tuple[int, int]:
    pages = conn.execute("""
        SELECT passage_id, text_raw FROM passages
        WHERE edition_id=%s ORDER BY seq
    """, (edition_id,)).fetchall()

    # stack[d] = toc_node_id of the innermost open node at depth kind d
    stack: dict[int, int | None] = {1: None, 2: None, 3: None}
    ord_n = 0
    nodes = 0
    anchors: list[tuple[int | None, int]] = []   # (toc_node_id, passage_id)

    def open_node(title: str, kind: int) -> int:
        nonlocal ord_n, nodes
        if kind == 1:
            parent, depth = None, 1
            stack[2] = stack[3] = None
        elif kind == 2:
            parent = stack[1]
            depth = 2 if parent else 1
            stack[3] = None
        else:
            parent = stack[2] or stack[1]
            depth = (2 if stack[1] and not stack[2] else 3) if parent else 1
        ord_n += 1
        nodes += 1
        nid = conn.execute("""
            INSERT INTO toc_nodes (edition_id, parent_id, title, is_leaf, ord, depth)
            VALUES (%s, %s, %s, true, %s, %s) RETURNING toc_node_id
        """, (edition_id, parent, title, ord_n, depth)).fetchone()[0]
        stack[kind] = nid
        if kind == 1:
            stack[2] = stack[3] = None
        return nid

    for pid, raw in pages:
        first_new: int | None = None
        for line in (raw or "").split("\n"):
            line = line.strip()
            if not line:
                continue
            hit = classify(line)
            if hit is None:
                continue
            kind, title = hit
            if not title:
                continue
            nid = open_node(title[:200], kind)
            if first_new is None:
                first_new = nid
        anchors.append((first_new or stack[3] or stack[2] or stack[1], pid))

    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE passages SET toc_node_id=%s WHERE passage_id=%s",
            [(nid, pid) for nid, pid in anchors if nid is not None])
    conn.execute("""
        UPDATE toc_nodes t SET is_leaf = NOT EXISTS (
            SELECT 1 FROM toc_nodes c WHERE c.parent_id = t.toc_node_id)
        WHERE t.edition_id = %s
    """, (edition_id,))
    return nodes, len(pages)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edition", type=int, help="one edition (default: all shamela)")
    ap.add_argument("--rebuild", action="store_true",
                    help="drop existing generated toc first")
    args = ap.parse_args()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")

    with psycopg.connect(url) as conn:
        if args.edition:
            eds = [(args.edition,)]
        else:
            eds = conn.execute(
                "SELECT edition_id FROM editions WHERE source='shamela' ORDER BY edition_id"
            ).fetchall()
        for (eid,) in eds:
            existing = conn.execute(
                "SELECT count(*) FROM toc_nodes WHERE edition_id=%s", (eid,)
            ).fetchone()[0]
            if existing and not args.rebuild:
                print(f"edition {eid}: toc exists ({existing} nodes), skip")
                continue
            if existing:
                conn.execute("""
                    UPDATE passages SET toc_node_id=NULL WHERE edition_id=%s
                """, (eid,))
                conn.execute("DELETE FROM toc_nodes WHERE edition_id=%s", (eid,))
            nodes, pages = build_edition(conn, eid)
            conn.commit()
            print(f"edition {eid}: {nodes} toc nodes over {pages} pages")
    print("done")


if __name__ == "__main__":
    main()
