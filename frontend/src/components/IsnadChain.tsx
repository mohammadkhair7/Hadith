import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

/** Sanad chain display: narrator pills joined by arrows. Resolved narrators
 *  link to the narrator-network page to identify them. */
export default function IsnadChain({ chain }: { chain: any }) {
  const { t } = useTranslation();
  if (!chain?.links?.length) return null;
  return (
    <section className="mt-6 bg-deep-teal text-islamic-light rounded-xl p-4">
      <h3 className="font-bold text-islamic-gold mb-3">{t("isnad_title")}</h3>
      <div className="flex flex-wrap items-center gap-2 font-arabic text-sm">
        {chain.links.map((l: any, i: number) => {
          const pill = (
            <span className={`bg-islamic-teal/40 rounded-full px-3 py-1 ${
              l.narrator_id ? "hover:bg-islamic-gold hover:text-deep-teal transition-colors" : ""}`}>
              <span className="text-xs text-islamic-gold me-1">{l.verb}</span>
              {l.canonical_ar || l.mention_ar}
            </span>
          );
          return (
            <span key={i} className="flex items-center gap-2">
              {i > 0 && <span className="text-orange-accent">←</span>}
              {l.narrator_id
                ? <Link to={`/narrators?id=${l.narrator_id}`}>{pill}</Link>
                : pill}
            </span>
          );
        })}
      </div>
      <div className="text-xs opacity-60 mt-2" dir="ltr">
        confidence {chain.confidence} · {chain.extractor}
      </div>
    </section>
  );
}
