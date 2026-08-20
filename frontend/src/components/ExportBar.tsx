import { useState } from "react";
import { useTranslation } from "react-i18next";
import { copyText, downloadCsv, downloadTxt, printPdf, tableHtml } from "../export";

type Props = {
  title: string;                                        // report title + filename base
  text: () => string;                                   // plain-text form
  csv?: () => (string | number | null | undefined)[][]; // rows incl. header (optional)
  html?: () => string;                                  // rich form for the PDF (defaults to <pre>)
};

/** Copy / TXT / CSV / PDF export toolbar for any result block. */
export default function ExportBar({ title, text, csv, html }: Props) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const fname = title.replace(/[^\w\u0600-\u06FF-]+/g, "_").slice(0, 60);

  const btn = "text-[11px] px-2.5 py-1 rounded-lg border border-islamic-teal/30 " +
    "text-islamic-teal hover:bg-islamic-teal hover:text-white transition-colors";

  return (
    <span className="flex items-center gap-1.5 noprint" dir="ltr">
      <button className={btn} onClick={async () => {
        await copyText(text()); setCopied(true); setTimeout(() => setCopied(false), 1500);
      }}>{copied ? "✓" : t("export_copy")}</button>
      <button className={btn} onClick={() => downloadTxt(`${fname}.txt`, text())}>TXT</button>
      {csv && (
        <button className={btn} onClick={() => downloadCsv(`${fname}.csv`, csv()!)}>CSV</button>
      )}
      <button className={btn} onClick={() => {
        const body = html ? html()
          : csv ? tableHtml(csv()[0].map(String), csv().slice(1))
          : `<pre style="white-space:pre-wrap">${text().replace(/</g, "&lt;")}</pre>`;
        printPdf(title, body);
      }}>PDF</button>
    </span>
  );
}
