"""Smoke test for POST /ask across the three routes."""
import sys

import httpx

BASE = "http://127.0.0.1:8090/api/v1"

QUESTIONS = [
    ("analytical", "كم عدد النصوص في كل مصدر من المصادر الثلاثة؟"),
    ("semantic", "ما فضل الصدقة على الفقراء؟"),
    ("graph", "من روى عن أبي هريرة؟"),
]

ok = True
for expected, q in QUESTIONS:
    r = httpx.post(f"{BASE}/ask", json={"question": q}, timeout=120)
    if r.status_code != 200:
        print(f"FAIL [{expected}] HTTP {r.status_code}: {r.text[:200]}")
        ok = False
        continue
    d = r.json()
    print(f"[{expected}] route={d['route']}"
          + (f" note={d.get('note')}" if d.get("note") else "")
          + (f" engine_error={d.get('engine_error')[:80]}" if d.get("engine_error") else ""))
    if d.get("sql"):
        print("  sql:", d["sql"][:150].replace("\n", " "))
        print("  rows:", d.get("rows", [])[:3])
    print("  answer:", (d.get("answer") or "")[:200].replace("\n", " "))
    print("  citations:", len(d.get("citations") or []))
    print()

sys.exit(0 if ok else 1)
