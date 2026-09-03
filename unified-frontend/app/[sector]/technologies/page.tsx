"use client";

import { useParams } from "next/navigation";
import { getSector } from "@/lib/sectors";
import type { SectorId } from "@/lib/sectors";
import { Zap, Info, CheckCircle, Clock, TrendingDown, BookOpen, Layers } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ScatterChart, Scatter, ZAxis, ReferenceLine,
} from "recharts";

// ─── Research-grade data ────────────────────────────────────────────────────

/** Technology Readiness Level (TRL 1–9) per route */
const TRL_DATA: Record<string, { trl: number; label: string }> = {
  // Steel
  "BF-BOF":       { trl: 9, label: "Commercial" },
  "Coal-DRI-EAF": { trl: 9, label: "Commercial" },
  "Coal-DRI-IF":  { trl: 9, label: "Commercial" },
  "NG-DRI-EAF":   { trl: 9, label: "Commercial" },
  "H2-DRI-EAF":   { trl: 7, label: "Demonstration" },
  "Scrap-EAF":    { trl: 9, label: "Commercial" },
  // Cement
  "Coal-OPC":        { trl: 9, label: "Commercial" },
  "Coal-Blended":    { trl: 9, label: "Commercial" },
  "Coal-LC3":        { trl: 8, label: "Early commercial" },
  "AltFuel-Blended": { trl: 9, label: "Commercial" },
  "CCUS-Blended":    { trl: 5, label: "Pilot / R&D" },
  // Aluminium
  "Coal-CPP":          { trl: 9, label: "Commercial" },
  "Grid-Electrolysis": { trl: 9, label: "Commercial" },
  "RE-Electrolysis":   { trl: 9, label: "Commercial" },
  "Inert-Anode":       { trl: 4, label: "Lab / R&D" },
  "Secondary-Al":      { trl: 9, label: "Commercial" },
  // Textile
  "Coal-Processing":    { trl: 9, label: "Commercial" },
  "Gas-Processing":     { trl: 9, label: "Commercial" },
  "Biomass-Processing": { trl: 8, label: "Early commercial" },
  "RE-Processing":      { trl: 8, label: "Early commercial" },
  "Circular-Textiles":  { trl: 7, label: "Demonstration" },
  // Fertiliser
  "Coal-Gasification": { trl: 9, label: "Commercial" },
  "NG-SMR":            { trl: 9, label: "Commercial" },
  "NG-SMR-CCUS":       { trl: 7, label: "Demonstration" },
  "Green-H2-Urea":     { trl: 7, label: "Demonstration" },
  "Bio-Ammonia":       { trl: 6, label: "Pilot" },
};

/** Learning rates (% cost reduction per doubling of global cumulative installed capacity) */
const LEARNING_RATES: Record<string, number> = {
  "BF-BOF": 2, "Coal-DRI-EAF": 3, "Coal-DRI-IF": 3, "NG-DRI-EAF": 5,
  "H2-DRI-EAF": 18, "Scrap-EAF": 4,
  "Coal-OPC": 1, "Coal-Blended": 2, "Coal-LC3": 12, "AltFuel-Blended": 5, "CCUS-Blended": 15,
  "Coal-CPP": 2, "Grid-Electrolysis": 3, "RE-Electrolysis": 14, "Inert-Anode": 20, "Secondary-Al": 6,
  "Coal-Processing": 2, "Gas-Processing": 3, "Biomass-Processing": 8, "RE-Processing": 12, "Circular-Textiles": 10,
  "Coal-Gasification": 2, "NG-SMR": 4, "NG-SMR-CCUS": 12, "Green-H2-Urea": 16, "Bio-Ammonia": 11,
};

/** LCOX = CAPEX × CRF + VOM, CRF at WACC=12%, n=25y = 0.1275 */
const CRF = 0.1275;
function lcox(capex: number, vom: number): number { return Math.round(capex * CRF + vom); }

