"use client";

import { useParams } from "next/navigation";
import { getSector } from "@/lib/sectors";
import { useState, useMemo, useEffect, useCallback } from "react";
import { fmt1, fmt2 } from "@/lib/format";
import { Info } from "lucide-react";
import { exportYearlyCSV } from "@/lib/export";
import {
  AreaChart, Area, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Legend, ReferenceLine,
} from "recharts";
import { runScenario } from "@/lib/api";
import type { YearlyResult } from "@/lib/api";
import { Tip } from "@/lib/tip";

type DemandKey = "niti" | "model_fitted" | "india_policy" | "international";

const SCENARIOS = [
  { key: "CPS", label: "Current Policy Scenario", desc: "Existing policies extended to 2070",
    tip: "Only policies already enacted today continue. No new climate commitments. Lower carbon prices, slower clean energy deployment." },
  { key: "NZS", label: "Net Zero Scenario",        desc: "Aggressive decarbonisation pathway",
    tip: "India achieves net-zero emissions by ~2070. Assumes strong policy action, high carbon prices, and rapid deployment of clean technology." },
];

const DEMAND_OPTS: { key: DemandKey; label: string; tip: string }[] = [
  { key: "niti",          label: "NITI Vol.4",             tip: "Official Government of India projection (NITI Aayog Vol.4, 2026). Aggressive infrastructure + manufacturing growth assumption." },
  { key: "model_fitted",  label: "Historical trend",       tip: "S-curve fitted to India's actual production data (1990–2025). Pure extrapolation — where the historical trend naturally leads." },
  { key: "india_policy",  label: "India Policy Consensus", tip: "Blend of National Policy targets and PM Gati Shakti. Assumes India meets its stated manufacturing goals." },
  { key: "international", label: "International Baseline", tip: "IEA STEPS + urbanisation model. Service-led economy — the more conservative international view of India's trajectory." },
];

const CHART_YEARS = [2024, 2028, 2032, 2036, 2040, 2044, 2048, 2052, 2056, 2060, 2065, 2070];
const TABLE_YEARS = [2024, 2030, 2035, 2040, 2050, 2060, 2070];

const T    = { text:"#23261f", sub:"#474c44", muted:"#7a7e74", dim:"#a8ada5", border:"#e8e5de", card:"#ffffff", bg:"#f7f6f2" };
const CARD: React.CSSProperties = { background: T.card, border:`1px solid ${T.border}`, borderRadius: 10, boxShadow:"0 1px 3px rgba(0,0,0,0.04)" };
const DIM  = { color: T.dim };
const TT   = { background:"#ffffff", border:`1px solid ${T.border}`, borderRadius: 6, fontSize: 12, color: T.text };

const SECTOR_ACCENT: Record<string, string> = {
  steel: "#2563eb", cement: "#ea580c", aluminium: "#0284c7",
  textile: "#db2777", fertiliser: "#65a30d",
};

