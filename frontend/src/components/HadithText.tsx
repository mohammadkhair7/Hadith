import { useState } from "react";
import { useTranslation } from "react-i18next";
import { cleanText, matnStart, stripTashkeel } from "../text";

/** Hadith body with the sanad visually distinguished from the matn.
 *  Uses the extractor's stored raw offset when available, otherwise the
 *  client-side marker heuristic. Honors tashkeel / matn-only preferences.
 *  Clicking the sanad or the matn toggles a strong highlight on that part. */
export default function HadithText({ raw, sanadEndRaw, prefs }: {
  raw: string;
  sanadEndRaw?: number | null;
  prefs: { tashkeel: boolean; matnOnly: boolean };
}) {
  const { t } = useTranslation();
  const [focus, setFocus] = useState<"" | "sanad" | "matn">("");
  const boundary = sanadEndRaw && sanadEndRaw > 0 ? sanadEndRaw : matnStart(raw);
  // clean AFTER slicing so the sanad/matn boundary offsets stay valid
  const fmt = (s: string) => cleanText(prefs.tashkeel ? s : stripTashkeel(s));

  if (boundary <= 0) {
    return <div className="arabic-text whitespace-pre-wrap">{fmt(raw)}</div>;
  }
  if (prefs.matnOnly) {
    return <div className="arabic-text whitespace-pre-wrap">{fmt(raw.slice(boundary))}</div>;
  }
  const toggle = (part: "sanad" | "matn") => setFocus(focus === part ? "" : part);
  const sanadCls =
    focus === "sanad"
      ? "bg-islamic-teal/20 text-deep-teal ring-2 ring-islamic-teal rounded px-0.5 box-decoration-clone"
      : focus === "matn"
        ? "text-gray-400"
        : "text-gray-500";
  const matnCls =
    focus === "matn"
      ? "bg-islamic-gold/40 ring-2 ring-islamic-gold rounded px-0.5 box-decoration-clone"
      : focus === "sanad"
        ? "text-gray-400"
        : "bg-islamic-gold/15 rounded px-0.5 box-decoration-clone";
  return (
    <div className="arabic-text whitespace-pre-wrap">
      <span className={`cursor-pointer transition-colors ${sanadCls}`}
        title={t("click_highlight_sanad")}
        onClick={() => toggle("sanad")}>
        {fmt(raw.slice(0, boundary))}
      </span>
      <span className={`cursor-pointer transition-colors ${matnCls}`}
        title={t("click_highlight_matn")}
        onClick={() => toggle("matn")}>
        {fmt(raw.slice(boundary))}
      </span>
    </div>
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
