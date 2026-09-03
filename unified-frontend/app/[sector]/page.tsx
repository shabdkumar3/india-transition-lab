"use client";

import { useParams } from "next/navigation";
import { getSector, SECTOR_LIST } from "@/lib/sectors";
import type { SectorId, SectorConfig, TechRoute } from "@/lib/sectors";
import Link from "next/link";
import { TrendingUp, BarChart3, FlaskConical, Zap, Factory, Building2, Scissors, Leaf } from "lucide-react";
import { useEffect, useState } from "react";
import { runScenario } from "@/lib/api";
import type { YearlyResult } from "@/lib/api";
import { fmt2, fmtJobsK } from "@/lib/format";

// ─── Textual sector metadata ─────────────────────────────────────────────────
const TEXT_META: Record<SectorId, {
  drivers: string[]; barriers: string[]; context: string; global: string; scope: string;
}> = {
  steel: {
    drivers: ["PM Gati Shakti & NIP — largest single demand catalyst", "NSP 2017: 300 Mt capacity by 2030 (current: ~175 Mt)", "Export ambition: top-3 global exporter by 2047", "Rising scrap availability — EAF economics improve post-2030"],
    barriers: ["Green H₂: $4–5/kg today; H₂-DRI viable below ~$2/kg", "BF-BOF plants: 25–30 yr lifetimes — stranded asset risk", "Coal-DRI dominance (60%): unique to India, hard to electrify", "No CCUS CO₂ storage infrastructure near steel clusters"],
    context: "India is the world's 2nd largest steel producer (144 Mt, 2024). Unlike China (BF-BOF) or EU (scrap-EAF), India's route mix is uniquely coal-DRI-heavy due to the Sponge Iron cluster in eastern states.",
    global: "Global steel emits ~3.4 GtCO₂/yr (8% of global total). IEA NZE requires intensity to fall from 1.9 tCO₂/t to below 0.5 tCO₂/t by 2050.",
    scope: "Scope 1 (process + fuel combustion) + Scope 2 (grid electricity). Excludes upstream mining, transport, end-of-life.",
  },
  cement: {
    drivers: ["PM Awas Yojana: 11.5M housing units — biggest demand catalyst", "World-class blending already: 70%+ PPC/PSC vs China 50%", "600 MW waste heat recovery untapped in existing plants", "LC3 cement (IIT Madras): ~40% lower CO₂ vs OPC"],
    barriers: ["Process CO₂ (limestone): ~60% irreducible without CCUS", "CCUS cost: $80–120/t (2024); needs <$50/t for viability", "Coal: 75% of kiln thermal energy — hard to switch", "IS 456 limits SCM substitution — standard revision needed"],
    context: "India is the world's 2nd largest cement producer (395 Mt, 2024) with one of the lowest intensities globally (0.62 tCO₂/t) due to high blending rates. The hard challenge is the irreducible limestone CO₂.",
    global: "Cement emits ~2.8 GtCO₂/yr globally. 60% is inherent to the process — CCUS or alternative binders are unavoidable. IEA NZE requires <0.10 tCO₂/t by 2050.",
    scope: "~60% calcination Scope 1 (inherent), ~35% fuel combustion, ~5% grid electricity.",
  },
  aluminium: {
    drivers: ["EV revolution: aluminium per EV is 2.5× conventional vehicle", "RE buildout: solar frames, wind housings — major demand", "NALCO 900 MW + Vedanta 1,000 MW RE PPAs already signed", "Secondary aluminium: recycling uses only 5% of primary energy"],
    barriers: ["~80% smelting on coal captive power — high structural inertia", "Inert anode technology: TRL 4–5; no commercial scale in India", "RE intermittency: smelting needs 24/7 power; storage is costly", "Green premium: Indian producers penalised vs coal competitors"],
    context: "India ranks 6th globally in primary aluminium but has the highest intensity (23.5 tCO₂/t vs world avg 11.5) due to near-total coal CPP. Smelters in Odisha/Jharkhand face structural lock-in.",
    global: "Aluminium emits 1.1 GtCO₂/yr globally. Range: 4.5 tCO₂/t (hydro) to 17+ tCO₂/t (coal). IEA NZE requires <4.0 tCO₂/t by 2050.",
    scope: "97%+ from electricity (Scope 2). Grid emission intensity is the dominant lever — more important than technology route choice.",
  },
  textile: {
    drivers: ["PM MITRA: 7 mega integrated parks with mandatory RE", "$100B textile export target by 2030 under RE mandate", "PLI MMF: 64 companies; man-made fibre is more efficient", "EU CBAM 2026: market forces driving decarbonisation now"],
    barriers: ["SME fragmentation: 75% of output in SMEs — capital-constrained", "Process heat: no cost-competitive electric alternative at scale", "Water-energy nexus: dyeing 150–300 L/kg; ZLD creates tension", "Synthetic growth: polyester growing faster — higher Scope 3"],
    context: "India is the world's 2nd largest textile exporter, employing 45M people. 75% is SME production. CO₂ intensity (3.8 tCO₂/t) is 60% above EU (1.8) due to coal steam.",
    global: "Textile & apparel: ~2.1 GtCO₂/yr globally. Most NZ analyses exclude it — ITL explicitly includes it, calibrated to TERI 2022 and MoT data.",
    scope: "~65% process heat (coal/gas steam), ~35% grid electricity. No irreducible process CO₂ — theoretically near-zero with clean heat + RE power.",
  },
  fertiliser: {
    drivers: ["NGHM: fertiliser is primary H₂ off-taker; ₹19,744 Cr allocated", "Self-sufficiency achieved 2024 (Gorakhpur, Ramagundam, Talcher)", "IFFCO Nano Urea: 240ml = 1 bag (45 kg); 100M bottles/yr target", "EU CBAM 2026: green premium commercially viable for exporters"],
    barriers: ["Urea price control: ₹242/bag retail vs ₹2,000+ market — no price signal", "Coal gasification lock-in: 60% India vs global 75% NG-SMR", "Green H₂ at $4–5/kg → green urea $350–400/t vs $200–250/t", "Green ammonia: −33°C liquefaction or pressurisation infrastructure"],
    context: "India is the world's 3rd largest urea producer (30.5 Mt, 2024). Unlike the rest of the world, 60% is coal-based. NGHM targets fertiliser as the anchor sector for green H₂ off-take.",
    global: "Nitrogen fertiliser: ~0.9 GtCO₂/yr from ammonia synthesis. IEA NZE requires shift to green H₂ and blue ammonia by 2050. Green-H₂-Urea can be net-negative in process CO₂.",
    scope: "Scope 1 process CO₂ from ammonia synthesis only. Upstream N₂O field emissions (~300× GWP) excluded — addressed by Nano Urea and precision agriculture.",
  },
};