/** Global CO₂ intensity benchmarks (tCO₂/t product, 2023–24) */
const GLOBAL_BENCHMARKS: Record<SectorId, {
  region: string; intensity: number; note: string; source: string; color: string;
}[]> = {
  steel: [
    { region: "India (avg)",  intensity: 2.54, note: "Coal-heavy DRI + BF-BOF, ~71% primary",       source: "worldsteel (2024)",                                      color: "#1d4f7a" },
    { region: "China (avg)",  intensity: 1.85, note: "Primarily BF-BOF; scrap share rising",         source: "worldsteel (2024)",                                      color: "#dc2626" },
    { region: "World (avg)",  intensity: 1.91, note: "All production routes weighted by output",     source: "worldsteel Statistical Yearbook (2023)",                  color: "#6b7280" },
    { region: "EU (avg)",     intensity: 1.52, note: "~40% EAF scrap; BF-BOF with NG co-firing",    source: "worldsteel / Eurofer (2024)",                            color: "#2563eb" },
    { region: "Global BAT",   intensity: 1.38, note: "Best BF-BOF + top-quartile efficiency",        source: "IEA Iron & Steel Technology Roadmap (2020)",             color: "#16a34a" },
    { region: "Near-zero",    intensity: 0.05, note: "H₂-DRI-EAF at scale (projected 2035+)",       source: "IEA Net Zero by 2050 (2021); HYBRIT pilot data",          color: "#0d9488" },
  ],
  cement: [
    { region: "India (avg)",  intensity: 0.62, note: "Highly blended PPC/PSC, among world's best",  source: "GNR Cement Sustainability Initiative (2023)",             color: "#c2410c" },
    { region: "China (avg)",  intensity: 0.65, note: "Improving blending rates; still OPC-heavy",    source: "GNR CSI / CBMA (2023)",                                  color: "#dc2626" },
    { region: "World (avg)",  intensity: 0.60, note: "Global mean across all kiln types",            source: "IEA Cement Technology Roadmap (2018)",                   color: "#6b7280" },
    { region: "EU (avg)",     intensity: 0.62, note: "Efficient kilns, moderate blending",           source: "CEMBUREAU Activity Report (2023)",                       color: "#2563eb" },
    { region: "Global BAT",   intensity: 0.50, note: "Pre-calciner kiln + high SCM substitution",   source: "IEA Cement Roadmap (2018); ECRA CCS study",              color: "#16a34a" },
    { region: "Near-zero",    intensity: 0.08, note: "CCUS + oxyfuel kiln (projected 2040+)",        source: "IEA ETP 2023; Global Cement & Concrete Assoc.",          color: "#0891b2" },
  ],
  aluminium: [
    { region: "India (avg)",  intensity: 23.5, note: "~80% coal captive power; Jharkhand, Odisha smelters (incl. Scope 1+2+PFC)", source: "NITI Aayog (2026) Vol.4 Ch.3.3; IAI (2023)",  color: "#0284c7" },
    { region: "China (avg)",  intensity: 13.2, note: "Shifting to hydro in Yunnan; coal still ~60%",        source: "IAI (2024); CNIA",                                color: "#dc2626" },
    { region: "World (avg)",  intensity: 11.5, note: "Weighted by production; global grid mix",             source: "IAI Global LCA (2023)",                           color: "#6b7280" },
    { region: "EU (avg)",     intensity:  6.7, note: "~55% renewable power; Norway, Iceland hydro",         source: "European Aluminium (2023)",                       color: "#2563eb" },
    { region: "Global BAT",   intensity:  4.5, note: "Hydro-powered Hall-Héroult + waste heat recovery",    source: "IEA Aluminium Roadmap (2022)",                    color: "#16a34a" },
    { region: "Near-zero",    intensity:  0.5, note: "Inert anode + 100% RE (projected 2035+)",             source: "Elysis JV; IEA NZE (2021)",                       color: "#0891b2" },
  ],
  textile: [
    { region: "India (avg)",  intensity: 3.8, note: "Coal-steam dominant; inefficient dyeing/finishing",    source: "TERI Textile Sector Study (2022)",                color: "#be185d" },
    { region: "China (avg)",  intensity: 2.4, note: "Natural gas transitioning; more efficient equipment",  source: "IEA Industrial Energy Technology (2023)",         color: "#dc2626" },
    { region: "World (avg)",  intensity: 2.6, note: "Weighted average, all processes",                      source: "IEA Industrial Heat Decarbonisation (2022)",      color: "#6b7280" },
    { region: "EU (avg)",     intensity: 1.8, note: "Gas + efficient electric heat; EURATEX survey",        source: "EURATEX (2022); IEA",                             color: "#2563eb" },
    { region: "Global BAT",   intensity: 1.2, note: "Heat pumps + best-in-class processing; EU mills",     source: "IEA ETP Clean Technology Guide (2023)",           color: "#16a34a" },
    { region: "Near-zero",    intensity: 0.3, note: "RE electric heat + circular fibre input (2030+)",      source: "UNECE Fashion and SDGs report; IEA",              color: "#0891b2" },
  ],
  fertiliser: [
    { region: "India (avg)",  intensity: 2.5, note: "Mix of coal gasification (~60%) + NG-SMR",    source: "IFA India Fertiliser Report (2023); MoC Annual",          color: "#4d7c0f" },
    { region: "China (avg)",  intensity: 3.2, note: "Heavily coal-based; world's largest producer", source: "IEA Ammonia Report (2021); CIEC",                        color: "#dc2626" },
    { region: "World (avg)",  intensity: 2.3, note: "NG-SMR dominant globally (75% of production)", source: "IFA World Fertilizer Outlook (2023)",                    color: "#6b7280" },
    { region: "EU (avg)",     intensity: 1.8, note: "NG-SMR with partial CCUS; Yara, OCI plants",  source: "Fertilizers Europe (2023); IEA Ammonia",                 color: "#2563eb" },
    { region: "Global BAT",   intensity: 1.6, note: "Best NG-SMR efficiency + process integration", source: "IEA Ammonia Technology Roadmap (2021)",                  color: "#16a34a" },
    { region: "Near-zero",    intensity:-0.7, note: "Green H₂ urea: CO₂ fixed into product (2030+)", source: "IEA NZE; Haldor Topsoe; IRENA H₂ Roadmap (2022)",     color: "#0891b2" },
  ],
};

