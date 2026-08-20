"""Repair and validate the 40343-al-bukhari.csv export (al-Jami' al-Sahih,
Dar al-Sha'b ed., Fath al-Bari numbering 1..7563).

The source file is one record per LF line (hno,id,nass,page,part) where nass
uses bare CR as internal line separator. Records whose nass contains no comma
were left unquoted by the exporter, so CRs leak out and naive CSV parsers
shatter them into extra rows. hno is empty everywhere; the hadith numbers are
inline in nass ("8- حدثنا", combined "408 و409-").

Output: a clean RFC-4180 CSV (utf-8 BOM, real newlines inside quoted nass)
with hno filled per record from the inline numbering, plus a validation
report proving the sequence 1..7563 is complete.
"""
import csv
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SRC = Path(r"E:\Quran Computing Institute\Hadith.chat\40343-al-bukhari.csv")
DST = Path(r"E:\Quran Computing Institute\Hadith.chat\40343-al-bukhari-formatted.csv")

_FIELDS = re.compile(r"^([^,]*),([^,]*),(.*),([^,]*),([^,]*)\r?$", re.S)
# hadith numbers at segment start: "8-", "408 و409-", "1241و1242-"
_NUM = re.compile(r"^(\d+(?:\s*و\s*\d+)*)\s*-\s*(.*)")
_MARKS = re.compile(r"[\u064B-\u0652\u0670\u0640]")
_HEADING = re.compile(r"^(باب|كتاب|سورة|أبواب|ابواب)\b")
# the numbering may only START at a real hadith (front matter also has a
# numbered list "1 - تم مقابلة الكتاب..."), so hadith 1 must open with a verb
_CHAIN_OPEN = re.compile(r"^و?(حدثنا|حدثني|اخبرنا|اخبرني|انبانا|قال)\b")


def parse_records(path: Path):
    data = path.open(encoding="utf-8-sig", newline="").read()
    lines = [l for l in data.split("\n") if l.strip()]
    recs = []
    for ln in lines[1:]:  # skip header
        m = _FIELDS.match(ln)
        if not m:
            raise SystemExit(f"unparseable line: {ln[:120]!r}")
        _hno, rid, nass, page, part = m.groups()
        if nass.startswith('"') and nass.endswith('"'):
            nass = nass[1:-1].replace('""', '"')
        segments = [s.strip() for s in nass.split("\r")]
        segments = [s for s in segments if s]
        recs.append((int(rid), segments, int(page), int(part)))
    return recs


def main() -> None:
    recs = parse_records(SRC)
    print(f"records parsed: {len(recs)}")

    last = 0
    anomalies = []
    heading_count = 0
    out_rows = []
    all_nums = set()
    for rid, segments, page, part in recs:
        rec_nums = []
        for seg in segments:
            m = _NUM.match(seg)
            if not m:
                continue
            nums = [int(x) for x in re.split(r"\s*و\s*", m.group(1))]
            title_bare = _MARKS.sub("", m.group(2))
            if _HEADING.match(title_bare):
                heading_count += 1
                continue
            if last == 0 and nums[0] == 1 and not _CHAIN_OPEN.match(title_bare):
                heading_count += 1
                continue
            if nums[0] == last + 1 and nums == list(range(nums[0], nums[-1] + 1)):
                rec_nums.extend(nums)
                all_nums.update(nums)
                last = nums[-1]
            elif nums[0] <= last or nums[0] > last + 1:
                # bab/kitab numbering without a keyword, or apparatus note
                heading_count += 1
            else:
                anomalies.append((rid, nums, seg[:60]))
        hno = ",".join(str(n) for n in rec_nums)
        text = "\n".join(segments)
        out_rows.append((hno, rid, text, page, part))

    print(f"hadith numbers accepted: {len(all_nums)} (expect 7563)")
    print(f"last number reached: {last}")
    missing = sorted(set(range(1, 7564)) - all_nums)
    print(f"missing: {len(missing)} {missing[:20]}")
    print(f"headings/other numbered segments: {heading_count}")
    print(f"anomalies: {len(anomalies)}")
    for a in anomalies[:10]:
        print("  ", a)

    with DST.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(["hno", "id", "nass", "page", "part"])
        w.writerows(out_rows)
    print(f"wrote {DST} ({DST.stat().st_size:,} bytes)")

    # round-trip check
    with DST.open(encoding="utf-8-sig", newline="") as f:
        back = list(csv.DictReader(f))
    ok = len(back) == len(out_rows) and all(
        b["nass"] == r[2] and b["hno"] == r[0] for b, r in zip(back, out_rows)
    )
    print(f"round-trip parse: {len(back)} rows, identical: {ok}")


if __name__ == "__main__":
    main()
