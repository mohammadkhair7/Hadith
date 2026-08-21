import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import AskPanel from "../components/AskPanel";
import ExportBar from "../components/ExportBar";

const stripTags = (s: string) => (s || "").replace(/<[^>]+>/g, "");

const SOURCES = ["", "sunna", "shamela"];

export default function Search() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") || "";
  const tab = params.get("tab") === "ask" ? "ask" : "texts";
  const [input, setInput] = useState(q);

  function setTab(next: "texts" | "ask") {
    const p = new URLSearchParams(params);
    if (next === "ask") p.set("tab", "ask");
    else p.delete("tab");
    setParams(p);
  }
  const [mode, setMode] = useState<"keyword" | "exact" | "semantic" | "hybrid">("keyword");
  const [source, setSource] = useState("");
  const [transmission, setTransmission] = useState("");
  const [htype, setHtype] = useState("");
  const [grade, setGrade] = useState("");
  const [taxonomy, setTaxonomy] = useState<any>(null);
  const [page, setPage] = useState(0);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const limit = 20;

  useEffect(() => {
    api("/classify/taxonomy").then(setTaxonomy).catch(() => {});
  }, []);

  useEffect(() => {
    setInput(q);
    if (!q || tab === "ask") return;
    setLoading(true);
    const sp = new URLSearchParams({ q, mode, limit: String(limit), offset: String(page * limit) });
    if (source) sp.set("source", source);
    if (transmission) sp.set("transmission", transmission);
    if (htype) sp.set("hadith_type", htype);
    if (grade) sp.set("grade", grade);
    api(`/search?${sp}`)
      .then(setResult)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [q, mode, source, transmission, htype, grade, page, tab]);

  const facetsActive = mode === "keyword" || mode === "exact";

  const tabCls = (active: boolean) =>
    `px-5 py-2 rounded-t-xl text-sm font-bold transition-colors border-b-2 ${
      active
        ? "border-islamic-gold text-deep-teal bg-white shadow-sm"
        : "border-transparent text-gray-400 hover:text-islamic-teal"
    }`;

  return (
    <div>
      <div className="flex gap-1 mb-4 border-b border-islamic-teal/20">
        <button onClick={() => setTab("texts")} className={tabCls(tab === "texts")}>
          {t("search_tab_texts")}
        </button>
        <button onClick={() => setTab("ask")} className={tabCls(tab === "ask")}>
          {t("ask_title")}
        </button>
      </div>

      {tab === "ask" ? (
        <AskPanel key={q} initialQ={input} />
      ) : (
      <>
      <form
        onSubmit={(e) => { e.preventDefault(); setPage(0); setParams({ q: input }); }}
        className="flex flex-wrap gap-2 mb-5"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("search_placeholder")}
          className="flex-1 min-w-[240px] border-2 border-islamic-teal rounded-xl px-4 py-2.5 font-arabic outline-none focus:border-islamic-gold"
        />
        <select value={mode} onChange={(e) => { setMode(e.target.value as any); setPage(0); }}
          className="border rounded-xl px-3 text-sm"
          title={t(`search_hint_${mode}`) as string}>
          <option value="keyword" title={t("search_hint_keyword") as string}>
            {t("search_mode_keyword")}</option>
          <option value="exact" title={t("search_hint_exact") as string}>
            {t("search_mode_exact")}</option>
          <option value="semantic" title={t("search_hint_semantic") as string}>
            {t("search_mode_semantic")}</option>
          <option value="hybrid" title={t("search_hint_hybrid") as string}>
            {t("search_mode_hybrid")}</option>
        </select>
        <select value={source} onChange={(e) => { setSource(e.target.value); setPage(0); }}
          className="border rounded-xl px-3 text-sm">
          {SOURCES.map((s) => (
            <option key={s} value={s}>{s ? t(`source_${s}`) : t("filter_all_sources")}</option>
          ))}
        </select>
        {facetsActive && taxonomy && (
          <>
            <select value={transmission}
              onChange={(e) => { setTransmission(e.target.value); setPage(0); }}
              className="border rounded-xl px-3 text-sm font-arabic"
              title={t("transmission_title") as string}>
              <option value="">{t("filter_any_transmission")}</option>
              {taxonomy.transmission.map((c: any) => (
                <optgroup key={c.key} label={`${c.ar} — ${c.chains.toLocaleString("en")}`}>
                  <option value={c.key}>
                    {t("filter_whole_class")} {c.ar}
                  </option>
                  {c.verbs.filter((v: any) => v.chains > 0).map((v: any) => (
                    <option key={v.verb} value={v.verb}>
                      {v.verb} — {v.chains.toLocaleString("en")}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <select value={htype}
              onChange={(e) => { setHtype(e.target.value); setPage(0); }}
              className="border rounded-xl px-3 text-sm font-arabic"
              title={t("hadith_type_title") as string}>
              <option value="">{t("filter_any_type")}</option>
              {taxonomy.hadith_types.map((c: any) => (
                <option key={c.key} value={c.key}>
                  {c.ar} — {c.passages.toLocaleString("en")}
                </option>
              ))}
            </select>
            <select value={grade}
              onChange={(e) => { setGrade(e.target.value); setPage(0); }}
              className="border rounded-xl px-3 text-sm font-arabic"
              title={t("grade_title") as string}>
              <option value="">{t("filter_any_grade")}</option>
              {(taxonomy.grades || []).map((g: any) => (
                <option key={g.key} value={g.key}>
                  {g.ar} — {g.passages.toLocaleString("en")}
                </option>
              ))}
            </select>
          </>
        )}
        <button className="bg-islamic-teal text-white rounded-xl px-6 hover:bg-deep-teal transition-colors">
          {t("nav_search")}
        </button>
      </form>

      {loading && <div className="text-center py-10 text-gray-400">{t("loading")}</div>}

      {result && !loading && (
        <>
          <div className="text-sm text-gray-500 mb-3 flex items-center gap-3 flex-wrap">
            <span>{result.total.toLocaleString("en")} {t("search_results")}</span>
            {result.items.length > 0 && (
              <ExportBar title={`${t("nav_search")}: ${q}`}
                text={() => result.items.map((r: any) =>
                  `${r.work_title}${r.hadith_num ? " #" + r.hadith_num : ""}\n${stripTags(r.snippet)}\n`).join("\n")}
                csv={() => [[t("nav_books"), t("hadith_no"), t("filter_all_sources"), t("nav_search")],
                  ...result.items.map((r: any) =>
                    [r.work_title, r.hadith_num, r.source, stripTags(r.snippet)])]} />
            )}
            {result.coverage &&
              result.coverage.editions_with_embeddings < result.coverage.editions_in_scope && (
              <span className="ms-3 text-orange-accent">
                ⚠ {t("coverage_notice", {
                  done: result.coverage.editions_with_embeddings,
                  total: result.coverage.editions_in_scope,
                })}
              </span>
            )}
          </div>
          {result.items.length === 0 && (
            <div className="text-center py-10 text-gray-400">{t("search_no_results")}</div>
          )}
          <div className="space-y-3">
            {result.items.map((r: any) => (
              <Link
                key={r.passage_id}
                to={`/passage/${r.passage_id}`}
                className="block bg-white rounded-xl p-4 shadow hover:shadow-md border-s-4 border-islamic-gold"
              >
                <div className="flex items-center gap-2 text-xs text-islamic-teal mb-2 flex-wrap">
                  <span className="font-bold">{r.work_title}</span>
                  {r.hadith_num && <span className="bg-islamic-gold/20 rounded-full px-2 py-0.5">{t("hadith_no")} {r.hadith_num}</span>}
                  <span className="bg-islamic-teal/10 rounded-full px-2 py-0.5">{t(`source_${r.source}`)}</span>
                </div>
                <p
                  className="arabic-text text-base leading-relaxed text-islamic-dark"
                  dangerouslySetInnerHTML={{ __html: r.snippet }}
                />
              </Link>
            ))}
          </div>
          {result.total > limit && (
            <div className="flex justify-center gap-2 mt-6">
              <button disabled={page === 0} onClick={() => setPage(page - 1)}
                className="px-4 py-2 rounded-lg bg-islamic-teal text-white disabled:opacity-30">
                {t("prev")}
              </button>
              <span className="px-4 py-2 text-sm text-gray-500">
                {page + 1} / {Math.ceil(result.total / limit)}
              </span>
              <button disabled={(page + 1) * limit >= result.total} onClick={() => setPage(page + 1)}
                className="px-4 py-2 rounded-lg bg-islamic-teal text-white disabled:opacity-30">
                {t("next")}
              </button>
            </div>
          )}
        </>
      )}
      </>
      )}
    </div>
  );
}
