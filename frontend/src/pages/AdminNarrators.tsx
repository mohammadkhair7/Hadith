import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { api, isLoggedIn } from "../api";
import AdminTabs from "../components/AdminTabs";

type Hit = { narrator_id: number; canonical_ar: string; generation?: string | null;
  death_year_h?: number | null; mentions: number };

/** Search box + result dropdown; calls onPick with the chosen narrator. */
function NarratorPicker({ label, onPick }: { label: string; onPick: (n: Hit) => void }) {
  const { t } = useTranslation();
  const [qs, setQs] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  async function search() {
    if (!qs.trim()) return;
    setHits(await api(`/narrators?search=${encodeURIComponent(qs.trim())}&limit=30`));
  }
  return (
    <div className="relative">
      <label className="text-xs font-bold text-deep-teal">{label}</label>
      <div className="flex gap-1 mt-1">
        <input value={qs} onChange={(e) => setQs(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); search(); } }}
          placeholder={t("narrators_search")}
          className="flex-1 border border-islamic-teal/50 rounded-lg px-3 py-1.5 text-sm font-arabic outline-none focus:border-islamic-teal" />
        <button type="button" onClick={search}
          className="bg-islamic-teal text-white rounded-lg px-3 text-sm">{t("nav_search")}</button>
      </div>
      {hits.length > 0 && (
        <div className="absolute z-20 mt-1 w-full bg-white border rounded-lg shadow-lg max-h-56 overflow-y-auto">
          {hits.map((h) => (
            <button key={h.narrator_id} type="button"
              onClick={() => { onPick(h); setHits([]); setQs(""); }}
              className="w-full text-start px-3 py-1.5 text-sm font-arabic hover:bg-islamic-teal/10 flex justify-between gap-2">
              <span>{h.canonical_ar}
                <span className="text-gray-400 text-xs"> #{h.narrator_id}</span></span>
              <span className="text-xs text-gray-400 shrink-0">{h.mentions} ↺</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Msg({ msg }: { msg: { ok: boolean; text: string } | null }) {
  if (!msg) return null;
  return (
    <div className={`text-sm rounded-lg px-3 py-2 mt-3 ${
      msg.ok ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>
      {msg.text}
    </div>
  );
}

export default function AdminNarrators() {
  const { t } = useTranslation();
  const nav = useNavigate();
  useEffect(() => { if (!isLoggedIn()) nav("/login"); }, []);

  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">{t("admin_narrators_title")}</h1>
      <AdminTabs />
      <div className="grid lg:grid-cols-2 gap-6">
        <MergePanel />
        <div className="space-y-6">
          <CreatePanel />
          <DeletePanel />
        </div>
      </div>
      <RelationsPanel />
      <AuditPanel />
    </div>
  );
}

// --- merge duplicate nodes ---------------------------------------------------

function MergePanel() {
  const { t } = useTranslation();
  const [sel, setSel] = useState<Hit[]>([]);
  const [target, setTarget] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  function add(h: Hit) {
    setMsg(null);
    setSel((prev) => (prev.some((x) => x.narrator_id === h.narrator_id) ? prev : [...prev, h]));
    setTarget((prev) => prev ?? h.narrator_id);
  }
  function remove(id: number) {
    setSel((prev) => prev.filter((x) => x.narrator_id !== id));
    setTarget((prev) => (prev === id ? null : prev));
    setConfirming(false);
  }

  async function doMerge() {
    if (!target || sel.length < 2) return;
    setBusy(true);
    setMsg(null);
    try {
      const r: any = await api("/admin/narrators/merge", {
        method: "POST",
        body: JSON.stringify({
          target_id: target,
          source_ids: sel.filter((x) => x.narrator_id !== target).map((x) => x.narrator_id),
        }),
      });
      setMsg({ ok: true, text: t("admin_merge_done", { n: r.merged, links: r.links_repointed }) });
      setSel([]);
      setTarget(null);
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <section className="bg-white rounded-2xl shadow p-5">
      <h2 className="font-bold text-deep-teal mb-1">{t("admin_merge_title")}</h2>
      <p className="text-xs text-gray-500 mb-3">{t("admin_merge_desc")}</p>
      <NarratorPicker label={t("admin_merge_add")} onPick={add} />
      {sel.length > 0 && (
        <div className="mt-3 space-y-1">
          <div className="text-xs font-bold text-deep-teal">{t("admin_merge_target_hint")}</div>
          {sel.map((h) => (
            <div key={h.narrator_id}
              className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm ${
                target === h.narrator_id ? "bg-islamic-gold/15 ring-1 ring-islamic-gold" : "bg-islamic-light"}`}>
              <input type="radio" name="merge-target" checked={target === h.narrator_id}
                onChange={() => setTarget(h.narrator_id)} />
              <span className="font-arabic flex-1">{h.canonical_ar}
                <span className="text-gray-400 text-xs"> #{h.narrator_id} · {h.mentions} ↺</span></span>
              {target === h.narrator_id && (
                <span className="text-[10px] font-bold text-islamic-gold">{t("admin_merge_target")}</span>
              )}
              <button onClick={() => remove(h.narrator_id)}
                className="text-gray-400 hover:text-red-500 px-1">✕</button>
            </div>
          ))}
        </div>
      )}
      {sel.length >= 2 && target && !confirming && (
        <button onClick={() => setConfirming(true)}
          className="mt-4 bg-islamic-teal text-white rounded-lg px-5 py-2 text-sm font-bold hover:bg-deep-teal">
          {t("admin_merge_btn", { n: sel.length })}
        </button>
      )}
      {confirming && (
        <div className="mt-4 bg-amber-50 border border-amber-300 rounded-lg p-3 text-sm">
          <div className="font-bold text-amber-800 mb-2">⚠ {t("admin_merge_confirm", {
            names: sel.filter((x) => x.narrator_id !== target).map((x) => x.canonical_ar).join("، "),
            target: sel.find((x) => x.narrator_id === target)?.canonical_ar,
          })}</div>
          <div className="flex gap-2">
            <button onClick={doMerge} disabled={busy}
              className="bg-amber-600 text-white rounded-lg px-4 py-1.5 text-sm font-bold disabled:opacity-50">
              {busy ? "…" : t("confirm")}
            </button>
            <button onClick={() => setConfirming(false)}
              className="bg-gray-200 rounded-lg px-4 py-1.5 text-sm">{t("cancel")}</button>
          </div>
        </div>
      )}
      <Msg msg={msg} />
    </section>
  );
}

