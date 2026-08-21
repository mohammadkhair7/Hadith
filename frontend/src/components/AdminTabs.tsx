import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";

const TABS = [
  { to: "/admin/narrators", key: "admin_tab_narrators" },
  { to: "/admin", key: "admin_tab_status" },
  { to: "/admin/embeddings", key: "admin_tab_embeddings" },
  { to: "/admin/translations", key: "admin_tab_translations" },
];

export default function AdminTabs() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap gap-1 mb-6 bg-white rounded-xl shadow p-1">
      {TABS.map((tab) => (
        <NavLink key={tab.to} to={tab.to} end={tab.to === "/admin"}
          className={({ isActive }) =>
            `px-4 py-2 rounded-lg text-sm font-bold transition-colors ${
              isActive
                ? "bg-islamic-teal text-white"
                : "text-deep-teal hover:bg-islamic-teal/10"
            }`}>
          {t(tab.key)}
        </NavLink>
      ))}
    </div>
  );
}
