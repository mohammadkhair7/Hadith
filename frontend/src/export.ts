/** Result export: clipboard copy, .txt / .csv download, print-to-PDF view. */

export function copyText(text: string): Promise<void> {
  return navigator.clipboard.writeText(text);
}

function download(filename: string, mime: string, content: string) {
  // BOM so Excel opens Arabic CSV/TXT correctly
  const blob = new Blob(["\uFEFF" + content], { type: `${mime};charset=utf-8` });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function downloadTxt(filename: string, text: string) {
  download(filename, "text/plain", text);
}

export function downloadCsv(filename: string, rows: (string | number | null | undefined)[][]) {
  const esc = (v: string | number | null | undefined) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  download(filename, "text/csv", rows.map((r) => r.map(esc).join(",")).join("\n"));
}

/** Opens a print-formatted RTL window; the browser's print dialog saves as PDF
 *  with correct Arabic shaping (far more reliable than client-side PDF libs). */
export function printPdf(title: string, bodyHtml: string) {
  const w = window.open("", "_blank", "width=900,height=700");
  if (!w) return;
  w.document.write(`<!DOCTYPE html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>${title}</title>
<style>
  body { font-family: "Amiri", "Traditional Arabic", "Segoe UI", serif;
         margin: 2cm; line-height: 2; color: #1A1A2E; }
  h1 { color: #0D7377; border-bottom: 3px solid #D4AF37; padding-bottom: 8px; font-size: 20px; }
  h2 { color: #14213D; font-size: 16px; margin-top: 24px; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: right; }
  th { background: #0D7377; color: white; }
  .meta { color: #888; font-size: 11px; margin-top: 24px; border-top: 1px solid #eee; padding-top: 8px; }
  mark { background: #D4AF3733; }
  @media print { .noprint { display: none; } }
</style></head>
<body>
<h1>${title}</h1>
${bodyHtml}
<div class="meta">AdvancedHadith — ${new Date().toLocaleString("en-GB")}</div>
<script>window.onload = () => setTimeout(() => window.print(), 300);</script>
</body></html>`);
  w.document.close();
}

export function tableHtml(headers: string[], rows: (string | number | null | undefined)[][]): string {
  const esc = (v: string | number | null | undefined) =>
    v == null ? "" : String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  return `<table><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}
