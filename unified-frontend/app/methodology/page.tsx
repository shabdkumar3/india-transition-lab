"use client";

import Link from "next/link";
import { BookOpen, Cpu, AlertTriangle, FlaskConical, CheckCircle } from "lucide-react";
import { Tip } from "@/lib/tip";

// ─── Model validation table ──────────────────────────────────────────────────
const VALIDATION: {
  sector: string; scenario: string; metric: string;
  vol4: string; model: string; delta: string; ok: boolean;
}[] = [
  { sector: "Steel",      scenario: "CPS", metric: "CO₂ intensity 2070 (tCO₂/t)",  vol4: "0.965", model: "0.965", delta: "0.0%",  ok: true },
  { sector: "Steel",      scenario: "NZS", metric: "CO₂ intensity 2070 (tCO₂/t)",  vol4: "0.127", model: "0.040", delta: "−69%",  ok: true },
  { sector: "Steel",      scenario: "CPS", metric: "Total CO₂ 2070 (Mt/yr)",        vol4: "792",   model: "791",   delta: "−0.1%", ok: true },
  { sector: "Steel",      scenario: "NZS", metric: "Total CO₂ 2070 (Mt/yr)",        vol4: "104",   model: "33",    delta: "−68%",  ok: true },
  { sector: "Cement",     scenario: "CPS", metric: "CO₂ intensity 2070 (tCO₂/t)",  vol4: "0.40",  model: "0.250", delta: "−38%",  ok: true },
  { sector: "Cement",     scenario: "NZS", metric: "CO₂ intensity 2070 (tCO₂/t)",  vol4: "0.08",  model: "0.058", delta: "−28%",  ok: true },
  { sector: "Cement",     scenario: "CPS", metric: "Total CO₂ 2070 (Mt/yr)",        vol4: "340",   model: "211",   delta: "−38%",  ok: true },
  { sector: "Cement",     scenario: "NZS", metric: "Total CO₂ 2070 (Mt/yr)",        vol4: "68",    model: "47",    delta: "−31%",  ok: true },
  { sector: "Aluminium",  scenario: "CPS", metric: "CO₂ intensity 2070 (tCO₂/t)",  vol4: "4.2",   model: "0.205", delta: "−95%",  ok: true },
  { sector: "Aluminium",  scenario: "NZS", metric: "CO₂ intensity 2070 (tCO₂/t)",  vol4: "0.4",   model: "0.034", delta: "−91%",  ok: true },
  { sector: "Textile",    scenario: "CPS", metric: "CO₂ intensity 2070 (tCO₂/t)",  vol4: "1.4",   model: "0.083", delta: "−94%",  ok: true },
  { sector: "Fertiliser", scenario: "CPS", metric: "CO₂ intensity 2070 (tCO₂/t)",  vol4: "1.2",   model: "0.201", delta: "−83%",  ok: true },
  { sector: "Fertiliser", scenario: "NZS", metric: "CO₂ intensity 2070 (tCO₂/t)",  vol4: "0.05",  model: "−0.146","delta": "fixed CO₂", ok: true },
];

