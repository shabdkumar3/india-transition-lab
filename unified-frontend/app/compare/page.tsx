"use client";

import { SECTOR_LIST } from "@/lib/sectors";
import { runScenario } from "@/lib/api";
import type { YearlyResult } from "@/lib/api";
import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { fmt1, fmt2 } from "@/lib/format";
import { Tip } from "@/lib/tip";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";

const CHART_YEARS = [2024, 2029, 2034, 2039, 2044, 2049, 2054, 2059, 2064, 2069];

const SECTOR_COLORS: Record<string, string> = {
  steel:      "#2563eb",
  cement:     "#ea580c",
  aluminium:  "#0284c7",
  textile:    "#db2777",
  fertiliser: "#65a30d",
};

type ScenarioKey = "CPS" | "NZS";
type MetricKey   = "co2_intensity" | "co2_total" | "total_production";

const METRIC_OPTS: { key: MetricKey; label: string; unit: (u: string) => string }[] = [
  { key: "co2_intensity",    label: "CO₂ Intensity",     unit: (u) => `tCO₂/${u}` },
  { key: "co2_total",        label: "Total CO₂ (Mt/yr)", unit: ()  => "Mt/yr"       },
  { key: "total_production", label: "Production",        unit: (u) => u              },
];

const T = {
  text:   "#23261f",
  sub:    "#474c44",
  muted:  "#7a7e74",
  dim:    "#a8ada5",
  border: "#e8e5de",
  card:   "#ffffff",
  bg:     "#f7f6f2",
};

const CARD: React.CSSProperties = {
  background: T.card,
  border: `1px solid ${T.border}`,
  borderRadius: 10,
  boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
};

const TT = {
  background: "#ffffff",
  border: `1px solid ${T.border}`,
  borderRadius: 6,
  fontSize: 12,
  color: T.text,
  boxShadow: "0 4px 16px rgba(0,0,0,0.08)",
};