// --- create a narrator --------------------------------------------------------

function CreatePanel() {
  const { t } = useTranslation();
  const [f, setF] = useState({ canonical_ar: "", kunya: "", laqab: "", generation: "",
    death_year_h: "", bio_summary: "" });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const r: any = await api("/admin/narrators", {
        method: "POST",
        body: JSON.stringify({
          canonical_ar: f.canonical_ar,
          kunya: f.kunya || null, laqab: f.laqab || null,
          generation: f.generation || null,
          death_year_h: f.death_year_h ? parseInt(f.death_year_h, 10) : null,
          bio_summary: f.bio_summary || null,
        }),
      });
      setMsg({ ok: true, text: t("admin_create_done", { id: r.narrator_id }) });
      setF({ canonical_ar: "", kunya: "", laqab: "", generation: "", death_year_h: "", bio_summary: "" });
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    } finally { setBusy(false); }
  }

  const inp = "border border-islamic-teal/40 rounded-lg px-3 py-1.5 text-sm font-arabic outline-none focus:border-islamic-teal w-full";
  return (
    <section className="bg-white rounded-2xl shadow p-5">
      <h2 className="font-bold text-deep-teal mb-3">{t("admin_create_title")}</h2>
      <form onSubmit={submit} className="grid grid-cols-2 gap-2 text-sm">
        <input required value={f.canonical_ar} placeholder={t("admin_create_name")}
          onChange={(e) => setF({ ...f, canonical_ar: e.target.value })}
          className={inp + " col-span-2"} />
        <input value={f.kunya} placeholder={t("admin_create_kunya")}
          onChange={(e) => setF({ ...f, kunya: e.target.value })} className={inp} />
        <input value={f.laqab} placeholder={t("admin_create_laqab")}
          onChange={(e) => setF({ ...f, laqab: e.target.value })} className={inp} />
        <select value={f.generation} onChange={(e) => setF({ ...f, generation: e.target.value })}
          className={inp}>
          <option value="">{t("admin_create_generation")}</option>
          <option value="صحابي">صحابي</option>
          <option value="تابعي">تابعي</option>
          <option value="من أتباع التابعين">من أتباع التابعين</option>
          <option value="من تبع الأتباع">من تبع الأتباع</option>
        </select>
        <input value={f.death_year_h} type="number" placeholder={t("admin_create_death")}
          onChange={(e) => setF({ ...f, death_year_h: e.target.value })} className={inp} />
        <textarea value={f.bio_summary} placeholder={t("admin_create_bio")} rows={2}
          onChange={(e) => setF({ ...f, bio_summary: e.target.value })}
          className={inp + " col-span-2"} />
        <button disabled={busy}
          className="col-span-2 bg-islamic-teal text-white rounded-lg py-2 font-bold hover:bg-deep-teal disabled:opacity-50">
          {busy ? "…" : t("admin_create_btn")}
        </button>
      </form>
      <Msg msg={msg} />
    </section>
  );
}