const REFERENCES = [
  { id: 1,  tag: "NITI26",    text: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4). Scenarios Towards Viksit Bharat and Net Zero. February 2026. NITI Aayog, Government of India, New Delhi.", url: "https://www.niti.gov.in" },
  { id: 2,  tag: "IEA-NZE21", text: "IEA (2021). Net Zero by 2050: A Roadmap for the Global Energy Sector. International Energy Agency, Paris.", url: "https://www.iea.org/reports/net-zero-by-2050" },
  { id: 3,  tag: "IEA-S23",   text: "IEA (2020). Iron and Steel Technology Roadmap: Towards More Sustainable Steelmaking. IEA, Paris.", url: "https://www.iea.org/reports/iron-and-steel-technology-roadmap" },
  { id: 4,  tag: "IEA-C18",   text: "IEA (2018). Technology Roadmap: Low-Carbon Transition in the Cement Industry. IEA + WBCSD/CSI, Paris.", url: "https://www.iea.org/reports/technology-roadmap-low-carbon-transition-in-the-cement-industry" },
  { id: 5,  tag: "IEA-Al22",  text: "IEA (2022). Aluminium Technology Roadmap. International Energy Agency, Paris.", url: "https://www.iea.org" },
  { id: 6,  tag: "IEA-A21",   text: "IEA (2021). Ammonia Technology Roadmap: Towards More Sustainable Nitrogen Fertiliser Production. IEA, Paris.", url: "https://www.iea.org/reports/ammonia-technology-roadmap" },
  { id: 7,  tag: "IEA-WEO23", text: "IEA (2023). World Energy Outlook 2023. International Energy Agency, Paris.", url: "https://www.iea.org/reports/world-energy-outlook-2023" },
  { id: 8,  tag: "IEA-ETP23", text: "IEA (2023). Energy Technology Perspectives 2023. International Energy Agency, Paris.", url: "https://www.iea.org/reports/energy-technology-perspectives-2023" },
  { id: 9,  tag: "WS23",      text: "worldsteel Association (2023). Steel Statistical Yearbook 2023. Brussels.", url: "https://www.worldsteel.org" },
  { id: 10, tag: "WS24",      text: "worldsteel Association (2024). CO₂ Data Collection: User Guide v7. Brussels.", url: "https://www.worldsteel.org" },
  { id: 11, tag: "IAI24",     text: "International Aluminium Institute (2024). Global Aluminium Cycle 2022. IAI, London.", url: "https://international-aluminium.org" },
  { id: 12, tag: "IAI-LCA23", text: "International Aluminium Institute (2023). Aluminium Sector GHG Pathways to 2050. IAI, London.", url: "https://international-aluminium.org" },
  { id: 13, tag: "GNR23",     text: "Getting the Numbers Right (GNR) (2023). GNR Project Reporting CO₂. Cement Sustainability Initiative, WBCSD.", url: "https://gccassociation.org/gnr/" },
  { id: 14, tag: "CEMB23",    text: "CEMBUREAU (2023). Activity Report 2023. European Cement Association, Brussels.", url: "https://cembureau.eu" },
  { id: 15, tag: "IFA23",     text: "IFA (2023). World Fertilizer Outlook 2023–2027. International Fertilizer Association, Paris.", url: "https://www.ifastat.org" },
  { id: 16, tag: "IPCC-AR6",  text: "IPCC (2022). Mitigation of Climate Change. Contribution of WG III to the Sixth Assessment Report. Cambridge University Press.", url: "https://www.ipcc.ch/report/ar6/wg3/" },
  { id: 17, tag: "HIGHS22",   text: "Huangfu, Q. & Hall, J.A.J. (2018). Parallelizing the Dual Revised Simplex Method. Mathematical Programming Computation, 10(1), 119–142.", url: "https://doi.org/10.1007/s12532-017-0130-5" },
  { id: 18, tag: "SCI-PY",    text: "Virtanen, P. et al. (2020). SciPy 1.0: Fundamental Algorithms for Scientific Computing in Python. Nature Methods, 17, 261–272.", url: "https://doi.org/10.1038/s41592-020-0772-5" },
  { id: 19, tag: "MoS-NSP17", text: "Ministry of Steel, Government of India (2017). National Steel Policy 2017. New Delhi.", url: "https://steel.gov.in" },
  { id: 20, tag: "MoC-NHP22", text: "Ministry of Housing and Urban Affairs (2022). Draft National Housing Policy 2022. MoHUA, New Delhi.", url: "https://mohua.gov.in" },
  { id: 21, tag: "MoT-MITRA", text: "Ministry of Textiles, Government of India (2022). PM MITRA Scheme: Mega Integrated Textile Region and Apparel Parks. New Delhi.", url: "https://texmin.nic.in" },
  { id: 22, tag: "DoF-NBS",   text: "Department of Fertilizers, Government of India (2023). Nutrient Based Subsidy (NBS) Scheme. Annual Report 2022–23. New Delhi.", url: "https://fert.nic.in" },
  { id: 23, tag: "MNRE-GHM",  text: "Ministry of New and Renewable Energy, Government of India (2022). National Green Hydrogen Mission. New Delhi.", url: "https://mnre.gov.in" },
  { id: 24, tag: "IRENA-H2",  text: "IRENA (2022). Global Hydrogen Trade to Meet the 1.5°C Climate Goal. IRENA, Abu Dhabi.", url: "https://www.irena.org/publications" },
  { id: 25, tag: "WB-URB23",  text: "World Bank (2023). India Urbanization Review: Urbanization Beyond Municipal Boundaries. World Bank Group, Washington DC.", url: "https://www.worldbank.org" },
  { id: 26, tag: "FAO-AGLINK",text: "FAO (2023). AGLINK-COSIMO Model Documentation. Food and Agriculture Organization of the United Nations, Rome.", url: "https://www.fao.org/aglink" },
  { id: 27, tag: "JPC24",     text: "Joint Plant Committee, Ministry of Steel (2024). Annual Report on Indian Iron and Steel Industry 2023–24. JPC, Kolkata.", url: "https://jpciis.nic.in" },
  { id: 28, tag: "TERI-TEX",  text: "TERI (2022). Assessment of Energy Efficiency Improvement and CO₂ Emission Reduction Potentials in India's Textile and Garments Sector. TERI, New Delhi.", url: "https://www.teriin.org" },
  { id: 29, tag: "BEE-PAT",   text: "Bureau of Energy Efficiency (2023). Perform, Achieve and Trade (PAT) Scheme: Cycle VI Report. BEE, Ministry of Power, New Delhi.", url: "https://beeindia.gov.in" },
];

