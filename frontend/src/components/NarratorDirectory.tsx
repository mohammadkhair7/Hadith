import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";

type Row = {
  narrator_id: number; canonical_ar: string; generation?: string | null;
  death_year_h?: number | null; rijal_grade?: string | null;
  tabaqa_label?: string | null; places?: string[] | null;
  mentions: number; chains: number; books: number;
};
type Facets = {
  generations: { generation: string; n: number }[];
  grades: { grade: string; n: number }[];
  places: { place: string; n: number }[];
  books: { edition_id: number; title_ar: string }[];
};

const PAGE = 25;
const EMPTY = {
  q_name: "", narrator_id: "", generation: "", grade: "", place: "",
  death_from: "", death_to: "", teacher: "", student: "",
  edition_id: "", topic: "", min_mentions: "",
};

/** Research panel under the narrator graph: list / filter / sort / search
 *  narrators on multiple criteria. onOpen loads a narrator into the graph. */
export default function NarratorDirectory({ onOpen }: { onOpen: (id: number) => void }) {
  const { t } = useTranslation();
  const [f, setF] = useState({ ...EMPTY });
  const [sort, setSort] = useState("mentions");
  const [facets, setFacets] = useState<Facets | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/narrators/directory/facets").then(setFacets).catch(() => {});
  }, []);

  async function load(p = 0, s = sort) {
    setLoading(true);
    setError("");
    const qp = new URLSearchParams({ sort: s, limit: String(PAGE), offset: String(p * PAGE) });
    Object.entries(f).forEach(([k, v]) => { if (String(v).trim()) qp.set(k, String(v).trim()); });
    try {
      const d: any = await api(`/narrators/directory?${qp}`);
      setRows(d.items);
      setTotal(d.total);
      setPage(p);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(0); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  const inp = "border border-islamic-teal/40 rounded-lg px-2 py-1.5 text-sm font-arabic outline-none focus:border-islamic-teal w-full bg-white";
  const pages = total !== null ? Math.ceil(total / PAGE) : 0;

  return (
    <section className="mt-6 bg-white rounded-2xl shadow p-5">
      <div className="flex flex-wrap items-baseline gap-3 mb-1">
        <h2 className="text-lg font-bold text-deep-teal">{t("dir_title")}</h2>
        <span className="text-xs text-gray-400">{t("dir_desc")}</span>
      </div>

      <form onSubmit={(e) => { e.preventDefault(); load(0); }}
        className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2 mt-3">
        <input value={f.q_name} onChange={(e) => setF({ ...f, q_name: e.target.value })}
          placeholder={t("dir_f_name")} className={inp + " col-span-2"} />
        <input value={f.narrator_id} type="number" onChange={(e) => setF({ ...f, narrator_id: e.target.value })}
          placeholder={t("dir_f_id")} className={inp} />
        <select value={f.generation} onChange={(e) => setF({ ...f, generation: e.target.value })} className={inp}>
          <option value="">{t("dir_f_generation")}</option>
          {facets?.generations.map((g) => (
            <option key={g.generation} value={g.generation}>{g.generation} ({g.n})</option>
          ))}
        </select>
        <select value={f.grade} onChange={(e) => setF({ ...f, grade: e.target.value })} className={inp}>
          <option value="">{t("dir_f_grade")}</option>
          {facets?.grades.map((g) => (
            <option key={g.grade} value={g.grade}>{g.grade} ({g.n})</option>
          ))}
        </select>
        <select value={f.place} onChange={(e) => setF({ ...f, place: e.target.value })} className={inp}>
          <option value="">{t("dir_f_place")}</option>
          {facets?.places.map((p) => (
            <option key={p.place} value={p.place}>{p.place} ({p.n})</option>
          ))}
        </select>
        <input value={f.death_from} type="number" onChange={(e) => setF({ ...f, death_from: e.target.value })}
          placeholder={t("dir_f_death_from")} className={inp} />
        <input value={f.death_to} type="number" onChange={(e) => setF({ ...f, death_to: e.target.value })}
          placeholder={t("dir_f_death_to")} className={inp} />
        <input value={f.teacher} onChange={(e) => setF({ ...f, teacher: e.target.value })}
          placeholder={t("dir_f_teacher")} className={inp} />
        <input value={f.student} onChange={(e) => setF({ ...f, student: e.target.value })}
          placeholder={t("dir_f_student")} className={inp} />
        <select value={f.edition_id} onChange={(e) => setF({ ...f, edition_id: e.target.value })} className={inp}>
          <option value="">{t("dir_f_book")}</option>
          {facets?.books.map((b) => (
            <option key={b.edition_id} value={b.edition_id}>{b.title_ar}</option>
          ))}
        </select>
        <input value={f.topic} onChange={(e) => setF({ ...f, topic: e.target.value })}
          placeholder={t("dir_f_topic")} className={inp} />
        <input value={f.min_mentions} type="number" onChange={(e) => setF({ ...f, min_mentions: e.target.value })}
          placeholder={t("dir_f_min_mentions")} className={inp} />
        <select value={sort} onChange={(e) => { setSort(e.target.value); load(0, e.target.value); }}
          className={inp}>
          <option value="mentions">{t("dir_s_mentions")}</option>
          <option value="chains">{t("dir_s_chains")}</option>
          <option value="death">{t("dir_s_death")}</option>
          <option value="death_desc">{t("dir_s_death_desc")}</option>
          <option value="name">{t("dir_s_name")}</option>
          <option value="id">{t("dir_s_id")}</option>
        </select>
        <button disabled={loading}
          className="bg-islamic-teal text-white rounded-lg px-4 py-1.5 text-sm font-bold hover:bg-deep-teal disabled:opacity-50">
          {loading ? "…" : t("dir_apply")}
        </button>
        <button type="button" onClick={() => { setF({ ...EMPTY }); }}
          className="bg-gray-100 text-gray-600 rounded-lg px-4 py-1.5 text-sm hover:bg-gray-200">
          {t("dir_reset")}
        </button>
      </form>

      {error && <div className="text-red-500 text-sm mt-3">{error}</div>}

      {total !== null && (
        <div className="mt-4">
          <div className="text-xs text-gray-500 mb-2">
            {t("dir_total", { n: total.toLocaleString("en") })}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[760px]">
              <thead>
                <tr className="bg-islamic-teal text-white text-xs">
                  <th className="p-2 text-start rounded-s-lg">#</th>
                  <th className="p-2 text-start">{t("dir_c_name")}</th>
                  <th className="p-2 text-start">{t("dir_c_generation")}</th>
                  <th className="p-2 text-start">{t("dir_c_grade")}</th>
                  <th className="p-2 text-center">{t("dir_c_death")}</th>
                  <th className="p-2 text-start">{t("dir_c_places")}</th>
                  <th className="p-2 text-center">{t("dir_c_mentions")}</th>
                  <th className="p-2 text-center">{t("dir_c_chains")}</th>
                  <th className="p-2 text-center rounded-e-lg">{t("dir_c_books")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.narrator_id}
                    onClick={() => { onOpen(r.narrator_id); window.scrollTo({ top: 0, behavior: "smooth" }); }}
                    className="border-b last:border-0 hover:bg-islamic-teal/5 cursor-pointer">
                    <td className="p-2 text-xs text-gray-400">{r.narrator_id}</td>
                    <td className="p-2 font-arabic font-bold text-deep-teal">{r.canonical_ar}</td>
                    <td className="p-2 font-arabic text-xs">{r.tabaqa_label || r.generation || "—"}</td>
                    <td className="p-2 font-arabic text-xs text-emerald-700">{r.rijal_grade || "—"}</td>
                    <td className="p-2 text-center text-xs">{r.death_year_h ? `${r.death_year_h} هـ` : "—"}</td>
                    <td className="p-2 font-arabic text-xs">{(r.places || []).slice(0, 3).join("، ") || "—"}</td>
                    <td className="p-2 text-center">{r.mentions.toLocaleString("en")}</td>
                    <td className="p-2 text-center">{r.chains.toLocaleString("en")}</td>
                    <td className="p-2 text-center">{r.books}</td>
                  </tr>
                ))}
                {rows.length === 0 && !loading && (
                  <tr><td colSpan={9} className="p-6 text-center text-gray-400">{t("dir_empty")}</td></tr>
                )}
              </tbody>
            </table>
          </div>
          {pages > 1 && (
            <div className="flex items-center justify-center gap-3 mt-3 text-sm">
              <button disabled={page === 0 || loading} onClick={() => load(page - 1)}
                className="px-3 py-1 rounded-lg bg-islamic-light disabled:opacity-40">‹</button>
              <span className="text-xs text-gray-500">{page + 1} / {pages}</span>
              <button disabled={page + 1 >= pages || loading} onClick={() => load(page + 1)}
                className="px-3 py-1 rounded-lg bg-islamic-light disabled:opacity-40">›</button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
