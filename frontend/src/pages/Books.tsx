import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function Books() {
  const { t } = useTranslation();
  const [works, setWorks] = useState<any[]>([]);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    api<any[]>("/works").then(setWorks).catch(console.error);
  }, []);

  const filtered = works.filter((w) => !filter || w.title_ar.includes(filter));

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-2xl font-bold">{t("nav_books")}</h1>
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="🔍"
          className="border rounded-lg px-3 py-1.5 text-sm w-64"
        />
        <span className="text-sm text-gray-500">{filtered.length}</span>
      </div>
      <div className="bg-white rounded-xl shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-deep-teal text-islamic-light">
            <tr>
              <th className="p-3 text-start">#</th>
              <th className="p-3 text-start">{t("nav_books")}</th>
              <th className="p-3 text-start">{t("editions")}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((w, i) => (
              <tr key={w.work_id} className="border-b last:border-0 hover:bg-islamic-teal/5">
                <td className="p-3 text-gray-400">{i + 1}</td>
                <td className="p-3 font-arabic">
                  <div className="font-bold">{w.title_ar}</div>
                  {w.author_ar && <div className="text-xs text-gray-500">{w.author_ar}</div>}
                </td>
                <td className="p-3">
                  <div className="flex gap-2 flex-wrap">
                    {w.editions.map((e: any) => (
                      <Link
                        key={e.edition_id}
                        to={`/read/${e.edition_id}`}
                        className="px-2 py-1 rounded bg-islamic-teal/10 text-islamic-teal hover:bg-islamic-teal hover:text-white transition-colors text-xs"
                      >
                        {e.source} ({(e.passage_count || 0).toLocaleString("en")})
                      </Link>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