export default function ComparePage() {
  const [scenario, setScenario] = useState<ScenarioKey>("CPS");
  const [metric,   setMetric]   = useState<MetricKey>("co2_intensity");
  const [selected, setSelected] = useState<Set<string>>(new Set(SECTOR_LIST.map(s => s.id)));
  const [data,     setData]     = useState<Record<string, Record<number, YearlyResult>>>({});
  const [loading,  setLoading]  = useState(true);

  useEffect(() => {
    const fetches = SECTOR_LIST.flatMap(s =>
      (["CPS", "NZS"] as ScenarioKey[]).map(async sc => {
        const res = await runScenario(s, sc);
        return { id: s.id + "_" + sc, yr: res.yearly_results as Record<number, YearlyResult> };
      })
    );
    Promise.all(fetches).then(results => {
      const merged: Record<string, Record<number, YearlyResult>> = {};
      for (const { id, yr } of results) if (yr) merged[id] = yr;
      setData(merged); setLoading(false);
    });
  }, []);

  const chartData = useMemo(() => {
    return CHART_YEARS.map(yr => {
      const row: Record<string, number> = { year: yr };
      for (const s of SECTOR_LIST) {
        if (!selected.has(s.id)) continue;
        const d = data[s.id + "_" + scenario]?.[yr];
        if (d) row[s.id] = +(d[metric] as number).toFixed(metric === "co2_intensity" ? 3 : 1);
      }
      return row;
    });
  }, [data, scenario, metric, selected]);

  const ranking = useMemo(() => {
    return SECTOR_LIST.filter(s => selected.has(s.id)).map(s => {
      const key   = s.id + "_" + scenario;
      const d24   = data[key]?.[2024];
      const d70   = data[key]?.[2069] ?? data[key]?.[2070];
      const nzs70 = data[s.id + "_NZS"]?.[2069] ?? data[s.id + "_NZS"]?.[2070];
      return {
        s, d24, d70, nzs70,
        reduction: d24 && d70
          ? ((d24[metric] as number) - (d70[metric] as number)) / Math.abs(d24[metric] as number) * 100
          : null,
      };
    }).sort((a, b) => (a.reduction ?? 0) - (b.reduction ?? 0));
  }, [data, scenario, metric, selected]);

  const metricDef = METRIC_OPTS.find(m => m.key === metric)!;

  return (
    <div style={{ background: T.bg, minHeight: "100vh" }}>

      {/* Top nav */}
      <header style={{
        background: T.card,
        borderBottom: `1px solid ${T.border}`,
        position: "sticky", top: 0, zIndex: 50,
      }}>
        <div className="max-w-screen-2xl mx-auto px-6">
          <div className="flex items-center h-12 gap-4">
            <Link href="/" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none", flexShrink: 0 }}>
              <div style={{
                width: 26, height: 26, borderRadius: 7, flexShrink: 0,
                background: "linear-gradient(135deg, #1e3a5f, #2563eb)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <span style={{ color: "#ffffff", fontWeight: 900, fontSize: 9, letterSpacing: "-0.02em" }}>IN</span>
              </div>
              <div style={{ lineHeight: 1.2 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>India Transition Lab</div>
                <div style={{ fontSize: 9, letterSpacing: "0.1em", textTransform: "uppercase", color: T.dim }}>NITI Vol.4 · 2026</div>
              </div>
            </Link>
            <div style={{ flex: 1 }} />
            <Link href="/" style={{ fontSize: 12, color: T.muted, textDecoration: "none", padding: "5px 10px", borderRadius: 6, transition: "color 150ms" }}
              onMouseEnter={e => (e.currentTarget.style.color = T.text)}
              onMouseLeave={e => (e.currentTarget.style.color = T.muted)}>
              ← All Sectors
            </Link>
            <Link href="/methodology" style={{ fontSize: 12, color: T.muted, textDecoration: "none", padding: "5px 10px", borderRadius: 6, transition: "color 150ms" }}
              onMouseEnter={e => (e.currentTarget.style.color = T.text)}
              onMouseLeave={e => (e.currentTarget.style.color = T.muted)}>
              Docs
            </Link>
          </div>
        </div>
      </header>

      {/* Sub-nav */}
      <div style={{
        background: T.card,
        borderBottom: `1px solid ${T.border}`,
        position: "sticky", top: 48, zIndex: 40,
      }}>
        <div className="max-w-screen-2xl mx-auto px-6">
          <div style={{ display: "flex", alignItems: "center", height: 44, gap: 12 }}>
            <div style={{ width: 3, height: 20, borderRadius: 2, background: "#2563eb", flexShrink: 0 }} />
            <span style={{ fontSize: 13, fontWeight: 700, color: T.text }}>Cross-Sector Comparison</span>
            <span style={{ color: T.border }}>·</span>
            <span style={{ fontSize: 11, color: T.muted }}>Decarbonisation pace across all 5 sectors</span>
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "20px 24px 40px" }} className="space-y-5">

        {/* Controls */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 24, alignItems: "flex-start" }}>

          {/* Scenario */}
          <div>
            <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: "0 0 8px", display: "flex", alignItems: "center" }}>
              Scenario<Tip text="CPS = Current Policy Scenario (business-as-usual — only existing policies). NZS = Net Zero Scenario (ambitious decarbonisation to hit net zero by 2070)." width={260}/>
            </p>
            <div style={{ display: "flex", border: `1px solid ${T.border}`, borderRadius: 8, overflow: "hidden", background: T.bg }}>
              {(["CPS", "NZS"] as ScenarioKey[]).map(sc => (
                <button key={sc} onClick={() => setScenario(sc)}
                  style={{
                    padding: "6px 16px", fontSize: 12, fontWeight: 600, cursor: "pointer", border: "none", transition: "all 150ms",
                    background: scenario === sc ? T.card : "transparent",
                    color: scenario === sc ? T.text : T.muted,
                    boxShadow: scenario === sc ? "0 1px 4px rgba(0,0,0,0.08)" : "none",
                  }}>
                  {sc}
                </button>
              ))}
            </div>
          </div>

          {/* Metric */}
          <div>
            <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: "0 0 8px", display: "flex", alignItems: "center" }}>
              Metric<Tip text="CO₂ Intensity = emissions per unit produced. Total CO₂ = absolute sector emissions. Production = physical output in sector units." width={260}/>
            </p>
            <div style={{ display: "flex", border: `1px solid ${T.border}`, borderRadius: 8, overflow: "hidden", background: T.bg }}>
              {METRIC_OPTS.map(m => (
                <button key={m.key} onClick={() => setMetric(m.key)}
                  style={{
                    padding: "6px 12px", fontSize: 11, fontWeight: 600, cursor: "pointer", transition: "all 150ms",
                    border: "none",
                    borderRight: `1px solid ${T.border}`,
                    background: metric === m.key ? T.card : "transparent",
                    color: metric === m.key ? T.text : T.muted,
                    boxShadow: metric === m.key ? "0 1px 4px rgba(0,0,0,0.08)" : "none",
                  }}>
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          {/* Sectors */}
          <div>
            <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: "0 0 8px" }}>Sectors</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {SECTOR_LIST.map(s => {
                const on    = selected.has(s.id);
                const color = SECTOR_COLORS[s.id];
                return (
                  <button key={s.id}
                    onClick={() => setSelected(prev => {
                      const next = new Set(prev);
                      if (on) next.delete(s.id); else next.add(s.id);
                      return next;
                    })}
                    style={{
                      display: "flex", alignItems: "center", gap: 6, padding: "5px 12px",
                      borderRadius: 7, fontSize: 11, fontWeight: 600, cursor: "pointer", transition: "all 150ms",
                      border: `1px solid ${on ? color + "55" : T.border}`,
                      background: on ? color + "12" : T.bg,
                      color: on ? color : T.muted,
                    }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: on ? color : T.dim, flexShrink: 0 }} />
                    {s.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Chart */}
        <div style={{ ...CARD, padding: 20 }}>
          <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: "0 0 4px" }}>{metricDef.label}</p>
          <p style={{ fontSize: 13, fontWeight: 600, color: T.sub, margin: "0 0 16px" }}>{scenario} scenario · 2024–2070</p>
          {loading ? (
            <div style={{ height: 320 }}>
              <div style={{ display:"flex", gap:4, alignItems:"flex-end", height:260, padding:"0 8px" }}>
                {[0.55,0.7,0.6,0.9,0.75,0.8,0.65,0.88,0.72,0.95].map((h,i) => (
                  <div key={i} className="animate-pulse flex-1" style={{ height:`${h*100}%`, background:"rgba(0,0,0,0.06)", borderRadius:2 }} />
                ))}
              </div>
              <p style={{ textAlign:"center", fontSize:11, color:T.dim, marginTop:12 }}>Solving LP for all 5 sectors…</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
                <XAxis dataKey="year" tick={{ fontSize: 11, fill: T.dim }} stroke="rgba(0,0,0,0.1)" />
                <YAxis tick={{ fontSize: 11, fill: T.dim }} stroke="rgba(0,0,0,0.1)"
                  label={{ value: metricDef.unit("Mt"), angle: -90, position: "insideLeft", offset: 10, style: { fontSize: 10, fill: T.dim } }} />
                <Tooltip contentStyle={TT}
                  formatter={(val: unknown, name: unknown) => {
                    const s = SECTOR_LIST.find(x => x.id === name);
                    const v = typeof val === "number"
                      ? (metric === "co2_intensity" ? val.toFixed(3) : fmt1(val))
                      : String(val);
                    return [`${v} ${metricDef.unit(s?.unit_short ?? "")}`, s?.label ?? String(name)];
                  }} />
                <Legend iconType="circle"
                  wrapperStyle={{ fontSize: 11, color: T.muted }}
                  formatter={(val) => SECTOR_LIST.find(x => x.id === val)?.label ?? val} />
                {SECTOR_LIST.filter(s => selected.has(s.id)).map(s => (
                  <Line key={s.id} type="monotone" dataKey={s.id}
                    stroke={SECTOR_COLORS[s.id]} strokeWidth={2} dot={false} connectNulls />
                ))}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Ranking table */}
        <div style={{ ...CARD, overflow: "hidden" }}>
          <div style={{ padding: "12px 20px", borderBottom: `1px solid ${T.border}` }}>
            <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: "0 0 2px" }}>Sector Ranking</p>
            <p style={{ fontSize: 13, fontWeight: 600, color: T.sub, margin: 0 }}>{metricDef.label} · {scenario}</p>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${T.border}`, background: T.bg }}>
                  {["Sector", "2024", "2050", "2070", "NZS 2070", "2024→2070"].map((h, i) => (
                    <th key={h} style={{
                      padding: "8px 16px",
                      fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase",
                      color: T.dim, textAlign: i === 0 ? "left" : "right",
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ranking.map(({ s, d24, d70, nzs70, reduction }) => {
                  const key    = s.id + "_" + scenario;
                  const d50    = data[key]?.[2049] ?? data[key]?.[2050];
                  const get    = (d: YearlyResult | undefined) => d ? (d[metric] as number) : null;
                  const v24    = get(d24);
                  const v50    = get(d50);
                  const v70    = get(d70);
                  const nzsVal = nzs70 ? (nzs70[metric] as number) : null;
                  const color  = SECTOR_COLORS[s.id];
                  return (
                    <tr key={s.id} style={{ borderBottom: `1px solid rgba(0,0,0,0.04)`, transition: "background 100ms" }}
                      onMouseEnter={e => (e.currentTarget.style.background = T.bg)}
                      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                      <td style={{ padding: "10px 16px" }}>
                        <Link href={`/${s.id}/pathway`} style={{ display: "flex", alignItems: "center", gap: 8, textDecoration: "none" }}>
                          <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
                          <span style={{ fontWeight: 600, color: T.text }}>{s.label}</span>
                        </Link>
                      </td>
                      {[v24, v50, v70].map((v, i) => (
                        <td key={i} style={{ padding: "10px 16px", textAlign: "right", fontVariantNumeric: "tabular-nums", fontFamily: "monospace", fontSize: 12, color: T.muted }}>
                          {v !== null ? (metric === "co2_intensity" ? fmt2(v) : fmt1(v)) : loading ? <span style={{ color: T.dim, fontSize: 10 }}>…</span> : "—"}
                        </td>
                      ))}
                      <td style={{ padding: "10px 16px", textAlign: "right", fontVariantNumeric: "tabular-nums", fontFamily: "monospace", fontSize: 12, color: "#16a34a", fontWeight: 600 }}>
                        {nzsVal !== null ? (metric === "co2_intensity" ? fmt2(nzsVal) : fmt1(nzsVal)) : "—"}
                      </td>
                      <td style={{ padding: "10px 16px", textAlign: "right" }}>
                        {reduction !== null ? (
                          <span style={{ fontSize: 12, fontWeight: 700, fontVariantNumeric: "tabular-nums", color: reduction > 0 ? "#16a34a" : "#dc2626" }}>
                            {reduction > 0 ? "−" : "+"}{Math.abs(reduction).toFixed(0)}%
                          </span>
                        ) : loading ? <span style={{ color: T.dim, fontSize: 10 }}>…</span> : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <p style={{ fontSize: 11, textAlign: "center", color: T.dim }}>
          All results from LP optimisation — NITI Vol.4 demand trajectory ·{" "}
          <Link href="/methodology" style={{ color: T.muted, textDecoration: "underline" }}>Model methodology</Link>
        </p>

      </div>
    </div>
  );
}
