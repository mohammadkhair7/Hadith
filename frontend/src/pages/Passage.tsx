import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, isLoggedIn } from "../api";
import DisplayToggles from "../components/DisplayToggles";
import ExportBar from "../components/ExportBar";
import HadithText, { GradeBadge } from "../components/HadithText";
import IsnadChain from "../components/IsnadChain";
import { matnStart, stripTashkeel, useDisplayPrefs } from "../text";

export default function Passage() {
  const { t, i18n } = useTranslation();
  const { passageId } = useParams();
  const nav = useNavigate();
  const [p, setP] = useState<any>(null);
  const [others, setOthers] = useState<any[]>([]);
  const [isnad, setIsnad] = useState<any[]>([]);
  const [saved, setSaved] = useState(false);
  const prefs = useDisplayPrefs();

  useEffect(() => {
    const lang = i18n.language !== "ar" ? `?lang=${i18n.language}` : "";
    api(`/passages/${passageId}${lang}`).then(setP).catch(console.error);
    api(`/passages/${passageId}/same-work`).then(setOthers).catch(() => {});
    api(`/passages/${passageId}/isnad`).then(setIsnad).catch(() => {});
    setSaved(false);
  }, [passageId, i18n.language]);

  async function favourite() {
    await api("/me/items", {
      method: "POST",
      body: JSON.stringify({ kind: "favourite", ref: { passage_id: Number(passageId) } }),
    });
    setSaved(true);
  }

  if (!p) return <div className="text-center py-16 text-gray-400">{t("loading")}</div>;

  const boundary = p.sanad_end_raw > 0 ? p.sanad_end_raw : matnStart(p.text_raw || "");

  return (
    <div className="max-w-4xl mx-auto">
      {p.breadcrumbs?.length > 0 && (
        <nav className="text-xs text-islamic-teal mb-3 flex flex-wrap gap-1 items-center">
          <Link to={`/read/${p.edition_id}`} className="font-bold hover:underline">{p.work_title}</Link>
          {p.breadcrumbs.map((b: any) => (
            <span key={b.toc_node_id}>‹ <span className="font-arabic">{b.title}</span></span>
          ))}
        </nav>
      )}

      <article className="bg-white rounded-xl shadow-lg p-6 border-t-4 border-islamic-gold">
        <div className="flex items-center gap-2 flex-wrap text-xs mb-4">
          {p.hadith_num && (
            <span className="bg-islamic-gold text-deep-teal font-bold rounded-full px-3 py-1">
              {t("hadith_no")} {p.hadith_num}
            </span>
          )}
          <span className="bg-islamic-teal/10 text-islamic-teal rounded-full px-3 py-1">
            {t(`source_${p.source}`)} — {p.edition_title}
          </span>
          {p.part && (
            <span className="bg-deep-teal/10 rounded-full px-3 py-1">
              {t("part_page")}: {p.part}/{p.page}
            </span>
          )}
          <GradeBadge grade={p.grade} />
          <DisplayToggles prefs={prefs} canMatn={boundary > 0} />
          <ExportBar title={`${p.work_title || ""} ${p.hadith_num ? "حديث " + p.hadith_num : ""}`}
            text={() => p.text_raw || ""}
            html={() => `<div style="white-space:pre-wrap">${(p.text_raw || "").replace(/</g, "&lt;")}</div>`} />
          {isLoggedIn() && (
            <button onClick={favourite} disabled={saved}
              className="text-orange-accent hover:scale-110 transition-transform">
              {saved ? "★" : "☆"} {t("add_favourite")}
            </button>
          )}
        </div>

        {boundary > 0 || p.kind === "unit" ? (
          <HadithText raw={p.text_raw || ""} sanadEndRaw={boundary} prefs={prefs} />
        ) : p.html && p.source !== "shamela" ? (
          <div className="arabic-text legacy-content"
            dangerouslySetInnerHTML={{ __html: prefs.tashkeel ? p.html : stripTashkeel(p.html) }} />
        ) : (
          <HadithText raw={p.text_raw || ""} prefs={prefs} />
        )}

        {p.translation && (
          <div className="mt-4 pt-4 border-t text-base leading-relaxed" dir="ltr">
            <div className="text-xs text-gray-400 mb-1">
              {p.translation.source} · {p.translation.status}
            </div>
            {p.translation.text}
          </div>
        )}
      </article>

      <div className="flex justify-between mt-4">
        {p.prev ? (
          <button onClick={() => nav(`/read/${p.edition_id}?seq=${p.prev.seq}`)}
            className="px-5 py-2 rounded-lg bg-islamic-teal text-white">{t("prev")}</button>
        ) : <span />}
        {p.next ? (
          <button onClick={() => nav(`/read/${p.edition_id}?seq=${p.next.seq}`)}
            className="px-5 py-2 rounded-lg bg-islamic-teal text-white">{t("next")}</button>
        ) : <span />}
      </div>

      {isnad.length > 0 && <IsnadChain chain={isnad[0]} />}

      {isnad.length > 0 && <Mutabaat passageId={passageId!} />}

      {p.subjects?.length > 0 && (
        <section className="mt-6">
          <h3 className="font-bold text-deep-teal mb-2">{t("related_subjects")}</h3>
          <div className="flex flex-wrap gap-2">
            {p.subjects.map((s: any) => (
              <Link key={s.subject_id} to={`/subjects?open=${s.subject_id}`}
                className="text-xs bg-islamic-teal/10 text-islamic-teal rounded-full px-3 py-1 hover:bg-islamic-teal hover:text-white transition-colors font-arabic">
                {s.title}
              </Link>
            ))}
          </div>
        </section>
      )}

      {others.length > 0 && (
        <section className="mt-6">
          <h3 className="font-bold text-deep-teal mb-2">{t("compare_editions")}</h3>
          <div className="flex flex-wrap gap-2">
            {others.map((e: any) => (
              <Link key={e.edition_id} to={`/read/${e.edition_id}`}
                className="text-xs bg-orange-accent/10 text-orange-accent rounded-full px-3 py-1 hover:bg-orange-accent hover:text-white transition-colors">
                {t(`source_${e.source}`)}: {e.title_ar}
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

/** Corroborating transmissions: hadiths sharing student→teacher pairs. */
function Mutabaat({ passageId }: { passageId: string }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    setRows([]);
    api(`/analytics/passages/${passageId}/mutabaat`).then(setRows).catch(() => {});
  }, [passageId]);
  if (!rows.length) return null;
  return (
    <section className="mt-6">
      <h3 className="font-bold text-deep-teal mb-2">{t("mutabaat_title")}</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        {rows.map((r) => (
          <Link key={r.passage_id} to={`/passage/${r.passage_id}`}
            className="block bg-white rounded-lg shadow-sm p-3 text-xs hover:shadow border-s-2 border-islamic-teal">
            <div className="flex justify-between mb-1">
              <span className="font-bold text-islamic-teal font-arabic">{r.work_title}</span>
              <span className="text-islamic-gold font-bold">
                {r.shared_pairs} {t("mutabaat_shared")}
              </span>
            </div>
            <span className="font-arabic text-gray-600">{r.preview}…</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
