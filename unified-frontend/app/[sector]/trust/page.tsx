"use client";

import { useParams } from "next/navigation";
import { getSector } from "@/lib/sectors";
import type { SectorId } from "@/lib/sectors";
import { Shield, CheckCircle, AlertTriangle, Database } from "lucide-react";

const T_ = { text:"#23261f", sub:"#474c44", muted:"#7a7e74", dim:"#a8ada5", border:"#e8e5de", card:"#ffffff", bg:"#f7f6f2" };
const CARD: React.CSSProperties = { background:T_.card, border:`1px solid ${T_.border}`, borderRadius:10, boxShadow:"0 1px 3px rgba(0,0,0,0.04)" };
const DIM = { color: T_.dim };

interface TrustMetric { label: string; value: string; status: "ok" | "warn" | "info"; note: string; }

const TRUST_DATA: Record<SectorId, TrustMetric[]> = {
  steel: [
    { label: "Model Engine", value: "Pyomo MILP (HiGHS)", status: "ok", note: "Full mixed-integer linear programming with provenance gating" },
    { label: "Solver", value: "HiGHS 1.7.1 via scipy", status: "ok", note: "Deterministic, reproducible" },
    { label: "Baseline Objective", value: "~1,727,000 M USD", status: "ok", note: "6-route model (updated from 3-route 506K baseline)" },
    { label: "Backend Tests", value: "~466/521 passing", status: "warn", note: "55 failures mostly stale tests from route expansion" },
    { label: "Route Economics", value: "3/6 fully frozen", status: "warn", note: "Coal-DRI-EAF, Coal-DRI-IF, H2-DRI-EAF are CANDIDATE" },
    { label: "Scrap Intensity", value: "1.08 t/t", status: "warn", note: "Not frozen to an Indian-specific source" },
    { label: "H2-DRI CAPEX", value: "820 $/t (IEA NZE)", status: "warn", note: "No Indian commercial H2-DRI plant exists yet" },
    { label: "M1 Electrolyser", value: "DEFERRED", status: "warn", note: "No real electrolyser dataset available" },
    { label: "Carbon Price", value: "Modelled trajectory", status: "info", note: "India has no enacted carbon pricing as of 2026" },
  ],
  cement: [
    { label: "Model Engine", value: "SciPy LP (HiGHS)", status: "ok", note: "Continuous LP with CRF+WACC+PLI" },
    { label: "Solver", value: "HiGHS via scipy", status: "ok", note: "Deterministic" },
    { label: "Backend Tests", value: "LP verified", status: "ok", note: "Feasibility confirmed for CPS and NZS" },
    { label: "CCUS CAPEX", value: "110 $/t (GCCA)", status: "warn", note: "No commercial CCUS in Indian cement" },
    { label: "LC3 CAPEX", value: "58 $/t (CANDIDATE)", status: "warn", note: "IIT Madras pilot \u2014 not commercial scale" },
    { label: "Carbon Price", value: "Modelled trajectory", status: "info", note: "No enacted carbon pricing for cement" },
  ],
  aluminium: [
    { label: "Model Engine", value: "SciPy LP (HiGHS)", status: "ok", note: "CRF+WACC+GridEI+PLI" },
    { label: "Inert Anode", value: "TRL 4 (Lab/R&D)", status: "warn", note: "No commercial scale globally" },
    { label: "RE Price Sensitivity", value: "High \u2014 dominant lever", status: "info", note: "97% of Al emissions from electricity" },
    { label: "Coal-CPP Dominance", value: "~80% of smelting", status: "warn", note: "Structural lock-in" },
  ],
  textile: [
    { label: "Model Engine", value: "SciPy LP (HiGHS)", status: "ok", note: "Multi-fuel routes" },
    { label: "SME Fragmentation", value: "75% in SMEs", status: "warn", note: "Capital-constrained" },
    { label: "Biomass Availability", value: "CANDIDATE", status: "warn", note: "Varies by region" },
    { label: "RE-Processing", value: "TRL 8", status: "ok", note: "Heat pump + RE proven" },
  ],
  fertiliser: [
    { label: "Model Engine", value: "SciPy LP (HiGHS)", status: "ok", note: "NGHM PLI + Green H\u2082 trajectory" },
    { label: "Green-H2-Urea", value: "TRL 7 \u2014 demo", status: "warn", note: "No Indian commercial plant" },
    { label: "Net-Negative CO\u2082", value: "\u22120.35 tCO\u2082/t", status: "info", note: "CO\u2082 fixed into urea product" },
    { label: "NG Price Sensitivity", value: "High", status: "info", note: "NG-SMR cheapest when gas is cheap" },
  ],
};

