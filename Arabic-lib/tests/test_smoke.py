"""Golden smoke tests over hadith samples: engine availability, annotation
layers, isnad parsing, unit segmentation. Run:
    .venv\\Scripts\\python Arabic-lib\\tests\\test_smoke.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arabiclib import annotate, available_engines
from arabiclib.indexing import segment_units
from arabiclib.indexing.tocbuild import build_toc
from arabiclib.isnad import parse_isnad

HADITH = ("حدثنا عبد الله بن يوسف قال أخبرنا مالك عن نافع عن عبد الله بن عمر "
          "أن رسول الله صلى الله عليه وسلم قال : « إنما الأعمال بالنيات »")

FLAT_PAGE = """كتاب الإيمان
باب بدء الوحي
1 - حدثنا الحميدي عبد الله بن الزبير قال حدثنا سفيان قال حدثنا يحيى بن سعيد الأنصاري
إنما الأعمال بالنيات وإنما لكل امرئ ما نوى
2 - حدثنا عبد الله بن يوسف قال أخبرنا مالك عن هشام بن عروة
باب علامات المنافق
3 - حدثنا سليمان أبو الربيع قال حدثنا إسماعيل بن جعفر"""

failures = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global failures
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        failures += 1


print("== engine availability ==")
avail = available_engines()
for layer, engines in avail.items():
    for e in engines:
        mark = "+" if e["available"] else "-"
        print(f"  [{mark}] {layer:12s} {e['engine']:8s} {e['reason'][:80]}")

print("\n== annotate ==")
ann = annotate(HADITH, layers=["segments", "pos", "roots", "morphology"])
check("tokens", len(ann.tokens) > 15, f"{len(ann.tokens)} tokens")
check("pos layer", len(ann.pos) > 10, f"{len(ann.pos)} tags via {ann.meta['engines'].get('pos')}")
check("roots layer", len(ann.roots) > 10, f"{len(ann.roots)} roots via {ann.meta['engines'].get('roots')}")
amal = next((r for r in ann.roots if "اعمال" in
             __import__('arabiclib.normalize', fromlist=['normalize_arabic'])
             .normalize_arabic(ann.tokens[r['token_idx']].text)), None)
if amal:
    check("root of الأعمال", amal["root"] in ("عمل", "ع.م.ل"), f"got {amal['root']}")

print("\n== isnad ==")
p = parse_isnad(HADITH)
check("isnad hops", len(p.hops) >= 3, f"{len(p.hops)} hops, conf={p.confidence}")
mentions = [h.mention for h in p.hops]
check("first narrator", any("عبد الله بن يوسف" in m for m in mentions), str(mentions[:2]))

print("\n== unit segmentation ==")
units = segment_units(FLAT_PAGE)
check("3 numbered units", sum(1 for u in units if u.hadith_num) == 3,
      f"nums={[u.hadith_num for u in units]}")
check("heading attached", any(u.heading and "باب" in u.heading for u in units))

print("\n== toc build ==")
toc = build_toc([FLAT_PAGE])
check("toc roots", len(toc) == 1 and toc[0].title.startswith("كتاب"),
      f"{len(toc)} roots")
check("toc children", len(toc[0].children) == 2,
      f"{len(toc[0].children)} children")

print(f"\n{failures} failures")
sys.exit(1 if failures else 0)