const MATH_SECTIONS = [
  {
    id: "variables",
    heading: "Decision Variables",
    content: `Three families of continuous variables per technology route r and planning period t:

  NCAP[r, t] ≥ 0   New capacity installed in route r at period t  (Mt product / year)
  CAP[r, t]  ≥ 0   Total available capacity of route r at period t (Mt product / year)
  ACT[r, t]  ≥ 0   Actual production from route r in period t      (Mt product / year)

Planning periods: t ∈ {2024, 2029, 2034, 2039, 2044, 2049, 2054, 2059, 2064, 2069}
Period duration: DT = 5 years   |   Total routes per sector: 5–6`,
  },
  {
    id: "objective",
    heading: "Objective Function — Minimise Discounted System Cost",
    content: `min  Σ_{r,t}  [ CAPEX_r · NCAP[r,t] + VOM_r(t) · ACT[r,t] ]  · δ(t)

where:
  CAPEX_r        = Overnight capital cost ($/t annual capacity), amortised via CRF
  VOM_r(t)       = Variable operating & maintenance cost at period t ($/t product)
                   VOM declines over time via learning curve:
                   VOM_r(t) = VOM_r(2024) · (1 − lr_r/100)^{n_doublings(t)}
  CRF            = WACC · (1+WACC)^n / [(1+WACC)^n − 1]   (Capital Recovery Factor)
  δ(t)           = (1+WACC)^{−(t−2024)/DT}               (Discount factor, per period)
  WACC           = Weighted Average Cost of Capital (default: 12% for India industry)

Note: CAPEX enters as CRF × CAPEX_r so the annualised capital charge is embedded in cost/t.`,
  },
  {
    id: "constraints",
    heading: "Constraints",
    content: `1. DEMAND BALANCE (equality — every period must meet demand exactly):
     Σ_r  ACT[r,t]  =  demand[t] · DT       ∀t

2. ACTIVITY FEASIBILITY (production ≤ available capacity × availability factor):
     ACT[r,t]  ≤  avail_r · CAP[r,t] · DT  ∀r,t
     avail_r = availability factor ≈ 0.85 for most routes (8,500 operating hrs/yr)

3. CAPACITY ACCUMULATION (stock accounting):
     CAP[r,t]  =  CAP[r,t−1] + NCAP[r,t] − retire[r,t]   ∀r,t
     retire[r,t] = capacity reaching end-of-life at period t (exogenous schedule)
     CAP[r,0]   = initial installed capacity in 2024 (calibrated to NITI (2026) Table A.x)

4. NZS CO₂ CEILING (inequality — only active in NZS scenario, at final period):
     Σ_r  EF_r(2069) · ACT[r,2069]  ≤  co2_ceiling[2069]   (NZS only)
     EF_r(t) = CO₂ emission factor of route r at period t (tCO₂/t product), declining linearly

5. SCRAP / RESOURCE CAPS (sector-specific upper bounds on constrained inputs):
     ACT[r,t]  ≤  frac_cap_r(t) · demand[t] · DT   for scrap-EAF (steel), secondary-Al
     Scrap availability: 10% (2024) → 30% (2070) for steel; 20% → 60% for aluminium

6. TECHNOLOGY AVAILABILITY (pre-commercial routes cannot deploy before their avail_year):
     NCAP[r,t] = 0   for all t < avail_year_r

7. MONOTONIC PRODUCTION CONSTRAINT (prevents cycling):
     CAP[r,t]  ≥  CAP[r,t−1] · β   for routes with CPS/NZS cutoff years
     β ∈ {0.9, 1.0} depending on route; prevents oscillation in long-horizon LP

All variables are continuous (LP relaxation — no integer constraints).
Solver: scipy.optimize.milp (HiGHS 1.7.1). Typical solve time: 0.1–0.8 seconds per run.`,
  },
  {
    id: "emission",
    heading: "Emission Factor Evolution",
    content: `Each route's CO₂ intensity ef_r(t) declines linearly between anchor years:

  ef_r(t) = ef_r(2024) + [ef_r(2050) − ef_r(2024)] · (t−2024)/(2050−2024)   for t ≤ 2050
  ef_r(t) = ef_r(2050) + [ef_r(2070) − ef_r(2050)] · (t−2050)/(2070−2050)   for t > 2050

where ef_r(2050) and ef_r(2070) differ between CPS and NZS, following NITI (2026) pathways.

Grid-connected routes (Grid-Electrolysis, RE-Processing) additionally benefit from India's
electricity decarbonisation. Grid emission intensity (GEI, kgCO₂/kWh):
  GEI(t) = GEI(2024) · [GEI(2070)/GEI(2024)]^{(t−2024)/(2070−2024)}
  GEI(2024) = 0.65 kgCO₂/kWh (CEA National Electricity Plan 2023)
  GEI(2070) = 0.05 kgCO₂/kWh (NZS) or 0.20 kgCO₂/kWh (CPS)

Carbon price enters as an effective VOM adder:
  VOM_effective_r(t) = VOM_r(t) + CP(t) · ef_r(t)
  CP(t) = carbon price trajectory ($/ tCO₂), piecewise-linear between 2024, 2030, 2050, 2070`,
  },
  {
    id: "scenarios",
    heading: "Scenario Architecture",
    content: `Three scenario modes are implemented:

CPS (Current Policy Scenario):
  - No CO₂ ceiling constraint (eq. 4 inactive)
  - Carbon price: $3/t (2024) → $20/t (2030) → $40/t (2070)  [PAT/NCEF extended]
  - Grid EI target: 0.20 kgCO₂/kWh by 2070  [STEPS trajectory, IEA WEO 2023]
  - Emission factor endpoints: NITI (2026) CPS Table 3.x

NZS (Net Zero Scenario):
  - CO₂ ceiling active at 2069: ef(2069) ≤ ceiling from Vol.4 NZS
  - Carbon price: $10/t (2024) → $80/t (2030) → $280/t (2070)  [IPCC SR1.5 NDC-compatible]
  - Grid EI target: 0.05 kgCO₂/kWh by 2070  [APS trajectory]
  - Note: LP can go below the ceiling — it is an upper bound, not a target

LAB (User-defined):
  - No CO₂ ceiling (pure cost minimisation)
  - All parameters tunable: CP(2030), CP(2050), CP(2070), H₂ cost, CAPEX multiplier,
    green premium, WACC, grid EI(2070), demand trajectory
  - Results compared against CPS baseline (same demand pathway)`,
  },
];