export default function TrustPage() {
  const params = useParams();
  const sectorId = (typeof params.sector === "string" ? params.sector : "steel") as SectorId;
  const s = getSector(sectorId);
  const metrics = TRUST_DATA[sectorId] ?? TRUST_DATA.steel;
  const okCount = metrics.filter(m => m.status === "ok").length;
  const warnCount = metrics.filter(m => m.status === "warn").length;
  const infoCount = metrics.filter(m => m.status === "info").length;

  return (
    <div>
      <div className="space-y-4">
        {/* Header */}
        <div style={{ borderBottom:`1px solid ${T_.border}`, paddingBottom:18, marginBottom:6 }}>
          <h1 style={{ fontSize:24, fontWeight:700, color:T_.text, margin:"0 0 4px", letterSpacing:"-0.01em" }}>Trust</h1>
          <p style={{ fontSize:13, color:T_.muted, margin:0 }}>Scientific transparency and model integrity for {s.label}</p>
        </div>

        <div style={{ ...CARD, padding:"16px 20px" }}>
          <div className="flex items-center gap-2 mb-1">
            <Shield className="h-4 w-4" style={{ color:T_.dim }} />
            <p className="text-[10px] font-semibold tracking-widest uppercase" style={DIM}>Trust Center</p>
          </div>
          <p className="text-sm" style={{ color:T_.muted }}>
            Scientific transparency for {s.label}. Every result is traceable to sources and assumptions.
          </p>
        </div>

        <div style={{ display:"flex", gap:12, flexWrap:"wrap" }}>
          {[
            { label:"Verified",       count:okCount,   color:"#16a34a", Icon:CheckCircle },
            { label:"Uncertain",      count:warnCount, color:"#d97706", Icon:AlertTriangle },
            { label:"Informational",  count:infoCount, color:"#2563eb", Icon:Database },
          ].map(s => (
            <div key={s.label} className="flex items-center gap-2 px-4 py-2.5 rounded-lg"
              style={{ background:s.color+"12", border:"1px solid "+s.color+"33" }}>
              <s.Icon className="h-4 w-4" style={{ color:s.color }} />
              <span className="text-sm font-semibold" style={{ color:s.color }}>{s.count}</span>
              <span className="text-xs" style={DIM}>{s.label}</span>
            </div>
          ))}
        </div>

        <div style={CARD} className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom:`1px solid ${T_.border}`, background:T_.bg }}>
                  {["Item", "Value", "Status", "Note"].map(h => (
                    <th key={h} className="text-left px-5 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {metrics.map((m, i) => {
                  const color = m.status === "ok" ? "#16a34a" : m.status === "warn" ? "#d97706" : "#2563eb";
                  const Icon = m.status === "ok" ? CheckCircle : m.status === "warn" ? AlertTriangle : Database;
                  return (
                    <tr key={i} style={{ borderBottom:`1px solid rgba(0,0,0,0.04)` }}>
                      <td className="px-5 py-3 font-medium" style={{ color:T_.sub }}>{m.label}</td>
                      <td className="px-5 py-3 font-mono text-xs" style={{ color:T_.muted }}>{m.value}</td>
                      <td className="px-5 py-3">
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded"
                          style={{ background:color+"14", color }}>
                          <Icon className="h-3 w-3" /> {m.status.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-xs max-w-sm" style={{ color:T_.dim }}>{m.note}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="text-[11px] text-center" style={DIM}>Model version: {s.vol4.citation}</div>
      </div>
    </div>
  );
}