// Real sector facts from NITI Vol.4 + public data (IEA, MoSPI, Ministry reports)
const SECTOR_FACTS: Record<SectorId, {
  global_rank: number; global_share: number; co2_share: number;
  jobs_k: number; inv_nzs: number; inv_cps: number; budget_gt: number;
}> = {
  steel:      { global_rank: 2,  global_share: 6.5, co2_share: 35, jobs_k: 600,   inv_nzs: 180, inv_cps: 40, budget_gt: 8.5 },
  cement:     { global_rank: 2,  global_share: 7.0, co2_share: 24, jobs_k: 1000,  inv_nzs: 55,  inv_cps: 22, budget_gt: 4.2 },
  aluminium:  { global_rank: 6,  global_share: 3.2, co2_share: 8,  jobs_k: 300,   inv_nzs: 42,  inv_cps: 12, budget_gt: 1.8 },
  textile:    { global_rank: 2,  global_share: 5.0, co2_share: 4,  jobs_k: 45000, inv_nzs: 28,  inv_cps: 8,  budget_gt: 0.9 },
  fertiliser: { global_rank: 3,  global_share: 7.5, co2_share: 5,  jobs_k: 300,   inv_nzs: 22,  inv_cps: 8,  budget_gt: 0.7 },
};

// NITI Vol.4 (2026) suggested route shares at 2070
// Steel: EXACT from Vol.4 Ch.3.1 p.94 narrative ("~50% BF-BOF … ~25% H₂-DRI-EAF … ~18% Scrap-EAF … ~7% NG-DRI")
// Others: approximate from fuel/scenario narrative — Vol.4 gives energy mix, not explicit route %; see Ch 3.2–3.5
const NITI_2070_SHARES: Record<SectorId, {
  exact: boolean;  // true = verbatim from Vol.4; false = approximate from fuel-mix narrative
  cps: { routeId: string; pct: number }[];
  nzs: { routeId: string; pct: number }[];
}> = {
  steel: {
    exact: true,
    cps: [
      { routeId: "BF-BOF",       pct: 50 },   // "BF-BOF remains the single largest route, ~50%"
      { routeId: "H2-DRI-EAF",   pct: 25 },   // "hydrogen DRI-EAF (25%)"
      { routeId: "Scrap-EAF",    pct: 18 },   // "scrap-based EAF (18%)"
      { routeId: "NG-DRI-EAF",   pct: 7  },   // "NG DRI-EAF (7%)"
    ],
    nzs: [
      { routeId: "H2-DRI-EAF",   pct: 50 },   // "~50% from GH₂ DRI-EAF"
      { routeId: "Scrap-EAF",    pct: 40 },   // "~40% from scrap-based EAF"
      { routeId: "BF-BOF",       pct: 10 },   // "~10% from coal BF-BOF with CCS"
    ],
  },
  cement: {
    exact: false,   // Vol.4 gives fuel mix (79% coal CPS / 46% coal NZS); route shares inferred
    cps: [
      { routeId: "Coal-Blended",    pct: 60 },
      { routeId: "AltFuel-Blended", pct: 20 },
      { routeId: "Coal-LC3",        pct: 12 },
      { routeId: "Coal-OPC",        pct: 8  },
    ],
    nzs: [
      { routeId: "CCUS-Blended",    pct: 45 },
      { routeId: "AltFuel-Blended", pct: 30 },
      { routeId: "Coal-Blended",    pct: 15 },
      { routeId: "Coal-LC3",        pct: 10 },
    ],
  },
  aluminium: {
    exact: false,   // Vol.4 Table 3.3: scrap 30% CPS / 40% NZS; electricity/captive split given; route % inferred
    cps: [
      { routeId: "CoalPP-Primary",  pct: 30 },  // coal captive 40% of 70% primary ≈ 28%; ~30% rounded
      { routeId: "GridPP-Primary",  pct: 30 },
      { routeId: "Secondary-Al",    pct: 30 },  // Table 3.3: scrap stays 30%
      { routeId: "RE-Primary",      pct: 10 },
    ],
    nzs: [
      { routeId: "RE-Primary",      pct: 45 },  // fully non-fossil captive; majority RE
      { routeId: "Secondary-Al",    pct: 40 },  // Table 3.3: scrap grows to 40%
      { routeId: "GridPP-Primary",  pct: 12 },
      { routeId: "CoalPP-Primary",  pct: 3  },  // coal phased out by 2070 in NZS
    ],
  },
  textile: {
    exact: false,   // Vol.4 Table 3.4: coal captive 40% CPS / 0% NZS; biomass/RE dominant; route % inferred
    cps: [
      { routeId: "Coal-Conventional", pct: 35 },
      { routeId: "Biomass-Cogen",     pct: 30 },
      { routeId: "RE-Electrified",    pct: 20 },
      { routeId: "Gas-Transition",    pct: 15 },
    ],
    nzs: [
      { routeId: "Biomass-Cogen",     pct: 55 },  // "biomass would contribute nearly 39% of energy" NZS 2070
      { routeId: "RE-Electrified",    pct: 35 },
      { routeId: "Gas-Transition",    pct: 8  },
      { routeId: "Coal-Conventional", pct: 2  },  // near-zero coal in NZS 2070
    ],
  },
  fertiliser: {
    exact: false,   // Vol.4 Fig 3.35: green H₂ = 3.5 Mt (CPS) / 4.5 Mt (NZS) for fertiliser 2070; route % inferred
    cps: [
      { routeId: "NG-SMR",       pct: 35 },
      { routeId: "NG-SMR-CCS",   pct: 25 },
      { routeId: "Green-H2",     pct: 20 },
      { routeId: "Coal-Gasif",   pct: 20 },
    ],
    nzs: [
      { routeId: "Green-H2",     pct: 55 },
      { routeId: "NG-SMR-CCS",   pct: 30 },
      { routeId: "NG-SMR",       pct: 12 },
      { routeId: "Coal-Gasif",   pct: 3  },
    ],
  },
};

