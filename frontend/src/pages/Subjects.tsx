import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";

type SubjectNode = {
  subject_id: number;
  title: string;
  has_children: boolean;
  passage_count?: number;
};

export default function Subjects() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const openId = params.get("open");
  const [roots, setRoots] = useState<SubjectNode[]>([]);
  const [selected, setSelected] = useState<number | null>(openId ? Number(openId) : null);
  const [passages, setPassages] = useState<any>(null);

  useEffect(() => {
    api<SubjectNode[]>("/subjects/tree").then(setRoots).catch(console.error);
  }, []);

  useEffect(() => {
    if (selected == null) return;
    setPassages(null);
    api(`/subjects/${selected}/passages?limit=30`).then(setPassages).catch(console.error);
  }, [selected]);

  return (
    <div className="flex flex-col md:flex-row gap-6">
      <aside className="md:w-96 shrink-0">
        <div className="bg-white rounded-xl shadow p-3 max-h-[80vh] overflow-y-auto toc-scroll">
          <h2 className="font-bold text-islamic-teal border-b pb-2 mb-2">{t("subjects_title")}</h2>
          {roots.map((n) => (
            <Branch key={n.subject_id} node={n} onSelect={setSelected} selected={selected}
              autoOpen={roots.length === 1} />
          ))}
        </div>
      </aside>

      <div className="flex-1 min-w-0">
        {selected == null && (
          <div className="text-center py-16 text-gray-400">{t("subjects_title")} ←</div>
        )}
        {selected != null && !passages && (
          <div className="text-center py-16 text-gray-400">{t("loading")}</div>
        )}
        {passages && (
          <div className="space-y-3">
            <div className="text-sm text-gray-500">
              {passages.total.toLocaleString("en")} {t("search_results")}
            </div>
            {passages.items.map((r: any) => (
              <Link key={r.passage_id} to={`/passage/${r.passage_id}`}
                className="block bg-white rounded-xl p-4 shadow hover:shadow-md border-s-4 border-islamic-teal">
                <div className="text-xs text-islamic-teal font-bold mb-1">
                  {r.work_title}
                  {r.hadith_num && <span className="ms-2 text-islamic-gold">#{r.hadith_num}</span>}
                </div>
                <p className="arabic-text text-base line-clamp-3">{r.preview}</p>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Branch({ node, onSelect, selected, autoOpen }: {
  node: SubjectNode;
  onSelect: (id: number) => void;
  selected: number | null;
  autoOpen?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState<SubjectNode[] | null>(null);

  useEffect(() => {
    if (autoOpen && node.has_children) {
      api<SubjectNode[]>(`/subjects/tree?parent_id=${node.subject_id}`).then((r) => {
        setChildren(r);
        setOpen(true);
      });
    }
  }, [autoOpen]);

  async function toggle() {
    onSelect(node.subject_id);
    if (!node.has_children) return;
    if (!open && children === null) {
      const r = await api<SubjectNode[]>(`/subjects/tree?parent_id=${node.subject_id}`);
      setChildren(r);
    }
    setOpen(!open);
  }

  return (
    <div className="text-sm">
      <button onClick={toggle}
        className={`w-full text-start py-1 px-1 rounded font-arabic hover:bg-islamic-teal/10 ${
          selected === node.subject_id ? "bg-islamic-gold/20 font-bold" : ""}`}>
        {node.has_children && <span className="text-islamic-gold me-1">{open ? "▾" : "▸"}</span>}
        {node.title}
      </button>
      {open && children && (
        <div className="ms-3 border-s border-islamic-teal/20 ps-2">
          {children.map((c) => (
            <Branch key={c.subject_id} node={c} onSelect={onSelect} selected={selected} />
          ))}
        </div>
      )}
    </div>
  );
}
