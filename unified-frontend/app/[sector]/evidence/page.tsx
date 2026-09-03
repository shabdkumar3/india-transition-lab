"use client";

import { useParams } from "next/navigation";
import { getSector } from "@/lib/sectors";
import type { SectorId, TechRoute as Route } from "@/lib/sectors";
import { useState, useMemo } from "react";
import { BookOpen, CheckCircle, Clock, AlertTriangle, Shield, Database } from "lucide-react";

const T_ = { text:"#23261f", sub:"#474c44", muted:"#7a7e74", dim:"#a8ada5", border:"#e8e5de", card:"#ffffff", bg:"#f7f6f2" };
const CARD: React.CSSProperties = { background:T_.card, border:`1px solid ${T_.border}`, borderRadius:10, boxShadow:"0 1px 3px rgba(0,0,0,0.04)" };
const DIM = { color: T_.dim };

type Status = "FROZEN" | "CANDIDATE" | "EXTERNAL_PENDING" | "SCENARIO";

interface EvidenceRow {
  route: string; routeColor: string;
  param: string; value: string; unit: string; source: string;
  year: number; status: Status; confidence: string;
}

/** Per-sector CAPEX/VOM sources — keyed by route id */
const ROUTE_SOURCES: Record<string, { capexSrc: string; capexYr: number; vomSrc: string; co2Src: string; co2Yr: number }> = {
  // Steel
  "BF-BOF":       { capexSrc:"IEA Iron & Steel Roadmap 2020",    capexYr:2020, vomSrc:"worldsteel / CRU 2023", co2Src:"worldsteel CO₂ Data Collection 2024", co2Yr:2024 },
  "Coal-DRI-EAF": { capexSrc:"IEA Iron & Steel Roadmap 2020",    capexYr:2020, vomSrc:"NITI Vol.4 (2023)",     co2Src:"NITI Aayog Vol.4 (2023)",              co2Yr:2023 },
  "Coal-DRI-IF":  { capexSrc:"NITI Vol.4 (2023)",                capexYr:2023, vomSrc:"NITI Vol.4 (2023)",     co2Src:"NITI Aayog Vol.4 (2023)",              co2Yr:2023 },
  "NG-DRI-EAF":   { capexSrc:"IEA Iron & Steel Roadmap 2020",    capexYr:2020, vomSrc:"GAIL / IEA 2023",       co2Src:"IEA Iron & Steel Roadmap 2020",        co2Yr:2020 },
  "H2-DRI-EAF":   { capexSrc:"IEA NZE 2021 + NITI Vol.4",       capexYr:2021, vomSrc:"IRENA H₂ Roadmap 2022", co2Src:"IEA NZE 2021",                         co2Yr:2021 },
  "Scrap-EAF":    { capexSrc:"Tata Steel Ludhiana 0.75 MTPA 2026",capexYr:2026,vomSrc:"MSTC / JPC 2024",      co2Src:"IEA/IMC-2021 EAF mass balance",        co2Yr:2021 },
  // Cement
  "Coal-OPC":        { capexSrc:"IEA Cement Roadmap 2020",       capexYr:2020, vomSrc:"CMA India 2023",        co2Src:"GNR Cement Sustainability Initiative 2023", co2Yr:2023 },
  "Coal-Blended":    { capexSrc:"IEA Cement Roadmap 2020",       capexYr:2020, vomSrc:"CMA India 2023",        co2Src:"GNR CSI 2023",                             co2Yr:2023 },
  "Coal-LC3":        { capexSrc:"IIT Madras / GCCA NZ 2021",     capexYr:2021, vomSrc:"IIT Madras pilot 2022", co2Src:"IEA Cement Roadmap 2018; ECRA",            co2Yr:2021 },
  "AltFuel-Blended": { capexSrc:"GCCA NZ Roadmap 2021",          capexYr:2021, vomSrc:"CMA India 2023",        co2Src:"GNR CSI 2023",                             co2Yr:2023 },
  "CCUS-Blended":    { capexSrc:"GCCA NZ Roadmap 2021",          capexYr:2021, vomSrc:"IEA ETP 2023",          co2Src:"IEA Cement Roadmap 2018",                  co2Yr:2018 },
  // Aluminium
  "Coal-CPP":          { capexSrc:"IEA Aluminium Roadmap 2022",  capexYr:2022, vomSrc:"IAI 2023",              co2Src:"IAI Global LCA 2023",                   co2Yr:2023 },
  "Grid-Electrolysis": { capexSrc:"IAI LCA 2023",                capexYr:2023, vomSrc:"IAI 2023",              co2Src:"IAI Global LCA 2023",                   co2Yr:2023 },
  "RE-Electrolysis":   { capexSrc:"IAI LCA 2023",                capexYr:2023, vomSrc:"MNRE RE tariff 2024",   co2Src:"IEA Aluminium Roadmap 2022",            co2Yr:2022 },
  "Inert-Anode":       { capexSrc:"Elysis JV; IEA NZE 2021",     capexYr:2021, vomSrc:"IEA NZE 2021",         co2Src:"Elysis JV; IEA NZE 2021",               co2Yr:2021 },
  "Secondary-Al":      { capexSrc:"IAI Secondary Al Survey 2023",capexYr:2023, vomSrc:"IAI 2023",              co2Src:"IAI Global LCA 2023",                   co2Yr:2023 },
  // Textile
  "Coal-Processing":    { capexSrc:"UNIDO 2021 + MoT 2023",      capexYr:2023, vomSrc:"BEE PAT textile 2022", co2Src:"TERI Textile Sector Study 2022",        co2Yr:2022 },
  "Gas-Processing":     { capexSrc:"GAIL industrial heat 2023",  capexYr:2023, vomSrc:"GAIL 2023",             co2Src:"IEA Industrial Heat 2023",              co2Yr:2023 },
  "Biomass-Processing": { capexSrc:"MNRE biomass cogen 2023",    capexYr:2023, vomSrc:"MNRE 2023",             co2Src:"TERI 2020 (biogenic = 0)",              co2Yr:2020 },
  "RE-Processing":      { capexSrc:"IEA ETP 2023",               capexYr:2023, vomSrc:"MNRE RE tariff 2024",   co2Src:"IEA ETP 2023",                          co2Yr:2023 },
  "Circular-Textiles":  { capexSrc:"EURATEX 2022; IEA",          capexYr:2022, vomSrc:"EURATEX 2022",          co2Src:"UNECE Fashion and SDGs; IEA",           co2Yr:2022 },
  // Fertiliser
  "Coal-Gasification":  { capexSrc:"IFA India Report 2023",      capexYr:2023, vomSrc:"IFA 2023 + FAI",        co2Src:"IFA 2023 + FAI India",                  co2Yr:2023 },
  "NG-SMR":             { capexSrc:"IEA Ammonia Roadmap 2021",   capexYr:2021, vomSrc:"IEA / GAIL 2023",        co2Src:"IEA Ammonia Technology Roadmap 2021",   co2Yr:2021 },
  "NG-SMR-CCUS":        { capexSrc:"IEA Ammonia Roadmap 2021",   capexYr:2021, vomSrc:"IEA ETP 2023",           co2Src:"IEA Ammonia Roadmap 2021",              co2Yr:2021 },
  "Green-H2-Urea":      { capexSrc:"IRENA H₂ Roadmap 2022",     capexYr:2022, vomSrc:"MNRE GHM 2023",          co2Src:"IEA NZE 2021",                          co2Yr:2021 },
  "Bio-Ammonia":        { capexSrc:"IEA ETP 2023",               capexYr:2023, vomSrc:"IEA ETP 2023",           co2Src:"IEA ETP 2023",                          co2Yr:2023 },
};

