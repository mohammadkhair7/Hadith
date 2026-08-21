"""Manual curation of the narrator knowledge graph (admin console):
merge duplicate narrator nodes, create/delete narrators, and add/remove
teacher-student relationships as MANUAL OVERRIDES layered on top of the
edges derived from isnad_links (the isnad data itself is never destroyed
by a relationship edit). Every action is written to admin_audit."""
import json

from .normalize import normalize_arabic

DDL = """
CREATE TABLE IF NOT EXISTS narrator_edges_manual (
    edge_id    bigserial PRIMARY KEY,
    student_id int NOT NULL REFERENCES narrators(narrator_id) ON DELETE CASCADE,
    teacher_id int NOT NULL REFERENCES narrators(narrator_id) ON DELETE CASCADE,
    action     text NOT NULL CHECK (action IN ('add', 'remove')),
    weight     int DEFAULT 1,
    note       text,
    created_by text,
    created_at timestamptz DEFAULT now(),
    UNIQUE (student_id, teacher_id, action)
);
CREATE TABLE IF NOT EXISTS admin_audit (
    audit_id    bigserial PRIMARY KEY,
    action      text NOT NULL,
    payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
    admin_email text,
    created_at  timestamptz DEFAULT now()
);
"""

_ensured = False


def ensure_tables(conn) -> None:
    global _ensured
    if _ensured:
        return
    conn.execute(DDL)
    conn.commit()
    _ensured = True


def audit(conn, action: str, payload: dict, admin: str | None) -> None:
    conn.execute(
        "INSERT INTO admin_audit (action, payload, admin_email) VALUES (%s, %s, %s)",
        (action, json.dumps(payload, ensure_ascii=False), admin))


_META_FILL = ("rijal_grade", "tabaqa", "tabaqa_label", "places", "school")


def merge_narrators(conn, target_id: int, source_ids: list[int],
                    admin: str | None) -> dict:
    """Repoint every reference from the source narrators to the target,
    keep the source names as aliases, backfill missing target fields,
    then delete the source rows. Returns affected counts."""
    ensure_tables(conn)
    source_ids = [s for s in dict.fromkeys(source_ids) if s != target_id]
    if not source_ids:
        raise ValueError("no source narrators to merge")
    rows = conn.execute(
        "SELECT narrator_id, canonical_ar, canonical_norm, generation, "
        "death_year_h, bio_summary, kunya, laqab, translit, meta "
        "FROM narrators WHERE narrator_id = ANY(%s)",
        (source_ids + [target_id],)).fetchall()
    by_id = {r["narrator_id"]: r for r in rows}   # rows are dicts (dict_row pool)
    if target_id not in by_id:
        raise ValueError("target narrator not found")
    missing = [s for s in source_ids if s not in by_id]
    if missing:
        raise ValueError(f"source narrators not found: {missing}")

    links = conn.execute(
        "UPDATE isnad_links SET narrator_id=%s WHERE narrator_id = ANY(%s)",
        (target_id, source_ids)).rowcount
    conn.execute(
        "UPDATE narrator_assessments SET narrator_id=%s WHERE narrator_id = ANY(%s)",
        (target_id, source_ids))

    # aliases: move without violating (narrator_id, alias_norm, alias_kind)
    conn.execute("""
        INSERT INTO narrator_aliases (narrator_id, alias_ar, alias_norm,
                                      alias_kind, translit, src_passage)
        SELECT %s, alias_ar, alias_norm, alias_kind, translit, src_passage
        FROM narrator_aliases WHERE narrator_id = ANY(%s)
        ON CONFLICT DO NOTHING
    """, (target_id, source_ids))
    conn.execute("DELETE FROM narrator_aliases WHERE narrator_id = ANY(%s)",
                 (source_ids,))
    # the source canonical names become aliases of the target
    conn.execute("""
        INSERT INTO narrator_aliases (narrator_id, alias_ar, alias_norm, alias_kind)
        SELECT %s, canonical_ar, canonical_norm, 'merged'
        FROM narrators WHERE narrator_id = ANY(%s)
        ON CONFLICT DO NOTHING
    """, (target_id, source_ids))

    # manual edges: re-key (delete + reinsert to honour the unique constraint)
    manual = conn.execute("""
        DELETE FROM narrator_edges_manual
        WHERE student_id = ANY(%s) OR teacher_id = ANY(%s)
        RETURNING student_id, teacher_id, action, weight, note, created_by
    """, (source_ids, source_ids)).fetchall()
    remap = {s: target_id for s in source_ids}
    for m in manual:
        st = remap.get(m["student_id"], m["student_id"])
        te = remap.get(m["teacher_id"], m["teacher_id"])
        if st == te:
            continue
        conn.execute("""
            INSERT INTO narrator_edges_manual
                (student_id, teacher_id, action, weight, note, created_by)
            VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
        """, (st, te, m["action"], m["weight"], m["note"], m["created_by"]))

    # backfill scalar fields the target lacks; merge meta (target wins)
    t = by_id[target_id]
    fields = ("generation", "death_year_h", "bio_summary", "kunya", "laqab", "translit")
    tgt = {k: t[k] for k in fields}
    meta = dict(t["meta"] or {})
    for s in source_ids:
        r = by_id[s]
        for key in fields:
            if tgt[key] is None and r[key] is not None:
                tgt[key] = r[key]
        smeta = r["meta"] or {}
        for mk in _META_FILL:
            if mk not in meta and smeta.get(mk) is not None:
                meta[mk] = smeta[mk]
    meta["merged_ids"] = sorted(set(meta.get("merged_ids", []) + source_ids))
    meta["merged_names"] = sorted(set(
        meta.get("merged_names", []) + [by_id[s]["canonical_ar"] for s in source_ids]))
    conn.execute("""
        UPDATE narrators SET generation=%s, death_year_h=%s, bio_summary=%s,
               kunya=%s, laqab=%s, translit=%s, meta=%s
        WHERE narrator_id=%s
    """, (tgt["generation"], tgt["death_year_h"], tgt["bio_summary"],
          tgt["kunya"], tgt["laqab"], tgt["translit"],
          json.dumps(meta, ensure_ascii=False), target_id))

    conn.execute("DELETE FROM narrators WHERE narrator_id = ANY(%s)", (source_ids,))
    audit(conn, "narrator_merge",
          {"target_id": target_id, "source_ids": source_ids,
           "source_names": [by_id[s]["canonical_ar"] for s in source_ids],
           "links_repointed": links}, admin)
    conn.commit()
    return {"target_id": target_id, "merged": len(source_ids),
            "links_repointed": links}


