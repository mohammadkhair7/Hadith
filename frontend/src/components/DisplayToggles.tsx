import { useTranslation } from "react-i18next";
import type { DisplayPrefs } from "../text";

function Pill({ on, label, onClick }: { on: boolean; label: string; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`text-xs rounded-full px-3 py-1 border transition-colors ${
        on ? "bg-islamic-teal text-white border-islamic-teal"
           : "bg-white text-islamic-teal border-islamic-teal/40 hover:border-islamic-teal"}`}>
      {label}
    </button>
  );
}

/** Tashkeel + matn-only toggles. `canMatn` hides the matn toggle when the
 *  passage has no detectable isnad/matn boundary. */
export default function DisplayToggles({ prefs, canMatn }: { prefs: DisplayPrefs; canMatn: boolean }) {
  const { t } = useTranslation();
  return (
    <span className="flex items-center gap-2 ms-auto">
      <Pill on={prefs.tashkeel} label={t("toggle_tashkeel")}
        onClick={() => prefs.setTashkeel(!prefs.tashkeel)} />
      {canMatn && (
        <Pill on={prefs.matnOnly} label={t("toggle_matn")}
          onClick={() => prefs.setMatnOnly(!prefs.matnOnly)} />
      )}
    </span>
  );
}
