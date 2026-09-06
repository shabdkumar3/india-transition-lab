"use client";

import { useParams } from "next/navigation";
import { getSector, logistic, piecewise, INDIA_POP, type SectorConfig } from "@/lib/sectors";
import { Tip } from "@/lib/tip";
import { useState, useMemo } from "react";
import { fmt1 } from "@/lib/format";
import {
  ComposedChart, Line, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";

const YEARS_CHART = Array.from({ length: 81 }, (_, i) => 1990 + i);
const YEARS_TABLE = [2030, 2035, 2040, 2050, 2060, 2070];

const T   = { text:"#23261f", sub:"#474c44", muted:"#7a7e74", dim:"#a8ada5", border:"#e8e5de", card:"#ffffff", bg:"#f7f6f2" };
const CARD: React.CSSProperties = { background:T.card, border:`1px solid ${T.border}`, borderRadius:10, boxShadow:"0 1px 3px rgba(0,0,0,0.04)" };
const DIM  = { color: T.dim };
const TT   = { background:"#ffffff", border:`1px solid ${T.border}`, borderRadius:6, fontSize:12, color:T.text };

export default function DemandPage() {
  const params   = useParams();
  const sectorId = typeof params.sector === "string" ? params.sector : "steel";
  const s        = getSector(sectorId);

  const [active, setActive] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(s.demandTrajectories.map((t) => [t.key, true]))
  );

  const { L, k, t0 } = s.logistic;

  const chartData = useMemo(() => {
    return YEARS_CHART.map((yr) => {
      const row: Record<string, number | null> = { year: yr };
      for (const traj of s.demandTrajectories) {
        // model_fitted draws from histFrom (shows historical context); all others start at 2024
        const lineStart = (traj.useLogistic || traj.key === "model_fitted") ? traj.histFrom : 2024;
        if (yr < lineStart) { row[traj.key] = null; continue; }
        row[traj.key] = traj.useLogistic ? logistic(yr, L, k, t0) : piecewise(traj.anchors, yr);
      }
      // model_fitted ref line for pre-2024 historical context (shown faintly)
      if (!active["model_fitted"]) row["_logistic_ref"] = logistic(yr, L, k, t0);
      return row;
    });
  }, [s, L, k, t0, active]);

  const histDots = useMemo(
    () => s.historical.map((h) => ({ year: h.year, hist: h.production_mt })),
    [s]
  );

  const pop2070 = INDIA_POP[2070] ?? 1629;

  return (
    <div>
      <div className="space-y-4">

        {/* Header */}
        <div style={{ borderBottom:`1px solid ${T.border}`, paddingBottom:18, marginBottom:6 }}>
          <h1 style={{ fontSize:24, fontWeight:700, color:T.text, margin:"0 0 4px", letterSpacing:"-0.01em" }}>Demand</h1>
          <p style={{ fontSize:13, color:T.muted, margin:0 }}>Production trajectories 1990–2070 · four scenarios</p>
        </div>

        {/* Trajectory toggles */}
        <div style={{ display:"flex", flexWrap:"wrap", gap:8, padding:"2px 0" }}>
          <span style={{ fontSize:9, fontWeight:700, letterSpacing:"0.14em", textTransform:"uppercase", color:T.dim, alignSelf:"center", marginRight:4, display:"flex", alignItems:"center" }}>
            Trajectories<Tip text="Four different projections of how much this sector will produce by 2070. Click to show/hide each. The LP solver uses whichever trajectory you select as the demand it must meet." width={260}/>
          </span>
          {s.demandTrajectories.map((t) => (
            <button key={t.key}
              onClick={() => setActive((a) => ({ ...a, [t.key]: !a[t.key] }))}
              style={{
                display:"flex", alignItems:"center", gap:8,
                padding:"7px 14px", borderRadius:8, fontSize:12, fontWeight:500,
                cursor:"pointer", transition:"all 150ms", border:"1px solid",
                ...(active[t.key]
                  ? { background:t.color+"18", color:t.color, borderColor:t.color+"55" }
                  : { background:"transparent", color:T.muted, borderColor:T.border })
              }}>
              <span style={{ width:8, height:8, borderRadius:"50%", flexShrink:0, background:t.color, opacity:active[t.key]?1:0.3 }} />
              {t.label}
              <span style={{ fontSize:10, opacity:0.55 }}>{fmt1(t.end_mt)} {s.unit_short}</span>
            </button>
          ))}
        </div>

        {/* Chart */}
        <div className="p-5" style={CARD}>
          <p className="text-[10px] font-semibold tracking-widest uppercase mb-1" style={DIM}>Production Trajectory</p>
          <p className="text-sm font-semibold mb-4" style={{ color:T.sub }}>{s.unit_short}/yr · 1990–2070</p>
          <ResponsiveContainer width="100%" height={360}>
            <ComposedChart data={chartData} margin={{ top:5, right:16, left:0, bottom:5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
              <XAxis dataKey="year" type="number" domain={[1990, 2070]}
                ticks={[1990, 2000, 2010, 2020, 2030, 2040, 2050, 2060, 2070]}
                tick={{ fontSize:11, fill:T.dim }} stroke="rgba(0,0,0,0.1)" />
              <YAxis tick={{ fontSize:11, fill:T.dim }} stroke="rgba(0,0,0,0.1)"
                label={{ value:s.unit_short, angle:-90, position:"insideLeft", offset:10, style:{ fontSize:10, fill:T.dim } }} />
              <Tooltip contentStyle={TT}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                formatter={(val: any, name: any) => {
                  const traj = s.demandTrajectories.find((t) => t.key === name);
                  return [`${fmt1(val as number)} ${s.unit_short}`, traj?.label ?? name];
                }} />
              <ReferenceLine x={2024} stroke="rgba(0,0,0,0.15)" strokeDasharray="4 3" strokeWidth={1} />

              {!active["model_fitted"] && (
                <Line dataKey="_logistic_ref" stroke="rgba(0,0,0,0.1)" strokeWidth={1}
                  strokeDasharray="6 4" dot={false} connectNulls legendType="none" name="_logistic_ref" />
              )}
              {s.demandTrajectories.map((t) =>
                active[t.key] ? (
                  <Line key={t.key} dataKey={t.key} stroke={t.color} strokeWidth={2}
                    strokeDasharray={t.dash} dot={false} connectNulls name={t.key} />
                ) : null
              )}
              <Scatter data={histDots} dataKey="hist" fill="#6b7280" shape="circle" name="Historical data" legendType="circle" />
            </ComposedChart>
          </ResponsiveContainer>
          <p className="text-[10px] mt-2" style={DIM}>
            Dots = historical production data · Lines start from 2024 baseline · Dashed = logistic reference
          </p>
        </div>

        {/* Milestone table */}
        <div style={CARD} className="overflow-hidden">
          <div className="px-5 py-3" style={{ borderBottom:`1px solid ${T.border}` }}>
            <p className="text-[10px] font-semibold tracking-widest uppercase mb-0.5" style={DIM}>Demand Milestones</p>
            <p className="text-sm font-semibold" style={{ color:T.sub }}>{s.unit_short} · key years</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom:`1px solid ${T.border}`, background:T.bg }}>
                  <th className="text-left px-5 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>Trajectory</th>
                  {YEARS_TABLE.map(yr => (
                    <th key={yr} className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>{yr}</th>
                  ))}
                  <th className="text-right px-5 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>
                    <span className="inline-flex items-center justify-end gap-0.5">kg/cap 2070<Tip text="Kilograms per person per year in 2070. A useful measure to compare how material-intensive India's consumption is vs other countries." width={240}/></span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {s.demandTrajectories.map((t) => {
                  const val2070 = t.useLogistic ? logistic(2070, L, k, t0) : piecewise(t.anchors, 2070);
                  const kgcap  = (val2070 * 1000) / pop2070;
                  return (
                    <tr key={t.key} style={{ borderBottom:`1px solid rgba(0,0,0,0.04)`, opacity:active[t.key]?1:0.4 }}>
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-2">
                          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background:t.color }} />
                          <div>
                            <p className="font-medium" style={{ color:T.sub }}>{t.label}</p>
                            <p className="text-[10px]" style={DIM}>{t.credibility}</p>
                          </div>
                        </div>
                      </td>
                      {YEARS_TABLE.map((yr) => {
                        const v = t.useLogistic ? logistic(yr, L, k, t0) : piecewise(t.anchors, yr);
                        return (
                          <td key={yr} className="px-4 py-3 text-right font-mono text-xs tabular-nums" style={{ color:T.muted }}>
                            {fmt1(v)}
                          </td>
                        );
                      })}
                      <td className="px-5 py-3 text-right font-mono text-xs tabular-nums" style={{ color:T.dim }}>{fmt1(kgcap)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Source cards — full detail */}
        <div className="space-y-5">
          <p className="text-[10px] font-semibold tracking-widest uppercase" style={DIM}>Methodology &amp; Sources</p>
          {s.demandTrajectories.map((t, idx) => {
            const val2070 = t.useLogistic ? logistic(2070, L, k, t0) : piecewise(t.anchors, 2070);
            const val2030 = t.useLogistic ? logistic(2030, L, k, t0) : piecewise(t.anchors, 2030);
            const val2050 = t.useLogistic ? logistic(2050, L, k, t0) : piecewise(t.anchors, 2050);
            return (
              <div key={t.key} style={{ ...CARD, borderRadius:12, overflow:"hidden" }}>
                {/* ── Top banner ── */}
                <div style={{ background:t.color, padding:"20px 24px 16px" }}>
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                      <p style={{ fontSize:11, fontWeight:700, letterSpacing:"0.1em", textTransform:"uppercase", color:"rgba(255,255,255,0.65)", marginBottom:4 }}>
                        Trajectory {idx + 1} of {s.demandTrajectories.length}
                      </p>
                      <h3 style={{ fontSize:22, fontWeight:800, color:"#ffffff", margin:"0 0 4px", letterSpacing:"-0.01em" }}>{t.label}</h3>
                      <p style={{ fontSize:12, color:"rgba(255,255,255,0.75)", margin:0 }}>{t.sublabel}</p>
                    </div>
                    <div style={{ textAlign:"right" }}>
                      <p style={{ fontSize:10, fontWeight:600, textTransform:"uppercase", letterSpacing:"0.08em", color:"rgba(255,255,255,0.6)", marginBottom:2 }}>2070 projection</p>
                      <p style={{ fontSize:36, fontWeight:900, color:"#ffffff", margin:0, lineHeight:1, fontVariantNumeric:"tabular-nums" }}>
                        {fmt1(val2070)}
                        <span style={{ fontSize:14, fontWeight:500, marginLeft:4 }}>{s.unit_short}</span>
                      </p>
                    </div>
                  </div>
                  {/* Key milestones inline */}
                  <div style={{ display:"flex", gap:24, marginTop:16, paddingTop:14, borderTop:"1px solid rgba(255,255,255,0.2)" }}>
                    {[["2030", val2030], ["2050", val2050], ["2070", val2070]].map(([yr, v]) => (
                      <div key={yr as string}>
                        <p style={{ fontSize:10, color:"rgba(255,255,255,0.55)", fontWeight:600, letterSpacing:"0.06em" }}>{yr as string}</p>
                        <p style={{ fontSize:16, fontWeight:700, color:"#ffffff", fontVariantNumeric:"tabular-nums" }}>{fmt1(v as number)} <span style={{ fontSize:11, fontWeight:400 }}>{s.unit_short}</span></p>
                      </div>
                    ))}
                    <div style={{ marginLeft:"auto", display:"flex", alignItems:"center" }}>
                      <span style={{ fontSize:10, fontWeight:700, padding:"4px 10px", borderRadius:20, background:"rgba(255,255,255,0.2)", color:"#ffffff", letterSpacing:"0.04em" }}>
                        {t.credibility}
                      </span>
                    </div>
                  </div>
                </div>

                {/* ── Body — method + assumption ── */}
                <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:0 }}>
                  <div style={{ padding:"20px 24px", borderRight:`1px solid ${T.border}` }}>
                    <p style={{ fontSize:10, fontWeight:700, letterSpacing:"0.12em", textTransform:"uppercase", color:T.dim, marginBottom:8 }}>
                      📐 How this trajectory was built
                    </p>
                    <p style={{ fontSize:13, lineHeight:1.7, color:T.muted, margin:0 }}>{t.method}</p>
                  </div>
                  <div style={{ padding:"20px 24px" }}>
                    <p style={{ fontSize:10, fontWeight:700, letterSpacing:"0.12em", textTransform:"uppercase", color:T.dim, marginBottom:8 }}>
                      💡 Key underlying assumption
                    </p>
                    <p style={{ fontSize:13, lineHeight:1.7, color:T.muted, margin:0 }}>{t.assumption}</p>
                  </div>
                </div>

                {/* ── Source footer ── */}
                <div style={{ padding:"14px 24px", borderTop:`1px solid ${T.border}`, background:T.bg, display:"flex", alignItems:"flex-start", gap:10 }}>
                  <span style={{ fontSize:11, fontWeight:700, color:t.color, flexShrink:0, marginTop:1 }}>Source</span>
                  <p style={{ fontSize:12, color:T.muted, margin:0, lineHeight:1.6 }}>{t.source}</p>
                </div>
              </div>
            );
          })}
        </div>

        {/* ── Technical Documentation Pane ── */}
        <TechDocPane s={s} L={L} k={k} t0={t0} />

      </div>
    </div>
  );
}

