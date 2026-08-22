import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../api";

type Filter =
  | { kind: "event"; key: string; label: string }
  | { kind: "year"; year: number }
  | { kind: "season"; key: string; label: string }
  | { kind: "companion"; key: string; label: string };

const SEASON_AR: Record<string, string> = { ramadan: "رمضان", hajj: "موسم الحج", eid: "العيد" };
const ERA_KEYS = ["meccan", "prophetic", "rashidun", "umayyad"];

/** Suggested origination timeline of the hadith corpus: dated events,
 *  seasonal anchors and companion lifespan windows (rule-estimated). */
export default function Timeline() {
  const { t, i18n } = useTranslation();
  const [data, setData] = useState<any>(null);
  const [failed, setFailed] = useState(false);
  const [filter, setFilter] = useState<Filter | null>(null);

  useEffect(() => {
    api("/analytics/timeline").then(setData).catch(() => setFailed(true));
  }, []);

  const yearLabel = (y: number) =>
    y < 0
      ? (i18n.language === "ar" ? `${-y} ق.هـ` : `${-y} BH`)
      : (i18n.language === "ar" ? `${y} هـ` : `${y} AH`);

  if (failed) return <div className="text-center py-16 text-gray-400">{t("analytics_error")}</div>;
  if (!data) return <div className="text-center py-16 text-gray-400">{t("loading")}</div>;

  const cov = data.coverage;
  const propheticYears = data.years.filter((y: any) => y.year <= 11);
  const laterYears = data.years.filter((y: any) => y.year > 11);
  const maxYearN = Math.max(...propheticYears.map((y: any) => y.n), 1);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">{t("tl_title")}</h1>
        <p className="text-sm text-gray-500 mt-1 max-w-3xl">{t("tl_desc")}</p>
      </div>

      {/* coverage cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card n={cov.dated} label={t("tl_dated")} sub={`${Math.round((cov.dated / Math.max(cov.units, 1)) * 100)}% / ${cov.units.toLocaleString("en")}`} />
        <Card n={cov.exact_year} label={t("tl_exact")} />
        <Card n={cov.windowed} label={t("tl_windowed")} />
        <Card n={cov.seasonal} label={t("tl_seasonal")} />
      </div>

      {/* year distribution chart (prophetic era) */}
      <section>
        <h2 className="text-lg font-bold border-s-4 border-islamic-gold ps-3 mb-3">
          {t("tl_years_chart")}
        </h2>
        <div className="bg-white rounded-xl shadow p-4 overflow-x-auto">
          <div className="flex items-end gap-1 h-48 min-w-[560px]" dir="rtl">
            {propheticYears.map((y: any) => {
              const active = filter?.kind === "year" && filter.year === y.year;
              return (
                <button key={y.year}
                  onClick={() => setFilter(active ? null : { kind: "year", year: y.year })}
                  className="flex-1 flex flex-col items-center justify-end h-full group"
                  title={`${yearLabel(y.year)}: ${y.n.toLocaleString("en")}`}>
                  <span className="text-[10px] text-gray-500 mb-0.5">{y.n.toLocaleString("en")}</span>
                  <div className={`w-full rounded-t transition-colors ${
                    active ? "bg-orange-accent" : "bg-islamic-teal group-hover:bg-islamic-gold"}`}
                    style={{ height: `${Math.max((y.n / maxYearN) * 100, 2)}%` }} />
                  <span className={`text-[10px] mt-1 ${y.year < 0 ? "text-gray-400" : "text-deep-teal font-bold"}`}>
                    {yearLabel(y.year)}
                  </span>
                </button>
              );
            })}
          </div>
          {laterYears.length > 0 && (
            <div className="mt-3 pt-3 border-t text-xs text-gray-500 flex flex-wrap gap-2 items-center">
              <span className="font-bold">{t("tl_post_prophetic")}:</span>
              {laterYears.map((y: any) => {
                const active = filter?.kind === "year" && filter.year === y.year;
                return (
                  <button key={y.year}
                    onClick={() => setFilter(active ? null : { kind: "year", year: y.year })}
                    className={`rounded-full px-2 py-0.5 border transition-colors ${
                      active ? "bg-orange-accent text-white border-orange-accent"
                             : "border-islamic-teal/30 hover:bg-islamic-teal/10"}`}>
                    {yearLabel(y.year)} · {y.n}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </section>

      <div className="grid lg:grid-cols-2 gap-8">
        {/* dated events, chronological, grouped by era */}
        <section>
          <h2 className="text-lg font-bold border-s-4 border-islamic-gold ps-3 mb-3">
            {t("tl_events")}
          </h2>
          <div className="bg-white rounded-xl shadow divide-y max-h-[32rem] overflow-y-auto toc-scroll">
            {ERA_KEYS.map((era) => {
              const evs = data.events.filter((e: any) => e.era === era);
              if (!evs.length) return null;
              return (
                <div key={era}>
                  <div className="px-3 py-1.5 bg-deep-teal/5 text-xs font-bold text-deep-teal">
                    {t(`tl_era_${era}`)}
                  </div>
                  {evs.map((e: any) => {
                    const active = filter?.kind === "event" && filter.key === e.event_key;
                    return (
                      <button key={e.event_key}
                        onClick={() => setFilter(active ? null
                          : { kind: "event", key: e.event_key, label: e.title_ar })}
                        className={`w-full flex items-center gap-2 px-3 py-1.5 text-sm text-start transition-colors ${
                          active ? "bg-islamic-gold/20" : "hover:bg-islamic-teal/5"}`}>
                        <span className="w-14 shrink-0 text-xs font-bold text-islamic-teal">
                          {yearLabel(e.year_ah)}
                        </span>
                        <span className="font-arabic flex-1">{e.title_ar}</span>
                        <span className="text-xs bg-islamic-teal/10 text-islamic-teal rounded-full px-2 py-0.5">
                          {e.n.toLocaleString("en")}
                        </span>
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>

          {/* seasonal anchors */}
          <h2 className="text-lg font-bold border-s-4 border-islamic-gold ps-3 my-3">
            {t("tl_seasons")}
          </h2>
          <div className="flex flex-wrap gap-2">
            {data.seasons.map((s: any) => {
              const active = filter?.kind === "season" && filter.key === s.season;
              return (
                <button key={s.season}
                  onClick={() => setFilter(active ? null
                    : { kind: "season", key: s.season, label: SEASON_AR[s.season] || s.season })}
                  className={`rounded-full px-4 py-1.5 text-sm font-arabic border transition-colors ${
                    active ? "bg-orange-accent text-white border-orange-accent"
                           : "bg-white border-islamic-teal/30 hover:bg-islamic-teal/10"}`}>
                  {SEASON_AR[s.season] || s.season} · {s.n.toLocaleString("en")}
                </button>
              );
            })}
          </div>
        </section>

        {/* companion lifespan windows */}
        <section>
          <h2 className="text-lg font-bold border-s-4 border-islamic-gold ps-3 mb-3">
            {t("tl_companions")}
          </h2>
          <div className="bg-white rounded-xl shadow divide-y max-h-[40rem] overflow-y-auto toc-scroll">
            {data.companions.map((c: any) => {
              const active = filter?.kind === "companion" && filter.key === c.companion_key;
              // range bar over the -13..93 hijri span
              const SPAN_MIN = -13, SPAN_MAX = 93;
              const from = ((c.win_from - SPAN_MIN) / (SPAN_MAX - SPAN_MIN)) * 100;
              const width = Math.max(((c.win_to - c.win_from) / (SPAN_MAX - SPAN_MIN)) * 100, 2);
              return (
                <button key={c.companion_key}
                  onClick={() => setFilter(active ? null
                    : { kind: "companion", key: c.companion_key, label: c.companion_ar })}
                  className={`w-full px-3 py-2 text-sm text-start transition-colors ${
                    active ? "bg-islamic-gold/20" : "hover:bg-islamic-teal/5"}`}>
                  <div className="flex items-center gap-2">
                    <span className="font-arabic font-bold flex-1 truncate">{c.companion_ar}</span>
                    <span className="text-xs text-gray-500">
                      {yearLabel(c.win_from)} ← {yearLabel(c.win_to)}
                    </span>
                    <span className="text-xs bg-islamic-teal/10 text-islamic-teal rounded-full px-2 py-0.5">
                      {c.n.toLocaleString("en")}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 bg-gray-100 rounded-full overflow-hidden" dir="rtl">
                    <div className="h-1.5 bg-islamic-gold/70 rounded-full"
                      style={{ marginRight: `${from}%`, width: `${width}%` }} />
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      </div>

      {/* drill-down list */}
      {filter && <HadithList filter={filter} yearLabel={yearLabel} />}

      <p className="text-xs text-gray-400 max-w-3xl">{t("tl_disclaimer")}</p>
    </div>
  );
}

function HadithList({ filter, yearLabel }: { filter: Filter; yearLabel: (y: number) => string }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const param =
    filter.kind === "event" ? `event=${filter.key}`
    : filter.kind === "year" ? `year=${filter.year}`
    : filter.kind === "season" ? `season=${filter.key}`
    : `companion=${filter.key}`;

  useEffect(() => {
    setItems([]);
    setTotal(0);
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [param]);

  function load(offset: number) {
    setLoading(true);
    api(`/analytics/timeline/hadiths?${param}&limit=20&offset=${offset}`)
      .then((r: any) => {
        setItems((prev) => offset === 0 ? r.items : [...prev, ...r.items]);
        setTotal(r.total);
      })
      .finally(() => setLoading(false));
  }

  const title = filter.kind === "year" ? yearLabel(filter.year) : filter.label;

  return (
    <section>
      <h2 className="text-lg font-bold border-s-4 border-orange-accent ps-3 mb-3">
        {t("tl_hadiths_for")} <span className="font-arabic">{title}</span>
        <span className="text-sm text-gray-400 ms-2">({total.toLocaleString("en")})</span>
      </h2>
      <div className="grid gap-2 md:grid-cols-2">
        {items.map((h) => (
          <Link key={h.passage_id} to={`/passage/${h.passage_id}`}
            className="block bg-white rounded-lg shadow-sm p-3 text-sm hover:shadow border-s-2 border-islamic-teal">
            <div className="flex items-center gap-2 flex-wrap text-xs mb-1">
              <span className="font-bold text-islamic-teal font-arabic">{h.work_title}</span>
              {h.hadith_num && <span className="text-islamic-gold font-bold">#{h.hadith_num}</span>}
              {h.year_best != null && (
                <span className="bg-islamic-teal/10 text-islamic-teal rounded-full px-2 py-0.5">
                  {yearLabel(h.year_best)}
                </span>
              )}
              {h.year_best == null && h.year_min != null && (
                <span className="bg-gray-100 text-gray-600 rounded-full px-2 py-0.5">
                  {yearLabel(h.year_min)} ← {yearLabel(h.year_max)}
                </span>
              )}
              {h.event_ar && (
                <span className="bg-islamic-gold/15 text-deep-teal rounded-full px-2 py-0.5 font-arabic">
                  {h.event_ar}
                </span>
              )}
              {h.hadith_type_ar && (
                <span className="bg-deep-teal/10 text-deep-teal rounded-full px-2 py-0.5 font-arabic">
                  {h.hadith_type_ar}
                </span>
              )}
            </div>
            <span className="font-arabic text-gray-700">{h.preview}…</span>
          </Link>
        ))}
      </div>
      {items.length < total && (
        <div className="text-center mt-4">
          <button onClick={() => load(items.length)} disabled={loading}
            className="px-5 py-2 rounded-lg bg-islamic-teal text-white disabled:opacity-40">
            {loading ? t("loading") : t("tl_load_more")}
          </button>
        </div>
      )}
    </section>
  );
}

function Card({ n, label, sub }: { n: number; label: string; sub?: string }) {
  return (
    <div className="bg-gradient-to-b from-deep-teal to-islamic-teal text-white rounded-xl p-4 text-center shadow">
      <div className="text-xl font-bold text-islamic-gold">{(n || 0).toLocaleString("en")}</div>
      <div className="text-xs opacity-85 mt-1">{label}</div>
      {sub && <div className="text-[10px] opacity-60 mt-0.5">{sub}</div>}
    </div>
  );
}
