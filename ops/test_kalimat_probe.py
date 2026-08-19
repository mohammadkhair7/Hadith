import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.translate import kalimat_lookup, _token_overlap
from app.services.normalize import normalize_arabic
from app.config import settings
import httpx
from urllib.parse import quote

print("api key set:", bool(settings.kalimat_api_key))

QUERIES = [
    "إنما الأعمال بالنيات وإنما لكل امرئ ما نوى",
    "من حسن إسلام المرء تركه ما لا يعنيه",
]
for q in QUERIES:
    url = (f"https://api.kalimat.dev/search?query={quote(q, safe='')}"
           f"&numResults=1&getText=2&getTotalResultsNum=1&indexes=[%22sunnah_lk%22]")
    r = httpx.get(url, headers={"X-Api-Key": settings.kalimat_api_key}, timeout=30)
    print("\nQ:", q[:50], "->", r.status_code)
    if r.status_code == 200:
        data = r.json()
        hits = data.get("results", []) if isinstance(data, dict) else data
        print("  hits:", len(hits))
        if hits:
            h = hits[0]
            print("  keys:", sorted(h.keys()))
            ar = h.get("matn_ar") or h.get("text") or ""
            print("  sim:", _token_overlap(normalize_arabic(q), normalize_arabic(ar)))
            print("  en_text:", (h.get("en_text") or "")[:150])
            print("  matn_en:", (h.get("matn_en") or "")[:150])
    else:
        print("  body:", r.text[:200])
    k = kalimat_lookup(q)
    print("  waterfall:", "HIT" if k else "MISS", (k or {}).get("meta", ""))