def create_narrator(conn, fields: dict, admin: str | None) -> int:
    ensure_tables(conn)
    name = (fields.get("canonical_ar") or "").strip()
    if not name:
        raise ValueError("canonical_ar is required")
    nid = conn.execute("""
        INSERT INTO narrators (canonical_ar, canonical_norm, kunya, laqab,
                               generation, death_year_h, bio_summary, meta)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING narrator_id
    """, (name, normalize_arabic(name), fields.get("kunya"), fields.get("laqab"),
          fields.get("generation"), fields.get("death_year_h"),
          fields.get("bio_summary"),
          json.dumps({"created_by_admin": True}, ensure_ascii=False),
          )).fetchone()["narrator_id"]
    audit(conn, "narrator_create", {"narrator_id": nid, "canonical_ar": name}, admin)
    conn.commit()
    return nid


def delete_narrator(conn, narrator_id: int, admin: str | None) -> dict:
    """Remove the narrator node. Isnad link rows are kept but un-resolved
    (narrator_id set NULL) so the raw sanad text is never lost."""
    ensure_tables(conn)
    row = conn.execute("SELECT canonical_ar FROM narrators WHERE narrator_id=%s",
                       (narrator_id,)).fetchone()
    if not row:
        raise ValueError("narrator not found")
    name = row["canonical_ar"]
    links = conn.execute(
        "UPDATE isnad_links SET narrator_id=NULL WHERE narrator_id=%s",
        (narrator_id,)).rowcount
    conn.execute("DELETE FROM narrator_aliases WHERE narrator_id=%s", (narrator_id,))
    conn.execute("DELETE FROM narrator_assessments WHERE narrator_id=%s", (narrator_id,))
    conn.execute("DELETE FROM narrator_edges_manual WHERE student_id=%s OR teacher_id=%s",
                 (narrator_id, narrator_id))
    conn.execute("DELETE FROM narrators WHERE narrator_id=%s", (narrator_id,))
    audit(conn, "narrator_delete",
          {"narrator_id": narrator_id, "canonical_ar": name,
           "links_unresolved": links}, admin)
    conn.commit()
    return {"narrator_id": narrator_id, "canonical_ar": name,
            "links_unresolved": links}
