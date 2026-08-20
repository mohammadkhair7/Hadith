import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../api";
import ExportBar from "../components/ExportBar";

export default function Ask() {
  const { t, i18n } = useTranslation();
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setLoading(true);
    setError("");
    setRes(null);
    try {
      const r = await api("/ask", {
        method: "POST",
        body: JSON.stringify({ question: q.trim(), lang: i18n.language }),
      });
      setRes(r);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">{t("ask_title")}</h1>
      <p className="text-sm text-gray-500 mb-5">{t("ask_sub")}</p>

      <form onSubmit={submit} className="flex gap-2 mb-6">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("ask_placeholder")}
          className="flex-1 border-2 border-islamic-teal rounded-xl px-4 py-3 font-arabic outline-none focus:border-islamic-gold"
        />
        <button disabled={loading}
          className="bg-islamic-teal text-white rounded-xl px-6 hover:bg-deep-teal transition-colors disabled:opacity-40">
          {loading ? "…" : t("ask_button")}
        </button>
      </form>

      {error && <div className="bg-red-50 text-red-600 rounded-lg p-3 text-sm mb-4">{error}</div>}
      {loading && <div className="text-center py-10 text-gray-400 animate-pulse">{t("ask_thinking")}</div>}

      {res && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl shadow-lg p-6 border-t-4 border-islamic-gold">
            <div className="text-xs text-gray-400 mb-2 flex items-center gap-2 flex-wrap" dir="ltr">
              <span>
                route: {res.route}
                {res.note && ` · ${res.note}`}
                {res.engine_error && ` · fell back (${res.engine_error.slice(0, 80)})`}
              </span>
              <ExportBar title={q.slice(0, 60)}
                text={() => `${q}\n\n${res.answer}\n\n${(res.citations || []).map(
                  (c: any, i: number) => `[${i + 1}] ${c.work_title}${c.hadith_num ? " #" + c.hadith_num : ""}`
                ).join("\n")}`} />
            </div>
            <div className="arabic-text whitespace-pre-wrap">{res.answer}</div>
          </div>

          {res.sql && (
            <details className="bg-deep-teal text-islamic-light rounded-xl p-4 text-xs">
              <summary className="cursor-pointer text-islamic-gold">SQL</summary>
              <pre className="mt-2 whitespace-pre-wrap" dir="ltr">{res.sql}</pre>
              <pre className="mt-2 whitespace-pre-wrap max-h-48 overflow-y-auto" dir="ltr">
                {JSON.stringify(res.rows?.slice(0, 20), null, 1)}
              </pre>
            </details>
          )}
          {res.cypher && (
            <details className="bg-deep-teal text-islamic-light rounded-xl p-4 text-xs">
              <summary className="cursor-pointer text-islamic-gold">Cypher</summary>
              <pre className="mt-2 whitespace-pre-wrap" dir="ltr">{res.cypher}</pre>
            </details>
          )}

          {res.citations?.length > 0 && (
            <section>
              <h3 className="font-bold text-deep-teal mb-2">{t("ask_sources")}</h3>
              <div className="space-y-2">
                {res.citations.map((c: any, i: number) => (
                  <Link key={c.passage_id} to={`/passage/${c.passage_id}`}
                    className="block bg-white rounded-lg p-3 shadow border-s-4 border-islamic-teal hover:shadow-md">
                    <div className="text-xs text-islamic-teal font-bold mb-1">
                      [{i + 1}] {c.work_title}
                      {c.hadith_num && ` — ${t("hadith_no")} ${c.hadith_num}`}
                    </div>
                    <p className="arabic-text text-sm line-clamp-2"
                      dangerouslySetInnerHTML={{ __html: c.snippet }} />
                  </Link>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