/** Policy instruments per sector */
const POLICY_CONTEXT: Record<SectorId, {
  instruments: { name: string; description: string; status: string }[];
  investment_bn_nzs: number;
  co2_share: number;
}> = {
  steel: {
    investment_bn_nzs: 420,
    co2_share: 35,
    instruments: [
      { name: "PAT Scheme (Cycle I–VI)",       description: "Perform, Achieve & Trade — energy efficiency certificates; 69 steel plants covered in BEE PAT", status: "Active" },
      { name: "National Steel Policy 2017",     description: "Target 300 Mt capacity by 2030, 160 kg/cap by 2030–31; technology upgradation fund", status: "Active" },
      { name: "NMIZ (National Mfg. Zones)",     description: "Dedicated steel clusters with shared infrastructure; Jagdishpur, Mundra hubs", status: "Active" },
      { name: "PM Gati Shakti NIP",             description: "₹111L Cr infrastructure plan 2021–26; largest steel consumer catalyst", status: "Active" },
      { name: "CCUS Mission (Proposed)",        description: "MoS & DST National CCUS Mission; ₹800 Cr R&D allocation pending", status: "Proposed" },
    ],
  },
  cement: {
    investment_bn_nzs: 85,
    co2_share: 28,
    instruments: [
      { name: "PAT Scheme (Cycle I–VI)",        description: "56 cement plants under BEE PAT; sector achieved 20% energy intensity improvement (2007–2023)", status: "Active" },
      { name: "National Cement Policy (Draft)",  description: "Min. clinker factor of 0.65 mandated; blending targets in IS 455/456", status: "Draft" },
      { name: "Green Building Rating (GRIHA)",   description: "GRIHA promotes LC3 and blended cement; 6,000+ buildings rated", status: "Active" },
      { name: "Waste Heat Recovery (WHR) PLI",  description: "MNRE WHR scheme; 600 MW WHR potential in cement; 75% capital subsidy", status: "Active" },
      { name: "CCUS Clusters (Vindhya)",        description: "Proposed CO₂ storage cluster near cement belt; DST + MoPNG initiative", status: "Proposed" },
    ],
  },
  aluminium: {
    investment_bn_nzs: 62,
    co2_share: 6,
    instruments: [
      { name: "NALCO / BALCO Captive RE",       description: "NALCO 900 MW RE + Vedanta 1000 MW; replacing coal CPP progressively", status: "Active" },
      { name: "National Aluminium Mission",      description: "MoM 2021: target 5 Mt primary by 2030 + secondary push", status: "Active" },
      { name: "PLI Advanced Chemistry Cell",     description: "₹18,100 Cr PLI for ACC batteries drives aluminium demand; 50 GWh target by 2030", status: "Active" },
      { name: "Aluminium Scrap Policy (2019)",   description: "BIS/MoM extended product liability; EV battery recycling linked", status: "Active" },
      { name: "Inert Anode R&D (DST)",          description: "DST Materials Mission: inert anode prototypes at IIT Bombay, IISc", status: "Pilot" },
    ],
  },
  textile: {
    investment_bn_nzs: 35,
    co2_share: 7,
    instruments: [
      { name: "PM MITRA Scheme",                description: "7 integrated textile parks; ₹4,445 Cr; plug-and-play RE infrastructure mandatory", status: "Active" },
      { name: "PLI Textiles (Man-made Fibre)",  description: "₹10,683 Cr PLI; 64 companies; technical textiles and MMF focus", status: "Active" },
      { name: "National Textile Policy (Draft)", description: "RE mandate for export-oriented units; EPR for textile waste", status: "Draft" },
      { name: "TERI CleanTex Programme",        description: "TERI + NITRA: energy benchmarking 300+ textile SMEs; roadmap to 2030", status: "Active" },
      { name: "GHG Protocol Reporting (SEBI)",  description: "SEBI BRSR Core: top 1000 listed companies mandatory GHG disclosure from FY23", status: "Active" },
    ],
  },
  fertiliser: {
    investment_bn_nzs: 48,
    co2_share: 8,
    instruments: [
      { name: "NBS Scheme (Nutrient-Based Subsidy)", description: "DoF: P&K subsidy linked to nutrient content; excludes urea (still price-controlled)", status: "Active" },
      { name: "PM Pranam Scheme",               description: "States incentivised to reduce chemical fertiliser use; alternate nutrients push", status: "Active" },
      { name: "Nano-Urea Programme (IFFCO)",    description: "IFFCO Nano Urea (240 ml = 1 bag); 100M bottles/yr capacity; reduces conventional urea 25–50%", status: "Active" },
      { name: "Green Hydrogen Mission — Fertiliser", description: "MNRE GHM: ₹19,744 Cr; Fertiliser sector identified as anchor off-taker for green ammonia", status: "Active" },
      { name: "IFFCO Ammonia–Urea CCUS Pilot", description: "IFFCO Phulpur plant: 0.1 Mt/yr CO₂ capture pilot (MEA); scaling to commercial FY26", status: "Pilot" },
    ],
  },
};

