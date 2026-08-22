import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { clearTokens, isLoggedIn } from "../api";
import { applyDir } from "../i18n";

export default function Layout() {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark"));

  function switchLang() {
    const next = i18n.language === "ar" ? "en" : "ar";
    i18n.changeLanguage(next);
    localStorage.setItem("lang", next);
    applyDir(next);
  }

  function switchTheme() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
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
        <div className="max-w-7xl mx-auto px-4 py-3 flex flex-wrap items-center gap-2 sm:gap-3">
          {/* hamburger: phones + small tablets get a collapsible menu */}
          <button
            onClick={() => setMenuOpen((v) => !v)}
            aria-label="menu" aria-expanded={menuOpen}
            className="lg:hidden text-2xl leading-none px-1 text-islamic-gold"
          >
            {menuOpen ? "✕" : "☰"}
          </button>
          <Link to="/" className="flex items-center gap-2" onClick={() => setMenuOpen(false)}>
            <span className="text-2xl text-islamic-gold">◈</span>
            <span className="font-bold text-lg">{t("app_title")}</span>
          </Link>
          <nav className="hidden lg:flex items-center gap-1">
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
          {/* on phones the search box drops to its own full-width row */}
          <form onSubmit={submit}
            className="order-last w-full lg:order-none lg:w-auto lg:flex-1 lg:min-w-[220px] lg:max-w-xl">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("search_placeholder")}
              className="w-full rounded-full px-4 py-2 text-sm text-islamic-dark outline-none ring-2 ring-transparent focus:ring-islamic-gold"
            />
          </form>
          <span className="flex-1 lg:hidden" />
          <button
            onClick={switchTheme}
            title={dark ? t("theme_light") as string : t("theme_dark") as string}
            className="px-2.5 py-1.5 rounded-full border border-islamic-gold text-islamic-gold text-sm hover:bg-islamic-gold hover:text-deep-teal transition-colors"
          >
            {dark ? "☀" : "☾"}
          </button>
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
        {/* mobile navigation drawer */}
        {menuOpen && (
          <nav className="lg:hidden max-w-7xl mx-auto px-4 pb-3 flex flex-col gap-1 border-t border-islamic-teal/40 pt-2">
            {([
              ["/", t("nav_home"), true],
              ["/books", t("nav_books"), false],
              ["/search", t("nav_search"), false],
              ["/subjects", t("nav_subjects"), false],
              ["/narrators", t("nav_narrators"), false],
              ["/analytics", t("nav_analytics"), false],
              ["/timeline", t("nav_timeline"), false],
              ...(isLoggedIn()
                ? [["/account", t("nav_account"), false],
                   ["/admin", t("nav_admin"), false]]
                : []),
            ] as [string, string, boolean][]).map(([to, label, end]) => (
              <NavLink key={to} to={to} end={end}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  `px-3 py-2.5 rounded-md text-sm ${
                    isActive
                      ? "bg-islamic-teal text-white"
                      : "text-islamic-light/90 hover:bg-islamic-teal/40"}`}>
                {label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6">
        <Outlet />
      </main>
      <footer className="bg-deep-teal text-islamic-light/70 text-center text-xs py-4">
        AdvancedHadith — al-maktaba al-shamela
      </footer>
    </div>
  );
}
