import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, isLoggedIn } from "../api";
import AdminTabs from "../components/AdminTabs";

export default function AdminTranslations() {
  const nav = useNavigate();
  const [rows, setRows] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [mode, setMode] = useState<"skip" | "overwrite">("skip");
  const [limit, setLimit] = useState<string>("100");
  const [error, setError] = useState("");
  const pollRef = useRef<number | null>(null);

  async function load() {
    try {
      const r: any = await api("/admin/translations/coverage?lang=en");
      setRows(r.editions);
      setJobs(r.jobs);
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
    }, 4000);
  }

  async function run() {
    setError("");
    try {
      await api("/admin/translations/jobs", {
        method: "POST",
        body: JSON.stringify({
          edition_ids: [...selected], mode, lang: "en",
          limit: limit ? parseInt(limit, 10) : null,
        }),
      });
      setSelected(new Set());
      await load();
      startPolling();
    } catch (e: any) {
      setError(e.message);
    }
  }

  function toggle(id: number) {
    const s = new Set(selected);
    s.has(id) ? s.delete(id) : s.add(id);
    setSelected(s);
  }

  const running = jobs.find((j) => j.status === "running");

  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Translation Management — English</h1>
      <AdminTabs />
      {error && <div className="bg-red-50 text-red-600 rounded-lg p-3 mb-4 text-sm">{error}</div>}

      <div className="flex items-center gap-3 mb-4 bg-white rounded-xl shadow p-4 flex-wrap" dir="ltr">
        <span className="text-sm">{selected.size} selected</span>
        <select value={mode} onChange={(e) => setMode(e.target.value as any)}
          className="border rounded-lg px-3 py-1.5 text-sm">
          <option value="skip">skip existing</option>
          <option value="overwrite">overwrite</option>
        </select>
        <label className="text-sm flex items-center gap-1">
          limit <input value={limit} onChange={(e) => setLimit(e.target.value.replace(/\D/g, ""))}
            className="border rounded-lg px-2 py-1 w-20 text-sm" placeholder="all" />
        </label>
        <button onClick={run} disabled={selected.size === 0 || !!running}
          className="bg-islamic-teal text-white rounded-lg px-5 py-1.5 text-sm disabled:opacity-30 hover:bg-deep-teal">
          Run translation job
        </button>
        <span className="text-xs text-gray-400">
          Kalimat.dev first (authenticated) → gemini-2.5-flash fallback
        </span>
      </div>

      {jobs.length > 0 && (
        <div className="bg-deep-teal text-white rounded-xl p-4 mb-4 text-sm space-y-2" dir="ltr">
          {jobs.slice(0, 5).map((j) => (
            <div key={j.job_id} className="flex items-center gap-3 flex-wrap">
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                j.status === "running" ? "bg-orange-accent text-deep-teal" :
                j.status === "done" ? "bg-neon-green text-deep-teal" : "bg-red-400"}`}>
                {j.status}
              </span>
              <span className="font-mono text-xs">{j.job_id}</span>
              <span>[{j.edition_ids.join(", ")}] {j.lang} · {j.mode}</span>
              <span className="text-islamic-gold">{j.done}/{j.total ?? "?"}</span>
              <span className="text-neon-green">kalimat {j.kalimat}</span>
              <span className="text-neon-blue">gemini {j.gemini}</span>
              {j.skipped > 0 && <span className="opacity-70">skip {j.skipped}</span>}
              {j.errors > 0 && <span className="text-red-300">err {j.errors}</span>}
              {j.status === "running" && (
                <button onClick={async () => {
                  await api(`/admin/translations/jobs/${j.job_id}/cancel`, { method: "POST" }).catch(() => {});
                  load();
                }} className="text-xs underline text-red-300">cancel</button>
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
              <th className="p-2 text-right">passages</th>
              <th className="p-2 text-right">translated</th>
              <th className="p-2 text-right">authenticated</th>
              <th className="p-2 text-right">stale</th>
              <th className="p-2 text-right">coverage</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const pct = r.passage_count
                ? Math.min(100, Math.round((r.translated / r.passage_count) * 100)) : 0;
              return (
                <tr key={r.edition_id} className="border-b last:border-0 hover:bg-islamic-teal/5">
                  <td className="p-2 text-center">
                    <input type="checkbox" checked={selected.has(r.edition_id)}
                      onChange={() => toggle(r.edition_id)} />
                  </td>
                  <td className="p-2 font-arabic" dir="rtl">{r.title_ar}</td>
                  <td className="p-2 text-center text-xs">{r.source}</td>
                  <td className="p-2 text-right">{r.passage_count.toLocaleString("en")}</td>
                  <td className="p-2 text-right">{r.translated.toLocaleString("en")}</td>
                  <td className="p-2 text-right text-neon-green font-bold">
                    {r.authenticated.toLocaleString("en")}
                  </td>
                  <td className="p-2 text-right text-orange-accent">
                    {r.stale > 0 ? r.stale.toLocaleString("en") : "—"}
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
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
