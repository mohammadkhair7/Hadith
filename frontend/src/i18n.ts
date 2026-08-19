import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ar from "./locales/ar.json";
import en from "./locales/en.json";

i18n.use(initReactI18next).init({
  resources: { ar: { translation: ar }, en: { translation: en } },
  lng: localStorage.getItem("lang") || "ar",
  fallbackLng: "ar",
  interpolation: { escapeValue: false },
});

export function applyDir(lang: string) {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
}

applyDir(i18n.language);

export default i18n;