export default function PathwayPage() {
  const params   = useParams();
  const sectorId = typeof params.sector === "string" ? params.sector : "steel";
  const s        = getSector(sectorId);
  const accent   = SECTOR_ACCENT[sectorId] ?? "#60a5fa";

  const [scenario,    setScenario]    = useState("CPS");
  const [demandModel, setDemandModel] = useState<DemandKey>("niti");
  const [running,     setRunning]     = useState(false);
  const [elapsed,     setElapsed]     = useState(0);   // seconds while solver runs
  const [run,         setRun]         = useState<Record<number, YearlyResult> | null>(null);
  const [runError,    setRunError]    = useState<string | null>(null);

  // Tick elapsed timer while a solve is in progress
  useEffect(() => {
    if (!running) { setElapsed(0); return; }
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, [running]);

  const doRun = useCallback(async (sc: string, dm: DemandKey) => {
    // Non-steel v3 backends: pass demand_model name — backend uses its own YAML trajectory
    // (avoids unit mismatch: frontend anchors are in Mt product, backends may use different units)
    // Steel backend: pass demand_anchors in Mt steel (it understands those natively)
    const overrides: Record<string, unknown> = sectorId === "steel"
      ? { demand_anchors: s.demandTrajectories.find((t) => t.key === dm)?.anchors ?? s.demandTrajectories[0].anchors }
      : { demand_model: dm };
    setRunning(true); setRunError(null);
    try {
      const result = await runScenario(s, sc, overrides);
      if (result.status === "not_available" || result.status === "infeasible") {
        setRunError(result.message ?? "Solver returned infeasible.");
      } else if (result.yearly_results) {
        setRun(result.yearly_results as Record<number, YearlyResult>);
      }
    } catch (e) { setRunError(e instanceof Error ? e.message : "Unknown error"); }
    setRunning(false);
  }, [s]);

  // Intentional one-time run of the default scenario on mount / sector switch.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { doRun("CPS", "niti"); }, [doRun]);

  const chartData = useMemo(() => {
    if (!run) return [];
    return CHART_YEARS.map((yr) => {
      const d = run[yr] ?? run[yr - 1] ?? run[yr + 1];
      if (!d) return { year: yr };
      const row: Record<string, number> = { year: yr };
      for (const [route, val] of Object.entries(d.production_by_route ?? {})) row[route] = +(val as number).toFixed(2);
      row["co2_intensity"] = d.co2_intensity;
      row["co2_total"]     = d.co2_total;
      return row;
    });
  }, [run]);

  const kpis = useMemo(() => {
    if (!run) return null;
    const yrs   = Object.keys(run).map(Number).sort((a, b) => a - b);
    const first = run[yrs[0]]; const last = run[yrs[yrs.length - 1]];
    if (!first || !last) return null;
    return {
      finalIntensity: last.co2_intensity,
      reductionPct:   ((first.co2_intensity - last.co2_intensity) / first.co2_intensity) * 100,
      finalDemand:    last.total_production,
      cumulativeCo2:  Object.values(run).reduce((a, y) => a + (y.co2_total ?? 0), 0),
    };
  }, [run]);

  const costChartData = useMemo(() => {
    if (!run) return [];
    return [2024, 2030, 2035, 2040, 2050, 2060, 2070].map((yr) => {
      const d = run[yr];
      if (!d) return { year: yr };
      const row: Record<string, number> = { year: yr };
      for (const route of s.routes) {
        row[route.id] = +(((d.production_by_route?.[route.id] ?? 0) * route.vom_usd_t) / 1000).toFixed(1);
      }
      return row;
    });
  }, [run, s]);

  const vol4Sc    = scenario === "NZS" ? s.vol4.co2_intensity.nzs : s.vol4.co2_intensity.cps;
  const vol4Total = scenario === "NZS" ? s.vol4.co2_total.nzs : s.vol4.co2_total.cps;
  const demLabel  = DEMAND_OPTS.find(d => d.key === demandModel)?.label ?? demandModel;

  function handleExport() {
    if (!run) return;
    exportYearlyCSV(run, s.routes.map(r => r.id),
      `${sectorId}_${scenario}_${demandModel}.csv`,
      { sector: s.label, scenario, demand_model: demandModel, generated: new Date().toISOString().slice(0, 10) });
  }

  return (
    <div>
      <div className="space-y-4">

        {/* ── Header ── */}
        <div style={{ borderBottom:`1px solid ${T.border}`, paddingBottom:18, marginBottom:6, display:"flex", alignItems:"flex-start", justifyContent:"space-between" }}>
          <div>
            <h1 style={{ fontSize:24, fontWeight:700, color:T.text, margin:"0 0 4px", letterSpacing:"-0.01em" }}>Pathway</h1>
            <p style={{ fontSize:13, color:T.muted, margin:0 }}>Technology mix and emissions trajectory · CPS or NZS</p>
          </div>
          {run && (
            <button
              onClick={handleExport}
              title="Download yearly results as CSV"
              style={{
                display:"flex", alignItems:"center", gap:6,
                padding:"7px 14px", borderRadius:8,
                background:"transparent", border:`1px solid ${T.border}`,
                cursor:"pointer", fontSize:12, fontWeight:600, color:T.muted,
                transition:"all 150ms",
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--accent,#6366f1)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--accent,#6366f1)"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = T.border; (e.currentTarget as HTMLButtonElement).style.color = T.muted; }}
            >
              ↓ CSV
            </button>
          )}
        </div>

        {/* Scenario + demand selectors */}
        <div style={{ ...CARD, padding:"16px 20px 14px", display:"flex", flexDirection:"column", gap:12 }}>
          {/* CPS / NZS tabs */}
          <div style={{ display:"flex", alignItems:"center", gap:0, borderBottom:`1px solid ${T.border}`, paddingBottom:2 }}>
            {SCENARIOS.map(sc => (
              <button key={sc.key}
                onClick={() => { setScenario(sc.key); doRun(sc.key, demandModel); }}
                disabled={running}
                style={{
                  padding:"8px 18px 10px",
                  background:"none", border:"none",
                  borderBottom:`2px solid ${scenario === sc.key ? accent : "transparent"}`,
                  marginBottom:-1,
                  cursor:"pointer",
                  transition:"color 150ms",
                  display:"flex", alignItems:"baseline", gap:8,
                }}>
                <span style={{ fontSize:13, fontWeight:800, color:scenario===sc.key ? accent : T.dim, letterSpacing:"0.04em" }}>{sc.key}</span>
                <span style={{ fontSize:11, color:T.dim, fontWeight:400, display:"flex", alignItems:"center", gap:2 }}>{sc.desc}<Tip text={sc.tip}/></span>
              </button>
            ))}
            {running && (
              <span style={{ marginLeft:"auto", fontSize:11, color:accent, alignSelf:"center", display:"flex", alignItems:"center", gap:5 }} className="animate-pulse">
                <svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="20" strokeDashoffset="0"><animateTransform attributeName="transform" type="rotate" from="0 5 5" to="360 5 5" dur="0.8s" repeatCount="indefinite"/></circle></svg>
                {elapsed > 0 ? `Solving… ${elapsed}s` : "Solving…"}
                {elapsed >= 5 && elapsed < 15 && <span style={{ opacity:0.7 }}>· HiGHS running</span>}
                {elapsed >= 15 && elapsed < 60 && <span style={{ opacity:0.7 }}>· optimising 47 years</span>}
                {elapsed >= 60 && <span style={{ opacity:0.7 }}>· almost done</span>}
              </span>
            )}
          </div>
          {/* Demand model pills */}
          <div style={{ display:"flex", flexWrap:"wrap", gap:6, alignItems:"center" }}>
            <span style={{ fontSize:9, fontWeight:700, letterSpacing:"0.12em", textTransform:"uppercase", color:T.dim, marginRight:4, display:"flex", alignItems:"center" }}>
              Demand<Tip text="Which projection of future demand the solver tries to meet." width={220}/>
            </span>
            {DEMAND_OPTS.map(d => (
              <button key={d.key}
                onClick={() => { setDemandModel(d.key); doRun(scenario, d.key); }}
                disabled={running}
                style={{
                  padding:"5px 12px", borderRadius:6, fontSize:11, fontWeight:500,
                  cursor:"pointer", transition:"all 150ms", border:"1px solid",
                  display:"flex", alignItems:"center",
                  ...(demandModel===d.key
                    ? { background:accent+"14", color:accent, borderColor:accent+"50" }
                    : { background:"transparent", color:T.muted, borderColor:T.border })
                }}>
                {d.label}<Tip text={d.tip} width={240}/>
              </button>
            ))}
          </div>
        </div>

        {runError && (
          <div className="flex items-start gap-2.5 rounded-lg px-4 py-3 text-sm"
            style={{ background:"#fffbeb", border:"1px solid #fde68a", color:"#b45309" }}>
            <Info className="h-4 w-4 mt-0.5 flex-shrink-0 opacity-70" />
            <div>
              <p className="font-medium">Live solver unavailable for this sector right now</p>
              <p className="text-xs mt-0.5" style={{ color:"#92400e" }}>
                Showing published NITI Vol.4 benchmark figures below instead of a fresh LP run.
              </p>
            </div>
          </div>
        )}

        {/* KPI strip */}
        {kpis && (
          <div style={{ ...CARD, display:"flex", flexWrap:"wrap", overflow:"hidden" }}>
            {[
              { label:`CO₂ intensity 2070`, val:`${fmt2(kpis.finalIntensity)} tCO₂/${s.unit_short}`,
                tip:`CO₂ emitted per unit of production in 2070. Lower is better. NITI Aayog targets ~0.5–1.2 tCO₂/${s.unit_short} depending on scenario.` },
              { label:"Intensity reduction", val:`${fmt1(kpis.reductionPct)}%`,
                tip:"How much CO₂ per unit of production improves from 2024 to 2070. E.g. 80% = each unit emits 80% less CO₂ than today." },
              { label:`Production 2070`, val:`${fmt1(kpis.finalDemand)} ${s.unit_short}`,
                tip:"Total output in 2070 — how much the sector produces to meet projected demand." },
              { label:"Cumulative CO₂ 2024–2070", val:`${fmt1(kpis.cumulativeCo2/1000)} GtCO₂`,
                tip:"Total CO₂ emitted by this sector across all years 2024–2070. This is the sector's contribution to India's overall carbon budget." },
            ].map((k,i) => (
              <div key={k.label} style={{ flex:"1 1 130px", padding:"14px 20px", borderRight:i<3?`1px solid ${T.border}`:"none" }}>
                <p style={{ fontSize:9, fontWeight:700, letterSpacing:"0.14em", textTransform:"uppercase", color:T.dim, margin:"0 0 8px", display:"flex", alignItems:"center" }}>
                  {k.label}<Tip text={k.tip} width={240}/>
                </p>
                <p style={{ fontSize:20, fontWeight:800, color:T.text, fontVariantNumeric:"tabular-nums", margin:0 }}>{k.val}</p>
              </div>
            ))}
          </div>
        )}

        {/* Tech mix chart */}
        {chartData.length > 0 && (
          <div className="p-5" style={CARD}>
            <p className="text-[10px] font-semibold tracking-widest uppercase mb-1" style={DIM}>Technology Mix</p>
            <p className="text-sm font-semibold mb-4" style={{ color:T.sub }}>{scenario} · {demLabel} ({s.unit_short}/yr)</p>
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={chartData} margin={{ top:4, right:12, left:0, bottom:4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
                <XAxis dataKey="year" tick={{ fontSize:11, fill:T.dim }} stroke="rgba(0,0,0,0.1)" />
                <YAxis tick={{ fontSize:11, fill:T.dim }} stroke="rgba(0,0,0,0.1)"
                  label={{ value:s.unit_short, angle:-90, position:"insideLeft", offset:10, style:{ fontSize:10, fill:T.dim } }} />
                <Tooltip contentStyle={TT} />
                <Legend iconType="circle" wrapperStyle={{ fontSize:11, color:T.muted }} />
                {s.routes.map(r => (
                  <Area key={r.id} type="monotone" dataKey={r.id} stackId="1"
                    stroke={r.color} fill={r.color} fillOpacity={0.75} name={r.label} />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Emissions charts */}
        {chartData.length > 0 && (
          <div style={CARD} className="overflow-hidden">
            <div className="px-5 py-3" style={{ borderBottom:`1px solid ${T.border}` }}>
              <p className="text-[10px] font-semibold tracking-widest uppercase mb-0.5" style={DIM}>Emissions</p>
              <p className="text-sm font-semibold" style={{ color:T.sub }}>{scenario} · {demLabel}</p>
            </div>
            <div style={{ display:"flex", flexWrap:"wrap", gap:20, padding:20 }}>
              <div style={{ flex:"1 1 280px", minWidth:0 }}>
                <p className="text-xs mb-3" style={DIM}>Total CO₂ (Mt/yr)</p>
                <ResponsiveContainer width="100%" height={180}>
                  <LineChart data={chartData} margin={{ top:4, right:16, left:0, bottom:4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
                    <XAxis dataKey="year" tick={{ fontSize:10, fill:T.dim }} stroke="rgba(0,0,0,0.1)" />
                    <YAxis tick={{ fontSize:10, fill:T.dim }} stroke="rgba(0,0,0,0.1)" />
                    <Tooltip contentStyle={TT} />
                    <Line type="monotone" dataKey="co2_total" stroke="#dc2626" strokeWidth={2} dot={false} name="CO₂ total" />
                    <ReferenceLine y={vol4Total[2050]} stroke="rgba(0,0,0,0.15)" strokeDasharray="4 3"
                      label={{ value:`Vol.4 '50`, position:"right", style:{ fontSize:9, fill:T.dim } }} />
                    <ReferenceLine y={vol4Total[2070]} stroke="rgba(0,0,0,0.15)" strokeDasharray="4 3"
                      label={{ value:`Vol.4 '70`, position:"right", style:{ fontSize:9, fill:T.dim } }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div style={{ flex:"1 1 280px", minWidth:0 }}>
                <p className="text-xs mb-3" style={DIM}>CO₂ intensity (tCO₂/{s.unit_short})</p>
                <ResponsiveContainer width="100%" height={180}>
                  <LineChart data={chartData} margin={{ top:4, right:16, left:0, bottom:4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
                    <XAxis dataKey="year" tick={{ fontSize:10, fill:T.dim }} stroke="rgba(0,0,0,0.1)" />
                    <YAxis tick={{ fontSize:10, fill:T.dim }} stroke="rgba(0,0,0,0.1)" />
                    <Tooltip contentStyle={TT} />
                    <Line type="monotone" dataKey="co2_intensity" stroke={accent} strokeWidth={2} dot={false} name="Intensity" />
                    <ReferenceLine y={vol4Sc[2050]} stroke="rgba(0,0,0,0.15)" strokeDasharray="4 3"
                      label={{ value:`Vol.4 '50`, position:"right", style:{ fontSize:9, fill:T.dim } }} />
                    <ReferenceLine y={vol4Sc[2070]} stroke="rgba(0,0,0,0.15)" strokeDasharray="4 3"
                      label={{ value:`Vol.4 '70`, position:"right", style:{ fontSize:9, fill:T.dim } }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}

        {/* Production by route table */}
        {run && (
          <div style={CARD} className="overflow-hidden">
            <div className="px-5 py-3" style={{ borderBottom:`1px solid ${T.border}` }}>
              <p className="text-[10px] font-semibold tracking-widest uppercase mb-0.5" style={DIM}>Production by Route</p>
              <p className="text-sm font-semibold" style={{ color:T.sub }}>{s.unit_short}/yr · {scenario} · {demLabel}</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom:`1px solid ${T.border}`, background:T.bg }}>
                    <th className="text-left px-5 py-2 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>Route</th>
                    {TABLE_YEARS.map(yr => (
                      <th key={yr} className="text-right px-3 py-2 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>{yr}</th>
                    ))}
                    <th className="text-right px-5 py-2 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>Share 2070</th>
                  </tr>
                </thead>
                <tbody>
                  {s.routes.map(route => {
                    const vals     = TABLE_YEARS.map(yr => run[yr]?.production_by_route?.[route.id] ?? null);
                    const tot70    = run[2070]?.total_production ?? 1;
                    const v70      = run[2070]?.production_by_route?.[route.id] ?? 0;
                    const sharePct = (v70 / tot70) * 100;
                    if (!vals.some(v => v !== null && v > 0.01)) return null;
                    return (
                      <tr key={route.id} style={{ borderBottom:`1px solid rgba(0,0,0,0.04)` }}>
                        <td className="px-5 py-2.5">
                          <div className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: route.color }} />
                            <span className="font-medium" style={{ color:T.sub }}>{route.label}</span>
                          </div>
                        </td>
                        {vals.map((v, i) => (
                          <td key={i} className="px-3 py-2.5 text-right font-mono text-xs tabular-nums">
                            {v !== null && v > 0.005
                              ? <span style={{ color:T.muted }}>{v < 10 ? v.toFixed(1) : Math.round(v)}</span>
                              : <span style={{ color:T.dim }}>—</span>}
                          </td>
                        ))}
                        <td className="px-5 py-2.5 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <div className="w-12 h-1 rounded-full overflow-hidden" style={{ background:`rgba(0,0,0,0.08)` }}>
                              <div className="h-full rounded-full" style={{ width:`${Math.min(sharePct,100)}%`, background:route.color }} />
                            </div>
                            <span className="text-xs font-mono tabular-nums w-8 text-right" style={{ color:T.muted }}>{sharePct.toFixed(0)}%</span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  <tr style={{ background:T.bg, borderTop:`1px solid ${T.border}` }}>
                    <td className="px-5 py-2.5 text-xs font-semibold" style={{ color:T.dim }}>Total demand</td>
                    {TABLE_YEARS.map(yr => {
                      const d = run[yr];
                      return (
                        <td key={yr} className="px-3 py-2.5 text-right font-mono text-xs tabular-nums" style={{ color:T.muted }}>
                          {d ? (d.total_production < 10 ? d.total_production.toFixed(1) : Math.round(d.total_production)) : "—"}
                        </td>
                      );
                    })}
                    <td className="px-5 py-2.5 text-right text-xs" style={{ color:T.dim }}>100%</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* O&M cost chart */}
        {costChartData.length > 0 && run && (
          <div className="p-5" style={CARD}>
            <p className="text-[10px] font-semibold tracking-widest uppercase mb-1" style={DIM}>Variable O&amp;M Cost</p>
            <p className="text-sm font-semibold mb-4" style={{ color:T.sub }}>M USD/yr · {scenario} · by route</p>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={costChartData} margin={{ top:4, right:12, left:0, bottom:4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
                <XAxis dataKey="year" tick={{ fontSize:11, fill:T.dim }} stroke="rgba(0,0,0,0.1)" />
                <YAxis tick={{ fontSize:11, fill:T.dim }} stroke="rgba(0,0,0,0.1)"
                  label={{ value:"M USD", angle:-90, position:"insideLeft", offset:10, style:{ fontSize:10, fill:T.dim } }} />
                <Tooltip contentStyle={TT}
                  formatter={(val: unknown, name: unknown) => {
                    const r = s.routes.find(x => x.id === name);
                    return [`${typeof val === "number" ? val.toFixed(0) : val} M USD`, r?.label ?? String(name)];
                  }} />
                <Legend iconType="circle" wrapperStyle={{ fontSize:11, color:T.muted }}
                  formatter={(val) => s.routes.find(x => x.id === val)?.label ?? val} />
                {s.routes.map(r => (
                  <Area key={r.id} type="monotone" dataKey={r.id} stackId="1"
                    stroke={r.color} fill={r.color} fillOpacity={0.75} name={r.id} />
                ))}
              </AreaChart>
            </ResponsiveContainer>
            <p className="text-[10px] mt-2" style={DIM}>Variable O&M only (energy + process inputs). CAPEX amortised separately.</p>
          </div>
        )}

        {/* Emissions summary table */}
        {run && (
          <div style={CARD} className="overflow-hidden">
            <div className="px-5 py-3" style={{ borderBottom:`1px solid ${T.border}` }}>
              <p className="text-[10px] font-semibold tracking-widest uppercase mb-0.5" style={DIM}>Emissions Summary</p>
              <p className="text-sm font-semibold" style={{ color:T.sub }}>{scenario} · {demLabel}</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom:`1px solid ${T.border}`, background:T.bg }}>
                    <th className="text-left px-5 py-2 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>Year</th>
                    <th className="text-right px-4 py-2 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>Demand ({s.unit_short})</th>
                    <th className="text-right px-4 py-2 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>CO₂ intensity</th>
                    <th className="text-right px-4 py-2 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>Total CO₂ (Mt)</th>
                    <th className="text-right px-5 py-2 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>vs Vol.4</th>
                  </tr>
                </thead>
                <tbody>
                  {[2024, 2030, 2035, 2040, 2045, 2050, 2055, 2060, 2065, 2070].map((yr) => {
                    const d = run[yr];
                    if (!d) return null;
                    const v4ref = vol4Sc[yr as keyof typeof vol4Sc];
                    const delta = v4ref ? d.co2_intensity - v4ref : null;
                    return (
                      <tr key={yr} style={{ borderBottom:`1px solid rgba(0,0,0,0.04)` }}>
                        <td className="px-5 py-2 font-medium" style={{ color:T.sub }}>{yr}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs tabular-nums" style={{ color:T.muted }}>{fmt1(d.total_production)}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs tabular-nums" style={{ color:T.muted }}>{fmt2(d.co2_intensity)}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs tabular-nums" style={{ color:T.muted }}>{fmt1(d.co2_total)}</td>
                        <td className="px-5 py-2 text-right font-mono text-xs tabular-nums">
                          {delta !== null ? (
                            <span style={{ color: delta <= 0 ? "#16a34a" : "#dc2626" }}>
                              {delta > 0 ? "+" : ""}{delta.toFixed(2)}
                            </span>
                          ) : <span style={{ color:T.dim }}>—</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Benchmark note */}
        <div className="flex items-start gap-2 text-xs rounded-lg px-4 py-3" style={{ ...CARD, color:T.muted }}>
          <Info className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" style={{ color:T.dim }} />
          <span>
            NITI Vol.4 benchmarks — {scenario} 2050:{" "}
            <strong style={{ color:T.sub }}>{vol4Sc[2050]} tCO₂/{s.unit_short}</strong>,
            2070:{" "}
            <strong style={{ color:T.sub }}>{vol4Sc[2070]} tCO₂/{s.unit_short}</strong>
            {" · "}{s.vol4.citation}
          </span>
        </div>

      </div>
    </div>
  );
}