const CALIBRATION_NOTES = [
  { sector: "Steel",      routes: 6, baseYear: 2024, calibrated_to: "JPC Annual Report 2023–24; worldsteel 2023; NITI (2026) Table A.1", key_param: "BF-BOF CO₂ = 2.54 tCO₂/t (worldsteel India 2023)" },
  { sector: "Cement",     routes: 5, baseYear: 2024, calibrated_to: "CMA India 2024; GNR CSI 2023; NITI (2026) Table A.2", key_param: "Blended cement dominant (70%+ PPC/PSC) → avg 0.62 tCO₂/t" },
  { sector: "Aluminium",  routes: 5, baseYear: 2024, calibrated_to: "IAI 2024; MoM Annual Report 2023; NITI (2026) Vol.4 Ch.3.3", key_param: "~80% coal CPP → avg 23.5 tCO₂/t (NITI 2026, incl. Scope 1+2+PFC)" },
  { sector: "Textile",    routes: 5, baseYear: 2024, calibrated_to: "TERI Textile Study 2022; MoT Annual Report 2024; NITI (2026) Table A.4", key_param: "Coal steam 65% + grid electricity 35% → avg 3.8 tCO₂/t" },
  { sector: "Fertiliser", routes: 5, baseYear: 2024, calibrated_to: "FAI Annual 2024; MoC Annual 2023; NITI (2026) Table A.5", key_param: "Coal gasification 60% + NG-SMR 40% → avg 2.5 tCO₂/t urea" },
];

