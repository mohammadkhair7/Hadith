import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../api";

type GNode = {
  narrator_id: number; name: string; mentions: number;
  x?: number; y?: number; vx?: number; vy?: number;
};
type GEdge = { student: number; teacher: number; weight: number };

const NEON = ["#10b981", "#3b82f6", "#facc15", "#22d3ee", "#ec4899", "#8b5cf6", "#f59e0b"];
const W = 900, H = 620;

export default function Narrators() {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [nodes, setNodes] = useState<Map<number, GNode>>(new Map());
  const [edges, setEdges] = useState<GEdge[]>([]);
  const [center, setCenter] = useState<number | null>(null);
  const [hover, setHover] = useState<GNode | null>(null);
  const [selected, setSelected] = useState<any>(null);
  const simRef = useRef<number | null>(null);
  const [, forceRender] = useState(0);

  async function search() {
    if (!query.trim()) return;
    setResults(await api(`/narrators?search=${encodeURIComponent(query.trim())}`));
  }

  async function loadGraph(id: number) {
    setResults([]);
    setCenter(id);
    const g: any = await api(`/narrators/${id}/graph?depth=1&cap=60`);
    const m = new Map<number, GNode>();
    g.nodes.forEach((n: any, i: number) => {
      const angle = (2 * Math.PI * i) / g.nodes.length;
      m.set(n.narrator_id, {
        ...n,
        x: W / 2 + (n.narrator_id === id ? 0 : 220 * Math.cos(angle)),
        y: H / 2 + (n.narrator_id === id ? 0 : 220 * Math.sin(angle)),
        vx: 0, vy: 0,
      });
    });
    setNodes(m);
    setEdges(g.edges);
    setSelected(await api(`/narrators/${id}`));
    startSim(m, g.edges);
  }

  async function expand(id: number) {
    const g: any = await api("/graph/expand", {
      method: "POST", body: JSON.stringify({ node_ids: [id], cap: 30 }),
    });
    const m = new Map(nodes);
    const base = m.get(id);
    g.nodes.forEach((n: any, i: number) => {
      if (!m.has(n.narrator_id)) {
        m.set(n.narrator_id, {
          ...n,
          x: (base?.x ?? W / 2) + 90 * Math.cos((2 * Math.PI * i) / g.nodes.length),
          y: (base?.y ?? H / 2) + 90 * Math.sin((2 * Math.PI * i) / g.nodes.length),
          vx: 0, vy: 0,
        });
      }
    });
    const seen = new Set(edges.map((e) => `${e.student}-${e.teacher}`));
    const merged = [...edges];
    g.edges.forEach((e: GEdge) => {
      if (!seen.has(`${e.student}-${e.teacher}`)) merged.push(e);
    });
    setNodes(m);
    setEdges(merged);
    setSelected(await api(`/narrators/${id}`));
    startSim(m, merged);
  }

  function startSim(m: Map<number, GNode>, es: GEdge[]) {
    if (simRef.current) cancelAnimationFrame(simRef.current);
    let ticks = 0;
    const arr = [...m.values()];
    function tick() {
      // repulsion
      for (const a of arr) {
        for (const b of arr) {
          if (a === b) continue;
          const dx = a.x! - b.x!, dy = a.y! - b.y!;
          const d2 = Math.max(dx * dx + dy * dy, 100);
          const f = 2600 / d2;
          a.vx! += (dx / Math.sqrt(d2)) * f;
          a.vy! += (dy / Math.sqrt(d2)) * f;
        }
      }
      // springs
      for (const e of es) {
        const s = m.get(e.student), tt = m.get(e.teacher);
        if (!s || !tt) continue;
        const dx = tt.x! - s.x!, dy = tt.y! - s.y!;
        const d = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
        const f = (d - 120) * 0.02;
        s.vx! += (dx / d) * f; s.vy! += (dy / d) * f;
        tt.vx! -= (dx / d) * f; tt.vy! -= (dy / d) * f;
      }
      for (const n of arr) {
        n.vx! *= 0.85; n.vy! *= 0.85;
        n.x! = Math.max(30, Math.min(W - 30, n.x! + n.vx!));
        n.y! = Math.max(24, Math.min(H - 24, n.y! + n.vy!));
      }
      forceRender((v) => v + 1);
      if (++ticks < 120) simRef.current = requestAnimationFrame(tick);
    }
    simRef.current = requestAnimationFrame(tick);
  }

  useEffect(() => () => { if (simRef.current) cancelAnimationFrame(simRef.current); }, []);

  const nodeArr = [...nodes.values()];

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <h1 className="text-2xl font-bold">{t("narrators_title")}</h1>
        <form onSubmit={(e) => { e.preventDefault(); search(); }} className="flex gap-2 flex-1 max-w-md">
          <input value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder={t("narrators_search")}
            className="flex-1 border-2 border-islamic-teal rounded-xl px-4 py-2 font-arabic outline-none" />
          <button className="bg-islamic-teal text-white rounded-xl px-4">{t("nav_search")}</button>
        </form>
      </div>

      {results.length > 0 && (
        <div className="bg-white rounded-xl shadow p-2 mb-4 max-h-56 overflow-y-auto">
          {results.map((r) => (
            <button key={r.narrator_id} onClick={() => loadGraph(r.narrator_id)}
              className="w-full text-start px-3 py-2 rounded hover:bg-islamic-teal/10 font-arabic flex justify-between">
              <span>{r.canonical_ar}</span>
              <span className="text-xs text-gray-400">{r.mentions} ↺</span>
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-col lg:flex-row gap-4">
        <div className="flex-1 bg-[#0a0a0a] rounded-2xl shadow-lg overflow-hidden relative" dir="ltr">
          {nodeArr.length === 0 ? (
            <div className="h-[620px] flex items-center justify-center text-gray-500 font-arabic">
              {t("narrators_hint")}
            </div>
          ) : (
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
              {edges.map((e, i) => {
                const s = nodes.get(e.student), tt = nodes.get(e.teacher);
                if (!s || !tt) return null;
                return (
                  <line key={i} x1={s.x} y1={s.y} x2={tt.x} y2={tt.y}
                    stroke="#334155" strokeWidth={Math.min(1 + e.weight / 8, 4)}
                    strokeOpacity={0.7} />
                );
              })}
              {nodeArr.map((n, i) => (
                <g key={n.narrator_id} transform={`translate(${n.x},${n.y})`}
                  className="cursor-pointer"
                  onMouseEnter={() => setHover(n)} onMouseLeave={() => setHover(null)}
                  onClick={() => expand(n.narrator_id)}>
                  <circle r={n.narrator_id === center ? 14 : Math.min(5 + Math.sqrt(n.mentions), 12)}
                    fill={n.narrator_id === center ? "#D4AF37" : NEON[i % NEON.length]}
                    stroke="#0a0a0a" strokeWidth={2} />
                  <text y={-14} textAnchor="middle" fill="#e2e8f0" fontSize={11}
                    className="font-arabic pointer-events-none">
                    {n.name.length > 22 ? n.name.slice(0, 22) + "…" : n.name}
                  </text>
                </g>
              ))}
            </svg>
          )}
          {hover && (
            <div className="absolute top-3 left-3 bg-deep-teal/95 text-white rounded-lg px-4 py-2 text-sm font-arabic" dir="rtl">
              <div className="font-bold text-islamic-gold">{hover.name}</div>
              <div className="text-xs opacity-80">{hover.mentions} {t("narrators_mentions")} — {t("narrators_click_expand")}</div>
            </div>
          )}
        </div>

        {selected && (
          <aside className="lg:w-80 bg-white rounded-2xl shadow p-4">
            <h2 className="font-arabic font-bold text-lg text-deep-teal border-b pb-2 mb-3">
              {selected.canonical_ar}
            </h2>
            <div className="text-sm space-y-1 mb-4">
              <div>{t("narrators_chains")}: <b>{selected.chains}</b></div>
              <div>{t("narrators_mentions")}: <b>{selected.mentions}</b></div>
              {selected.death_year_h && <div>ت {selected.death_year_h} هـ</div>}
            </div>
            {selected.aliases?.length > 1 && (
              <div className="flex flex-wrap gap-1 mb-4">
                {selected.aliases.map((a: any, i: number) => (
                  <span key={i} className="text-xs bg-islamic-teal/10 text-islamic-teal rounded-full px-2 py-0.5 font-arabic">
                    {a.alias_ar}
                  </span>
                ))}
              </div>
            )}
            <NarratorHadiths id={selected.narrator_id} />
          </aside>
        )}
      </div>
    </div>
  );
}

function NarratorHadiths({ id }: { id: number }) {
  const { t } = useTranslation();
  const [data, setData] = useState<any>(null);
  useEffect(() => { api(`/narrators/${id}/hadiths?limit=5`).then(setData); }, [id]);
  if (!data) return null;
  return (
    <div>
      <h3 className="font-bold text-sm text-deep-teal mb-2">
        {t("narrators_hadiths")} ({data.total})
      </h3>
      <div className="space-y-2">
        {data.items.map((h: any) => (
          <Link key={h.passage_id} to={`/passage/${h.passage_id}`}
            className="block text-xs bg-islamic-light rounded-lg p-2 hover:bg-islamic-teal/10">
            <span className="text-islamic-gold font-bold">#{h.hadith_num}</span>
            <span className="font-arabic"> {h.preview.slice(0, 90)}…</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
