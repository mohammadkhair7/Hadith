/** Arabic display utilities: tashkeel stripping and matn boundary detection. */
import { useEffect, useState } from "react";

const DIACRITICS = /[\u064B-\u065F\u0670\u06D6-\u06ED\u0640]/g;
const DIA_ONE = /[\u064B-\u065F\u0670\u06D6-\u06ED\u0640]/;

export function stripTashkeel(s: string): string {
  return s.replace(DIACRITICS, "");
}

// crawler artifacts embedded in some source pages
const JUNK = /AddHistory\([^)]*\)[^;\n]*;?|\[\d+\/\d+\]/g;
// abjad page-number marker glued to the start of scanned pages ("هـ." "يب." ...)
const ABJAD_PREFIX = /^(?:[\u0621-\u064A\u0640][\u064B-\u0652\u0670]*){1,4}\.\s*/;

/** Remove source-side noise (crawler junk, leading abjad page numbers) for display. */
export function cleanText(s: string): string {
  return s.replace(JUNK, " ").replace(ABJAD_PREFIX, "");
}

/** Normalize one char for marker matching (diacritics removed by caller). */
function normChar(c: string): string {
  if ("أإآٱ".includes(c)) return "ا";
  if (c === "ى") return "ي";
  if (c === "ؤ") return "و";
  if (c === "ئ") return "ي";
  if (c === "ة") return "ه";
  return c;
}

const MATN_MARKERS =
  /(قال|يقول|سمعت)\s+(رسول\s+الله|النبي)|ان\s+(رسول\s+الله|النبي)\s|عن\s+النبي\s/g;

/**
 * Heuristic matn boundary: index in the RAW string where the matn begins
 * (the last Prophet-speech marker). Returns -1 when not found or when the
 * remainder would be too short to be a matn.
 */
export function matnStart(raw: string): number {
  let norm = "";
  const map: number[] = [];
  for (let i = 0; i < raw.length; i++) {
    const c = raw[i];
    if (DIA_ONE.test(c)) continue;
    norm += normChar(c);
    map.push(i);
  }
  let last = -1;
  let m: RegExpExecArray | null;
  MATN_MARKERS.lastIndex = 0;
  while ((m = MATN_MARKERS.exec(norm)) !== null) last = m.index;
  if (last < 0 || norm.length - last < 25 || last === 0) return -1;
  return map[last];
}

export type DisplayPrefs = {
  tashkeel: boolean;
  matnOnly: boolean;
  setTashkeel: (v: boolean) => void;
  setMatnOnly: (v: boolean) => void;
};

/** Reader display preferences persisted in localStorage. */
export function useDisplayPrefs(): DisplayPrefs {
  const [tashkeel, setTk] = useState(() => localStorage.getItem("ah_tashkeel") !== "0");
  const [matnOnly, setMt] = useState(() => localStorage.getItem("ah_matn") === "1");
  useEffect(() => { localStorage.setItem("ah_tashkeel", tashkeel ? "1" : "0"); }, [tashkeel]);
  useEffect(() => { localStorage.setItem("ah_matn", matnOnly ? "1" : "0"); }, [matnOnly]);
  return { tashkeel, matnOnly, setTashkeel: setTk, setMatnOnly: setMt };
}

/** Apply the two toggles to a raw passage text. */
export function displayText(raw: string, prefs: { tashkeel: boolean; matnOnly: boolean }): string {
  let out = raw;
  if (prefs.matnOnly) {
    const i = matnStart(raw);
    if (i > 0) out = out.slice(i);
  }
  if (!prefs.tashkeel) out = stripTashkeel(out);
  return out;
}