// --- delete a narrator ----------------------------------------------------------

function DeletePanel() {
  const { t } = useTranslation();
  const [victim, setVictim] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function pick(h: Hit) {
    setMsg(null);
    setVictim(await api(`/narrators/${h.narrator_id}`));
  }

  async function doDelete() {
    if (!victim) return;
    setBusy(true);
    setMsg(null);
    try {
      const r: any = await api(`/admin/narrators/${victim.narrator_id}`, { method: "DELETE" });
      setMsg({ ok: true, text: t("admin_delete_done", { name: r.canonical_ar, links: r.links_unresolved }) });
      setVictim(null);
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    } finally { setBusy(false); }
  }

  return (
    <section className="bg-white rounded-2xl shadow p-5">
      <h2 className="font-bold text-deep-teal mb-3">{t("admin_delete_title")}</h2>
      <NarratorPicker label={t("admin_delete_pick")} onPick={pick} />
      {victim && (
        <div className="mt-3 bg-red-50 border border-red-300 rounded-lg p-3 text-sm">
          <div className="font-bold text-red-700 mb-1">⚠ {t("admin_delete_warn", {
            name: victim.canonical_ar, mentions: victim.mentions, chains: victim.chains })}</div>
          <div className="text-xs text-red-600 mb-2">{t("admin_delete_note")}</div>
          <div className="flex gap-2">
            <button onClick={doDelete} disabled={busy}
              className="bg-red-600 text-white rounded-lg px-4 py-1.5 text-sm font-bold disabled:opacity-50">
              {busy ? "…" : t("admin_delete_btn")}
            </button>
            <button onClick={() => setVictim(null)}
              className="bg-gray-200 rounded-lg px-4 py-1.5 text-sm">{t("cancel")}</button>
          </div>
        </div>
      )}
      <Msg msg={msg} />
    </section>
  );
}

// --- relationship overrides -------------------------------------------------------