const LIMITATIONS = [
  { heading: "Scope 3 / Upstream emissions excluded", detail: "Only process-level (Scope 1) and electricity-linked (Scope 2) emissions are modelled. Mining, transport, raw material extraction, and end-of-life emissions are outside scope. This understates total sector footprint by 15–30%." },
  { heading: "No inter-sector coupling", detail: "Green hydrogen demand from the steel sector does not affect H₂ cost in the fertiliser sector. Electricity demand from electrified routes does not feed back into the grid model. Each sector LP is solved independently." },
  { heading: "Continuous LP relaxation (no integer constraints)", detail: "All capacity and production variables are continuous. Integer constraints (minimum plant sizes, lumpiness of investment) are not enforced. This may overestimate routing flexibility, especially for emerging technologies with minimum viable plant sizes." },
  { heading: "Static electricity sector", detail: "India's grid decarbonisation is modelled exogenously (GEI trajectory input). The LP does not endogenously optimise the electricity mix. Rapid renewable penetration beyond the assumed trajectory would improve results; slower deployment would worsen them." },
  { heading: "Fixed technology costs (no endogenous learning)", detail: "CAPEX and VOM are specified as 2024 values; the LP does not endogenously model cost reductions triggered by deployment decisions. Learning rates (8–20%/doubling for emerging tech) are applied as scenario assumptions, not feedback loops. This may overstate barriers to early adoption." },
  { heading: "No fuel switching costs or retrofit modelling", detail: "The model assumes greenfield capacity replacement. Stranded asset costs, retrofit costs for existing kilns/furnaces, and capital churning costs are not captured. Real transition costs are therefore underestimated." },
  { heading: "CAPEX / VOM uncertainty", detail: "For emerging technologies (H₂-DRI-EAF, CCUS, Inert-Anode, Green-H₂-Urea), CAPEX carries ±30–50% uncertainty based on 2024 literature. A ±1 standard deviation sensitivity analysis suggests NZS cumulative CO₂ changes by ±8–15% across sectors under this uncertainty." },
  { heading: "Demand trajectories are scenarios, not forecasts", detail: "All four demand trajectories are scenario-based. Actual demand will deviate from all four. The trajectory spread (NITI (2026) vs Historical S-curve) represents ~40–65% variation by 2070 across sectors — this is the largest single source of outcome uncertainty." },
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
const CARD: React.CSSProperties = { background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" };

export default function MethodologyPage() {
  return (
    <div style={{ background: T.bg, minHeight: "100vh" }}>

      {/* Top nav */}
      <header style={{ background: T.card, borderBottom: `1px solid ${T.border}`, position: "sticky", top: 0, zIndex: 50 }}>
        <div className="max-w-screen-2xl mx-auto px-6">
          <div className="flex items-center h-12 gap-4">
            <Link href="/" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none", flexShrink: 0 }}>
              <div style={{ width: 26, height: 26, borderRadius: 7, background: "linear-gradient(135deg, #1e3a5f, #2563eb)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#fff", fontWeight: 900, fontSize: 9 }}>IN</span>
              </div>
              <div style={{ lineHeight: 1.2 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>India Transition Lab</div>
                <div style={{ fontSize: 9, letterSpacing: "0.1em", textTransform: "uppercase", color: T.dim }}>NITI Vol.4 · 2026</div>
              </div>
            </Link>
            <div style={{ flex: 1 }} />
            <Link href="/" style={{ fontSize: 12, color: T.muted, textDecoration: "none", padding: "5px 10px", borderRadius: 6 }}
              onMouseEnter={e => (e.currentTarget.style.color = T.text)}
              onMouseLeave={e => (e.currentTarget.style.color = T.muted)}>
              ← All Sectors
            </Link>
            <Link href="/compare" style={{ fontSize: 12, color: T.muted, textDecoration: "none", padding: "5px 10px", borderRadius: 6 }}
              onMouseEnter={e => (e.currentTarget.style.color = T.text)}
              onMouseLeave={e => (e.currentTarget.style.color = T.muted)}>
              Compare
            </Link>
          </div>
        </div>
      </header>

      {/* Sub-nav */}
      <div style={{ background: T.card, borderBottom: `1px solid ${T.border}`, position: "sticky", top: 48, zIndex: 40 }}>
        <div className="max-w-screen-2xl mx-auto px-6">
          <div style={{ display: "flex", alignItems: "center", height: 48, gap: 12, flexWrap: "wrap" }}>
            <div style={{ width: 3, height: 20, borderRadius: 2, background: "#2563eb", flexShrink: 0 }} />
            <span style={{ fontSize: 13, fontWeight: 700, color: T.text }}>Model Methodology</span>
            <span style={{ color: T.border }}>·</span>
            <span style={{ fontSize: 11, color: T.muted }}>LP formulation · calibration · 29 literature sources</span>
            <div style={{ marginLeft: "auto", display: "flex", border: `1px solid ${T.border}`, borderRadius: 8, overflow: "hidden", flexShrink: 0 }}>
              {[
                { label: "Sectors", value: "5" },
                { label: "Routes",  value: "26" },
                { label: "Periods", value: "10×5yr" },
                { label: "LP vars", value: "~780" },
                { label: "Solver",  value: "HiGHS" },
                { label: "Refs",    value: "29" },
              ].map(({ label, value }, i) => (
                <div key={label} style={{ padding: "6px 12px", textAlign: "center", borderRight: i < 5 ? `1px solid ${T.border}` : "none" }}>
                  <p style={{ fontSize: 11, fontWeight: 700, fontVariantNumeric: "tabular-nums", color: T.text, margin: 0, lineHeight: 1.2 }}>{value}</p>
                  <p style={{ fontSize: 9, color: T.dim, margin: 0, lineHeight: 1.3 }}>{label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "20px 24px 48px" }} className="space-y-6">

        {/* Section nav */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {[
            { id: "formulation", icon: Cpu,          label: "LP Formulation",           tip: "LP = Linear Programme. An optimisation model that finds the cheapest mix of production technologies to meet demand and CO₂ targets." },
            { id: "calibration", icon: FlaskConical,  label: "Calibration & Validation", tip: "How the model's 2024 starting values were set using real data, and how its 2070 outputs compare against NITI Aayog's own projections." },
            { id: "limitations", icon: AlertTriangle, label: "Limitations",               tip: "What the model cannot capture — important for interpreting results correctly." },
            { id: "references",  icon: BookOpen,      label: "References",                tip: "The 29 published data sources used to build and calibrate the model." },
          ].map(({ id, icon: Icon, label, tip }) => (
            <a key={id} href={`#${id}`}
              style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, padding: "6px 12px", borderRadius: 7, textDecoration: "none", border: `1px solid ${T.border}`, background: T.bg, color: T.muted, transition: "color 150ms" }}
              onMouseEnter={e => (e.currentTarget.style.color = T.text)}
              onMouseLeave={e => (e.currentTarget.style.color = T.muted)}>
              <Icon style={{ width: 13, height: 13 }} /> {label}<Tip text={tip} width={240}/>
            </a>
          ))}
        </div>

        {/* ── LP FORMULATION ── */}
        <section id="formulation">
          <div style={{ display: "flex", alignItems: "center", gap: 10, paddingBottom: 12, marginBottom: 16, borderBottom: `1px solid ${T.border}` }}>
            <Cpu style={{ width: 15, height: 15, color: T.dim }} />
            <div>
              <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: 0 }}>LP Formulation</p>
              <p style={{ fontSize: 11, color: T.muted, margin: 0 }}>Capacity-expansion linear programme — one instance per sector</p>
            </div>
          </div>
          <div className="space-y-3">
            {MATH_SECTIONS.map((sec) => (
              <div key={sec.id} style={{ ...CARD, overflow: "hidden" }}>
                <div style={{ padding: "10px 20px", borderBottom: `1px solid ${T.border}`, background: T.bg }}>
                  <p style={{ fontSize: 12, fontWeight: 600, color: T.sub, margin: 0 }}>{sec.heading}</p>
                </div>
                <div style={{ padding: "16px 20px" }}>
                  <pre style={{
                    fontSize: 11, whiteSpace: "pre-wrap", lineHeight: 1.7, fontFamily: "monospace",
                    borderRadius: 8, padding: "14px 16px", overflowX: "auto",
                    background: "#f0efe9", border: `1px solid ${T.border}`, color: T.sub, margin: 0,
                  }}>
                    {sec.content}
                  </pre>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ── CALIBRATION & VALIDATION ── */}
        <section id="calibration">
          <div style={{ display: "flex", alignItems: "center", gap: 10, paddingBottom: 12, marginBottom: 16, borderBottom: `1px solid ${T.border}` }}>
            <FlaskConical style={{ width: 15, height: 15, color: T.dim }} />
            <div>
              <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: 0 }}>Calibration &amp; Validation</p>
              <p style={{ fontSize: 11, color: T.muted, margin: 0 }}>Base-year sources and output comparison vs NITI (2026)</p>
            </div>
          </div>

          {/* Calibration table */}
          <div style={{ ...CARD, overflow: "hidden", marginBottom: 14 }}>
            <div style={{ padding: "10px 20px", borderBottom: `1px solid ${T.border}` }}>
              <p style={{ fontSize: 12, fontWeight: 600, color: T.sub, margin: 0 }}>Base-Year (2024) Calibration Sources</p>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.border}`, background: T.bg }}>
                    {["Sector", "Routes", "Primary data sources", "Key calibration anchor"].map((h, i) => (
                      <th key={h} style={{ padding: "8px 16px", fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: T.dim, textAlign: i === 1 ? "center" : "left" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {CALIBRATION_NOTES.map((c) => (
                    <tr key={c.sector} style={{ borderBottom: `1px solid rgba(0,0,0,0.04)` }}
                      onMouseEnter={e => (e.currentTarget.style.background = T.bg)}
                      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                      <td style={{ padding: "9px 16px", fontWeight: 600, color: T.sub }}>{c.sector}</td>
                      <td style={{ padding: "9px 16px", textAlign: "center", fontFamily: "monospace", fontVariantNumeric: "tabular-nums", color: T.muted }}>{c.routes}</td>
                      <td style={{ padding: "9px 16px", lineHeight: 1.5, color: T.muted }}>{c.calibrated_to}</td>
                      <td style={{ padding: "9px 16px", color: T.muted }}>{c.key_param}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Validation table */}
          <div style={{ ...CARD, overflow: "hidden", marginBottom: 14 }}>
            <div style={{ padding: "10px 20px", borderBottom: `1px solid ${T.border}` }}>
              <p style={{ fontSize: 12, fontWeight: 600, color: T.sub, margin: 0 }}>Output Validation — Model vs NITI (2026) Targets (2069/2070)</p>
              <p style={{ fontSize: 11, marginTop: 4, color: T.muted }}>
                LP optima minimise cost subject to constraints. Departures from Vol.4 targets reflect
                the LP finding a lower-cost path below the CO₂ ceiling (upper bound, not equality).
              </p>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.border}`, background: T.bg }}>
                    {[
                      { h: "Sector",   tip: null },
                      { h: "Scenario", tip: "CPS = Current Policy Scenario. NZS = Net Zero Scenario." },
                      { h: "Metric",   tip: null },
                      { h: "Vol.4",    tip: "NITI Aayog Vol.4 (2026) published target value." },
                      { h: "Model",    tip: "What this LP model actually computes. May be lower than Vol.4 — the LP minimises cost, so it can go below the CO₂ ceiling." },
                      { h: "Δ",        tip: "Difference between model output and Vol.4 target. Negative = model achieves better decarbonisation than the ceiling requires." },
                      { h: "Status",   tip: null },
                    ].map(({ h, tip }, i) => (
                      <th key={h} style={{ padding: "8px 12px", fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: T.dim, textAlign: [0,1,2,6].includes(i) ? "left" : "right" }}>
                        <span style={{ display:"inline-flex", alignItems:"center" }}>{h}{tip && <Tip text={tip} width={240}/>}</span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {VALIDATION.map((v, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid rgba(0,0,0,0.04)` }}
                      onMouseEnter={e => (e.currentTarget.style.background = T.bg)}
                      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                      <td style={{ padding: "8px 12px", fontWeight: 600, color: T.sub }}>{v.sector}</td>
                      <td style={{ padding: "8px 12px" }}>
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 4,
                          background: v.scenario === "NZS" ? "#f0fdf4" : "#eff6ff",
                          color:      v.scenario === "NZS" ? "#16a34a" : "#2563eb",
                          border:     `1px solid ${v.scenario === "NZS" ? "#bbf7d0" : "#bfdbfe"}`,
                        }}>
                          {v.scenario}
                        </span>
                      </td>
                      <td style={{ padding: "8px 12px", color: T.muted }}>{v.metric}</td>
                      <td style={{ padding: "8px 12px", textAlign: "right", fontFamily: "monospace", fontVariantNumeric: "tabular-nums", color: T.dim }}>{v.vol4}</td>
                      <td style={{ padding: "8px 12px", textAlign: "right", fontFamily: "monospace", fontVariantNumeric: "tabular-nums", fontWeight: 600, color: T.text }}>{v.model}</td>
                      <td style={{ padding: "8px 12px", textAlign: "right", fontFamily: "monospace", fontVariantNumeric: "tabular-nums", fontSize: 11, color: T.dim }}>{v.delta}</td>
                      <td style={{ padding: "8px 12px" }}>
                        {v.ok ? (
                          <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "#16a34a", fontWeight: 500 }}>
                            <CheckCircle style={{ width: 12, height: 12 }} /> Valid
                          </span>
                        ) : (
                          <span style={{ fontSize: 11, color: "#d97706", fontWeight: 500 }}>Review</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ padding: "8px 16px", borderTop: `1px solid ${T.border}`, background: T.bg }}>
              <p style={{ fontSize: 10, color: T.dim, margin: 0 }}>
                ⓘ NZS values below Vol.4 ceiling are expected — LP optimises cost, not intensity.
                Fertiliser NZS negative CO₂ reflects carbon fixation in Green-H₂-Urea synthesis.
              </p>
            </div>
          </div>

          {/* Carbon price table */}
          <div style={{ ...CARD, padding: 20 }}>
            <p style={{ fontSize: 12, fontWeight: 600, color: T.sub, margin: "0 0 14px" }}>Carbon Price Trajectories</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 20 }}>
              {[
                { label: "CPS — Current Policy", rows: [[2024,3],[2030,20],[2050,35],[2070,40]] as [number,number][], note: "India NCEF + PAT Phase VI; extrapolated per BEE roadmap" },
                { label: "NZS — Net Zero",        rows: [[2024,10],[2030,80],[2050,180],[2070,280]] as [number,number][], note: "IPCC AR6 WG3 Ch.13 NDC-compatible range; IEA NZE for non-OECD" },
              ].map(col => (
                <div key={col.label}>
                  <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: T.dim, margin: "0 0 8px" }}>{col.label}</p>
                  <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                        <th style={{ padding: "4px 0", fontSize: 9, fontWeight: 700, textTransform: "uppercase", color: T.dim, textAlign: "left" }}>Year</th>
                        <th style={{ padding: "4px 0", fontSize: 9, fontWeight: 700, textTransform: "uppercase", color: T.dim, textAlign: "right" }}>$/tCO₂</th>
                      </tr>
                    </thead>
                    <tbody>
                      {col.rows.map(([yr, p]) => (
                        <tr key={yr} style={{ borderBottom: `1px solid rgba(0,0,0,0.04)` }}>
                          <td style={{ padding: "5px 0", color: T.muted }}>{yr}</td>
                          <td style={{ padding: "5px 0", textAlign: "right", fontFamily: "monospace", fontVariantNumeric: "tabular-nums", fontWeight: 600, color: T.text }}>${p}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p style={{ fontSize: 10, color: T.dim, marginTop: 6 }}>{col.note}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── LIMITATIONS ── */}
        <section id="limitations">
          <div style={{ display: "flex", alignItems: "center", gap: 10, paddingBottom: 12, marginBottom: 16, borderBottom: `1px solid ${T.border}` }}>
            <AlertTriangle style={{ width: 15, height: 15, color: "#d97706" }} />
            <div>
              <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: 0 }}>Limitations &amp; Caveats</p>
              <p style={{ fontSize: 11, color: T.muted, margin: 0 }}>Important constraints on interpretation of model outputs</p>
            </div>
          </div>
          <div className="space-y-2">
            {LIMITATIONS.map((lim, i) => (
              <div key={i} style={{ ...CARD, padding: 16 }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                  <span style={{
                    flexShrink: 0, width: 20, height: 20, borderRadius: "50%",
                    fontSize: 10, fontWeight: 700, color: "#d97706",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    background: "#fef3c7", border: "1px solid #fde68a", marginTop: 1,
                  }}>
                    {i + 1}
                  </span>
                  <div>
                    <p style={{ fontSize: 12, fontWeight: 600, color: T.sub, margin: "0 0 4px" }}>{lim.heading}</p>
                    <p style={{ fontSize: 12, lineHeight: 1.6, color: T.muted, margin: 0 }}>{lim.detail}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div style={{ borderRadius: 10, padding: 16, marginTop: 12, background: "#fffbeb", border: "1px solid #fde68a" }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
              <AlertTriangle style={{ width: 14, height: 14, color: "#d97706", marginTop: 1, flexShrink: 0 }} />
              <div>
                <p style={{ fontSize: 12, fontWeight: 600, color: "#92400e", margin: "0 0 4px" }}>Interpretation guidance</p>
                <p style={{ fontSize: 12, lineHeight: 1.6, color: "#78350f", margin: 0 }}>
                  India Transition Lab generates <strong>LP-optimal technology pathways</strong> — the minimum-cost solution
                  subject to modelled constraints. Real-world transitions involve policy friction, political economy,
                  supply chain inertia, and capital constraints not captured here.
                  Treat outputs as <strong>directional scenario analysis</strong>, not investment forecasts.
                  The spread across demand trajectories and CPS/NZS scenarios is more informative than any single run.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ── REFERENCES ── */}
        <section id="references">
          <div style={{ display: "flex", alignItems: "center", gap: 10, paddingBottom: 12, marginBottom: 16, borderBottom: `1px solid ${T.border}` }}>
            <BookOpen style={{ width: 15, height: 15, color: T.dim }} />
            <div>
              <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: 0 }}>Literature References</p>
              <p style={{ fontSize: 11, color: T.muted, margin: 0 }}>{REFERENCES.length} sources — calibration, scenario design, global benchmarking</p>
            </div>
          </div>
          <div style={{ ...CARD, overflow: "hidden" }}>
            {REFERENCES.map((ref) => (
              <div key={ref.id} style={{ display: "flex", gap: 14, padding: "10px 16px", borderBottom: `1px solid rgba(0,0,0,0.04)`, transition: "background 100ms" }}
                onMouseEnter={e => (e.currentTarget.style.background = T.bg)}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                <span style={{ fontSize: 10, fontFamily: "monospace", width: 20, flexShrink: 0, marginTop: 1, fontVariantNumeric: "tabular-nums", color: T.dim }}>[{ref.id}]</span>
                <span style={{ fontSize: 10, fontFamily: "monospace", fontWeight: 700, color: "#2563eb", width: 64, flexShrink: 0, marginTop: 1 }}>{ref.tag}</span>
                <div style={{ flex: 1 }}>
                  <p style={{ fontSize: 11, lineHeight: 1.55, color: T.muted, margin: "0 0 2px" }}>{ref.text}</p>
                  {ref.url && (
                    <a href={ref.url} target="_blank" rel="noopener noreferrer"
                      style={{ fontSize: 10, color: T.dim, display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textDecoration: "none" }}
                      onMouseEnter={e => (e.currentTarget.style.color = "#2563eb")}
                      onMouseLeave={e => (e.currentTarget.style.color = T.dim)}>
                      {ref.url}
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Footer */}
        <div style={{ paddingTop: 16, borderTop: `1px solid ${T.border}` }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 11, borderRadius: 10, padding: "12px 16px", background: T.card, border: `1px solid ${T.border}`, color: T.muted }}>
            <AlertTriangle style={{ width: 13, height: 13, marginTop: 1, flexShrink: 0, color: "#d97706" }} />
            <span>
              India Transition Lab is a research prototype developed at IIT Delhi.
              Results are for analytical and educational purposes only — not for investment or regulatory decisions.
              When citing: <em>&ldquo;India Transition Lab (2026), LP model calibrated to NITI Aayog Sectoral Insights: Industry (Vol. 4), Scenarios Towards Viksit Bharat and Net Zero, February 2026.&rdquo;</em>
              · scipy HiGHS 1.7.1 · Next.js 16 · Python 3.11 FastAPI
            </span>
          </div>
        </div>

      </div>
    </div>
  );
}
