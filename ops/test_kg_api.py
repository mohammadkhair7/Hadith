"""Smoke test the Phase 6 narrator/graph endpoints + graph route in /ask."""
import sys

import httpx

BASE = "http://127.0.0.1:8090/api/v1"
ok = True


def check(name, cond, detail=""):
    global ok
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")
    if not cond:
        ok = False


r = httpx.get(f"{BASE}/narrators", params={"search": "مالك"}, timeout=30).json()
check("narrator search", len(r) > 0, f"{len(r)} hits, top: {r[0]['canonical_ar']} ({r[0]['mentions']})")
nid = r[0]["narrator_id"]

n = httpx.get(f"{BASE}/narrators/{nid}", timeout=30).json()
check("narrator profile", n["chains"] > 0, f"chains={n['chains']} mentions={n['mentions']}")

g = httpx.get(f"{BASE}/narrators/{nid}/graph", params={"depth": 1, "cap": 50}, timeout=60).json()
check("subgraph", len(g["nodes"]) > 3 and len(g["edges"]) > 3,
      f"{len(g['nodes'])} nodes {len(g['edges'])} edges capped={g['capped']}")

e = httpx.post(f"{BASE}/graph/expand", json={"node_ids": [nid], "cap": 20}, timeout=60).json()
check("expand", len(e["edges"]) > 0, f"{len(e['nodes'])} nodes {len(e['edges'])} edges")

h = httpx.get(f"{BASE}/narrators/{nid}/hadiths", params={"limit": 3}, timeout=30).json()
check("hadiths", h["total"] > 0, f"total={h['total']}")

if h["items"]:
    pid = h["items"][0]["passage_id"]
    isn = httpx.get(f"{BASE}/passages/{pid}/isnad", timeout=30).json()
    check("passage isnad", len(isn) > 0 and len(isn[0]["links"]) >= 2,
          f"{len(isn[0]['links']) if isn else 0} links")

a = httpx.post(f"{BASE}/ask", json={"question": "من روى عن ابن عمر؟"}, timeout=120).json()
check("/ask graph route", a["route"] == "graph" and bool(a.get("cypher")),
      f"cypher={str(a.get('cypher'))[:90]}")
check("/ask graph rows", len(a.get("rows") or []) > 0, f"{len(a.get('rows') or [])} rows")
print("answer:", (a.get("answer") or "")[:250].replace("\n", " "))

sys.exit(0 if ok else 1)
