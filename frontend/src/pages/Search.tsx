import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";

const SOURCES = ["", "sunna", "shamela", "alifta"];

export default function Search() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") || "";
  const [input, setInput] = useState(q);
  const [mode, setMode] = useState<"keyword" | "exact" | "semantic" | "hybrid">("keyword");
  const [source, setSource] = useState("");
  const [page, setPage] = useState(0);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const limit = 20;

  useEffect(() => {
    setInput(q);
    if (!q) return;
    setLoading(true);
    const sp = new URLSearchParams({ q, mode, limit: String(limit), offset: String(page * limit) });
    if (source) sp.set("source", source);
    api(`/search?${sp}`)
      .then(setResult)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [q, mode, source, page]);

  return (
    <div>
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
          className="border rounded-xl px-3 text-sm">
          <option value="keyword">{t("search_mode_keyword")}</option>
          <option value="exact">{t("search_mode_exact")}</option>
          <option value="semantic">{t("search_mode_semantic")}</option>
          <option value="hybrid">{t("search_mode_hybrid")}</option>
        </select>
        <select value={source} onChange={(e) => { setSource(e.target.value); setPage(0); }}
          className="border rounded-xl px-3 text-sm">
          {SOURCES.map((s) => (
            <option key={s} value={s}>{s ? t(`source_${s}`) : t("filter_all_sources")}</option>
          ))}
        </select>
        <button className="bg-islamic-teal text-white rounded-xl px-6 hover:bg-deep-teal transition-colors">
          {t("nav_search")}
        </button>
      </form>

      {loading && <div className="text-center py-10 text-gray-400">{t("loading")}</div>}

      {result && !loading && (
        <>
          <div className="text-sm text-gray-500 mb-3">
            {result.total.toLocaleString("en")} {t("search_results")}
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
    </div>
  );
}