function routeToRows(r: Route): EvidenceRow[] {
  const src = ROUTE_SOURCES[r.id] ?? {
    capexSrc: "NITI Vol.4 (2023)", capexYr: 2023,
    vomSrc: "NITI Vol.4 (2023)",
    co2Src: "NITI Vol.4 (2023)", co2Yr: 2023,
  };
  const isCandidate = !!r.pending;
  const capexStatus: Status = isCandidate ? "CANDIDATE" : "FROZEN";
  const vomStatus: Status   = "EXTERNAL_PENDING";
  const co2Status: Status   = isCandidate ? "CANDIDATE" : "FROZEN";

  return [
    {
      route: r.label, routeColor: r.color,
      param: "CAPEX", value: String(r.capex_usd_t), unit: "$/t-cap",
      source: src.capexSrc, year: src.capexYr,
      status: capexStatus,
      confidence: isCandidate ? "Low–Medium" : "High",
    },
    {
      route: r.label, routeColor: r.color,
      param: "VOM", value: String(r.vom_usd_t), unit: "$/t",
      source: src.vomSrc, year: src.capexYr,
      status: vomStatus,
      confidence: "Medium",
    },
    {
      route: r.label, routeColor: r.color,
      param: "CO₂ intensity", value: String(r.co2_intensity), unit: "tCO₂/t",
      source: src.co2Src, year: src.co2Yr,
      status: co2Status,
      confidence: isCandidate ? "Medium" : "High",
    },
  ];
}

