import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import DisplayToggles from "../components/DisplayToggles";
import HadithText, { GradeBadge } from "../components/HadithText";
import IsnadChain from "../components/IsnadChain";
import { cleanText, matnStart, segmentHadiths, stripTashkeel, useDisplayPrefs } from "../text";

type TocNode = {
  toc_node_id: number;
  source_node_id: number;
  title: string;
  is_leaf: boolean;
  has_children: boolean;
};

export default function Reader() {
  const { t } = useTranslation();
  const { editionId } = useParams();
  const [params, setParams] = useSearchParams();
  const seq = parseInt(params.get("seq") || "0", 10);

  const [edition, setEdition] = useState<any>(null);
  const [roots, setRoots] = useState<TocNode[]>([]);
  const [passage, setPassage] = useState<any>(null);
  const [total, setTotal] = useState(0);
  const [isnad, setIsnad] = useState<any[]>([]);
  const prefs = useDisplayPrefs();

  useEffect(() => {
    api(`/editions/${editionId}/toc`).then((r: any) => {
      setEdition(r.edition);
      setRoots(r.nodes);
    });
  }, [editionId]);

  useEffect(() => {
    api(`/editions/${editionId}/passages?seq=${seq}&limit=1`).then((r: any) => {
      const p = r.items[0] || null;
      setPassage(p);
      setTotal(r.total);
      setIsnad([]);
      if (p) api(`/passages/${p.passage_id}/isnad`).then(setIsnad).catch(() => {});
    });
  }, [editionId, seq]);

  function gotoSeq(s: number) {
    setParams({ seq: String(Math.max(0, s)) });
    window.scrollTo({ top: 0 });
  }

  const raw = passage?.text_raw || "";
  const dbBoundary = passage?.sanad_end_raw > 0
    ? passage.sanad_end_raw
    : isnad[0]?.sanad_end_raw > 0 ? isnad[0].sanad_end_raw : 0;
  const hasChains = passage
    ? dbBoundary > 0 || matnStart(raw) > 0 || segmentHadiths(raw).length > 0
    : false;
  // legacy HTML rendering only for pages without hadith chains (tables etc.)
  const useHadithText = passage
    ? passage.kind === "unit" || passage.source === "shamela" || !passage.html || hasChains
    : false;

  return (
    <div className="flex gap-6">
      <aside className="w-72 shrink-0 hidden md:block">
        <div className="bg-white rounded-xl shadow p-3 sticky top-20 max-h-[80vh] overflow-y-auto toc-scroll">
          <h3 className="font-bold text-islamic-teal border-b pb-2 mb-2">{t("reader_toc")}</h3>
          {roots.map((n) => (
            <TocBranch key={n.toc_node_id} node={n} editionId={editionId!} gotoSeq={gotoSeq} />
          ))}
        </div>
      </aside>

      <div className="flex-1 min-w-0">
        {edition && (
          <div className="bg-gradient-to-l from-deep-teal to-islamic-teal text-white rounded-xl p-4 mb-4 shadow">
            <h1 className="font-arabic font-bold text-xl">{edition.title_ar}</h1>
            <div className="text-xs opacity-80 mt-1">
              {total.toLocaleString("en")} {t("stats_passages")}
            </div>
          </div>
        )}

        {passage ? (
          <>
            <article className="bg-white rounded-xl shadow p-6">
              <div className="flex items-center gap-2 flex-wrap text-xs mb-4">
                {passage.hadith_num && (
                  <span className="bg-islamic-gold text-deep-teal font-bold rounded-full px-3 py-1">
                    {t("hadith_no")} {passage.hadith_num}
                  </span>
                )}
                {passage.grade_ar && <GradeBadge grade={passage} />}
                {passage.part && (
                  <span className="bg-islamic-teal/10 text-islamic-teal rounded-full px-3 py-1">
                    {t("part_page")}: {passage.part}/{passage.page}
                  </span>
                )}
                <Link to={`/passage/${passage.passage_id}`}
                  className="text-islamic-teal underline decoration-dotted">
                  ↗
                </Link>
                <DisplayToggles prefs={prefs}
                  canMatn={hasChains} />
              </div>
              <div className="max-h-[68vh] overflow-y-auto toc-scroll pe-2 break-words">
                {useHadithText ? (
                  <HadithText raw={raw} diac={passage.text_diac}
                    sanadEndRaw={dbBoundary} spans={passage.structure_spans}
                    prefs={prefs} />
                ) : (
                  <div className="arabic-text legacy-content"
                    dangerouslySetInnerHTML={{
                      __html: cleanText(prefs.tashkeel ? passage.html : stripTashkeel(passage.html)) }} />
                )}
              </div>
            </article>
            {isnad.length > 0 && <IsnadChain chain={isnad[0]} />}
          </>
        ) : (
          <div className="text-center py-16 text-gray-400">{t("loading")}</div>
        )}

        <div className="flex justify-between mt-4">
          <button onClick={() => gotoSeq(seq - 1)} disabled={seq <= 0}
            className="px-5 py-2 rounded-lg bg-islamic-teal text-white disabled:opacity-30">
            {t("prev")}
          </button>
          <PageJump seq={seq} total={total} gotoSeq={gotoSeq} />
          <button onClick={() => gotoSeq(seq + 1)} disabled={seq + 1 >= total}
            className="px-5 py-2 rounded-lg bg-islamic-teal text-white disabled:opacity-30">
            {t("next")}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Direct page navigation: type a page number (1..total) and press Enter. */
function PageJump({ seq, total, gotoSeq }: {
  seq: number; total: number; gotoSeq: (s: number) => void;
}) {
  const [val, setVal] = useState(String(seq + 1));
  useEffect(() => { setVal(String(seq + 1)); }, [seq]);

  function commit() {
    const n = parseInt(val, 10);
    if (!isNaN(n) && total > 0) {
      gotoSeq(Math.min(Math.max(n, 1), total) - 1);
    } else {
      setVal(String(seq + 1));
    }
  }

  return (
    <span className="flex items-center gap-1.5 text-sm text-gray-500 self-center" dir="ltr">
      <input type="number" min={1} max={total} value={val}
        onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") { commit(); (e.target as HTMLInputElement).blur(); } }}
        onBlur={commit}
        aria-label="page number"
        className="w-20 border border-islamic-teal/30 rounded-lg px-2 py-1 text-center
          focus:outline-none focus:ring-2 focus:ring-islamic-teal/50" />
      <span>/ {total.toLocaleString("en")}</span>
    </span>
  );
}

function TocBranch({ node, editionId, gotoSeq }: {
  node: TocNode; editionId: string; gotoSeq: (s: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState<TocNode[] | null>(null);

  async function toggle() {
    if (node.is_leaf) {
      const r: any = await api(`/editions/${editionId}/toc-leaf/${node.toc_node_id}`)
        .catch(() => null);
      if (r?.seq != null) gotoSeq(r.seq);
      return;
    }
    if (!open && children === null) {
      const r: any = await api(`/editions/${editionId}/toc?parent_id=${node.toc_node_id}`);
      setChildren(r.nodes);
    }
    setOpen(!open);
  }

  return (
    <div className="text-sm">
      <button onClick={toggle}
        className={`w-full text-start py-1 px-1 rounded hover:bg-islamic-teal/10 ${
          node.is_leaf ? "text-islamic-dark" : "font-semibold text-deep-teal"}`}>
        {!node.is_leaf && <span className="text-islamic-gold me-1">{open ? "▾" : "▸"}</span>}
        <span className="font-arabic">{node.title}</span>
      </button>
      {open && children && (
        <div className="ms-3 border-s border-islamic-teal/20 ps-2">
          {children.map((c) => (
            <TocBranch key={c.toc_node_id} node={c} editionId={editionId} gotoSeq={gotoSeq} />
          ))}
        </div>
      )}
    </div>
  );
}