function baseYearDemand(demand: Record<number, number>): number {
  return demand[2024] ?? demand[2025] ?? (Object.values(demand)[0] ?? 0);
}

function deriveNumeric(s: SectorConfig) {
  const co2_2024 = Math.round(baseYearDemand(s.vol4.demand) * s.routes[0].co2_intensity);
  const intensity_2024 = s.routes[0].co2_intensity;
  const co2_cps = s.vol4.co2_total.cps[2070];
  const co2_nzs = s.vol4.co2_total.nzs[2070];
  const nzs_pct = co2_cps > 0 ? Math.round((1 - co2_nzs / co2_cps) * 100) : 0;
  const facts   = SECTOR_FACTS[s.id as SectorId] ?? { global_rank: 0, global_share: 0, co2_share: 0, jobs_k: 0, inv_nzs: 0, inv_cps: 0, budget_gt: 0 };
  return { co2_2024, intensity_2024, nzs_pct, ...facts };
}

const DATA: Record<SectorId, ReturnType<typeof deriveNumeric> & typeof TEXT_META[SectorId]> = {} as any;
for (const s of SECTOR_LIST) { DATA[s.id] = { ...deriveNumeric(s), ...TEXT_META[s.id] }; }

const NAV = [
  { href: "/pathway",      icon: TrendingUp,  label: "Pathway",      desc: "LP-optimal mix 2024–2070" },
  { href: "/technologies", icon: Zap,         label: "Technologies", desc: "TRL, LCOX, MAC curves" },
  { href: "/demand",       icon: BarChart3,    label: "Demand",       desc: "4 demand trajectories" },
  { href: "/lab",          icon: FlaskConical, label: "Lab",          desc: "Custom scenario builder" },
];

