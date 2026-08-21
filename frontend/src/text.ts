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

/** Remove source-side noise (crawler junk, leading abjad page numbers,
 *  § heading markers) for display. */
export function cleanText(s: string): string {
  return s.replace(JUNK, " ").replace(ABJAD_PREFIX, "").replace(/§/g, "");
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

// strong markers embed a speech verb; weak ones (عن/أن + النبي) also occur
// descriptively in commentary, so they only count when a speech cue follows
const MATN_STRONG = /(قال|يقول|فقال|سمعت)\s+(رسول\s+الله|النبي)/g;
const MATN_WEAK = /(عن|ان)\s+(النبي|رسول\s+الله)\s/g;
// cue expected shortly after a weak marker (past the ﷺ honorific):
// a speech/report verb or an explicit quote opener
const SPEECH_CUE = /^.{0,45}?(قال|يقول|فقال|سئل|نهي|امر|اوصي|خطب|كتب|:|«)/;

/** Diacritics-insensitive normalized view of a string plus an index map
 *  back to the original offsets. */
function normWithMap(raw: string): { norm: string; map: number[] } {
  let norm = "";
  const map: number[] = [];
  for (let i = 0; i < raw.length; i++) {
    const c = raw[i];
    if (DIA_ONE.test(c)) continue;
    norm += normChar(c);
    map.push(i);
  }
  return { norm, map };
}

// a speech opener directly before a Prophet marker: the matn really starts
// there («عن أبيه قال : لم أتخلف عن النبي ﷺ...» — قال opens the matn)
const SPEECH_OPEN = /(قال|قالت)\s*:/g;

/**
 * Heuristic matn boundary: index in the RAW string where the matn begins
 * (the FIRST valid Prophet-speech marker, mirroring the DB extractor).
 * Weak markers (عن النبي / أن رسول الله) are only accepted when followed by
 * a speech cue — a bare honorific mention in commentary is NOT a matn start.
 * When a «قال :» speech opener directly precedes the marker (same sentence),
 * the boundary is pulled back to it — the Prophet mention is INSIDE the matn.
 * Returns -1 when not found or when the remainder would be too short.
 */
export function matnStart(raw: string): number {
  const { norm, map } = normWithMap(raw);
  let best = -1;
  let m: RegExpExecArray | null;
  MATN_STRONG.lastIndex = 0;
  while ((m = MATN_STRONG.exec(norm)) !== null) {
    best = m.index;
    break;
  }
  MATN_WEAK.lastIndex = 0;
  while ((m = MATN_WEAK.exec(norm)) !== null) {
    if (best >= 0 && m.index >= best) break;
    if (SPEECH_CUE.test(norm.slice(m.index + m[0].length, m.index + m[0].length + 60))) {
      best = m.index;
      break;
    }
  }
  if (best > 8) {
    // look back for a «قال :» in the same sentence, at most ~50 chars before
    const from = Math.max(8, best - 50);
    const win = norm.slice(from, best);
    let last = -1;
    let sp: RegExpExecArray | null;
    SPEECH_OPEN.lastIndex = 0;
    while ((sp = SPEECH_OPEN.exec(win)) !== null) last = sp.index;
    if (last >= 0 && !/[.؟!؛»]/.test(win.slice(last))) best = from + last;
  }
  if (best < 0 || norm.length - best < 25 || best === 0) return -1;
  return map[best];
}

// after the Prophet's quoted words end, collections append takhrij /
// mutaba'at / footnotes — these sentence-initial markers close the matn
const MATN_TAIL = new RegExp(
  "(?:[.؟!؛»]|\\n)\\s*(و?تابعه|و?رواه|و?اخرجه|متفق عليه|قال ابو عيسي|" +
  "وفي الباب عن|_حاشيه|\\d+\\s*[-–—]\\s*باب)", "g");

/**
 * Index in the RAW string where the matn (started at rawStart) ends, i.e.
 * where trailing takhrij/commentary/footnotes begin. -1 = runs to the end.
 */
export function matnEnd(raw: string, rawStart: number): number {
  if (rawStart < 0) return -1;
  const { norm, map } = normWithMap(raw);
  // locate rawStart in normalized space
  let from = norm.length;
  for (let i = 0; i < map.length; i++) {
    if (map[i] >= rawStart) { from = i; break; }
  }
  MATN_TAIL.lastIndex = from;
  let m: RegExpExecArray | null;
  while ((m = MATN_TAIL.exec(norm)) !== null) {
    const cut = m.index + 1; // keep the closing punctuation inside the matn
    if (cut - from >= 25) return map[cut] ?? -1;
  }
  return -1;
}

// A hadith chain start: a transmission verb at a sentence boundary
// (text start, after punctuation, or after a hadith number like "19 -").
// NOT after a colon: "قال : حدثنا" continues the SAME chain (nested isnad).
const CHAIN_VERB = "و?(?:حدثنا|حدثني|اخبرنا|اخبرني|انبانا|انباني)";
const CHAIN_START = new RegExp(
  `(?:^|[.؟!؛»\\)\\]\\n]\\s*|\\d\\s*[-–—]\\s*)(${CHAIN_VERB})\\s`, "g");

/**
 * Start offsets (in the ORIGINAL string) of each hadith transmission chain.
 * Returns [] when fewer than two chains are found (single-hadith text).
 */
export function segmentHadiths(raw: string): number[] {
  const { norm, map } = normWithMap(raw);
  const starts: number[] = [];
  let m: RegExpExecArray | null;
  CHAIN_START.lastIndex = 0;
  while ((m = CHAIN_START.exec(norm)) !== null) {
    const pos = m.index + m[0].indexOf(m[1]);
    starts.push(map[pos]);
    // allow overlapping sentence-boundary lookarounds
    CHAIN_START.lastIndex = m.index + m[0].length - 1;
  }
  return starts.length >= 2 ? starts : [];
}

// only the marks that diacritization inserts (NOT tatweel, which is base text)
const MARK_ONE = /[\u064B-\u0652\u0670]/;

/** Map a character offset in the bare text to the same logical position in
 *  the diacritized text (identical base chars, marks inserted). */
export function mapRawOffset(diac: string, rawOffset: number): number {
  let count = 0;
  for (let i = 0; i < diac.length; i++) {
    if (MARK_ONE.test(diac[i])) continue;
    if (count === rawOffset) return i;
    count++;
  }
  return diac.length;
}

/* ---------- markdown-style page structure (shamela page display) ---------- */

export type PageBlock = { kind: "h1" | "h2" | "h3" | "para"; from: number; to: number };

// mirrors ops/build_shamela_toc.py heading grammar
const H_DECOR = /^[\s\d\u0660-\u0669\-–—=*.،:()\[\]«»_§]+/;
const H_SKIP = /^(البحر\s|ص\s*[::]?\s*\d|\d|رقم\s)/;
const H_K1 = /^(كتاب|ابواب|سوره|تفسير سوره)\s+\S/;
const H_K2 = /^باب(\s|$)/;
const H_K3 = /^(فصل|مقدمه|خاتمه|مساله)(\s|$)/;

function headingKind(line: string): "h1" | "h2" | "h3" | null {
  const t = line.trim();
  if (t.length < 3 || t.length > 160) return null;
  let bare = "";
  for (const c of stripTashkeel(t)) bare += normChar(c);
  bare = bare.trim();
  const bracketed = /^\[.{2,140}\]$/.test(bare);
  const core = bare.replace(H_DECOR, "").replace(/[\][]+$/, "").trim();
  if (!core || core.length > 95) return null;
  if (H_K1.test(core)) return "h1";
  if (H_K2.test(core)) return "h2";
  if (H_K3.test(core)) return "h3";
  if ((bracketed || t.startsWith("§")) && !H_SKIP.test(core)) return "h3";
  return null;
}

/** Split a page into heading and paragraph blocks (RAW-text offsets).
 *  Consecutive non-heading lines form ONE paragraph block, so hadith
 *  segmentation and matn detection keep working on whole passages. */
export function pageBlocks(raw: string): PageBlock[] {
  const blocks: PageBlock[] = [];
  let pos = 0;
  let paraFrom = -1;
  const flush = (end: number) => {
    if (paraFrom >= 0 && end > paraFrom) blocks.push({ kind: "para", from: paraFrom, to: end });
    paraFrom = -1;
  };
  for (const line of raw.split("\n")) {
    const start = pos;
    const end = pos + line.length;
    pos = end + 1;
    if (!line.trim()) {
      flush(start);
      continue;
    }
    const k = headingKind(line);
    if (k) {
      flush(start);
      blocks.push({ kind: k, from: start, to: end });
    } else if (paraFrom < 0) {
      paraFrom = start;
    }
  }
  flush(raw.length);
  return blocks;
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
    if (i > 0) {
      const e = matnEnd(raw, i);
      out = e > i ? out.slice(i, e) : out.slice(i);
    }
  }
  if (!prefs.tashkeel) out = stripTashkeel(out);
  return out;
}