function TrlBadge({ trl, label }: { trl: number; label: string }) {
  const color =
    trl >= 9 ? "#16a34a" :
    trl >= 7 ? "#2563eb" :
    trl >= 5 ? "#d97706" : "#dc2626";
  const bg =
    trl >= 9 ? "rgba(22,163,74,0.12)" :
    trl >= 7 ? "rgba(37,99,235,0.12)" :
    trl >= 5 ? "rgba(217,119,6,0.12)" : "rgba(220,38,38,0.12)";
  return (
    <span className="inline-flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded"
      style={{ background: bg, color }}>
      TRL {trl} · {label}
    </span>
  );
}

export default function TechnologiesPage() {
  const params = useParams();
  const sectorId = (typeof params.sector === "string" ? params.sector : "steel") as SectorId;
  const s = getSector(sectorId);

  const policy     = POLICY_CONTEXT[sectorId];
  const maxCo2     = Math.max(...s.routes.map(r => r.co2_intensity));

  // LCOX (Levelised Cost of X) for each route
  const routesWithLcox = s.routes.map(r => ({
    ...r,
    lcox:          lcox(r.capex_usd_t, r.vom_usd_t),
    trl:           TRL_DATA[r.id]?.trl ?? 9,
    trlLabel:      TRL_DATA[r.id]?.label ?? "Commercial",
    learningRate:  LEARNING_RATES[r.id] ?? 3,
  }));

  // MAC vs cheapest (by lcox) route
  const incumbent = routesWithLcox.reduce((a, b) => (a.co2_intensity > b.co2_intensity ? a : b));
  const routesWithMac = routesWithLcox.map(r => {
    const deltaCost = r.lcox - incumbent.lcox;
    const deltaCo2  = incumbent.co2_intensity - r.co2_intensity;
    const mac = deltaCo2 > 0.01 ? Math.round(deltaCost / deltaCo2) : null;
    return { ...r, mac };
  });

  // Sorted for MAC curve (by mac, ascending)
  const macCurveData = routesWithMac
    .filter(r => r.mac !== null && r.id !== incumbent.id)
    .sort((a, b) => (a.mac ?? 0) - (b.mac ?? 0));

  // Scatter data: CO2 vs LCOX
  const scatterData = routesWithLcox.map(r => ({
    name: r.label, x: r.co2_intensity, y: r.lcox, color: r.color, trl: r.trl,
  }));

  const T = { text:"#23261f", sub:"#474c44", muted:"#7a7e74", dim:"#a8ada5", border:"#e8e5de", card:"#ffffff", bg:"#f7f6f2" };
  const tooltipStyle = { background:"#ffffff", border:`1px solid ${T.border}`, borderRadius:6, fontSize:12, color:T.text };
  const CARD: React.CSSProperties = { background:T.card, border:`1px solid ${T.border}`, borderRadius:10, boxShadow:"0 1px 3px rgba(0,0,0,0.04)" };
  const DIM  = { color: T.dim };

  return (
    <div>

      <div className="space-y-4">

        {/* Header */}
        <div style={{ borderBottom:`1px solid ${T.border}`, paddingBottom:18, marginBottom:6 }}>
          <h1 style={{ fontSize:24, fontWeight:700, color:T.text, margin:"0 0 4px", letterSpacing:"-0.01em" }}>Technologies</h1>
          <p style={{ fontSize:13, color:T.muted, margin:0 }}>Route costs, TRL, learning rates and global benchmarks</p>
        </div>

        {/* ── 1. Route techno-economic table ── */}
        <div style={CARD} className="overflow-hidden">
          <div className="px-5 py-3 flex items-center justify-between" style={{ borderBottom:`1px solid ${T.border}` }}>
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4" style={{ color:T.dim }} />
              <p className="text-[10px] font-semibold tracking-widest uppercase" style={DIM}>Route Techno-Economic Characterisation</p>
            </div>
            <span className="text-[10px]" style={DIM}>LCOX = CAPEX×CRF + VOM · WACC=12%, n=25yr</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ borderBottom:`1px solid ${T.border}`, background:T.bg }}>
                  <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>Route</th>
                  <th className="text-right px-3 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>TRL</th>
                  <th className="text-right px-3 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>CAPEX ($/t-cap)</th>
                  <th className="text-right px-3 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>VOM ($/t)</th>
                  <th className="text-right px-3 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>LCOX ($/t)</th>
                  <th className="text-right px-3 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>CO₂ (tCO₂/t)</th>
                  <th className="text-right px-3 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>Learning</th>
                  <th className="text-right px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>Available</th>
                </tr>
              </thead>
              <tbody>
                {routesWithMac.sort((a, b) => a.lcox - b.lcox).map((r) => {
                  const co2Frac = r.co2_intensity / maxCo2;
                  return (
                    <tr key={r.id} style={{ borderBottom:`1px solid rgba(0,0,0,0.04)` }}>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: r.color }} />
                          <span className="font-semibold" style={{ color:T.sub }}>{r.label}</span>
                        </div>
                        <p className="text-[10px] mt-0.5 ml-4" style={DIM}>{r.description}</p>
                        <div className="ml-4 mt-1">
                          <TrlBadge trl={r.trl} label={r.trlLabel} />
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right">
                        <div className="flex justify-end">
                          {Array.from({ length: 9 }).map((_, i) => (
                            <div key={i} className="w-1.5 h-4 mx-px rounded-sm"
                              style={{ background: i < r.trl ? (r.trl >= 8 ? "#16a34a" : r.trl >= 6 ? "#2563eb" : r.trl >= 4 ? "#d97706" : "#dc2626") : "rgba(0,0,0,0.1)" }} />
                          ))}
                        </div>
                        <span className="font-mono tabular-nums" style={{ color:T.muted }}>{r.trl}/9</span>
                      </td>
                      <td className="px-3 py-3 text-right">
                        <span className="font-mono tabular-nums" style={{ color:T.muted }}>{r.capex_usd_t}</span>
                        <div className="h-1 mt-1 rounded-full w-16 ml-auto overflow-hidden" style={{ background:"rgba(0,0,0,0.08)" }}>
                          <div className="h-full bg-blue-500 rounded-full" style={{ width: `${(r.capex_usd_t / Math.max(...s.routes.map(x => x.capex_usd_t))) * 100}%` }} />
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right">
                        <span className="font-mono tabular-nums" style={{ color:T.muted }}>{r.vom_usd_t}</span>
                        <div className="h-1 mt-1 rounded-full w-16 ml-auto overflow-hidden" style={{ background:"rgba(0,0,0,0.08)" }}>
                          <div className="h-full bg-orange-500 rounded-full" style={{ width: `${(r.vom_usd_t / Math.max(...s.routes.map(x => x.vom_usd_t))) * 100}%` }} />
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right">
                        <span className="font-mono tabular-nums font-semibold" style={{ color:T.sub }}>{r.lcox}</span>
                        <div className="h-1 mt-1 rounded-full w-16 ml-auto overflow-hidden" style={{ background:"rgba(0,0,0,0.08)" }}>
                          <div className="h-full bg-violet-500 rounded-full" style={{ width: `${(r.lcox / Math.max(...routesWithLcox.map(x => x.lcox))) * 100}%` }} />
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right">
                        <span className="font-mono tabular-nums font-semibold"
                          style={{ color: co2Frac < 0.1 ? "#16a34a" : co2Frac < 0.4 ? "#d97706" : "#dc2626" }}>
                          {r.co2_intensity.toFixed(2)}
                        </span>
                        <div className="h-1 mt-1 rounded-full w-16 ml-auto overflow-hidden" style={{ background:"rgba(0,0,0,0.08)" }}>
                          <div className="h-full rounded-full"
                            style={{ width: `${co2Frac * 100}%`, background: co2Frac < 0.1 ? "#16a34a" : co2Frac < 0.4 ? "#d97706" : "#dc2626" }} />
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right">
                        <span className="font-mono font-medium tabular-nums"
                          style={{ color: r.learningRate >= 12 ? "#16a34a" : r.learningRate >= 6 ? "#d97706" : T.dim }}>
                          {r.learningRate}%
                        </span>
                        <p className="text-[9px]" style={{ color:T.dim }}>per doubling</p>
                      </td>
                      <td className="px-4 py-3 text-right">
                        {r.avail_year ? (
                          <span className="flex items-center justify-end gap-1 font-medium text-xs" style={{ color:"#d97706" }}>
                            <Clock className="h-3 w-3" /> {r.avail_year}
                          </span>
                        ) : (
                          <span className="flex items-center justify-end gap-1 font-medium text-xs" style={{ color:"#16a34a" }}>
                            <CheckCircle className="h-3 w-3" /> Now
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="px-5 py-2" style={{ borderTop:`1px solid ${T.border}`, background:T.bg }}>
            <p className="text-[10px]" style={DIM}>
              LCOX = Levelised Cost of {s.product}. CRF at WACC=12%, lifetime=25yr.
              Learning rates from IEA ETP 2023. TRL per IEA scale (1=concept, 9=commercial).
            </p>
          </div>
        </div>

        {/* ── 3. MAC curve ── */}
        {macCurveData.length > 0 && (
          <div className="p-5" style={CARD}>
            <div className="flex items-center gap-2 mb-1">
              <TrendingDown className="h-4 w-4" style={{ color:T.dim }} />
              <p className="text-[10px] font-semibold tracking-widest uppercase" style={DIM}>
                Marginal Abatement Cost vs {incumbent.label} ($/tCO₂)
              </p>
            </div>
            <p className="text-xs mb-4" style={{ color:T.muted }}>
              MAC = (LCOX_alt − LCOX_incumbent) / (CO₂_incumbent − CO₂_alt).
              Negative = saves money AND reduces CO₂. Defines the minimum carbon price for cost-competitiveness.
            </p>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={macCurveData} margin={{ top:4, right:20, left:20, bottom:4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
                <XAxis dataKey="label" tick={{ fontSize:10, fill:T.dim }} stroke="rgba(0,0,0,0.1)" />
                <YAxis tick={{ fontSize:10, fill:T.dim }} stroke="rgba(0,0,0,0.1)"
                  label={{ value:"$/tCO₂", angle:-90, position:"insideLeft", offset:10, style:{ fontSize:10, fill:T.dim } }} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v: unknown) => [`$${v}/tCO₂ abated`, "MAC"]} />
                <ReferenceLine y={0} stroke={T.border} />
                <Bar dataKey="mac" radius={[3, 3, 0, 0]}>
                  {macCurveData.map(r => (
                    <Cell key={r.id} fill={(r.mac ?? 0) < 0 ? "#16a34a" : (r.mac ?? 0) < 100 ? "#d97706" : "#dc2626"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div className="flex flex-wrap gap-4 mt-3 text-[10px]" style={DIM}>
              <span className="flex items-center gap-1.5"><span className="w-3 h-2 rounded-sm inline-block" style={{ background: "#16a34a" }} /> Negative — already cost-competitive</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-2 rounded-sm inline-block" style={{ background: "#d97706" }} /> &lt;$100/tCO₂ — competitive with moderate carbon price</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-2 rounded-sm inline-block" style={{ background: "#dc2626" }} /> &gt;$100/tCO₂ — requires strong carbon price</span>
            </div>
          </div>
        )}

        {/* ── 4. Cost vs CO₂ scatter ── */}
        <div className="p-5" style={CARD}>
          <p className="text-[10px] font-semibold tracking-widest uppercase mb-1" style={DIM}>LCOX vs CO₂ Intensity — LP Trade-off Space</p>
          <p className="text-xs mb-4" style={{ color:T.muted }}>
            Routes in the <strong style={{ color:"#16a34a" }}>lower-left</strong> (cheap AND clean) dominate the optimal LP solution.
            Routes in the <strong style={{ color:"#dc2626" }}>upper-right</strong> are used only when no cheaper alternative exists.
            Carbon pricing shifts the frontier by penalising high-CO₂ routes.
          </p>
          <ResponsiveContainer width="100%" height={260}>
            <ScatterChart margin={{ top:16, right:20, left:20, bottom:20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
              <XAxis dataKey="x" type="number" name="CO₂" tick={{ fontSize:10, fill:T.dim }} stroke="rgba(0,0,0,0.1)"
                label={{ value:`CO₂ intensity (tCO₂/${s.unit_short})`, position:"insideBottom", offset:-10, style:{ fontSize:10, fill:T.dim } }} />
              <YAxis dataKey="y" type="number" name="LCOX" tick={{ fontSize:10, fill:T.dim }} stroke="rgba(0,0,0,0.1)"
                label={{ value:"LCOX ($/t)", angle:-90, position:"insideLeft", offset:12, style:{ fontSize:10, fill:T.dim } }} />
              <ZAxis range={[80, 80]} />
              <Tooltip contentStyle={tooltipStyle}
                content={({ payload }) => {
                  if (!payload?.length) return null;
                  const d = payload[0]?.payload as { name: string; x: number; y: number };
                  return (
                    <div className="rounded p-2 text-xs" style={{ background:T.card, border:`1px solid ${T.border}` }}>
                      <div className="font-semibold mb-0.5" style={{ color:T.text }}>{d.name}</div>
                      <div style={{ color:T.muted }}>CO₂: {d.x.toFixed(2)} tCO₂/{s.unit_short}</div>
                      <div style={{ color:T.muted }}>LCOX: ${d.y}/t</div>
                    </div>
                  );
                }} />
              <Scatter data={scatterData} shape={(props) => {
                const { cx, cy, payload } = props as { cx: number; cy: number; payload: { name: string; color: string } };
                return (
                  <g>
                    <circle cx={cx} cy={cy} r={10} fill={payload.color} fillOpacity={0.85} />
                    <text x={cx} y={cy - 14} textAnchor="middle" fontSize={8} fill={T.dim}>{payload.name}</text>
                  </g>
                );
              }} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>

        {/* ── 5. Policy instruments ── */}
        <div style={CARD} className="overflow-hidden">
          <div className="px-5 py-3 flex items-center gap-2 flex-wrap" style={{ borderBottom:`1px solid ${T.border}` }}>
            <BookOpen className="h-4 w-4" style={{ color:T.dim }} />
            <p className="text-[10px] font-semibold tracking-widest uppercase" style={DIM}>
              Policy Instruments — {s.label}
            </p>
            <span className="ml-auto text-[10px]" style={DIM}>
              NZS investment 2024–2050:{" "}
              <span className="font-semibold" style={{ color:T.sub }}>${policy.investment_bn_nzs}B</span>
              {" · "}Share of industrial CO₂:{" "}
              <span className="font-semibold" style={{ color:T.sub }}>{policy.co2_share}%</span>
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ borderBottom:`1px solid ${T.border}`, background:T.bg }}>
                  <th className="text-left px-5 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>Policy Instrument</th>
                  <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>Description</th>
                  <th className="text-right px-5 py-2.5 text-[10px] font-semibold uppercase tracking-wider" style={DIM}>Status</th>
                </tr>
              </thead>
              <tbody>
                {policy.instruments.map((p) => (
                  <tr key={p.name} style={{ borderBottom:`1px solid rgba(0,0,0,0.04)` }}>
                    <td className="px-5 py-2.5 font-semibold whitespace-nowrap" style={{ color:T.sub }}>{p.name}</td>
                    <td className="px-4 py-2.5 leading-relaxed" style={{ color:T.muted }}>{p.description}</td>
                    <td className="px-5 py-2.5 text-right">
                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded" style={
                        p.status === "Active" ? { background:"rgba(22,163,74,0.12)", color:"#16a34a" } :
                        p.status === "Draft"  ? { background:"rgba(37,99,235,0.12)",  color:"#2563eb" } :
                        p.status === "Pilot"  ? { background:"rgba(217,119,6,0.12)",  color:"#d97706" } :
                        { background:`rgba(0,0,0,0.05)`, color:T.muted }
                      }>
                        {p.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* ── 6. Technology deployment timeline ── */}
        <div className="p-5" style={CARD}>
          <div className="flex items-center gap-2 mb-4">
            <Layers className="h-4 w-4" style={{ color:T.dim }} />
            <p className="text-[10px] font-semibold tracking-widest uppercase" style={DIM}>Technology Deployment Timeline</p>
          </div>
          <div className="relative">
            <div className="flex mb-2">
              {[2024, 2030, 2035, 2040, 2050, 2060, 2070].map(yr => (
                <div key={yr} className="flex-1 text-[9px] text-center" style={{ color:T.dim }}>{yr}</div>
              ))}
            </div>
            <div className="relative h-px mb-5" style={{ background:T.border }}>
              {[2024, 2030, 2035, 2040, 2050, 2060, 2070].map((yr, i) => (
                <div key={yr} className="absolute top-0 w-px h-2 -translate-y-1"
                  style={{ left:`${(i / 6) * 100}%`, background:T.dim }} />
              ))}
            </div>
            {s.routes.map((route) => {
              const startYear = route.avail_year ?? 2024;
              const startPct  = Math.max(0, ((startYear - 2024) / (2070 - 2024)) * 100);
              const trl = TRL_DATA[route.id]?.trl ?? 9;
              return (
                <div key={route.id} className="flex items-center gap-3 mb-3">
                  <div className="w-28 flex-shrink-0 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: route.color }} />
                    <span className="text-[10px] font-medium truncate" style={{ color:T.muted }}>{route.label}</span>
                  </div>
                  <div className="flex-1 relative h-6">
                    <div className="absolute inset-y-0 rounded"
                      style={{
                        left: `${startPct}%`,
                        right: 0,
                        background: route.color + "18",
                        borderLeft: `2px solid ${route.color}`,
                      }} />
                    <div className="absolute top-0 bottom-0 flex items-center"
                      style={{ left: `calc(${startPct}% + 6px)` }}>
                      <span className="text-[9px]" style={{ color:T.dim }}>
                        {startYear > 2024 ? `→ ${startYear}` : "Available now"} · TRL {trl}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <p className="text-[10px] mt-2" style={DIM}>
            Shaded region = years when route is available in the LP model.
            TRL from IEA Technology Readiness Level methodology.
          </p>
        </div>

        {/* Footer note */}
        <div className="flex items-start gap-2 text-xs rounded-lg px-4 py-3" style={{ ...CARD, color:T.muted }}>
          <Info className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" style={{ color:T.dim }} />
          <span>
            CO₂ intensities are 2024 base-year values and decline over the planning horizon as grids decarbonise.
            CAPEX/VOM are 2024 USD; green routes see learning-curve cost reductions in later periods.
            MAC is computed against the highest-emission route ({incumbent.label}).
            Sources: IEA Iron &amp; Steel Roadmap (2020); IEA Cement Roadmap (2018); IEA Aluminium Roadmap (2022);
            NITI Aayog Vol.4 (2023); worldsteel Statistical Yearbook (2023); IAI Global LCA (2023).
          </span>
        </div>

      </div>
    </div>
  );
}