/* ─── Collapsible derivation-notes pane ─────────────────────────────────── */

function TechDocPane({ s, L, k, t0 }: { s: SectorConfig; L: number; k: number; t0: number }) {
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState(0);

  const T   = { text:"#23261f", sub:"#474c44", muted:"#7a7e74", dim:"#a8ada5", border:"#e8e5de", card:"#ffffff", bg:"#f7f6f2" };
  const CARD: React.CSSProperties = { background:T.card, border:`1px solid ${T.border}`, borderRadius:10, boxShadow:"0 1px 3px rgba(0,0,0,0.04)" };

  const YEARS_ANCHOR = [2024, 2030, 2035, 2040, 2050, 2060, 2070];

  const traj = s.demandTrajectories[activeTab];
  if (!traj) return null;

  return (
    <div style={{ marginTop: 24 }}>
      {/* Toggle header */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "flex", alignItems: "center", gap: 10,
          width: "100%", padding: "14px 18px",
          background: T.card, border: `1px solid ${T.border}`,
          borderRadius: open ? "10px 10px 0 0" : 10,
          cursor: "pointer", textAlign: "left",
          boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
          transition: "border-radius 150ms",
        }}
      >
        <span style={{ fontSize: 16, lineHeight: 1 }}>📖</span>
        <span style={{ fontSize: 12, fontWeight: 700, color: T.sub, flex: 1 }}>
          Technical Derivation Notes
        </span>
        <span style={{ fontSize: 10, color: T.dim, marginRight: 6 }}>
          Exact numbers · Calculation steps · Data provenance
        </span>
        <span style={{ fontSize: 14, color: T.dim, transform: open ? "rotate(180deg)" : "rotate(0)", transition: "transform 200ms" }}>▾</span>
      </button>

      {open && (
        <div style={{ border: `1px solid ${T.border}`, borderTop: "none", borderRadius: "0 0 10px 10px", background: T.bg }}>

          {/* Trajectory tabs */}
          <div style={{ display: "flex", borderBottom: `1px solid ${T.border}`, overflowX: "auto" }}>
            {s.demandTrajectories.map((t, i) => (
              <button
                key={t.key}
                onClick={() => setActiveTab(i)}
                style={{
                  padding: "10px 18px", fontSize: 11, fontWeight: 600,
                  whiteSpace: "nowrap", cursor: "pointer",
                  color: activeTab === i ? t.color : T.muted,
                  background: "transparent",
                  border: "none",
                  borderBottom: activeTab === i ? `2px solid ${t.color}` : "2px solid transparent",
                  transition: "color 150ms",
                }}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Content for active trajectory */}
          <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>

            {/* Header strip */}
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: traj.color, flexShrink: 0 }} />
              <span style={{ fontSize: 14, fontWeight: 700, color: T.sub }}>{traj.label}</span>
              <span style={{ fontSize: 11, color: T.dim }}>·</span>
              <span style={{ fontSize: 11, color: T.dim }}>{traj.sublabel}</span>
            </div>

            {/* Anchor year table */}
            <div style={{ ...CARD, overflow: "hidden" }}>
              <div style={{ padding: "10px 16px", borderBottom: `1px solid ${T.border}`, background: T.bg }}>
                <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: 0 }}>
                  Projected Demand by Year · {s.unit_short}
                </p>
              </div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                      {YEARS_ANCHOR.map(yr => (
                        <th key={yr} style={{ padding: "8px 14px", textAlign: "right", fontWeight: 700, color: T.dim, fontSize: 10, letterSpacing: "0.06em" }}>{yr}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      {YEARS_ANCHOR.map(yr => {
                        const v = traj.useLogistic ? logistic(yr, L, k, t0) : piecewise(traj.anchors, yr);
                        return (
                          <td key={yr} style={{ padding: "10px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: yr === 2070 ? traj.color : T.muted, fontWeight: yr === 2070 ? 700 : 400 }}>
                            {v.toFixed(1)}
                          </td>
                        );
                      })}
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Derivation notes */}
            {traj.derivation ? (
              <div style={{ ...CARD, padding: "16px 20px" }}>
                <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, marginBottom: 8 }}>
                  🔢 How these numbers were derived
                </p>
                <p style={{ fontSize: 12, lineHeight: 1.8, color: T.muted, margin: 0, whiteSpace: "pre-wrap" }}>
                  {traj.derivation}
                </p>
              </div>
            ) : (
              <div style={{ ...CARD, padding: "14px 20px" }}>
                <p style={{ fontSize: 12, color: T.dim, margin: 0 }}>No derivation notes yet for this trajectory.</p>
              </div>
            )}

            {/* Source */}
            <div style={{ display: "flex", gap: 8, padding: "10px 0" }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: traj.color, flexShrink: 0, marginTop: 1 }}>📄 Source</span>
              <p style={{ fontSize: 11, color: T.muted, margin: 0, lineHeight: 1.6 }}>{traj.source}</p>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
