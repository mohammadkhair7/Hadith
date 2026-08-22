import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { api, isLoggedIn } from "../api";

export default function Account() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [me, setMe] = useState<any>(null);
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    if (!isLoggedIn()) { nav("/login"); return; }
    api("/auth/me").then(setMe).catch(() => nav("/login"));
    api<any[]>("/me/items").then(setItems).catch(console.error);
  }, []);

  async function remove(id: number) {
    await api(`/me/items/${id}`, { method: "DELETE" });
    setItems(items.filter((i) => i.item_id !== id));
  }

  const favs = items.filter((i) => i.kind === "favourite");
  const notes = items.filter((i) => i.kind === "note");

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">{t("nav_account")}</h1>
      {me && (
        <div className="text-sm text-gray-500 mb-6" dir="ltr">
          {me.email} {me.is_admin && <span className="text-islamic-gold font-bold">· admin</span>}
        </div>
      )}

      <section className="mb-8">
        <h2 className="font-bold text-deep-teal border-s-4 border-islamic-gold ps-3 mb-3">
          {t("favourites")} ({favs.length})
        </h2>
        <div className="space-y-2">
          {favs.map((f) => (
            <div key={f.item_id} className="bg-white rounded-lg p-3 shadow flex items-center gap-3">
              <Link to={`/passage/${f.ref?.passage_id}`}
                className="flex-1 text-sm min-w-0 group">
                <span className="text-islamic-teal group-hover:underline font-bold">
                  {f.passage?.work_title || f.title || `#${f.ref?.passage_id}`}
                  {f.passage?.hadith_num && ` — ${f.passage.hadith_num}`}
                </span>
                {f.passage?.snippet && (
                  <span className="block font-arabic text-gray-600 truncate mt-0.5">
                    {f.passage.snippet}…
                  </span>
                )}
              </Link>
              <button onClick={() => remove(f.item_id)} className="text-red-400 hover:text-red-600">✕</button>
            </div>
          ))}
          {favs.length === 0 && <div className="text-sm text-gray-400">—</div>}
        </div>
      </section>

      <section>
        <h2 className="font-bold text-deep-teal border-s-4 border-islamic-teal ps-3 mb-3">
          {t("notes")} ({notes.length})
        </h2>
        <div className="space-y-2">
          {notes.map((n) => (
            <div key={n.item_id} className="bg-white rounded-lg p-3 shadow flex items-start gap-3">
              <div className="flex-1 text-sm">
                <Link to={`/passage/${n.ref?.passage_id}`} className="text-islamic-teal hover:underline">
                  {n.passage?.work_title || `#${n.ref?.passage_id}`}
                  {n.passage?.hadith_num && ` — ${n.passage.hadith_num}`}
                </Link>
                {n.passage?.snippet && (
                  <span className="block font-arabic text-gray-400 text-xs truncate">
                    {n.passage.snippet}…
                  </span>
                )}
                <p className="font-arabic mt-1">{n.body}</p>
              </div>
              <button onClick={() => remove(n.item_id)} className="text-red-400 hover:text-red-600">✕</button>
            </div>
          ))}
          {notes.length === 0 && <div className="text-sm text-gray-400">—</div>}
        </div>
      </section>
    </div>
  );
}