const STATUS_COLORS: Record<Status, string> = {
  FROZEN: "#16a34a", CANDIDATE: "#2563eb", EXTERNAL_PENDING: "#d97706", SCENARIO: "#7a7e74",
};

interface TrustMetric { label: string; value: string; status: "ok" | "warn" | "info"; note: string; }

const TRUST_DATA: Record<SectorId, TrustMetric[]> = {
  steel: [
    { label: "Model Engine",       value: "Pyomo MILP (HiGHS)",    status: "ok",   note: "Full MILP with provenance gating" },
    { label: "Solver",             value: "HiGHS 1.7.1 via scipy", status: "ok",   note: "Deterministic, reproducible" },
    { label: "Baseline Objective", value: "~1,727,000 M USD",      status: "ok",   note: "6-route model" },
    { label: "Route Economics",    value: "3/6 fully frozen",       status: "warn", note: "Coal-DRI-EAF, Coal-DRI-IF, H2-DRI-EAF are CANDIDATE" },
    { label: "Scrap Intensity",    value: "1.08 t/t",               status: "warn", note: "Not frozen to Indian-specific source" },
    { label: "H2-DRI CAPEX",      value: "820 $/t (IEA NZE)",      status: "warn", note: "No Indian commercial H2-DRI plant exists yet" },
    { label: "Carbon Price",       value: "Modelled trajectory",    status: "info", note: "India has no enacted carbon pricing as of 2026" },
  ],
  cement: [
    { label: "Model Engine",  value: "SciPy LP (HiGHS)",   status: "ok",   note: "Continuous LP with CRF+WACC+PLI" },
    { label: "Solver",        value: "HiGHS via scipy",     status: "ok",   note: "Deterministic" },
    { label: "CCUS CAPEX",    value: "110 $/t (GCCA)",      status: "warn", note: "No commercial CCUS in Indian cement" },
    { label: "LC3 CAPEX",     value: "58 $/t (CANDIDATE)",  status: "warn", note: "IIT Madras pilot — not commercial scale" },
    { label: "Carbon Price",  value: "Modelled trajectory", status: "info", note: "No enacted carbon pricing for cement" },
  ],
  aluminium: [
    { label: "Model Engine",       value: "SciPy LP (HiGHS)",   status: "ok",   note: "CRF+WACC+GridEI+PLI" },
    { label: "Inert Anode",        value: "TRL 4 (Lab/R&D)",    status: "warn", note: "No commercial scale globally" },
    { label: "RE Price",           value: "High sensitivity",    status: "info", note: "97% of Al emissions from electricity" },
    { label: "Coal-CPP Dominance", value: "~80% of smelting",   status: "warn", note: "Structural lock-in" },
  ],
  textile: [
    { label: "Model Engine",     value: "SciPy LP (HiGHS)",   status: "ok",   note: "Multi-fuel routes" },
    { label: "SME Fragmentation",value: "75% in SMEs",         status: "warn", note: "Capital-constrained; deployment risk" },
    { label: "Biomass Supply",   value: "CANDIDATE",           status: "warn", note: "Regional variability high" },
    { label: "RE-Processing",    value: "TRL 8",               status: "ok",   note: "Heat pump + RE proven" },
  ],
  fertiliser: [
    { label: "Model Engine",     value: "SciPy LP (HiGHS)",   status: "ok",   note: "NGHM PLI + Green H₂ trajectory" },
    { label: "Green-H2-Urea",   value: "TRL 7 — demo",        status: "warn", note: "No Indian commercial plant" },
    { label: "Net-Negative CO₂", value: "−0.35 tCO₂/t",      status: "info", note: "CO₂ fixed into urea product" },
    { label: "NG Price",         value: "High sensitivity",    status: "info", note: "NG-SMR cheapest when gas is cheap" },
  ],
};

