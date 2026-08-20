import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../api";
import ExportBar from "../components/ExportBar";

const NEON = ["#10b981", "#3b82f6", "#facc15", "#22d3ee", "#ec4899", "#8b5cf6", "#f59e0b", "#ef4444"];
const GRADE_AR: Record<string, string> = {
  sahih: "صحيح", hasan: "حسن", maqbul: "مقبول", daif: "ضعيف", mawdu: "موضوع", other: "أخرى",
};

export default function Analytics() {
  const { t } = useTranslation();
  const [ov, setOv] = useState<any>(null);
  const [grades, setGrades] = useState<any>(null);
  const [narrators, setNarrators] = useState<any[]>([]);
  const [pairs, setPairs] = useState<any[]>([]);
  const [lengths, setLengths] = useState<any[]>([]);
  const [verbs, setVerbs] = useState<any[]>([]);

  useEffect(() => {
    api("/analytics/overview").then(setOv).catch(console.error);
    api("/analytics/grades").then(setGrades).catch(() => {});
    api("/analytics/top-narrators?limit=20").then(setNarrators).catch(() => {});
    api("/analytics/top-pairs?limit=20").then(setPairs).catch(() => {});
    api("/analytics/chain-lengths").then(setLengths).catch(() => {});
    api("/analytics/verbs").then(setVerbs).catch(() => {});
  }, []);

  if (!ov) return <div className="text-center py-16 text-gray-400">{t("loading")}</div>;
  const tt = ov.totals;

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">{t("analytics_title")}</h1>

      {/* stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Card n={tt.units} label={t("an_units")} />
        <Card n={tt.chains} label={t("an_chains")} />
        <Card n={tt.links} label={t("an_links")} />
        <Card n={tt.narrators} label={t("an_narrators")} />
        <Card n={tt.links ? Math.round((tt.links_resolved / tt.links) * 100) : 0}
          label={t("an_resolved")} suffix="%" />
        <Card n={tt.graded} label={t("an_graded")} />
      </div>

      {/* per-book isnad coverage */}
      <Section title={t("an_books_coverage")}
        exp={{
          title: t("an_books_coverage"),
          csv: () => [[t("nav_books"), t("an_units"), t("an_chains"), "%", t("an_matn_marked"), t("an_graded")],
            ...ov.books.map((b: any) => [b.title_ar, b.units, b.chains,
              b.units ? Math.round((b.chains / b.units) * 100) : 0, b.matn_boundaries, b.graded])],
        }}>
        <div className="overflow-x-auto bg-white rounded-xl shadow">
          <table className="w-full text-sm">
            <thead className="bg-deep-teal text-islamic-light">
              <tr>
                <th className="p-2 text-start">{t("nav_books")}</th>
                <th className="p-2">{t("an_units")}</th>
                <th className="p-2">{t("an_chains")}</th>
                <th className="p-2">{t("an_coverage")}</th>
                <th className="p-2">{t("an_matn_marked")}</th>
                <th className="p-2">{t("an_graded")}</th>
              </tr>
            </thead>
            <tbody>
              {ov.books.map((b: any) => {
                const pct = b.units ? Math.round((b.chains / b.units) * 100) : 0;
                return (
                  <tr key={b.edition_id} className="border-b last:border-0 hover:bg-islamic-teal/5 text-center">
                    <td className="p-2 text-start font-arabic">
                      <Link className="hover:text-islamic-teal font-bold" to={`/read/${b.edition_id}`}>
                        {b.title_ar}
                      </Link>
                    </td>
                    <td className="p-2">{b.units.toLocaleString("en")}</td>
                    <td className="p-2">{b.chains.toLocaleString("en")}</td>
                    <td className="p-2">
                      <div className="flex items-center gap-1 justify-center">
                        <div className="w-20 bg-gray-100 rounded-full h-2 overflow-hidden">
                          <div className="h-2 rounded-full bg-islamic-teal" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-xs w-8">{pct}%</span>
                      </div>
                    </td>
                    <td className="p-2">{b.matn_boundaries.toLocaleString("en")}</td>
                    <td className="p-2">{b.graded.toLocaleString("en")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>

      <div className="grid lg:grid-cols-2 gap-8">
        {/* grade distribution */}
        {grades?.distribution?.length > 0 && (
          <Section title={t("an_grades")}
            exp={{
              title: t("an_grades"),
              csv: () => [[t("an_grade"), t("an_count")],
                ...grades.distribution.map((g: any) => [GRADE_AR[g.grade_norm] || g.grade_norm, g.n])],
            }}>
            <BarChart data={grades.distribution.map((g: any) => ({
              label: GRADE_AR[g.grade_norm] || g.grade_norm, value: g.n }))} />
          </Section>
        )}

        {/* transmission verbs */}
        {verbs.length > 0 && (
          <Section title={t("an_verbs")}
            exp={{
              title: t("an_verbs"),
              csv: () => [[t("an_verb"), t("an_count")], ...verbs.map((v: any) => [v.verb, v.n])],
            }}>
            <BarChart data={verbs.slice(0, 8).map((v: any) => ({ label: v.verb, value: v.n }))} />
          </Section>
        )}

        {/* chain lengths */}
        {lengths.length > 0 && (
          <Section title={t("an_chain_lengths")}
            exp={{
              title: t("an_chain_lengths"),
              csv: () => [[t("an_hops"), t("an_count")], ...lengths.map((l: any) => [l.hops, l.n])],
            }}>
            <BarChart data={lengths.filter((l: any) => l.hops <= 12)
              .map((l: any) => ({ label: String(l.hops), value: l.n }))} />
          </Section>
        )}

        {/* top narrators */}
        {narrators.length > 0 && (
          <Section title={t("an_top_narrators")}
            exp={{
              title: t("an_top_narrators"),
              csv: () => [[t("nav_narrators"), t("narrators_mentions"), t("narrators_chains"), t("an_books")],
                ...narrators.map((n: any) => [n.canonical_ar, n.mentions, n.chains, n.books])],
            }}>
            <div className="bg-white rounded-xl shadow divide-y">
              {narrators.map((n: any, i: number) => (
                <Link key={n.narrator_id} to={`/narrators?id=${n.narrator_id}`}
                  className="flex items-center gap-2 px-3 py-1.5 hover:bg-islamic-teal/5 text-sm">
                  <span className="w-5 text-xs text-gray-400">{i + 1}</span>
                  <span className="w-2.5 h-2.5 rounded-full shrink-0"
                    style={{ background: NEON[i % NEON.length] }} />
                  <span className="font-arabic flex-1 truncate">{n.canonical_ar}</span>
                  <span className="text-xs text-gray-500">{n.mentions.toLocaleString("en")}</span>
                </Link>
              ))}
            </div>
          </Section>
        )}
      </div>

      {/* top transmission pairs */}
      {pairs.length > 0 && (
        <Section title={t("an_top_pairs")}
          exp={{
            title: t("an_top_pairs"),
            csv: () => [[t("an_student"), t("an_teacher"), t("an_count")],
              ...pairs.map((p: any) => [p.student, p.teacher, p.weight])],
          }}>
          <div className="bg-white rounded-xl shadow divide-y">
            {pairs.map((p: any, i: number) => (
              <div key={i} className="flex items-center gap-2 px-3 py-1.5 text-sm font-arabic">
                <span className="w-5 text-xs text-gray-400">{i + 1}</span>
                <Link to={`/narrators?id=${p.student_id}`} className="hover:text-islamic-teal font-bold">
                  {p.student}
                </Link>
                <span className="text-orange-accent text-xs">{t("narrated_from")}</span>
                <Link to={`/narrators?id=${p.teacher_id}`} className="hover:text-islamic-teal font-bold flex-1 truncate">
                  {p.teacher}
                </Link>
                <span className="text-xs bg-islamic-gold/20 text-deep-teal rounded-full px-2 py-0.5 font-bold">
                  {p.weight.toLocaleString("en")}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

function Card({ n, label, suffix }: { n: number; label: string; suffix?: string }) {
  return (
    <div className="bg-gradient-to-b from-deep-teal to-islamic-teal text-white rounded-xl p-4 text-center shadow">
      <div className="text-xl font-bold text-islamic-gold">
        {(n || 0).toLocaleString("en")}{suffix || ""}
      </div>
      <div className="text-xs opacity-85 mt-1">{label}</div>
    </div>
  );
}

function Section({ title, exp, children }: {
  title: string;
  exp?: { title: string; csv: () => (string | number | null | undefined)[][] };
  children: ReactNode;
}) {
  return (
    <section>
      <div className="flex items-center gap-3 mb-3">
        <h2 className="text-lg font-bold border-s-4 border-islamic-gold ps-3">{title}</h2>
        {exp && <ExportBar title={exp.title} csv={exp.csv}
          text={() => exp.csv().map((r) => r.join("\t")).join("\n")} />}
      </div>
      {children}
    </section>
  );
}

function BarChart({ data }: { data: { label: string; value: number }[] }) {
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div className="bg-white rounded-xl shadow p-4 space-y-2">
      {data.map((d, i) => (
        <div key={i} className="flex items-center gap-2 text-sm">
          <span className="w-20 font-arabic text-end shrink-0">{d.label}</span>
          <div className="flex-1 bg-gray-100 rounded-full h-5 overflow-hidden" dir="ltr">
            <div className="h-5 rounded-full flex items-center justify-end pe-2 text-[10px] text-white font-bold"
              style={{ width: `${Math.max((d.value / max) * 100, 4)}%`, background: NEON[i % NEON.length] }}>
              {d.value.toLocaleString("en")}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
