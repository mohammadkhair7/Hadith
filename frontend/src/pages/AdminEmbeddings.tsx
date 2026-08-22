import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { api, isLoggedIn } from "../api";
import AdminTabs from "../components/AdminTabs";

type Row = {
  edition_id: number;
  source: string;
  title_ar: string;
  work_kind: string;
  passage_count: number;
  chunks_embedded: number;
  chunks_failed: number;
  passages_embedded: number;
  est_tokens_total: number;
  est_cost_usd: number;
  last_run: string | null;
};

export default function AdminEmbeddings() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [rows, setRows] = useState<Row[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [staged, setStaged] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [mode, setMode] = useState<"skip" | "overwrite">("skip");
  const [error, setError] = useState("");
  const pollRef = useRef<number | null>(null);

  async function load() {
    try {
      const r: any = await api("/admin/embeddings/coverage");
      setRows(r.editions);
      setJobs(r.jobs);
      setStaged(r.staged ?? 0);
      return r.jobs;
    } catch (e: any) {
      setError(e.message);
      return [];
    }
  }

  useEffect(() => {
    if (!isLoggedIn()) { nav("/login"); return; }
    load();
    return () => { if (pollRef.current) window.clearInterval(pollRef.current); };
  }, []);

  function startPolling() {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = window.setInterval(async () => {
      const js = await load();
      if (!js.some((j: any) => j.status === "running") && pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }, 3000);
  }

  async function run() {
    setError("");
    try {
      await api("/admin/embeddings/jobs", {
        method: "POST",
        body: JSON.stringify({ edition_ids: [...selected], mode }),
      });
      setSelected(new Set());
      await load();
      startPolling();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function importStaged() {
    setError("");
    try {
      await api("/admin/embeddings/import-staged", { method: "POST" });
      await load();
      startPolling();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function cancel(jobId: string) {
    await api(`/admin/embeddings/jobs/${jobId}/cancel`, { method: "POST" }).catch(() => {});
    load();
  }

  function toggle(id: number) {
    const s = new Set(selected);
    s.has(id) ? s.delete(id) : s.add(id);
    setSelected(s);
  }

  const running = jobs.find((j) => j.status === "running");

  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Embedding Management</h1>
      <AdminTabs />
      {error && <div className="bg-red-50 text-red-600 rounded-lg p-3 mb-4 text-sm">{error}</div>}

      <div className="flex items-center gap-3 mb-4 bg-white rounded-xl shadow p-4 flex-wrap">
        <span className="text-sm">{selected.size} selected</span>
        <select value={mode} onChange={(e) => setMode(e.target.value as any)}
          className="border rounded-lg px-3 py-1.5 text-sm" dir="ltr">
          <option value="skip">skip existing (default)</option>
          <option value="overwrite">overwrite (re-embed)</option>
        </select>
        <button onClick={run} disabled={selected.size === 0 || !!running}
          className="bg-islamic-teal text-white rounded-lg px-5 py-1.5 text-sm disabled:opacity-30 hover:bg-deep-teal">
          Run embedding job
        </button>
        {staged > 0 && (
          <button onClick={importStaged} disabled={!!running}
            className="bg-islamic-gold text-deep-teal rounded-lg px-5 py-1.5 text-sm font-bold disabled:opacity-30"
            title="vectors staged in Postgres by ops/railway_push_vectors.py — imports them into this environment's Redis (no API cost)">
            Import {staged.toLocaleString("en")} staged vectors
          </button>
        )}
        <span className="text-xs text-gray-400" dir="ltr">
          embedding is <b>per page</b> (each page split into ≤1,500-char chunks), not per word —
          cost estimated at gemini-embedding-001 (768-d) rates, $0.15 / 1M input tokens; never automatic
        </span>
      </div>

      {jobs.length > 0 && (
        <div className="bg-deep-teal text-white rounded-xl p-4 mb-4 text-sm space-y-2" dir="ltr">
          {jobs.slice(0, 5).map((j) => (
            <div key={j.job_id} className="flex items-center gap-3 flex-wrap">
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                j.status === "running" ? "bg-orange-accent text-deep-teal" :
                j.status === "done" ? "bg-neon-green text-deep-teal" : "bg-red-400 text-white"}`}>
                {j.status}
              </span>
              <span className="font-mono text-xs">{j.job_id}</span>
              <span>editions [{j.edition_ids.join(", ")}] · {j.mode}</span>
              <span className="text-islamic-gold">
                {j.done_chunks}/{j.total_chunks ?? "?"} chunks
              </span>
              {j.errors > 0 && <span className="text-red-300">{j.errors} errors</span>}
              {j.error && <span className="text-red-300 text-xs">{j.error}</span>}
              {j.status === "running" && (
                <button onClick={() => cancel(j.job_id)}
                  className="text-xs underline text-red-300">cancel</button>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="bg-white rounded-xl shadow overflow-x-auto">
        <table className="w-full text-sm" dir="ltr">
          <thead className="bg-islamic-teal text-white">
            <tr>
              <th className="p-2"></th>
              <th className="p-2 text-left">book</th>
              <th className="p-2">source</th>
              <th className="p-2">kind</th>
              <th className="p-2 text-right"
                title="rows embedded per book: printed pages for Shamela books, hadith units for aljam3 books">
                pages</th>
              <th className="p-2 text-right">embedded</th>
              <th className="p-2 text-right">coverage</th>
              <th className="p-2 text-right">est. tokens</th>
              <th className="p-2 text-right">est. cost</th>
              <th className="p-2">last run</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const pct = r.passage_count
                ? Math.min(100, Math.round((r.passages_embedded / r.passage_count) * 100)) : 0;
              return (
                <tr key={r.edition_id} className="border-b last:border-0 hover:bg-islamic-teal/5">
                  <td className="p-2 text-center">
                    <input type="checkbox" checked={selected.has(r.edition_id)}
                      onChange={() => toggle(r.edition_id)} />
                  </td>
                  <td className="p-2 font-arabic" dir="rtl">{r.title_ar}</td>
                  <td className="p-2 text-center text-xs">{r.source}</td>
                  <td className="p-2 text-center text-xs">{r.work_kind}</td>
                  <td className="p-2 text-right">{r.passage_count.toLocaleString("en")}</td>
                  <td className="p-2 text-right">
                    {r.passages_embedded.toLocaleString("en")}
                    {r.chunks_failed > 0 && <span className="text-red-500 text-xs"> +{r.chunks_failed}✕</span>}
                  </td>
                  <td className="p-2 text-right">
                    <div className="flex items-center gap-2 justify-end">
                      <div className="w-20 h-2 bg-gray-200 rounded-full overflow-hidden">
                        <div className={`h-full ${pct === 100 ? "bg-neon-green" : "bg-islamic-gold"}`}
                          style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-xs w-8">{pct}%</span>
                    </div>
                  </td>
                  <td className="p-2 text-right text-xs text-gray-500">
                    {r.est_tokens_total.toLocaleString("en")}
                  </td>
                  <td className="p-2 text-right text-xs text-gray-500"
                    title="gemini-embedding-001 (768-d), $0.15 / 1M input tokens">
                    ${(r.est_cost_usd ?? 0).toFixed(2)}
                  </td>
                  <td className="p-2 text-xs text-gray-400">
                    {r.last_run ? new Date(r.last_run).toLocaleString("en-GB") : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