const STATUSES: Status[] = ["FROZEN", "CANDIDATE", "EXTERNAL_PENDING"];

export default function EvidenceTrustPage() {
  const params   = useParams();
  const sectorId = (typeof params.sector === "string" ? params.sector : "steel") as SectorId;
  const s        = getSector(sectorId);
  const metrics  = TRUST_DATA[sectorId] ?? TRUST_DATA.steel;

  const [filter, setFilter] = useState<string>("all");
  const [paramFilter, setParamFilter] = useState<string>("all");

  // Build evidence rows dynamically from routes
  const allRows: EvidenceRow[] = useMemo(
    () => s.routes.flatMap(routeToRows),
    [s]
  );

  const filtered = useMemo(() => allRows.filter(row => {
    const statusOk = filter === "all" || row.status === filter;
    const paramOk  = paramFilter === "all" || row.param === paramFilter;
    return statusOk && paramOk;
  }), [allRows, filter, paramFilter]);

  const okCount   = metrics.filter(m => m.status === "ok").length;
  const warnCount = metrics.filter(m => m.status === "warn").length;
  const infoCount = metrics.filter(m => m.status === "info").length;

  const totalRows   = allRows.length;
  const frozenCount = allRows.filter(r => r.status === "FROZEN").length;

  return (
    <div>
      <div className="space-y-4">

        {/* Header */}
        <div style={{ borderBottom:`1px solid ${T_.border}`, paddingBottom:18, marginBottom:6 }}>
          <h1 style={{ fontSize:24, fontWeight:700, color:T_.text, margin:"0 0 4px", letterSpacing:"-0.01em" }}>Evidence &amp; Trust</h1>
          <p style={{ fontSize:13, color:T_.muted, margin:0 }}>
            Parameter provenance, data confidence and model integrity for {s.label}
          </p>
        </div>

        {/* ── Section 1: Evidence ── */}
        <div style={{ ...CARD, padding:"14px 20px" }}>
          <div className="flex items-center gap-2 mb-1">
            <BookOpen className="h-4 w-4" style={{ color:T_.dim }} />
            <p className="text-[10px] font-semibold tracking-widest uppercase" style={DIM}>
              Parameter Evidence &amp; Provenance
              <span style={{ color:T_.muted, fontWeight:400, textTransform:"none", letterSpacing:0 }}>
                {" "}— {totalRows} parameters across {s.routes.length} routes
                ({frozenCount} frozen, {totalRows - frozenCount} candidate/pending)
              </span>
            </p>
          </div>
          <p className="text-sm mt-1" style={{ color:T_.muted }}>
            <span style={{ color:"#16a34a", fontWeight:600 }}>FROZEN</span> = published official data ·{" "}
            <span style={{ color:"#2563eb", fontWeight:600 }}>CANDIDATE</span> = derived/projected ·{" "}
            <span style={{ color:"#d97706", fontWeight:600 }}>EXTERNAL PENDING</span> = source identified, value estimated
          </p>
        </div>

        {/* Filters */}
        <div style={{ display:"flex", gap:8, flexWrap:"wrap", alignItems:"center" }}>
          <span style={{ fontSize:9, fontWeight:700, letterSpacing:"0.12em", textTransform:"uppercase", color:T_.dim }}>Status</span>
          {["all", ...STATUSES].map(st => (
            <button key={st} onClick={() => setFilter(st)}
              style={{
                padding:"5px 12px", borderRadius:6, fontSize:11, fontWeight:600,
                cursor:"pointer", transition:"all 150ms", border:"1px solid",
                ...(filter === st
                  ? { background:"#2563eb14", color:"#2563eb", borderColor:"#2563eb44" }
                  : { background:"transparent", color:T_.muted, borderColor:T_.border })
              }}>
              {st === "all" ? "All" : st.replace(/_/g, " ")}
            </button>
          ))}
          <span style={{ fontSize:9, fontWeight:700, letterSpacing:"0.12em", textTransform:"uppercase", color:T_.dim, marginLeft:8 }}>Param</span>
          {["all", "CAPEX", "VOM", "CO₂ intensity"].map(p => (
            <button key={p} onClick={() => setParamFilter(p)}
              style={{
                padding:"5px 12px", borderRadius:6, fontSize:11, fontWeight:600,
                cursor:"pointer", transition:"all 150ms", border:"1px solid",
                ...(paramFilter === p
                  ? { background:"#d9770614", color:"#d97706", borderColor:"#d9770644" }
                  : { background:"transparent", color:T_.muted, borderColor:T_.border })
              }}>
              {p === "all" ? "All params" : p}
            </button>
          ))}
        </div>

        <div style={CARD} className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom:`1px solid ${T_.border}`, background:T_.bg }}>
                  {["Route", "Parameter", "Value", "Source", "Year", "Status", "Confidence"].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((e, i) => {
                  const stColor = STATUS_COLORS[e.status];
                  const Icon = e.status === "FROZEN" ? CheckCircle : e.status === "CANDIDATE" ? Clock : AlertTriangle;
                  return (
                    <tr key={i} style={{ borderBottom:`1px solid rgba(0,0,0,0.04)` }}>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background:e.routeColor }} />
                          <span className="text-xs font-medium whitespace-nowrap" style={{ color:T_.sub }}>{e.route}</span>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-xs font-semibold" style={{ color:T_.muted }}>{e.param}</td>
                      <td className="px-4 py-2.5 font-mono text-xs tabular-nums" style={{ color:T_.sub }}>{e.value} <span style={{ color:T_.dim }}>{e.unit}</span></td>
                      <td className="px-4 py-2.5 text-xs max-w-52" style={{ color:T_.muted }}>{e.source}</td>
                      <td className="px-4 py-2.5 font-mono text-xs" style={{ color:T_.dim }}>{e.year}</td>
                      <td className="px-4 py-2.5">
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded whitespace-nowrap"
                          style={{ background:stColor+"18", color:stColor }}>
                          <Icon className="h-3 w-3" /> {e.status.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-xs" style={{ color:T_.dim }}>{e.confidence}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-2" style={{ borderTop:`1px solid ${T_.border}`, background:T_.bg }}>
            <p className="text-[10px]" style={DIM}>
              Showing {filtered.length} of {totalRows} parameter rows · {s.routes.length} routes × 3 params (CAPEX, VOM, CO₂) each
            </p>
          </div>
        </div>

        {/* ── Section 2: Trust ── */}
        <div style={{ borderTop:`2px solid ${T_.border}`, paddingTop:20 }}>
          <div style={{ ...CARD, padding:"14px 20px", marginBottom:12 }}>
            <div className="flex items-center gap-2 mb-1">
              <Shield className="h-4 w-4" style={{ color:T_.dim }} />
              <p className="text-[10px] font-semibold tracking-widest uppercase" style={DIM}>Model Trust &amp; Integrity</p>
            </div>
            <p className="text-sm" style={{ color:T_.muted }}>
              Scientific transparency for {s.label}. Every result is traceable to sources and assumptions.
            </p>
          </div>

          <div style={{ display:"flex", gap:12, flexWrap:"wrap", marginBottom:12 }}>
            {[
              { label:"Verified",      count:okCount,   color:"#16a34a", Icon:CheckCircle },
              { label:"Uncertain",     count:warnCount, color:"#d97706", Icon:AlertTriangle },
              { label:"Informational", count:infoCount, color:"#2563eb", Icon:Database },
            ].map(m => (
              <div key={m.label} className="flex items-center gap-2 px-4 py-2.5 rounded-lg"
                style={{ background:m.color+"12", border:"1px solid "+m.color+"33" }}>
                <m.Icon className="h-4 w-4" style={{ color:m.color }} />
                <span className="text-sm font-semibold" style={{ color:m.color }}>{m.count}</span>
                <span className="text-xs" style={DIM}>{m.label}</span>
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
                    const Icon  = m.status === "ok" ? CheckCircle : m.status === "warn" ? AlertTriangle : Database;
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
        </div>

        <p className="text-[11px] text-center" style={DIM}>{s.vol4.citation}</p>
      </div>
    </div>
  );
}
