import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../api";

type Work = {
  work_id: number;
  title_ar: string;
  author_ar: string | null;
  kind: string;
  editions: { edition_id: number; source: string; passage_count: number; section_name?: string }[];
};

export default function Home() {
  const { t } = useTranslation();
  const [works, setWorks] = useState<Work[]>([]);

  useEffect(() => {
    api<Work[]>("/works").then(setWorks).catch(console.error);
  }, []);

  const matn = works.filter((w) => w.kind === "matn");
  const service = works.filter((w) => w.kind === "service");
  const other = works.filter((w) => !["matn", "service"].includes(w.kind));
  const totalPassages = works.reduce(
    (acc, w) => acc + w.editions.reduce((a, e) => a + (e.passage_count || 0), 0), 0);

  return (
    <div>
      <section className="text-center py-10 bg-gradient-to-b from-deep-teal to-islamic-teal text-islamic-light rounded-2xl mb-8 shadow-lg">
        <h1 className="text-3xl md:text-4xl font-bold font-arabic mb-3">{t("home_headline")}</h1>
        <p className="text-islamic-light/85">{t("home_sub")}</p>
        <div className="flex justify-center gap-8 mt-6 text-sm">
          <Stat n={works.length} label={t("stats_works")} />
          <Stat n={totalPassages} label={t("stats_passages")} />
          <Stat n={21994} label={t("stats_subjects")} />
        </div>
      </section>

      <Collection title={t("kind_matn")} works={matn} accent="border-islamic-gold" />
      <Collection title={t("kind_service")} works={service} accent="border-islamic-teal" />
      <Collection title={t("kind_other")} works={other} accent="border-orange-accent" />
    </div>
  );
}

function Stat({ n, label }: { n: number; label: string }) {
  return (
    <div>
      <div className="text-2xl font-bold text-islamic-gold">{n.toLocaleString("en")}</div>
      <div>{label}</div>
    </div>
  );
}

function Collection({ title, works, accent }: { title: string; works: Work[]; accent: string }) {
  if (!works.length) return null;
  return (
    <section className="mb-8">
      <h2 className={`text-xl font-bold mb-4 border-s-4 ${accent} ps-3`}>{title}</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {works.map((w) => {
          const main = w.editions.find((e) => e.source === "sunna") || w.editions[0];
          return (
            <Link
              key={w.work_id}
              to={`/read/${main.edition_id}`}
              className="block bg-white rounded-xl p-4 shadow hover:shadow-lg border border-transparent hover:border-islamic-teal transition-all"
            >
              <div className="font-arabic font-bold text-islamic-dark">{w.title_ar}</div>
              {w.author_ar && <div className="text-sm text-gray-500 mt-1">{w.author_ar}</div>}
              <div className="flex gap-2 mt-2 flex-wrap">
                {w.editions.map((e) => (
                  <span
                    key={e.edition_id}
                    className="text-[11px] px-2 py-0.5 rounded-full bg-islamic-teal/10 text-islamic-teal"
                  >
                    {e.source} · {(e.passage_count || 0).toLocaleString("en")}
                  </span>
                ))}
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
