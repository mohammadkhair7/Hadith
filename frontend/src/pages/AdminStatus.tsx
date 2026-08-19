import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { api, isLoggedIn } from "../api";

export default function AdminStatus() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [s, setS] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isLoggedIn()) { nav("/login"); return; }
    api("/admin/status").then(setS).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="text-center py-16 text-red-500">{error}</div>;
  if (!s) return <div className="text-center py-16 text-gray-400">{t("loading")}</div>;

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center gap-4 mb-6">
        <h1 className="text-2xl font-bold">{t("admin_status")}</h1>
        <Link to="/admin/embeddings"
          className="text-sm bg-islamic-gold text-deep-teal rounded-lg px-4 py-1.5 font-bold hover:bg-orange-accent transition-colors">
          Embedding Management
        </Link>
        <Link to="/admin/translations"
          className="text-sm bg-islamic-teal text-white rounded-lg px-4 py-1.5 font-bold hover:bg-deep-teal transition-colors">
          Translation Management
        </Link>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        {Object.entries(s.counts || {}).map(([k, v]: any) => (
          <div key={k} className="bg-deep-teal text-white rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-islamic-gold">{Number(v).toLocaleString("en")}</div>
            <div className="text-xs opacity-80" dir="ltr">{k}</div>
          </div>
        ))}
      </div>

      <section className="mb-8">
        <h2 className="font-bold text-deep-teal mb-3">by source</h2>
        <div className="bg-white rounded-xl shadow overflow-hidden">
          <table className="w-full text-sm" dir="ltr">
            <thead className="bg-islamic-teal text-white">
              <tr><th className="p-2 text-left">source</th><th className="p-2 text-right">editions</th><th className="p-2 text-right">passages</th></tr>
            </thead>
            <tbody>
              {(s.by_source || []).map((r: any) => (
                <tr key={r.source} className="border-b last:border-0">
                  <td className="p-2">{r.source}</td>
                  <td className="p-2 text-right">{Number(r.editions).toLocaleString("en")}</td>
                  <td className="p-2 text-right">{Number(r.passages).toLocaleString("en")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mb-8">
        <h2 className="font-bold text-deep-teal mb-3">ETL</h2>
        <div className="bg-white rounded-xl shadow p-4 text-xs font-mono space-y-1 max-h-64 overflow-y-auto" dir="ltr">
          {(s.etl_recent || []).map((r: any, i: number) => (
            <div key={i}>
              <span className="text-islamic-teal">{r.step}</span> — {r.status} — {r.updated_at}
            </div>
          ))}
        </div>
      </section>

      <div className="text-sm text-gray-500" dir="ltr">
        DB size: {s.db_size} · embeddings: {JSON.stringify(s.embeddings)}
      </div>
    </div>
  );
}