function RelationsPanel() {
  const { t } = useTranslation();
  const [student, setStudent] = useState<Hit | null>(null);
  const [teacher, setTeacher] = useState<Hit | null>(null);
  const [action, setAction] = useState<"add" | "remove">("add");
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [list, setList] = useState<any[]>([]);

  async function refresh() {
    setList(await api("/admin/narrators/relations"));
  }
  useEffect(() => { refresh().catch(() => {}); }, []);

  async function submit() {
    if (!student || !teacher) return;
    setBusy(true);
    setMsg(null);
    try {
      await api("/admin/narrators/relations", {
        method: "POST",
        body: JSON.stringify({
          student_id: student.narrator_id, teacher_id: teacher.narrator_id,
          action, note: note || null,
        }),
      });
      setMsg({ ok: true, text: t("admin_rel_done") });
      setStudent(null); setTeacher(null); setNote("");
      refresh();
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    } finally { setBusy(false); setConfirming(false); }
  }

  async function undo(edgeId: number) {
    await api(`/admin/narrators/relations/${edgeId}`, { method: "DELETE" });
    refresh();
  }

  return (
    <section className="bg-white rounded-2xl shadow p-5 mt-6">
      <h2 className="font-bold text-deep-teal mb-1">{t("admin_rel_title")}</h2>
      <p className="text-xs text-gray-500 mb-3">{t("admin_rel_desc")}</p>
      <div className="grid md:grid-cols-2 gap-3">
        <div>
          <NarratorPicker label={t("admin_rel_student")} onPick={(h) => { setStudent(h); setMsg(null); }} />
          {student && <div className="mt-1 text-sm font-arabic bg-islamic-light rounded px-2 py-1">
            {student.canonical_ar} <span className="text-xs text-gray-400">#{student.narrator_id}</span>
            <button onClick={() => setStudent(null)} className="text-gray-400 hover:text-red-500 float-end">✕</button>
          </div>}
        </div>
        <div>
          <NarratorPicker label={t("admin_rel_teacher")} onPick={(h) => { setTeacher(h); setMsg(null); }} />
          {teacher && <div className="mt-1 text-sm font-arabic bg-islamic-light rounded px-2 py-1">
            {teacher.canonical_ar} <span className="text-xs text-gray-400">#{teacher.narrator_id}</span>
            <button onClick={() => setTeacher(null)} className="text-gray-400 hover:text-red-500 float-end">✕</button>
          </div>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 mt-3 text-sm">
        <label className="flex items-center gap-1">
          <input type="radio" checked={action === "add"} onChange={() => setAction("add")} />
          {t("admin_rel_add")}
        </label>
        <label className="flex items-center gap-1">
          <input type="radio" checked={action === "remove"} onChange={() => setAction("remove")} />
          {t("admin_rel_remove")}
        </label>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("admin_rel_note")}
          className="flex-1 min-w-40 border border-islamic-teal/40 rounded-lg px-3 py-1.5 font-arabic outline-none" />
        {!confirming ? (
          <button disabled={!student || !teacher}
            onClick={() => (action === "remove" ? setConfirming(true) : submit())}
            className="bg-islamic-teal text-white rounded-lg px-4 py-1.5 font-bold disabled:opacity-40">
            {busy ? "…" : t("admin_rel_btn")}
          </button>
        ) : (
          <span className="flex items-center gap-2 bg-amber-50 border border-amber-300 rounded-lg px-3 py-1.5">
            <span className="text-amber-800 text-xs font-bold">⚠ {t("admin_rel_remove_warn")}</span>
            <button onClick={submit} disabled={busy}
              className="bg-amber-600 text-white rounded px-3 py-1 text-xs font-bold">{t("confirm")}</button>
            <button onClick={() => setConfirming(false)}
              className="bg-gray-200 rounded px-3 py-1 text-xs">{t("cancel")}</button>
          </span>
        )}
      </div>
      <Msg msg={msg} />
      {list.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-bold text-deep-teal mb-2">{t("admin_rel_list")}</h3>
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {list.map((r) => (
              <div key={r.edge_id} className="flex items-center gap-2 text-sm bg-islamic-light rounded-lg px-3 py-1.5">
                <span className={`text-xs font-bold rounded-full px-2 py-0.5 ${
                  r.action === "add" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-600"}`}>
                  {r.action === "add" ? t("admin_rel_add") : t("admin_rel_remove")}
                </span>
                <span className="font-arabic flex-1">
                  {r.student_name} <span className="text-xs text-gray-400">{t("narrated_from")}</span> {r.teacher_name}
                  {r.note && <span className="text-xs text-gray-400"> — {r.note}</span>}
                </span>
                <button onClick={() => undo(r.edge_id)} title={t("admin_rel_undo")}
                  className="text-xs text-gray-400 hover:text-red-500">{t("admin_rel_undo")}</button>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

// --- audit trail ------------------------------------------------------------------

function AuditPanel() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    api("/admin/narrators/audit?limit=30").then(setRows).catch(() => {});
  }, []);
  if (rows.length === 0) return null;
  return (
    <section className="bg-white rounded-2xl shadow p-5 mt-6">
      <h2 className="font-bold text-deep-teal mb-3">{t("admin_audit_title")}</h2>
      <div className="space-y-1 max-h-64 overflow-y-auto text-xs font-mono" dir="ltr">
        {rows.map((r) => (
          <div key={r.audit_id} className="flex gap-2">
            <span className="text-gray-400 shrink-0">{String(r.created_at).slice(0, 16)}</span>
            <span className="text-islamic-teal font-bold shrink-0">{r.action}</span>
            <span className="font-arabic truncate">{JSON.stringify(r.payload)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