const ACCENT: Record<string, string> = {
  steel: "#2563eb", cement: "#ea580c", aluminium: "#0284c7",
  textile: "#db2777", fertiliser: "#65a30d",
};

const SECTOR_ICON: Record<string, React.ElementType> = {
  steel: Factory, cement: Building2, aluminium: Zap,
  textile: Scissors, fertiliser: Leaf,
};

// Light theme tokens
const T = {
  text:    "#23261f",
  sub:     "#474c44",
  muted:   "#7a7e74",
  dim:     "#a8ada5",
  border:  "#e8e5de",
  card:    "#ffffff",
  bg:      "#f7f6f2",
};

export default function SectorOverview() {
  const params   = useParams();
  const sectorId = (typeof params.sector === "string" ? params.sector : "steel") as SectorId;
  const s        = getSector(sectorId);
  const D        = DATA[sectorId];
  const accent   = ACCENT[sectorId] ?? "#2563eb";
  const SectorIcon = SECTOR_ICON[sectorId] ?? Factory;
  const vol4c    = s.vol4.co2_intensity.cps;
  const vol4n    = s.vol4.co2_intensity.nzs;

  const [live, setLive] = useState<{
    i24: number | null; c70: number | null; n70: number | null;
    loading: boolean; ok: boolean;
  }>({ i24: null, c70: null, n70: null, loading: true, ok: false });

  useEffect(() => {
    Promise.all([runScenario(s, "CPS"), runScenario(s, "NZS")]).then(([c, n]) => {
      const cY = c.yearly_results as Record<number, YearlyResult> | undefined;
      const nY = n.yearly_results as Record<number, YearlyResult> | undefined;
      const i24 = cY?.[2024]?.co2_intensity ?? null;
      const c70 = (cY?.[2069] ?? cY?.[2070])?.co2_intensity ?? null;
      const n70 = (nY?.[2069] ?? nY?.[2070])?.co2_intensity ?? null;
      setLive({ i24, c70, n70, loading: false, ok: !!(i24 && c70 && n70) });
    }).catch(() => setLive(p => ({ ...p, loading: false })));
  }, [s]);

  const maxIntensity = Math.max(...s.routes.map(r => r.co2_intensity));

  return (
    <div>
      {/* ── HERO STRIP ── */}
      <div style={{ background: accent + "0e", border: `1px solid ${accent}22`, borderRadius: 14, padding: "24px 28px", marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{ width: 48, height: 48, borderRadius: 14, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, background: accent + "18", border: `1px solid ${accent}35` }}>
              <SectorIcon style={{ width: 22, height: 22, color: accent }} />
            </div>
            <div>
              <h1 style={{ fontSize: 28, fontWeight: 900, color: T.text, lineHeight: 1, margin: 0, letterSpacing: "-0.02em" }}>{s.label}</h1>
              <p style={{ fontSize: 13, marginTop: 5, color: T.muted, margin: "5px 0 0" }}>{s.description}</p>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 12px", borderRadius: 8, background: T.card, border: `1px solid ${T.border}` }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", flexShrink: 0, background: live.loading ? "#f59e0b" : live.ok ? "#16a34a" : "#d1d5db" }} />
            <span style={{ fontSize: 11, color: T.muted, fontWeight: 500 }}>
              {live.loading ? "LP computing…" : live.ok ? "Live model" : "Offline — showing Vol.4"}
            </span>
          </div>
        </div>

        {/* Big 3-stat row */}
        <div style={{ display: "flex", gap: 0, marginTop: 20, flexWrap: "wrap", background: T.card, borderRadius: 12, border: `1px solid ${T.border}`, overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
          {[
            { label: "CO₂ TODAY", value: String(D.co2_2024), sub: `Mt/yr · ${D.co2_share}% of India industrial`, color: T.text },
            { label: "NZS INTENSITY CUT", value: `−${D.nzs_pct}%`, sub: `${D.intensity_2024} → ${vol4n[2070]} tCO₂/${s.unit_short} · by 2070`, color: accent },
            { label: "NZS INVESTMENT", value: `$${D.inv_nzs}B`, sub: `additional 2024–2050 · vs BAU $${D.inv_cps}B`, color: T.text },
          ].map((stat, i) => (
            <div key={stat.label} style={{ flex: "1 1 160px", padding: "20px 24px", borderRight: i < 2 ? `1px solid ${T.border}` : "none" }}>
              <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, marginBottom: 10, margin: "0 0 10px" }}>{stat.label}</p>
              <p style={{ fontSize: 38, fontWeight: 900, color: stat.color, lineHeight: 1, margin: "0 0 8px", letterSpacing: "-0.02em" }}>{stat.value}</p>
              <p style={{ fontSize: 12, color: T.muted, margin: 0 }}>{stat.sub}</p>
            </div>
          ))}
        </div>

        {/* Context text */}
        <p style={{ fontSize: 13, lineHeight: 1.65, color: T.sub, maxWidth: 700, margin: "16px 0 0" }}>
          {D.context}
        </p>
      </div>

      {/* ── CANONICAL NUMBERS STRIP ── */}
      <div style={{ display: "flex", flexWrap: "wrap", border: `1px solid ${T.border}`, borderRadius: 12, overflow: "hidden", background: T.card, marginBottom: 20, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
        {[
          { label: "Baseline intensity 2024", value: `${D.intensity_2024}`, unit: `tCO₂/${s.unit_short}`, sub: "actual observed", color: T.text, live_val: live.i24 },
          { label: "CPS intensity 2070",      value: `${vol4c[2070]}`,      unit: `tCO₂/${s.unit_short}`, sub: "NITI Vol.4 CPS",   color: "#dc2626",  live_val: live.c70 },
          { label: "NZS intensity 2070",      value: `${vol4n[2070]}`,      unit: `tCO₂/${s.unit_short}`, sub: "NITI Vol.4 NZS",   color: "#16a34a",  live_val: live.n70 },
          { label: "NZS CO₂ total 2070",      value: `${s.vol4.co2_total.nzs[2070]}`, unit: "Mt/yr", sub: `vs ${D.co2_2024} Mt today`, color: "#16a34a", live_val: null },
        ].map((k, i) => (
          <div key={k.label} style={{ flex: "1 1 140px", padding: "18px 22px", borderRight: i < 3 ? `1px solid ${T.border}` : "none" }}>
            <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.13em", textTransform: "uppercase", color: T.dim, margin: "0 0 12px" }}>
              {k.label}
            </p>
            <p style={{ fontSize: 26, fontWeight: 900, lineHeight: 1, color: k.color, fontVariantNumeric: "tabular-nums", margin: "0 0 4px" }}>
              {live.ok && k.live_val !== null ? fmt2(k.live_val) : k.value}
            </p>
            <p style={{ fontSize: 11, color: T.muted, margin: "0 0 6px" }}>{k.unit}</p>
            <p style={{ fontSize: 10, color: T.dim, margin: 0 }}>
              {live.ok && k.live_val !== null ? "● live computed" : `◆ ${k.sub}`}
            </p>
          </div>
        ))}
      </div>

      {/* ── MAIN CONTENT ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

        {/* Route intensity + position */}
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>

          <div style={{ flex: "2 1 380px", background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
            <div style={{ padding: "14px 20px 12px", borderBottom: `1px solid ${T.border}` }}>
              <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: 0 }}>
                Production Routes · CO₂ Intensity (tCO₂/{s.unit_short})
              </p>
            </div>
            <div style={{ padding: "14px 20px 18px", display: "flex", flexDirection: "column", gap: 14 }}>
              {s.routes.map(r => {
                const frac = r.co2_intensity / maxIntensity;
                return (
                  <div key={r.id}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <span style={{ width: 8, height: 8, borderRadius: "50%", background: r.color, flexShrink: 0 }} />
                        <span style={{ fontSize: 13, fontWeight: 600, color: T.sub }}>{r.label}</span>
                        {r.pending && (
                          <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 4, background: "#fef3c7", color: "#b45309", border: "1px solid #fde68a" }}>
                            from {r.avail_year}
                          </span>
                        )}
                        {!r.nitiMentioned && (
                          <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 4, background: "#f3f4f6", color: "#6b7280", border: "1px solid #e5e7eb" }}>
                            research / model only
                          </span>
                        )}
                      </div>
                      <span style={{ fontSize: 14, fontWeight: 800, color: r.color, fontVariantNumeric: "tabular-nums" }}>
                        {r.co2_intensity}
                      </span>
                    </div>
                    <div style={{ height: 5, borderRadius: 3, background: "rgba(0,0,0,0.06)" }}>
                      <div style={{ height: "100%", borderRadius: 3, width: `${frac * 100}%`, background: `linear-gradient(90deg, ${r.color}55, ${r.color})` }} />
                    </div>
                    <p style={{ fontSize: 10, marginTop: 4, color: T.dim, margin: "4px 0 0" }}>{r.description}</p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Position + investment */}
          <div style={{ flex: "1 1 220px", display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ borderRadius: 12, padding: 20, background: T.card, border: `1px solid ${T.border}`, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
              <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: "0 0 14px" }}>
                India&apos;s Position
              </p>
              {[
                ["Global rank",          `#${D.global_rank}`],
                ["World output share",   `${D.global_share}%`],
                ["India industry CO₂",   `${D.co2_share}%`],
                ["Employment",           fmtJobsK(D.jobs_k)],
                ["NZS carbon budget",    `${D.budget_gt} GtCO₂`],
              ].map(([lbl, val]) => (
                <div key={lbl} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "9px 0", borderBottom: `1px solid rgba(0,0,0,0.04)` }}>
                  <span style={{ fontSize: 12, color: T.muted }}>{lbl}</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: T.text, fontVariantNumeric: "tabular-nums" }}>{val}</span>
                </div>
              ))}
            </div>

            <div style={{ borderRadius: 12, padding: 20, background: T.card, border: `1px solid ${T.border}`, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
              <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: "0 0 14px" }}>
                Investment Gap 2024–2050
              </p>
              {[
                { label: "CPS pathway", val: `$${D.inv_cps}B`, frac: D.inv_cps / D.inv_nzs, color: "#2563eb" },
                { label: "NZS pathway", val: `$${D.inv_nzs}B`, frac: 1,                      color: "#16a34a" },
              ].map(r => (
                <div key={r.label} style={{ marginBottom: 14 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span style={{ fontSize: 12, color: T.muted }}>{r.label}</span>
                    <span style={{ fontSize: 14, fontWeight: 800, color: r.color, fontVariantNumeric: "tabular-nums" }}>{r.val}</span>
                  </div>
                  <div style={{ height: 6, borderRadius: 3, background: "rgba(0,0,0,0.06)" }}>
                    <div style={{ height: "100%", borderRadius: 3, width: `${r.frac * 100}%`, background: `linear-gradient(90deg, ${r.color}60, ${r.color})` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── NITI Vol.4 2070 Route Shares ── */}
        {(() => {
          const nitiData = NITI_2070_SHARES[sectorId as SectorId];
          const routeMap = Object.fromEntries(s.routes.map(r => [r.id, r]));
          const maxPct = 100;
          const scenarios: { key: "cps" | "nzs"; label: string; color: string; borderColor: string; tagColor: string; tagBg: string }[] = [
            { key: "cps", label: "CPS 2070", color: "#2563eb", borderColor: "rgba(37,99,235,0.2)", tagColor: "#1e40af", tagBg: "#dbeafe" },
            { key: "nzs", label: "NZS 2070", color: "#16a34a", borderColor: "rgba(22,163,74,0.2)", tagColor: "#14532d", tagBg: "#dcfce7" },
          ];
          return (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
              {/* header */}
              <div style={{ padding: "13px 20px 11px", borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                <div>
                  <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: "0 0 3px" }}>
                    NITI Vol.4 · Suggested Route Mix at 2070
                  </p>
                  <p style={{ fontSize: 11, color: T.muted, margin: 0 }}>
                    {nitiData.exact
                      ? "Verbatim from NITI Aayog (2026) Vol.4 Ch.3.1 — exact text values"
                      : "Inferred from Vol.4 energy-mix narrative — NITI gives fuel-share data, not explicit route %"}
                  </p>
                </div>
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: "3px 9px", borderRadius: 20,
                  background: nitiData.exact ? "#dcfce7" : "#fef3c7",
                  color:      nitiData.exact ? "#14532d"  : "#b45309",
                  border:     nitiData.exact ? "1px solid #bbf7d0" : "1px solid #fde68a",
                }}>
                  {nitiData.exact ? "● EXACT" : "◐ APPROXIMATE"}
                </span>
              </div>

              {/* two-column CPS / NZS */}
              <div style={{ display: "flex", gap: 0 }}>
                {scenarios.map((sc, si) => (
                  <div key={sc.key} style={{ flex: 1, padding: "16px 20px", borderRight: si === 0 ? `1px solid ${T.border}` : "none" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
                      <span style={{
                        fontSize: 10, fontWeight: 700, padding: "3px 10px", borderRadius: 20,
                        background: sc.tagBg, color: sc.tagColor, border: `1px solid ${sc.borderColor}`,
                      }}>
                        {sc.label}
                      </span>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      {nitiData[sc.key].map(({ routeId, pct }) => {
                        const route = routeMap[routeId];
                        const barColor = route ? route.color : sc.color;
                        return (
                          <div key={routeId}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                                <span style={{ width: 7, height: 7, borderRadius: "50%", background: barColor, flexShrink: 0 }} />
                                <span style={{ fontSize: 12, fontWeight: 600, color: T.sub }}>
                                  {route ? route.label : routeId}
                                </span>
                              </div>
                              <span style={{ fontSize: 13, fontWeight: 800, color: barColor, fontVariantNumeric: "tabular-nums" }}>
                                {pct}%
                              </span>
                            </div>
                            <div style={{ height: 5, borderRadius: 3, background: "rgba(0,0,0,0.06)" }}>
                              <div style={{ height: "100%", borderRadius: 3, width: `${(pct / maxPct) * 100}%`, background: `linear-gradient(90deg, ${barColor}60, ${barColor})`, transition: "width 400ms ease" }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>

              {/* footer citation */}
              <div style={{ padding: "9px 20px", borderTop: `1px solid ${T.border}`, background: "rgba(0,0,0,0.02)" }}>
                <p style={{ fontSize: 10, color: T.dim, margin: 0 }}>
                  Source: NITI Aayog (2026), <em>Sectoral Insights: Industry (Vol. 4)</em>, Ch.3.1–3.5 · February 2026
                  {!nitiData.exact && " · Route shares inferred from energy-mix tables; NITI does not publish explicit route-% for this sector"}
                </p>
              </div>
            </div>
          );
        })()}

        {/* Drivers + Barriers */}
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
          {[
            { title: "Drivers",  items: D.drivers,  dotColor: "#16a34a", bg: "#f0fdf4", border: "rgba(22,163,74,0.2)"  },
            { title: "Barriers", items: D.barriers, dotColor: "#dc2626", bg: "#fef2f2", border: "rgba(220,38,38,0.2)"  },
          ].map(col => (
            <div key={col.title} style={{ flex: "1 1 300px", minWidth: 0, background: col.bg, border: `1px solid ${col.border}`, borderRadius: 12, overflow: "hidden" }}>
              <div style={{ padding: "11px 20px 9px", borderBottom: `1px solid ${col.border}` }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: col.dotColor, letterSpacing: "0.08em" }}>
                  {col.title.toUpperCase()}
                </span>
              </div>
              <div style={{ padding: "4px 0" }}>
                {col.items.map((item, i) => (
                  <div key={i} style={{ padding: "9px 20px", display: "flex", gap: 12, alignItems: "flex-start", borderBottom: i < col.items.length - 1 ? `1px solid rgba(0,0,0,0.05)` : "none" }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: col.dotColor, flexShrink: 0, marginTop: 7 }} />
                    <p style={{ fontSize: 13, lineHeight: 1.55, color: T.sub, margin: 0, wordBreak: "break-word", minWidth: 0 }}>{item}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Analysis tools */}
        <div>
          <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", color: T.dim, textTransform: "uppercase", marginBottom: 10 }}>
            Explore this sector
          </p>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {NAV.map(({ href, icon: Icon, label, desc }) => (
              <Link key={href} href={`/${sectorId}${href}`}
                style={{ flex: "1 1 130px", minWidth: 0, background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: "16px 16px 14px", display: "flex", flexDirection: "column", gap: 10, textDecoration: "none", transition: "border-color 150ms, box-shadow 150ms", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}
                onMouseEnter={e => { const el = e.currentTarget as HTMLElement; el.style.borderColor = accent + "55"; el.style.boxShadow = `0 4px 12px ${accent}14`; }}
                onMouseLeave={e => { const el = e.currentTarget as HTMLElement; el.style.borderColor = T.border; el.style.boxShadow = "0 1px 3px rgba(0,0,0,0.04)"; }}>
                <div style={{ width: 32, height: 32, borderRadius: 8, background: accent + "14", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <Icon style={{ width: 15, height: 15, color: accent }} />
                </div>
                <div>
                  <p style={{ fontSize: 13, fontWeight: 700, color: T.text, margin: 0 }}>{label}</p>
                  <p style={{ fontSize: 11, color: T.dim, margin: "3px 0 0", lineHeight: 1.4 }}>{desc}</p>
                </div>
              </Link>
            ))}
          </div>
        </div>

        {/* Global context */}
        <div style={{ borderRadius: 12, padding: 20, background: T.card, border: `1px solid ${T.border}`, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: "0 0 8px" }}>Global Context</p>
              <p style={{ fontSize: 13, lineHeight: 1.6, color: T.sub, margin: 0 }}>{D.global}</p>
            </div>
            <div style={{ flex: 1, minWidth: 200, borderLeft: `1px solid ${T.border}`, paddingLeft: 24 }}>
              <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: "0 0 8px" }}>Emissions Scope</p>
              <p style={{ fontSize: 13, lineHeight: 1.6, color: T.sub, margin: 0 }}>{D.scope}</p>
            </div>
          </div>
          <p style={{ fontSize: 10, marginTop: 14, paddingTop: 12, borderTop: `1px solid rgba(0,0,0,0.05)`, color: T.dim, margin: "14px 0 0" }}>
            {s.vol4.citation}
          </p>
        </div>

      </div>
    </div>
  );
}
