import { useState } from "react";
import { useTranslation } from "react-i18next";
import { cleanText, mapRawOffset, matnEnd, matnStart, segmentHadiths, stripTashkeel } from "../text";

type Prefs = { tashkeel: boolean; matnOnly: boolean };

/** Hadith body with the sanad visually distinguished from the matn.
 *
 *  - Single hadith: uses the extractor's stored raw offset when available,
 *    otherwise the client-side marker heuristic.
 *  - Pages with SEVERAL hadiths: each transmission chain becomes its own
 *    section with its own sanad/matn split (never one giant sanad).
 *  - When a diacritized rendering is available and tashkeel is on, it is
 *    displayed instead of the bare text (offsets are remapped).
 *  - Clicking a sanad or a matn toggles a strong highlight on that part;
 *    "matn only" lists every matn in its own section. */
export default function HadithText({ raw, diac, sanadEndRaw, prefs }: {
  raw: string;
  diac?: string | null;
  sanadEndRaw?: number | null;
  prefs: Prefs;
}) {
  const [focus, setFocus] = useState("");
  const text = prefs.tashkeel && diac ? diac : raw;
  const usingDiac = text !== raw;
  const fmt = (s: string) => cleanText(prefs.tashkeel ? s : stripTashkeel(s));
  const toggle = (key: string) => setFocus(focus === key ? "" : key);

  // trust the extractor's stored boundary (single hadith unit) when present
  if (sanadEndRaw && sanadEndRaw > 0) {
    const b = usingDiac ? mapRawOffset(text, sanadEndRaw) : sanadEndRaw;
    return (
      <div className="arabic-text whitespace-pre-wrap">
        <HadithBlock text={text} boundary={b} end={matnEnd(text, b)} fmt={fmt}
          focusKey="0" focus={focus} toggle={toggle} matnOnly={prefs.matnOnly} />
      </div>
    );
  }

  const starts = segmentHadiths(text);
  if (starts.length === 0) {
    const b = matnStart(text);
    return (
      <div className="arabic-text whitespace-pre-wrap">
        <HadithBlock text={text} boundary={b} end={matnEnd(text, b)} fmt={fmt}
          focusKey="0" focus={focus} toggle={toggle} matnOnly={prefs.matnOnly} />
      </div>
    );
  }

  // several hadiths on one page: one section per chain
  const intro = text.slice(0, starts[0]);
  const segs = starts.map((s, i) => text.slice(s, starts[i + 1] ?? text.length));
  return (
    <div className="arabic-text whitespace-pre-wrap space-y-3">
      {!prefs.matnOnly && intro.trim() && <div>{fmt(intro)}</div>}
      {segs.map((seg, i) => {
        const b = matnStart(seg);
        if (prefs.matnOnly && b <= 0) return null;
        return (
          <div key={i}
            className="border-s-2 border-islamic-gold/50 ps-3 rounded-sm">
            <HadithBlock text={seg} boundary={b} end={matnEnd(seg, b)} fmt={fmt}
              focusKey={String(i)} focus={focus} toggle={toggle}
              matnOnly={prefs.matnOnly} />
          </div>
        );
      })}
    </div>
  );
}

function HadithBlock({ text, boundary, end, fmt, focusKey, focus, toggle, matnOnly }: {
  text: string;
  boundary: number;
  end: number;           // where the matn stops (takhrij/footnotes follow); -1 = text end
  fmt: (s: string) => string;
  focusKey: string;
  focus: string;
  toggle: (key: string) => void;
  matnOnly: boolean;
}) {
  const { t } = useTranslation();
  if (boundary <= 0) return <span>{fmt(text)}</span>;
  const matnTo = end > boundary ? end : text.length;
  if (matnOnly) return <span>{fmt(text.slice(boundary, matnTo))}</span>;

  const sKey = `${focusKey}:sanad`;
  const mKey = `${focusKey}:matn`;
  const other = focus && focus.startsWith(`${focusKey}:`);
  const sanadCls =
    focus === sKey
      ? "bg-islamic-teal/20 text-deep-teal ring-2 ring-islamic-teal rounded px-0.5 box-decoration-clone"
      : other
        ? "text-gray-400"
        : "text-gray-500";
  const matnCls =
    focus === mKey
      ? "bg-islamic-gold/40 ring-2 ring-islamic-gold rounded px-0.5 box-decoration-clone"
      : other
        ? "text-gray-400"
        : "bg-islamic-gold/15 rounded px-0.5 box-decoration-clone";
  return (
    <>
      <span className={`cursor-pointer transition-colors ${sanadCls}`}
        title={t("click_highlight_sanad")}
        onClick={() => toggle(sKey)}>
        {fmt(text.slice(0, boundary))}
      </span>
      <span className={`cursor-pointer transition-colors ${matnCls}`}
        title={t("click_highlight_matn")}
        onClick={() => toggle(mKey)}>
        {fmt(text.slice(boundary, matnTo))}
      </span>
      {matnTo < text.length && (
        <span className={other ? "text-gray-400" : "text-gray-600"}>
          {fmt(text.slice(matnTo))}
        </span>
      )}
    </>
  );
}

const GRADE_COLORS: Record<string, string> = {
  sahih: "bg-emerald-600",
  hasan: "bg-blue-600",
  maqbul: "bg-cyan-600",
  daif: "bg-orange-500",
  mawdu: "bg-red-600",
  other: "bg-gray-500",
};

export function GradeBadge({ grade }: { grade?: { grade_ar?: string; grade_norm?: string } | null }) {
  if (!grade?.grade_ar) return null;
  return (
    <span className={`${GRADE_COLORS[grade.grade_norm || "other"] || GRADE_COLORS.other}
      text-white font-bold rounded-full px-3 py-1 font-arabic`}>
      {grade.grade_ar}
    </span>
  );
}
