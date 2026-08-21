import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { clearTokens, isLoggedIn } from "../api";
import { applyDir } from "../i18n";

export default function Layout() {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const [q, setQ] = useState("");

  function switchLang() {
    const next = i18n.language === "ar" ? "en" : "ar";
    i18n.changeLanguage(next);
    localStorage.setItem("lang", next);
    applyDir(next);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (q.trim()) nav(`/search?q=${encodeURIComponent(q.trim())}`);
  }

  const link = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-2 rounded-md text-sm transition-colors ${
      isActive
        ? "bg-islamic-teal text-white"
        : "text-islamic-light/90 hover:bg-islamic-teal/40"
    }`;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-deep-teal text-islamic-light shadow-lg sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 py-3 flex flex-wrap items-center gap-3">
          <Link to="/" className="flex items-center gap-2">
            <span className="text-2xl text-islamic-gold">◈</span>
            <span className="font-bold text-lg">{t("app_title")}</span>
          </Link>
          <nav className="flex items-center gap-1">
            <NavLink to="/" className={link} end>{t("nav_home")}</NavLink>
            <NavLink to="/books" className={link}>{t("nav_books")}</NavLink>
            <NavLink to="/search" className={link}>{t("nav_search")}</NavLink>
            <NavLink to="/subjects" className={link}>{t("nav_subjects")}</NavLink>
            <NavLink to="/narrators" className={link}>{t("nav_narrators")}</NavLink>
            <NavLink to="/analytics" className={link}>{t("nav_analytics")}</NavLink>
            <NavLink to="/timeline" className={link}>{t("nav_timeline")}</NavLink>
            {isLoggedIn() && <NavLink to="/account" className={link}>{t("nav_account")}</NavLink>}
            {isLoggedIn() && <NavLink to="/admin" className={link}>{t("nav_admin")}</NavLink>}
          </nav>
          <form onSubmit={submit} className="flex-1 min-w-[220px] max-w-xl">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("search_placeholder")}
              className="w-full rounded-full px-4 py-2 text-sm text-islamic-dark outline-none ring-2 ring-transparent focus:ring-islamic-gold"
            />
          </form>
          <button
            onClick={switchLang}
            className="px-3 py-1.5 rounded-full border border-islamic-gold text-islamic-gold text-sm hover:bg-islamic-gold hover:text-deep-teal transition-colors"
          >
            {i18n.language === "ar" ? "EN" : "عربي"}
          </button>
          {isLoggedIn() ? (
            <button
              onClick={() => { clearTokens(); nav("/"); }}
              className="text-sm text-islamic-light/80 hover:text-orange-accent"
            >
              {t("logout")}
            </button>
          ) : (
            <Link to="/login" className="text-sm text-islamic-gold hover:text-orange-accent">
              {t("login")}
            </Link>
          )}
        </div>
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6">
        <Outlet />
      </main>
      <footer className="bg-deep-teal text-islamic-light/70 text-center text-xs py-4">
        AdvancedHadith — al-jami3 · al-maktaba al-shamela
      </footer>
    </div>
  );
}
