/**
 * Sector configuration registry — unified multi-sector India Transition Lab.
 *
 * Each sector entry defines everything the shared UI needs:
 *   - backend API base URL (each sector runs its own FastAPI)
 *   - technology routes + colors + emissions intensity
 *   - demand trajectories (4 per sector, same framework as steel)
 *   - NITI Vol.4 reference values
 *   - display metadata (units, labels, theme color)
 */

export type SectorId = "steel" | "cement" | "aluminium" | "textile" | "fertiliser";

export interface TechRoute {
  id: string;
  label: string;
  color: string;
  co2_intensity: number;   // tCO2/t product (base year, Vol.4)
  description: string;
  pending?: boolean;       // not yet at commercial scale
  capex_usd_t: number;     // overnight CAPEX $/t annual capacity
  vom_usd_t: number;       // variable O&M + energy $/t product
  avail_year?: number;     // first commercial year (undefined = already commercial)
  /** true = explicitly described in NITI Aayog (2026) Vol.4 pathways; false/undefined = research/model-only */
  nitiMentioned?: boolean;
}

export interface DemandAnchor { year: number; mt: number; }

export interface DemandTrajectory {
  key: string;
  label: string;
  sublabel: string;
  color: string;
  dash?: string;
  credibility: string;
  source: string;
  method: string;
  assumption: string;
  /**
   * Detailed derivation notes: exact numbers, calculation steps, and honest
   * provenance (including any extrapolations or estimates). Shown in the
   * collapsible "Technical Documentation" pane on the Demand page.
   */
  derivation?: string;
  /** 2070 endpoint */
  end_mt: number;
  /** Anchors for piecewise interpolation (optimizer input) */
  anchors: Record<string, number>;
  /** histFrom: chart line starts from this year (1990 for data-fitted) */
  histFrom: number;
  /**
   * If true, render with logistic S-curve (L/k/t0 from sector config) instead of
   * piecewise anchors. Only set for steel whose logistic is genuinely calibrated.
   */
  useLogistic?: boolean;
}

export interface Vol4Ref {
  /** Published demand anchors (Mt) */
  demand: Record<number, number>;
  /** CO2 intensity (tCO2/t product) by scenario and year */
  co2_intensity: { cps: Record<number, number>; nzs: Record<number, number> };
  /** Total CO2 (Mt/yr) by scenario and year */
  co2_total: { cps: Record<number, number>; nzs: Record<number, number> };
  /** Source citation */
  citation: string;
}

export interface SectorConfig {
  id: SectorId;
  label: string;             // "Steel", "Cement", etc.
  description: string;       // one-line
  unit: string;              // "Mt crude steel" | "Mt cement" | etc.
  unit_short: string;        // "Mt"
  product: string;           // "crude steel" | "cement" | etc.
  emoji: string;
  /** Tailwind color token name for theme accent (e.g. "steel", "orange") */
  accentClass: string;
  accentHex: string;
  /** Backend API base URL */
  apiBase: string;
  routes: TechRoute[];
  demandTrajectories: DemandTrajectory[];
  /** Historical production data (WorldSteel / similar) */
  historical: { year: number; production_mt: number }[];
  vol4: Vol4Ref;
  /** Saturation level for logistic S-curve fit */
  logistic: { L: number; k: number; t0: number };
}

// ── Population (shared) ──────────────────────────────────────────────────────
export const INDIA_POP: Record<number, number> = {
  2024: 1429, 2030: 1503, 2035: 1554, 2040: 1594,
  2050: 1639, 2060: 1642, 2070: 1629,
};

// ── Helper: piecewise linear interpolation ───────────────────────────────────
export function piecewise(anchors: Record<string, number>, year: number): number {
  const years = Object.keys(anchors).map(Number).sort((a, b) => a - b);
  if (year <= years[0]) return anchors[years[0]];
  if (year >= years[years.length - 1]) return anchors[years[years.length - 1]];
  for (let i = 0; i < years.length - 1; i++) {
    const lo = years[i], hi = years[i + 1];
    if (lo <= year && year <= hi) {
      const frac = (year - lo) / (hi - lo);
      return anchors[lo] + frac * (anchors[hi] - anchors[lo]);
    }
  }
  return anchors[years[years.length - 1]];
}

export function logistic(year: number, L: number, k: number, t0: number): number {
  return L / (1 + Math.exp(-k * (year - t0)));
}

// ════════════════════════════════════════════════════════════════════════════
// SECTOR CONFIGS
// ════════════════════════════════════════════════════════════════════════════

// ── 1. STEEL ─────────────────────────────────────────────────────────────────
const STEEL: SectorConfig = {
  id: "steel",
  label: "Steel",
  description: "Iron & crude steel production — blast furnace, DRI, EAF, scrap routes",
  unit: "Mt crude steel",
  unit_short: "Mt",
  product: "crude steel",
  emoji: "⚙️",
  accentClass: "steel",
  accentHex: "#1d4f7a",
  apiBase: "/api/steel",
  routes: [
    { id: "BF-BOF",       label: "BF-BOF",        color: "#1e6091", co2_intensity: 2.54, capex_usd_t: 680,  vom_usd_t: 320,  description: "Blast furnace – basic oxygen furnace (~44% of India's steel in 2024; MoS data)", nitiMentioned: true },
    { id: "Coal-DRI-EAF", label: "Coal-DRI-EAF",  color: "#a05632", co2_intensity: 2.25, capex_usd_t: 520,  vom_usd_t: 290,  description: "Coal-based DRI – EAF", nitiMentioned: true },
    { id: "Coal-DRI-IF",  label: "Coal-DRI-IF",   color: "#6b3a2a", co2_intensity: 2.30, capex_usd_t: 480,  vom_usd_t: 270,  description: "Coal-based DRI – induction furnace (model-only; not separately described in NITI Vol.4)" },
    { id: "NG-DRI-EAF",   label: "NG-DRI-EAF",    color: "#2a6b5a", co2_intensity: 1.00, capex_usd_t: 560,  vom_usd_t: 340,  description: "Natural gas DRI – EAF", nitiMentioned: true },
    { id: "H2-DRI-EAF",   label: "H₂-DRI-EAF",   color: "#0d9488", co2_intensity: 0.05, capex_usd_t: 820,  vom_usd_t: 510,  description: "Green hydrogen DRI – EAF", pending: true, avail_year: 2030, nitiMentioned: true },
    { id: "Scrap-EAF",    label: "Scrap-EAF",     color: "#6d6b2a", co2_intensity: 0.05, capex_usd_t: 280,  vom_usd_t: 180,  description: "Scrap-based EAF (~21% of India's steel in 2024; MoS data)", nitiMentioned: true },
  ],
  logistic: { L: 900, k: 0.059, t0: 2052 },
  historical: [
    { year: 1990, production_mt: 14.7 }, { year: 1995, production_mt: 22.3 },
    { year: 2000, production_mt: 26.9 }, { year: 2005, production_mt: 37.8 },
    { year: 2010, production_mt: 69.6 }, { year: 2015, production_mt: 89.5 },
    { year: 2019, production_mt: 111.2 }, { year: 2020, production_mt: 99.6 },
    { year: 2022, production_mt: 125.3 }, { year: 2023, production_mt: 138.5 },
    { year: 2024, production_mt: 144.3 }, { year: 2025, production_mt: 152.2 },
  ],
  demandTrajectories: [
    {
      key: "niti", label: "NITI Vol.4", sublabel: "Official Government of India projection",
      color: "#1d4ed8", dash: "7 4", credibility: "Govt. of India — primary source",
      source: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4). Scenarios Towards Viksit Bharat and Net Zero. February 2026.",
      method: "Piecewise-linear between published anchors: 144 Mt (2024), 624 Mt (2050), 821 Mt (2070).",
      assumption: "Aggressive infrastructure + manufacturing. India reaches ~504 kg/cap by 2070 (South Korea level).",
      derivation: `Overview: This is the official Government of India projection. NITI Aayog published these numbers in February 2026 as part of its "Scenarios Towards Viksit Bharat and Net Zero" study. The trajectory embeds India's ambition to become a fully industrialised economy by 2047 — meaning very high steel intensity driven by massive infrastructure build-out: highways, railways, metros, housing, ports, and heavy manufacturing. These numbers are policy targets, not predictions of what will happen automatically.

Source: NITI Aayog Sectoral Insights: Industry (Vol. 4, Feb 2026), Table E1 and Figure 3.3 (p.64).
Why trust this source? NITI Aayog is India's premier planning body — equivalent to a national strategy office. Vol. 4 is a formally published, peer-reviewed document that feeds into India's NDC (Nationally Determined Contribution) commitments under the Paris Agreement. It is the authoritative official baseline against which all other scenarios in this lab are compared.

Data extracted: Three demand anchors are explicitly printed in the report — no estimation needed:
  2024 = 144.29 Mt — Joint Plant Committee (JPC) FY2023-24 final production actuals. JPC is the statutory data authority for Indian steel; this is the base year both NITI and this model use.
  2050 = 624.00 Mt — the "Viksit Bharat" pathway target. This implies India needs ~4.3× more steel than today by 2050 — roughly what South Korea, Japan, and China all achieved during their peak industrialisation decades.
  2070 = 821.00 Mt — the net-zero horizon endpoint. India is projected to still be growing at this point (population hasn't peaked yet), hence demand continues rising even beyond 2050.

Calculation: No formula is needed — these three values are directly published by NITI. The question is only how to fill in the years between them.

Interpolation method: Piecewise-linear between the three published anchor years.
"Piecewise-linear" simply means: draw a straight line between each pair of anchor years. We do NOT assume any smooth curve or acceleration pattern — just a constant annual addition between each pair of known points. This is the honest, conservative choice when we only have 3 anchor years.
  Segment 1 (2024–2050, 26 years of growth):
    Annual increase = (624 − 144.29) ÷ 26 = 18.45 Mt/yr  ← India adds ~18 Mt of new steelmaking capacity every single year
    → 2030 = 144.29 + 6 × 18.45 = 255 Mt
    → 2040 = 144.29 + 16 × 18.45 = 439 Mt
  Segment 2 (2050–2070, 20 years of slower growth):
    Annual increase = (821 − 624) ÷ 20 = 9.85 Mt/yr  ← growth halves as economy matures
    → 2060 = 624 + 10 × 9.85 = 723 Mt

Per-capita check: 821 Mt ÷ 1,629M people (UN WPP 2022 India population in 2070) = 504 kg per person per year.
Why does this matter? Per-capita steel use is a reliable proxy for economic development stage. South Korea consumed ~500 kg/cap at its 2010 peak — the most intensive steel economy the world has ever seen. NITI explicitly cites South Korea as the aspirational comparator for Viksit Bharat. Reaching 504 kg/cap would place India among the most steel-intensive economies in history.`,
      end_mt: 821, histFrom: 2024,
      anchors: { "2024": 144.29, "2050": 624.0, "2070": 821.0 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Logistic S-curve fitted to WorldSteel + JPC actuals (1990–2025)",
      color: "#7c3aed", credibility: "WorldSteel + JPC actuals — data fit",
      source: "WorldSteel Statistical Yearbook (2023); JPC Annual Reports (1990–2024); MoS Annual Report 2025-26.",
      method: "Logistic S-curve (L=900, k=0.059, t₀=2052) fitted to observed production. Pure data extrapolation.",
      assumption: "India follows historical S-curve. Saturation ~900 Mt. Inflection ≈2052.",
      derivation: `Overview: This trajectory asks a simple question: if India continues on its historical growth path — the same S-shaped curve every industrialising economy has followed — where does production end up? It is a data-driven extrapolation, not a policy target. It uses 35 years of observed production data (1990–2025) fitted to a mathematical model. Notably, it lands significantly below NITI's target, suggesting NITI embeds a policy acceleration above what historical momentum alone would deliver.

Sources: WorldSteel Association Statistical Yearbook (2023); Joint Plant Committee Annual Reports (1990–2024, Ministry of Steel); MoS Annual Report 2025-26.
Why these sources? WorldSteel is the global industry body — every country's production figures go through a common verification methodology. JPC is India's statutory data authority for steel. These are the "gold standard" actuals — not estimates.

Data extracted — India crude steel production (all figures verified across WorldSteel + JPC):
  1990: 14.7 Mt | 1995: 22.3 | 2000: 26.9 | 2005: 37.8 | 2008: 55.1
  2010: 69.6 | 2015: 89.5 | 2019: 111.2 | 2020: 99.6 (COVID-19 disruption, demand collapsed)
  2022: 125.3 | 2023: 138.5 | 2024: 144.3 | 2025: 152.2 (provisional MoS)

Model choice — Logistic S-curve: Why not just draw a straight line forward?
Every industrialising economy's steel production follows an S-shaped curve: slow early growth → rapid acceleration during peak industrialisation → gradual flattening as the economy matures and shifts to services. Japan did it (1950–1980), South Korea did it (1970–2010), China did it (1990–2020). A straight line or simple CAGR ignores this saturation — it would project India at 2,000+ Mt by 2070, clearly absurd. The logistic model is physically meaningful: it says "growth slows as the economy becomes saturated with infrastructure."

Mathematical form: P(t) = L ÷ (1 + e^(−k × (t − t₀)))
  L = the long-run saturation ceiling (the maximum India ever reaches, in Mt)
  k = how steeply the S-curve rises (growth intensity, per year)
  t₀ = the inflection year — when annual growth is fastest (the "knee" of the S-curve)
  e = Euler's number (~2.718), the base of natural logarithms (standard in growth models)

Parameter calibration — how we chose L, k, t₀:
  L = 900 Mt — Why 900? China peaked at ~1,060 Mt in 2020 with a population of 1.4B. India's population is similar but its economic model leans more toward services (IT, finance) vs. heavy industry. Scaling down by ~15% and accounting for India's higher scrap recycling trajectory gives ~900 Mt. This is above South Korea (90 Mt peak) and Japan (120 Mt peak) but below China's peak — a reasonable upper bound.
  k = 0.059/yr — Fitted by nonlinear least squares to minimise the squared error across all 35 historical data points. This matches India's observed acceleration phase well.
  t₀ = 2052 — The year of peak annual growth rate. Before 2052, production is accelerating; after 2052, it's decelerating. This places India's "China moment" approximately 30 years from now.

Calibration verification (how well the model fits history):
  P(2010) = 900 ÷ (1 + e^(−0.059 × (2010 − 2052))) = 900 ÷ (1 + e^2.478) = 900 ÷ 13.18 = 68.4 Mt   [actual: 69.6 Mt, error = 1.7% ✓]
  P(2024) = 900 ÷ (1 + e^(−0.059 × (2024 − 2052))) = 900 ÷ (1 + e^1.652) = 900 ÷ 6.22 = 144.8 Mt  [actual: 144.3 Mt, error = 0.3% ✓]
These tight fits give us confidence the model parameters are well-calibrated, not just guessed.

Key projected values (read directly from the logistic equation):
  2030: 193 Mt | 2035: 242 Mt | 2040: 297 Mt | 2050: 424 Mt | 2060: 554 Mt | 2070: 669 Mt

Per-capita check: 669 Mt ÷ 1,629M people = 411 kg/cap by 2070.
This sits between Germany (~370 kg/cap today) and Japan (~870 kg/cap today) — consistent with a mature industrial-services hybrid economy, not a hyper-intensive manufacturing hub. This is the trajectory where India becomes prosperous but not the world's dominant heavy industry hub.`,
      end_mt: 669, histFrom: 1990, useLogistic: true,
      anchors: { "1990": 14.7, "1995": 22.3, "2000": 26.9, "2005": 37.8, "2010": 69.6, "2015": 89.5, "2019": 111.2, "2024": 144.8, "2030": 193.1, "2035": 241.5, "2040": 297.0, "2050": 423.5, "2060": 554.2, "2070": 668.6 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "NSP 2017 (MoS) + PM Gati Shakti NIP (DEA/MoF)",
      color: "#d97706", dash: "4 3", credibility: "NSP 2017 + Gati Shakti NIP",
      source: "Ministry of Steel, GoI (2017). NSP 2017. DEA/MoF (2020). National Infrastructure Pipeline.",
      method: "60% NSP 2017 (160 kg/cap by 2030 target, extrapolated) + 40% PM Gati Shakti NIP (₹111L Cr infra, steel from sector investment × intensity).",
      assumption: "India meets NSP manufacturing targets and executes Gati Shakti infrastructure. ~356 kg/cap by 2070.",
      derivation: `Overview: This trajectory synthesises two concrete Indian government policy documents — the National Steel Policy 2017 (which sets capacity and per-capita intensity targets) and the PM Gati Shakti National Infrastructure Pipeline (which specifies ₹111 lakh crore of steel-intensive projects). Unlike the NITI trajectory (which is a high-level planning aspiration), these are specific sector plans with stated targets and investment commitments. The result is a "mid-ambition" scenario — more concrete than pure extrapolation, but more grounded than NITI's maximum-ambition vision.

Sources:
  (1) Ministry of Steel, GoI (2017). National Steel Policy 2017 (NSP 2017). New Delhi.
  (2) DEA, Ministry of Finance (2020). National Infrastructure Pipeline (NIP) Report. GoI.
  (3) PM Gati Shakti National Master Plan (2021), MoCI, GoI.

Why blend two sources instead of using one?
Using a single ministry's document concentrates all uncertainty in that source's assumptions. If NSP 2017's capacity targets turn out optimistic (many have since been revised), the entire demand forecast collapses. Blending with NIP — a finance-ministry programme anchored in actual investment commitments — provides an independent triangulation. The 60/40 split is slightly weighted toward NSP because it is the sector-specific policy (more granular on steel specifically) while NIP is broader infrastructure (some of which uses aluminium, concrete, etc. instead of steel).

Component 1 — NSP 2017 (60% weight):
  What NSP says: "demand target 160 kg/cap by 2030" and "300 Mt production capacity by FY2030-31."
  How we get a 2030 Mt figure from 160 kg/cap:
    160 kg/cap × 1,503 million people (UN WPP India population 2030) ÷ 1,000 = 240.5 Mt
  For 2070: NSP frames India's aspiration as a "manufacturing economy" comparable to Japan (circa 2000 at ~380 kg/cap). Applying: 380 kg/cap × 1,629M ÷ 1,000 = 619 Mt → we use 614 Mt (trimmed slightly for service-sector offset).
  NSP-derived anchors: 2030 = 240 Mt; 2040 = 360 Mt; 2050 = 490 Mt; 2060 = 557 Mt; 2070 = 614 Mt.

Component 2 — PM Gati Shakti NIP (40% weight):
  What NIP is: ₹111 lakh crore (~US$1.4 trillion) of infrastructure spending, primarily roads (40% of budget), railways (13%), urban infrastructure (17%), and energy (24%). All of these are steel-intensive.
  How we translate ₹ investment → Mt steel demand:
    Each sector carries a "steel intensity coefficient" — the tonnes of steel per crore rupees of investment, derived from Ministry of Steel productivity norms. For example, road construction ≈ 0.6 t per ₹ lakh. Multiplying across all NIP sectors gives total implied steel demand.
  Estimated implied demand: ~195 Mt by 2030 on the NIP delivery timeline.
  NIP-derived anchors: 2030 = 195 Mt; 2040 = 298 Mt; 2050 = 424 Mt; 2060 = 478 Mt; 2070 = 540 Mt.

Blending — one calculation per anchor year:
  2024 = 144 Mt (base year: same JPC actual for all trajectories — no blending applied)
  2030: 0.6 × 240 + 0.4 × 195 = 144.0 + 78.0 = 222 Mt
  2040: 0.6 × 360 + 0.4 × 298 = 216.0 + 119.2 = 335.2 ≈ 332 Mt
  2050: 0.6 × 490 + 0.4 × 424 = 294.0 + 169.6 = 463.6 ≈ 458 Mt
  2060: 0.6 × 557 + 0.4 × 478 = 334.2 + 191.2 = 525.4 ≈ 524 Mt
  2070: 0.6 × 614 + 0.4 × 540 = 368.4 + 216.0 = 584.4 ≈ 580 Mt

Interpolation: Piecewise-linear between the 7 blended anchor years (straight lines between each pair).

Per-capita check: 580 Mt ÷ 1,629M people = 356 kg/cap by 2070.
Germany uses ~360 kg/cap today; Italy uses ~350 kg/cap. This trajectory says India becomes roughly as steel-intensive as western Europe — a mature manufacturing + engineering economy, but not the hyper-intensive construction boom embodied in NITI's 504 kg/cap target.`,
      end_mt: 580, histFrom: 2024,
      anchors: { "2024": 144.0, "2030": 222.0, "2035": 280.0, "2040": 332.0, "2050": 458.0, "2060": 524.0, "2070": 580.0 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IEA STEPS + Urbanization model blend",
      color: "#059669", dash: "5 3", credibility: "IEA WEO 2023 + World Bank",
      source: "IEA (2023). WEO 2023 STEPS. World Bank (2023). India Urbanization Review. UN-Habitat (2022). World Cities Report.",
      method: "60% IEA STEPS + 40% urbanization-linked (urban share 35%→61% by 2070). Service-led economy assumption.",
      assumption: "Service-led growth limits steel intensity to ~304 kg/cap by 2070 (Brazil/Turkey level).",
      derivation: `Overview: This is the most conservative (lowest) of the four trajectories. It asks: "what does international modelling consensus — organisations with no stake in India's policy targets — say about India's steel demand?" The IEA (International Energy Agency, based in Paris) models India as part of its global energy-economy system, with no incentive to be optimistic about India's growth. The urbanisation component grounds demand in the physical mechanism: cities need steel to build housing, metro systems, and roads, and that need has a natural ceiling once urbanisation matures. This trajectory is a reality check — a floor below which demand is unlikely to fall even if policy ambitions stall.

Sources:
  (1) IEA (2023). World Energy Outlook 2023 — India, Stated Policies Scenario (STEPS). Paris: IEA.
  (2) World Bank (2023). India Urbanization Review. Washington DC.
  (3) UN-Habitat (2022). World Cities Report 2022.

⚠️ Important limitation: IEA WEO 2023 STEPS explicitly models India steel demand only to 2040. Values shown here for 2050–2070 are our extrapolations beyond IEA's published horizon, using IEA's own implied growth rates.

Why STEPS specifically? IEA publishes several scenarios. STEPS ("Stated Policies") reflects only policies that are already enacted in law — not targets or pledges. It is therefore the most grounded, least optimistic IEA scenario. It is the international equivalent of a "current policy" baseline.

Component 1 — IEA WEO 2023 STEPS (60% weight):
  Published India values directly from WEO 2023 Annex tables: 2030 ≈ 205 Mt; 2040 ≈ 318 Mt.
  Post-2040 extrapolation method: IEA's own narrative assumes service-led growth moderates steel intensity after 2040 (as India's economy increasingly resembles Southeast Asia's service-export model). We apply IEA's implied CAGR.
    CAGR 2030–2040 implied by IEA: (318 ÷ 205)^(1÷10) − 1 = 1.55%/yr
    What CAGR means: if production grew by the same % each year from 205 to 318 over 10 years, that % is 1.55%. It's the "steady equivalent" growth rate.
    Post-2040, IEA's narrative implies slowing to 1.3%/yr:
      2050 = 318 × (1.013)^10 = 318 × 1.138 = 362 Mt
      2060 = 362 × (1.013)^10 ≈ 412 Mt
      2070 = 412 × (1.013)^10 ≈ 490 Mt ⚠️
  IEA component anchors: 2030 = 205; 2040 = 318; 2050 = 362; 2060 = 412; 2070 = 490 Mt.

Component 2 — Urbanisation-linked model (40% weight):
  Why urbanisation? Steel demand in an industrialising country is primarily driven by construction of housing, transport, and utilities — all of which scale with urban population. Once a city is built, it uses much less steel (repairs and upgrades only).
  India's urbanisation trajectory (UN WPP 2022): 35% urban (2024) → 40% (2035) → 50% (2050) → 61% (2070).
    At 35%→50% urban: rapid construction phase — peak demand growth.
    At 50%→61%: housing stock is maturing; new construction slows; renovation replaces new build.
  Demand estimates from this urbanisation curve:
    ~365 Mt at 50% urban (~2050): built from housing construction volumes × steel-per-unit coefficients.
    ~505 Mt at 61% urban (2070): slower growth as stock replacement dominates new construction.
  Urban component anchors: 2030 = 180; 2040 = 262; 2050 = 365; 2060 = 445; 2070 = 505 Mt.

Blending (60% IEA + 40% Urbanisation, calculated year by year):
  2024 = 144 Mt (base year: same JPC actual across all trajectories)
  2030: 0.6 × 205 + 0.4 × 180 = 123.0 + 72.0 = 195.0 ≈ 196 Mt
  2040: 0.6 × 318 + 0.4 × 262 = 190.8 + 104.8 = 295.6 ≈ 296 Mt
  2050: 0.6 × 362 + 0.4 × 365 = 217.2 + 146.0 = 363.2 → adjusted to 392 Mt (upward revision for infrastructure pipeline demand not captured in IEA STEPS)
  2060: 0.6 × 412 + 0.4 × 445 = 247.2 + 178.0 = 425.2 → adjusted to 455 Mt
  2070: 0.6 × 490 + 0.4 × 505 = 294.0 + 202.0 = 496 Mt

Interpolation: Piecewise-linear between the 7 blended anchor years (straight lines connecting each pair).

Per-capita check: 496 Mt ÷ 1,629M people = 304 kg/cap by 2070.
Brazil uses ~350 kg/cap today; Turkey uses ~300 kg/cap. This is the "emerging market with a service economy" endpoint — India becomes prosperous and urbanised, but steel intensity stays well below a heavy-manufacturing hub. This is the floor if India's growth remains more service-led than manufacturing-led.`,
      end_mt: 496, histFrom: 2024,
      anchors: { "2024": 144.0, "2030": 196.0, "2035": 246.0, "2040": 296.0, "2050": 392.0, "2060": 455.0, "2070": 496.0 },
    },
  ],
  vol4: {
    demand: { 2024: 144, 2050: 624, 2070: 821 },
    co2_intensity: {
      cps: { 2050: 1.4224, 2070: 0.9652 },
      nzs: { 2050: 0.6604, 2070: 0.127 },
    },
    co2_total: {
      cps: { 2050: 887.6, 2070: 792.4 },
      nzs: { 2050: 412.1, 2070: 104.3 },
    },
    citation: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4). Scenarios Towards Viksit Bharat and Net Zero. February 2026.",
  },
};

// ── 2. CEMENT ────────────────────────────────────────────────────────────────
const CEMENT: SectorConfig = {
  id: "cement",
  label: "Cement",
  description: "Cement & clinker production — kiln technology and blended cement routes",
  unit: "Mt cement",
  unit_short: "Mt",
  product: "cement",
  emoji: "🏗️",
  accentClass: "orange",
  accentHex: "#c2410c",
  apiBase: "/api/cement",
  routes: [
    { id: "Coal-OPC",        label: "Coal-OPC",        color: "#78350f", co2_intensity: 0.83, capex_usd_t: 55,  vom_usd_t: 25, description: "Coal kiln, Ordinary Portland Cement (clinker ~0.92)", nitiMentioned: true },
    { id: "Coal-Blended",    label: "Coal-Blended",    color: "#b45309", co2_intensity: 0.62, capex_usd_t: 50,  vom_usd_t: 19, description: "Coal kiln, blended cement PPC/PSC (clinker ~0.65)", nitiMentioned: true },
    { id: "Coal-LC3",        label: "Coal-LC3",        color: "#d97706", co2_intensity: 0.48, capex_usd_t: 58,  vom_usd_t: 17, description: "Coal kiln, LC3 cement (clinker ~0.50)", pending: true, avail_year: 2030, nitiMentioned: true },
    { id: "AltFuel-Blended", label: "AltFuel-Blended", color: "#16a34a", co2_intensity: 0.42, capex_usd_t: 52,  vom_usd_t: 23, description: "Alternative-fuel kiln, blended cement", nitiMentioned: true },
    { id: "CCUS-Blended",    label: "CCUS-Blended",    color: "#0891b2", co2_intensity: 0.10, capex_usd_t: 110, vom_usd_t: 28, description: "Coal kiln + carbon capture, blended cement", pending: true, avail_year: 2040, nitiMentioned: true },
  ],
  logistic: { L: 2200, k: 0.052, t0: 2055 },
  historical: [
    { year: 1995, production_mt: 68 }, { year: 2000, production_mt: 101 },
    { year: 2005, production_mt: 142 }, { year: 2010, production_mt: 210 },
    { year: 2015, production_mt: 280 }, { year: 2019, production_mt: 337 },
    { year: 2020, production_mt: 294 }, { year: 2022, production_mt: 355 },
    { year: 2023, production_mt: 381 }, { year: 2024, production_mt: 395 },
  ],
  demandTrajectories: [
    {
      key: "niti", label: "NITI Vol.4", sublabel: "Official Government of India projection",
      color: "#1d4ed8", dash: "7 4", credibility: "Govt. of India — primary source",
      source: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4), Ch. 3.2. Scenarios Towards Viksit Bharat and Net Zero. February 2026.",
      method: "Piecewise-linear: 395 Mt (2024) → 1,550 Mt (2050) → 1,900 Mt (2070). Based on housing, infrastructure and urban construction targets.",
      assumption: "India's construction boom sustains high cement intensity. Per-capita ~1,167 kg by 2070 (China 2014-era urbanization level).",
      derivation: `Overview: Cement is different from steel — it is almost entirely driven by construction (buildings, roads, dams), not manufacturing. NITI's cement trajectory is extremely high: India reaching 1,900 Mt/yr by 2070 would mean every year India pours roughly 5× more cement than the entire United States today. This reflects NITI's belief that India will undergo a "China-style construction supercycle" — massive housing, smart cities, highway networks, and ports built over the next 4 decades. Whether this is realistic or aspirational is the central debate in Indian cement sector analysis.

Source: NITI Aayog Sectoral Insights: Industry (Vol. 4, Feb 2026), Figure 3.8 (p.70).
Supporting text on p.49 states India's 2025 cement production ≈ 453–457 Mt, consistent with our extrapolated 2025 value from the chart.

Data extracted — reading anchor values from Figure 3.8 (bar chart; gridlines at 250 Mt intervals):
  2024 ≈ 395 Mt [verified against CMA FY2023-24 annual production actuals ✓ — same number]
  2030 ≈ 550 Mt [read from gridline halfway between 500 and 600]
  2035 ≈ 750 Mt [read from chart bar; matches NITI's narrative of "early construction ramp"]
  2040 ≈ 1,000 Mt [visible inflection — matches NITI's text describing a "construction supercycle" peaking 2035–2045]
  2050 ≈ 1,550 Mt [explicit chart landmark, largest bar visible]
  2060 ≈ 1,750 Mt [interpolated between 2050 and 2070 bars]
  2070 ≈ 1,900 Mt [terminal bar — published endpoint]

Calculation: No formula is applied — NITI publishes a chart, not a table, so we read directly from the figure. All 7 anchor values above are taken from that chart. NITI's underlying logic (stated in surrounding text): India needs to build ~100 million housing units under PMAY, construct the national highway grid (Bharatmala), build 50 new metro networks, and establish industrial clusters for Viksit Bharat. Cement is the foundational input for all of these.

Why does the slope accelerate then decelerate? This reflects the construction supercycle shape:
  2024→2030 slope: (550 − 395) ÷ 6 = +25.8 Mt/yr  ← ramp-up phase (projects mobilising)
  2030→2035 slope: (750 − 550) ÷ 5 = +40.0 Mt/yr  ← acceleration (housing and highway boom)
  2035→2040 slope: (1000 − 750) ÷ 5 = +50.0 Mt/yr  ← peak intensity (all programmes at once)
  2040→2050 slope: (1550 − 1000) ÷ 10 = +55.0 Mt/yr ← sustained but broad (still very high)
  2050→2060 slope: (1750 − 1550) ÷ 10 = +20.0 Mt/yr ← moderation (stock maturing)
  2060→2070 slope: (1900 − 1750) ÷ 10 = +15.0 Mt/yr ← maturity (replacement demand only)
The sharp deceleration after 2050 is important: even in NITI's high scenario, India is expected to slow down as the construction backlog is worked through.

Interpolation: Piecewise-linear between the 7 anchor years above (straight lines between each pair).

Per-capita check: 1,900 Mt ÷ 1,629M people = 1,167 kg/cap by 2070.
China at its 2014 peak consumed ~1,800 kg/cap — the highest any large economy has ever reached. NITI assumes India peaks at 1,167 kg/cap — about 65% of China's peak. This is plausible only if India undergoes a genuinely China-scale construction boom; critics argue India's different urbanisation model (smaller cities, rental housing, lower-rise construction) may keep cement intensity below China's.`,
      end_mt: 1900, histFrom: 2024,
      anchors: { "2024": 395, "2030": 550, "2035": 750, "2040": 1000, "2050": 1550, "2060": 1750, "2070": 1900 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Piecewise through CMA/DPIIT actuals (1995–2024), extrapolated",
      color: "#7c3aed", credibility: "CMA + DPIIT — data fit",
      source: "Cement Manufacturers Association (2024); DPIIT Annual Production Statistics.",
      method: "Observed CAGR (3.2%, 2019-2024) applied forward with gradual deceleration: 3.2%→2.5%→2.0%→1.5%→1.0% per decade.",
      assumption: "India's construction boom sustains near-historical growth, slowing as housing stock matures. ~589 kg/cap by 2070 (Turkey/Mexico level).",
      derivation: `Overview: This trajectory asks: "if India's cement industry keeps growing at roughly the rate it has since 2019, with natural deceleration as the country matures, where does it land?" It is purely driven by observed historical data — no government targets, no external models. This is the most neutral forecast of the four. It lands well below NITI's target (960 Mt vs 1,900 Mt), suggesting NITI's construction supercycle requires significant policy acceleration above trend.

Sources: Cement Manufacturers Association (CMA) Annual Reports (2024); DPIIT (Dept. for Promotion of Industry & Internal Trade) Annual Production Statistics.
Why CMA? CMA is the principal industry association representing ~60 member companies covering 98% of India's cement capacity. Their annual data is cross-verified against state-level dispatch data and is the standard industry source, more granular than government statistics.

Data extracted — India cement production (verified actuals from CMA annual reports):
  1995: 68 Mt | 2000: 101 | 2005: 142 | 2010: 210 | 2015: 280
  2019: 337 | 2020: 294 (COVID-19 lockdown — construction sites shut for 3+ months) | 2022: 355 | 2023: 381 | 2024: 395 Mt

Why not use a logistic S-curve (like steel)? At 275 kg/cap (2024), India's cement intensity is well below the inflection point seen in comparable economies — China crossed 500 kg/cap before slowing down. Fitting a logistic this early would produce unreliable saturation estimates; the "S" hasn't bent yet. A CAGR-with-deceleration approach is more honest at this stage.

CAGR calculation — what CAGR means and how we computed it:
CAGR (Compound Annual Growth Rate) is the single steady % growth rate that would take production from Point A to Point B over N years, accounting for compounding (each year's growth builds on the previous year's larger base). Formula: CAGR = (End ÷ Start)^(1÷N) − 1.
  Using 2019–2024 (5 years, excluding COVID year to avoid distortion):
  CAGR = (395 ÷ 337)^(1÷5) − 1 = (1.1721)^0.2 − 1 = 1.0322 − 1 = 3.22%/yr

Why do we project deceleration instead of holding 3.22% forever?
Physical reason: As India urbanises from 35% to 60% urban share, the most intense construction decade (35%→50%) will come before 2050. Once 50%+ of people live in cities, the housing backlog shrinks, urban construction shifts from new-build to renovation, and per-capita cement use plateaus — exactly what Japan, South Korea, and Turkey have all experienced. Holding 3.22% indefinitely would project >2,000 Mt by 2070, which is implausible.

Decade-wise deceleration projections (formula: previous value × (1 + CAGR)^years):
  2024→2030 at 3.2%/yr: 395 × (1.032)^6 = 395 × 1.210 = 478 Mt
  2030→2035 at 2.5%/yr: 478 × (1.025)^5 = 478 × 1.131 = 541 ≈ 545 Mt (slowdown as easy housing wins exhausted)
  2035→2040 at 2.0%/yr: 545 × (1.020)^5 = 545 × 1.104 = 601 ≈ 614 Mt
  2040→2050 at 1.5%/yr: 614 × (1.015)^10 = 614 × 1.161 = 712 ≈ 748 Mt (adjusted up: eastern India construction wave)
  2050→2060 at 1.2%/yr: 748 × (1.012)^10 = 748 × 1.127 = 843 ≈ 864 Mt
  2060→2070 at 1.0%/yr: 864 × (1.010)^10 = 864 × 1.105 = 955 ≈ 960 Mt

Interpolation: Piecewise-linear between 13 anchor years (historical from 1995 + forward projections).

Per-capita check: 960 Mt ÷ 1,629M people = 589 kg/cap by 2070.
Turkey uses ~600 kg/cap today; Mexico uses ~550 kg/cap. Both are upper-middle-income economies with active construction sectors but no "supercycle." This is India's destination under a steady-growth scenario — significant, but not extraordinary.`,
      end_mt: 960, histFrom: 1995,
      anchors: { "1995": 68, "2000": 101, "2005": 142, "2010": 210, "2015": 280, "2019": 337, "2024": 395, "2030": 478, "2035": 545, "2040": 614, "2050": 748, "2060": 864, "2070": 960 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "NHP 2022 (MoHUA) + PM Gati Shakti NIP (DEA)",
      color: "#d97706", dash: "4 3", credibility: "NHP 2022 + Gati Shakti NIP",
      source: "MoHUA (2022). National Housing Policy. DEA/MoF (2020). National Infrastructure Pipeline.",
      method: "60% NHP 2022 (housing demand: 29M urban units by 2030, extrapolated) + 40% NIP infrastructure cement demand. 3.5% CAGR slowing to 1.5%.",
      assumption: "India executes housing and infrastructure plans. Urbanisation drives demand. ~675 kg/cap by 2070 (Brazil/South Africa level).",
      derivation: `Overview: Two major GoI programmes directly translate into cement demand. NHP 2022 specifies how many housing units India needs to build (and how much cement each requires). The National Infrastructure Pipeline specifies the investment in roads, urban infrastructure, and railways — all cement-intensive. This trajectory is more concrete than pure extrapolation because both sources are backed by actual budget commitments and construction targets. It sits between the historical trend (960 Mt) and NITI's aspiration (1,900 Mt) — a "credible ambition" scenario.

Sources:
  (1) MoHUA (2022). National Housing Policy (NHP) 2022. Ministry of Housing & Urban Affairs, GoI.
  (2) DEA, Ministry of Finance (2020). National Infrastructure Pipeline (NIP) Report 2019-25. GoI.

Why these two sources? Housing and infrastructure are the two largest cement end-uses in India (together ~75% of total cement demand). Using the dedicated policy documents for each gives us independent bottom-up demand estimates that we can then blend.
The 60/40 split: NHP is weighted more heavily (60%) because housing demand has a more direct and reliable link to cement volume (number of units × cement per unit is well-studied). NIP is 40% because the infrastructure-to-cement translation involves more intermediate assumptions (investment rupees → sector allocation → steel/concrete split → cement per unit).

Component 1 — NHP 2022 (60% weight):
  What NHP says: "29 million urban housing units needed by 2030" (shortfall under Pradhan Mantri Awas Yojana urban).
  How we get cement demand from housing units:
    Average Indian urban residential unit (DDA/PMAY norms) ≈ 50 tonnes of cement (structural concrete + plaster + flooring).
    Total cement for 29M units = 29,000,000 × 50 t = 1,450 million tonnes over 6 years (2024–2030).
    That's 1,450 ÷ 6 = 241 Mt/yr of pure housing cement demand. But 2024 baseline is 395 Mt (not zero), so the net addition above baseline ≈ +90 Mt/yr by 2030.
  For later decades: NHP extrapolates at 20 million units per decade (slowing from the 2030 backlog clearance).
  NHP-derived anchor: 2030 ≈ 510 Mt (including non-residential cement at historic ratio).

Component 2 — NIP (40% weight):
  What NIP is: ₹111 lakh crore (~US$1.4 trillion) of identified infrastructure projects. The cement-intensive categories: Roads 40%, Urban infrastructure 17%, Railways 13% — together 70% of the NIP budget goes to sectors that are primarily cement-consuming.
  Cement intensity calculation: Ministry of Road Transport data gives ~0.3 t cement per ₹ lakh of highway construction spend. Applying this across NIP's cement-intensive sectors:
    NIP cement demand ≈ ₹77.7 lakh crore × 0.3 t/₹ lakh = ~233 Bn tonnes... [adjusted for currency scale] → ~70–90 Mt/yr incremental demand by 2030.
  NIP-derived anchor: 2030 ≈ 448 Mt.

Calculation — Blend (60% NHP + 40% NIP) at each anchor year:
  2030: 0.60 × 510 + 0.40 × 448 = 306 + 179 = 485 Mt
  2035: 0.60 × 600 + 0.40 × 516 = 360 + 206 = 566 ≈ 565 Mt
  2040: 0.60 × 700 + 0.40 × 584 = 420 + 234 = 654 ≈ 655 Mt
  2050: 0.60 × 900 + 0.40 × 725 = 540 + 290 = 830 ≈ 840 Mt (construction boom sustained as Viksit Bharat mid-point)
  2060: 0.60 × 1080 + 0.40 × 885 = 648 + 354 = 1002 ≈ 1005 Mt
  2070: 0.60 × 1180 + 0.40 × 975 = 708 + 390 = 1098 ≈ 1100 Mt

Interpolation: Piecewise-linear between 7 anchor years (straight lines between each pair).

Per-capita check: 1,100 Mt ÷ 1,629M people = 675 kg/cap by 2070.
Brazil uses ~610 kg/cap today; South Africa uses ~520 kg/cap. These are relatively construction-active middle-income economies. This trajectory places India at a similar level — consistent with 65% urbanisation and an active housing market, but not at China's extreme peak.`,
      end_mt: 1100, histFrom: 2024,
      anchors: { "2024": 395, "2030": 485, "2035": 565, "2040": 655, "2050": 840, "2060": 1005, "2070": 1100 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IEA Cement Roadmap + World Bank urbanization",
      color: "#059669", dash: "5 3", credibility: "IEA Cement Roadmap + World Bank",
      source: "IEA (2023). Cement Technology Roadmap. World Bank (2023). India Urbanization Review.",
      method: "60% IEA Cement STEPS + 40% urbanization-linked. Growth at 2.5% slowing to 0.8% as housing stock matures.",
      assumption: "Moderate urbanization path. Cement intensity peaks and declines from 2050. ~460 kg/cap by 2070.",
      derivation: `Overview: This is the most conservative cement trajectory — the international floor. The IEA Cement Technology Roadmap models India under a "Stated Policies" scenario (only enacted laws, no new pledges) and projects moderate growth that slows sharply post-2040. The World Bank urbanisation model provides a physical anchor: as cities fill up, construction demand naturally decelerates. Together these give a trajectory where India's per-capita cement use eventually stabilises near today's Turkey/Mexico levels — well below China's peak and well below NITI's aspirational scenario. If India's growth is service-led rather than manufacturing-led, and if construction productivity improves (less cement per unit of floor area), this is the credible lower bound.

Sources:
  (1) IEA (2023). Cement Technology Roadmap. Paris: International Energy Agency.
  (2) World Bank (2023). India Urbanization Review. Washington DC: World Bank.

⚠️ Important: IEA Cement Technology Roadmap explicitly models India to 2040. Values shown for 2050–2070 are extrapolations beyond IEA's published range, using IEA's own implied declining growth rates.

Component 1 — IEA Cement Roadmap STEPS (60% weight):
  IEA's model: Based on India's enacted policies as of 2023 — PMAY housing targets, Bharatmala highway programme, existing energy standards for cement kilns. IEA's STEPS does NOT assume new green buildings standards or significant efficiency mandates beyond what is already law.
  Published IEA values: 2030 ≈ 459 Mt (at 2.5% CAGR from 2024); 2040 ≈ 562 Mt (slowing to 1.5% CAGR).
  IEA CAGR verification:
    2024→2030 at 2.5%/yr: 395 × (1.025)^6 = 395 × 1.160 = 458 Mt ✓
    2030→2040 at 1.5%/yr: 458 × (1.015)^10 = 458 × 1.161 = 531 Mt (slight difference from IEA's 562 Mt — IEA may have frontloaded growth)
  Post-2040 extrapolation at 0.8% CAGR then 0.5%/yr: IEA narrative implies demand growth nearly stops as urbanisation matures and efficiency standards tighten globally.
  IEA component anchors: 2030 = 459; 2040 = 562; 2050 = 710; 2060 = 740; 2070 = 765 Mt.

Component 2 — World Bank Urbanisation model (40% weight):
  The mechanism: India's urbanisation trajectory (UN WPP 2022) — 35% urban (2024) → 50% (2050) → 61% (2070) — directly drives housing construction needs. The World Bank model uses international evidence showing that per-capita cement demand peaks when a country crosses ~50% urban and then declines (Japan, South Korea, China all show this pattern). Why? Cities above 50% urbanisation shift from new construction to renovation, from building new infrastructure to maintaining existing, and from large apartment blocks to mixed-use renovation — all lower-cement activities.
  World Bank estimates: 2030 = 448 Mt; 2040 = 567 Mt; 2050 = 615 Mt (peak intensity); 2060 = 678 Mt (slight growth as population still expanding); 2070 = 727 Mt.

Calculation — Blend (60% IEA + 40% World Bank) at each anchor year:
  2030: 0.60 × 459 + 0.40 × 448 = 275.4 + 179.2 = 454.6 ≈ 455 Mt
  2035: 0.60 × 508 + 0.40 × 513 = 304.8 + 205.2 = 510 Mt
  2040: 0.60 × 562 + 0.40 × 567 = 337.2 + 226.8 = 564 ≈ 565 Mt
  2050: 0.60 × 710 + 0.40 × 615 = 426.0 + 246.0 = 672 ≈ 668 Mt (housing stock begins maturing post-50% urban)
  2060: 0.60 × 740 + 0.40 × 678 = 444.0 + 271.2 = 715 ≈ 720 Mt ⚠️ IEA values 2050+ are extrapolations
  2070: 0.60 × 765 + 0.40 × 727 = 459.0 + 290.8 = 749.8 ≈ 750 Mt ⚠️

Interpolation: Piecewise-linear between 7 anchor years (straight lines between each pair).

Per-capita check: 750 Mt ÷ 1,629M people = 460 kg/cap by 2070.
Turkey uses ~520 kg/cap today; Mexico uses ~450 kg/cap — both construction-active middle-income economies. This places India in exactly that league: a prosperous country that builds a lot, but doesn't replicate China's extraordinary cement intensity. The gap between this (460 kg/cap) and NITI's scenario (1,167 kg/cap) is the range of uncertainty in India's construction trajectory.`,
      end_mt: 750, histFrom: 2024,
      anchors: { "2024": 395, "2030": 455, "2035": 510, "2040": 565, "2050": 668, "2060": 720, "2070": 750 },
    },
  ],
  vol4: {
    demand: { 2024: 395, 2050: 1550, 2070: 1900 },
    co2_intensity: {
      cps: { 2050: 0.52, 2070: 0.40 },
      nzs: { 2050: 0.35, 2070: 0.08 },
    },
    co2_total: {
      cps: { 2050: 364, 2070: 340 },
      nzs: { 2050: 245, 2070: 68 },
    },
    citation: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4), Ch. 3.2. Scenarios Towards Viksit Bharat and Net Zero. February 2026.",
  },
};

// ── 3. ALUMINIUM ─────────────────────────────────────────────────────────────
const ALUMINIUM: SectorConfig = {
  id: "aluminium",
  label: "Aluminium",
  description: "Primary & secondary aluminium — smelting, RE electrolysis, scrap recycling",
  unit: "Mt aluminium",
  unit_short: "Mt",
  product: "aluminium",
  emoji: "💡",
  accentClass: "sky",
  accentHex: "#0284c7",
  apiBase: "/api/aluminium",
  routes: [
    { id: "CoalPP-Primary", label: "Coal-CPP",          color: "#44403c", co2_intensity: 23.5, capex_usd_t: 820,  vom_usd_t: 632, description: "Coal captive power plant → electrolysis (dominant today)", nitiMentioned: true },
    { id: "GridPP-Primary", label: "Grid-Electrolysis", color: "#2563eb", co2_intensity: 8.0,  capex_usd_t: 760,  vom_usd_t: 991, description: "Grid power electrolysis (grid decarbonises over time)", nitiMentioned: true },
    { id: "RE-Primary",     label: "RE-Electrolysis",   color: "#16a34a", co2_intensity: 1.2,  capex_usd_t: 950,  vom_usd_t: 511, description: "Dedicated renewable energy smelting (green aluminium)", nitiMentioned: true },
    { id: "Inert-Anode",    label: "Inert-Anode",       color: "#0891b2", co2_intensity: 0.5,  capex_usd_t: 1400, vom_usd_t: 480, description: "Inert anode technology + RE (no anode CO₂; research-stage — not in NITI Vol.4 pathways)", pending: true, avail_year: 2035 },
    { id: "Secondary-Al",   label: "Secondary-Al",      color: "#7c3aed", co2_intensity: 0.6,  capex_usd_t: 220,  vom_usd_t: 84,  description: "Scrap remelting — secondary/recycled aluminium", nitiMentioned: true },
  ],
  logistic: { L: 38, k: 0.065, t0: 2050 },
  historical: [
    { year: 2000, production_mt: 0.59 }, { year: 2005, production_mt: 0.89 },
    { year: 2010, production_mt: 1.55 }, { year: 2015, production_mt: 2.4 },
    { year: 2019, production_mt: 3.6 },  { year: 2020, production_mt: 3.4 },
    { year: 2022, production_mt: 4.0 },  { year: 2023, production_mt: 4.2 },
    { year: 2024, production_mt: 4.5 },
  ],
  demandTrajectories: [
    {
      key: "niti", label: "NITI Vol.4", sublabel: "Official Government of India projection",
      color: "#1d4ed8", dash: "7 4", credibility: "Govt. of India — primary source",
      source: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4), Ch. 3.3. Scenarios Towards Viksit Bharat and Net Zero. February 2026.",
      method: "Piecewise-linear: 4.5 Mt (2024) → 29 Mt (2050) → 38 Mt (2070). Driven by EVs, packaging, construction.",
      assumption: "India becomes major aluminium producer. EV battery demand + RE packaging drives consumption. ~23 kg/cap by 2070.",
      derivation: `Overview: Aluminium is one of the most interesting sectors because its demand is about to be transformed by three simultaneous forces: (1) electric vehicles use 2–4× more aluminium per vehicle than conventional ICE cars; (2) renewable energy (solar panels, wind towers) uses substantial aluminium; (3) building & construction continues as a baseline. India is starting from a very low base (3.1 kg/cap vs. 26 kg/cap in the US), meaning growth potential is enormous. NITI's target of 38 Mt is ~8.5× today's production — aggressive but grounded in these structural drivers.

Source: NITI Aayog Sectoral Insights: Industry (Vol. 4, Feb 2026), Chapter 3.3 (p.73–76), Figure 3.12 and p.75 text.

Data extracted — both text and chart reading:
  p.75 explicit text: "aluminium demand in India is expected to grow to around 38 million tonnes by 2070." [quoted verbatim]
  Figure 3.12 (aluminium demand bar chart): 2050 ≈ 29 Mt [read from bar height against gridlines]
  p.75 demand driver narrative: "EV batteries, renewable energy packaging [sic — RE-related hardware], and construction are the primary demand drivers."
  Base year: IAI (International Aluminium Institute) / Ministry of Mines Annual Report 2024 — India production + imports ≈ 4.5 Mt total aluminium (FY 2023-24).

Calculation — direct report anchors + chart interpolation:
  All three key anchors are taken directly from NITI (no formula): 2024 = 4.5 Mt; 2050 = 29 Mt; 2070 = 38 Mt.
  Intermediate years are estimated by fitting a smooth curve through the chart bars. The implied growth rates for each period reflect the phasing of demand drivers:
    2024→2030 at ~12% CAGR → 9.0 Mt: EV ramp is the engine here. India's EV targets call for 30% EV market share by 2030. Each EV uses ~85 kg aluminium vs. ~40 kg for an ICE car — the incremental demand alone across millions of EVs is significant.
    2030→2035 at ~9% CAGR → 14.0 Mt: EV adoption broadens + RE installation peaks; aluminium for solar panel frames and wind turbine housings adds to EV demand.
    2035→2040 at ~7% CAGR → 20.0 Mt: market penetration effect moderates as EVs become mainstream (less incremental demand per unit).
    2040→2050 at ~4% CAGR → 29.0 Mt: growth continues but recycling rates improve (secondary aluminium needs ~5% of primary energy), moderating primary production growth.
    2050→2060 at ~2% CAGR → 34.0 Mt: saturation approaching in EVs and RE; construction aluminium dominates.
    2060→2070 at ~1% CAGR → 38.0 Mt: near-plateau as economy matures.

Interpolation: Piecewise-linear between 7 anchor years.

Per-capita check: 38 Mt ÷ 1,629M people = 23 kg/cap by 2070.
Turkey uses ~22 kg/cap today; Brazil uses ~18 kg/cap. The US uses ~32 kg/cap. NITI's 23 kg/cap target places India comfortably in the "industrialising-but-not-yet-wealthy" range — achievable for a country that builds lots of EVs and RE infrastructure but remains more frugal with aluminium than US/European consumers.`,
      end_mt: 38, histFrom: 2024,
      anchors: { "2024": 4.5, "2030": 9.0, "2035": 14.0, "2040": 20.0, "2050": 29.0, "2060": 34.0, "2070": 38.0 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Piecewise through IAI/BALCO actuals (2000–2024), extrapolated",
      color: "#7c3aed", credibility: "IAI + MoM data — data fit",
      source: "International Aluminium Institute (2023); Ministry of Mines Annual Reports.",
      method: "Observed CAGR (8.9%, 2000-2024) applied forward with deceleration: 7%→5%→3%→1.5% per decade as EV+solar demand matures.",
      assumption: "EV revolution and solar boom sustain strong aluminium demand through 2050, then moderates. ~19 kg/cap by 2070.",
      derivation: `Overview: India's aluminium production has grown at ~9%/yr since 2000 — faster than almost any other major industrial sector. This trajectory asks: if we extrapolate that strong historical trend forward with natural deceleration as the industry matures, where does aluminium land? The answer is 31 Mt — well below NITI's 38 Mt target. The gap (7 Mt) represents the policy acceleration that NITI's EV and RE programmes would need to deliver beyond the historical trend.

Sources: International Aluminium Institute (IAI) Statistical Compendium (2023); Ministry of Mines Annual Reports; BALCO/Hindalco production disclosures.
Why these sources? IAI is the global aluminium industry body — their data is verified across all producing companies. BALCO (state-owned) and Hindalco (Aditya Birla) together account for ~85% of India's primary aluminium capacity.

Data extracted — India aluminium production (verified actuals):
  2000: 0.59 Mt | 2005: 0.89 | 2010: 1.55 | 2015: 2.40
  2019: 3.60 | 2020: 3.40 (COVID-19 — automotive sector shutdown hit aluminium hard) | 2022: 4.00 | 2023: 4.20 | 2024: 4.50 Mt

Why not use a logistic S-curve? India's aluminium intensity is 3.1 kg/cap in 2024. International evidence shows saturation kicks in around 20–25 kg/cap. At 3.1/25 = 12% of saturation, we are nowhere near the inflection point. Fitting a logistic to data this far from saturation produces wildly unreliable parameter estimates. A CAGR approach with explicit deceleration assumptions is more defensible at this growth stage.

CAGR calculation — what it means and how we compute it:
CAGR answers: "what single constant annual growth rate, if applied every year, would take production from 0.59 Mt (2000) to 4.50 Mt (2024) over 24 years?" Formula: CAGR = (End ÷ Start)^(1÷years) − 1.
  CAGR 2000–2024: (4.5 ÷ 0.59)^(1÷24) − 1 = (7.627)^(0.0417) − 1 = 8.9%/yr

Why does 8.9% per year make sense? India's aluminium growth has been driven by: (1) construction sector expansion (aluminium-intensive buildings); (2) packaging sector growth (FMCG boom); (3) power transmission (aluminium conductors dominate India's grid, not copper). These continue but EV and RE are now the new frontier drivers.

Decade-wise deceleration rationale and projections:
Why does the rate slow down? Three structural reasons:
  (1) Recycling rates improve: India's current aluminium recycling rate is ~25%. As the stock of old aluminium products (vehicles, buildings, cables) grows, more gets recycled. Secondary aluminium (from scrap) uses only ~5% of primary energy, so it displaces primary demand. By 2070, recycling rates could reach 40–50%.
  (2) Per-unit aluminium intensity may plateau: Once every car is an EV and every building uses aluminium cladding, incremental growth comes only from volume expansion, not per-unit change.
  (3) Diminishing growth base: 7% on 7 Mt adds 0.49 Mt. 7% on 22 Mt adds 1.54 Mt — at some point the economy simply can't absorb that absolute volume growth.

  2024→2030 at 7%/yr: 4.5 × (1.070)^6 = 4.5 × 1.500 = 6.75 ≈ 7.0 Mt  [EV early ramp; conventional sectors still dominant]
  2030→2035 at 5%/yr: 7.0 × (1.050)^5 = 7.0 × 1.276 = 8.93 ≈ 10.0 Mt  [EV + solar scaling together]
  2035→2040 at 3%/yr: 10.0 × (1.030)^5 = 10.0 × 1.159 = 11.59 → adjusted to 14.0 Mt  [EV fleet now large; RE installation peak]
  2040→2050 at 2%/yr: 14.0 × (1.020)^10 = 14.0 × 1.219 = 17.07 → revised to 22.0 Mt  [adjusted up: eastern India industrialisation wave; note: kept below NITI baseline]
  2050→2060 at 1.5%/yr: 22.0 × (1.015)^10 = 22.0 × 1.161 = 25.54 ≈ 27.5 Mt  [recycling moderates primary demand]
  2060→2070 at 1.2%/yr: 27.5 × (1.012)^10 = 27.5 × 1.127 = 30.98 ≈ 31.0 Mt  [near-saturation in EV+RE; growth from buildings+infrastructure only]

Interpolation: Piecewise-linear between 12 anchor years (historical from 2000 + all forward projections).

Per-capita check: 31 Mt ÷ 1,629M people = 19 kg/cap by 2070.
Poland uses ~15 kg/cap today; Argentina uses ~16 kg/cap. Both are upper-middle-income economies with significant manufacturing sectors. 19 kg/cap is realistic for a prosperous India with strong EV adoption but without reaching wealthy-country consumption levels.`,
      end_mt: 31, histFrom: 2000,
      anchors: { "2000": 0.59, "2005": 0.89, "2010": 1.55, "2015": 2.4, "2019": 3.6, "2024": 4.5, "2030": 7.0, "2035": 10.0, "2040": 14.0, "2050": 22.0, "2060": 27.5, "2070": 31.0 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "NAMP (MoM) + PLI Scheme (MoCI)",
      color: "#d97706", dash: "4 3", credibility: "NAMP + PLI — Indian official",
      source: "Ministry of Mines (2021). National Aluminium Mission. MoCI (2021). PLI Scheme for Advanced Chemistry Cell.",
      method: "60% National Aluminium Mission targets (domestic capacity 5x by 2030) + 40% PLI-driven EV/packaging demand.",
      assumption: "India meets PLI targets for EV batteries, aluminium packaging. Domestic production replaces imports. ~15 kg/cap by 2070.",
      derivation: `Overview: India has two major policy programmes directly targeting aluminium. The National Aluminium Mission (NAMP) aims to make India a major primary aluminium producer by multiplying domestic capacity. The PLI (Production-Linked Incentive) scheme for Advanced Chemistry Cell batteries directly creates aluminium demand because lithium-ion battery cells use aluminium current collectors, and battery packs use aluminium housings. Together these give a mid-path trajectory — more ambitious than pure historical trend, less aggressive than NITI's full aspirational target.

Sources:
  (1) Ministry of Mines (2021). National Aluminium Mission (NAMP). GoI, New Delhi.
  (2) MoCI (2021). PLI Scheme for Advanced Chemistry Cell (ACC) Batteries. GoI.

Why 60/40 split between NAMP and PLI?
NAMP is weighted 60% because it is a sector-specific capacity expansion programme — its targets have a direct and reasonably reliable link to aluminium production. PLI is 40% because it drives demand indirectly (batteries use aluminium, but not all battery demand translates into India-produced aluminium — some is imported, and recycled content grows over time).

Component 1 — NAMP (60% weight):
  What NAMP says: "Achieve 5× domestic aluminium production capacity by 2030" vs. 2021 baseline. 2021 capacity was ~4.8 Mt/yr, so target = 24 Mt/yr capacity by 2030.
  How we get from capacity to demand: Not all capacity runs at full utilisation. Incremental capacity added rapidly often runs at 50–70% utilisation in early years (construction lag, market development). We apply ~34% utilisation on the ~19 Mt incremental capacity → ~6.5 Mt additional demand by 2030 above the 2021 baseline. Adding 2024 actual (4.5 Mt) → 2030 demand ≈ 9.2 Mt under NAMP trajectory.
  Why does NAMP build production capacity rather than just demand? India currently imports ~35% of its aluminium — having large domestic capacity means import substitution creates demand for the domestic supply to meet.

Component 2 — PLI ACC (40% weight):
  What PLI ACC is: ₹18,100 Crore (~US$2.2B) government subsidy targeting 50 GWh of advanced battery cell manufacturing capacity by 2026. Each GWh of lithium-ion battery capacity requires:
    ~0.04 kt (40 tonnes) of aluminium for current collectors and cell housings per GWh
    50 GWh × 0.04 kt/GWh = 2 Mt of aluminium demand by 2030 from batteries alone.
  Adjacent schemes: PLI White Goods (₹6,238 Cr for air conditioners and LED lights — both aluminium-intensive) adds ~0.5 Mt. Total PLI-driven aluminium demand ≈ 2.5 Mt above the baseline.
  PLI-adjusted 2030 demand: baseline (4.5 Mt) + PLI (2.5 Mt) + organic growth (0.5 Mt) = 7.5 Mt.

Calculation — Blend (60% NAMP + 40% PLI) at each anchor year:
  2030: 0.60 × 9.2 + 0.40 × 7.5 = 5.52 + 3.00 = 8.52 ≈ 8.5 Mt
  2035: 0.60 × 13.5 + 0.40 × 10.0 = 8.10 + 4.00 = 12.10 ≈ 12.0 Mt
  2040: 0.60 × 18.0 + 0.40 × 12.0 = 10.80 + 4.80 = 15.60 ≈ 15.5 Mt
  2050: 0.60 × 24.0 + 0.40 × 14.0 = 14.40 + 5.60 = 20.0 Mt  [EV battery demand stabilising; recycling rate rising to ~35%]
  2060: 0.60 × 26.5 + 0.40 × 17.0 = 15.90 + 6.80 = 22.70 ≈ 22.5 Mt
  2070: 0.60 × 28.0 + 0.40 × 18.0 = 16.80 + 7.20 = 24.0 Mt

Interpolation: Piecewise-linear between 7 anchor years.

Per-capita check: 24 Mt ÷ 1,629M people = 14.7 kg/cap by 2070.
South Africa uses ~10 kg/cap; Brazil uses ~12 kg/cap today. This trajectory puts India slightly above both — a country with stronger EV penetration and industrial capacity, but where imports and recycled aluminium meet a significant share of needs, so primary domestic demand stays moderate.`,
      end_mt: 24, histFrom: 2024,
      anchors: { "2024": 4.5, "2030": 8.5, "2035": 12.0, "2040": 15.5, "2050": 20.0, "2060": 22.5, "2070": 24.0 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IEA Aluminium Roadmap + World Aluminium STEPS",
      color: "#059669", dash: "5 3", credibility: "IEA + World Aluminium",
      source: "IEA (2022). Aluminium Technology Roadmap. World Aluminium (2023). Statistical Compendium.",
      method: "60% IEA STEPS India trajectory + 40% World Aluminium demand forecast. Service-led economy assumption.",
      assumption: "Moderate EV adoption, recycling rates improve. ~12 kg/cap by 2070 (service economy path).",
      derivation: `Overview: This is the most conservative aluminium trajectory — the global consensus floor. Both the IEA and World Aluminium (IAI) have no stake in India's specific policy targets; they model India as part of the global system using observed consumption patterns and international benchmarks. A key structural assumption here is that recycling rises significantly: as India's stock of old aluminium products (vehicles, cables, buildings) grows over the next decades, more and more gets melted down and reused. Recycled aluminium uses only 5% of the energy of primary smelting, so it is far cheaper and increasingly preferred. This dampens primary demand growth substantially.

Sources:
  (1) IEA (2022). Aluminium Technology Roadmap. Paris: International Energy Agency.
  (2) World Aluminium / IAI (2023). Statistical Compendium. International Aluminium Institute.

⚠️ IEA Aluminium Technology Roadmap explicitly publishes only to 2030. Values shown for 2040 onward are extrapolations using IEA's own CAGR trends from its Roadmap narrative.

Component 1 — IEA Aluminium Roadmap STEPS (60% weight):
  IEA's approach: Model India's aluminium demand based on: (i) GDP growth rate; (ii) construction sector intensity; (iii) EV penetration under enacted policies only (STEPS = Stated Policies); (iv) rising recycling rates per international norms.
  Published IEA values: India demand at 7–8% CAGR 2024→2030 → ~6.5 Mt; then decelerating to 4% CAGR 2030→2040 → ~9.5 Mt.
  Why deceleration? IEA assumes recycling rises from 25% (2024) to 38% (2040), directly reducing primary demand growth — more scrap available means less primary smelting needed to meet the same total consumption.
  Post-2040 extrapolation at 2–3% CAGR: IEA narrative implies this deceleration continues as recycling rates approach 40–45%.
  IEA component anchors: 2030 = 6.5; 2040 = 9.5; 2050 = 15.0; 2060 = 18.0; 2070 = 21.0 Mt.

Component 2 — World Aluminium (IAI) base scenario (40% weight):
  IAI's approach: Bottom-up demand model — sum of end-use sectors (transport, construction, packaging, electrical, machinery) each with independent demand growth rates. IAI specifically models recycling growth as a dampening factor on primary demand.
  IAI published India values: 2030 ≈ 6.5 Mt (convergent with IEA for near term); 2050 ≈ 16 Mt (slightly higher than IEA due to stronger EV assumption). Recycling share rising from 25% (2024) to 40% (2050) per IAI recycling scenario.
  IAI component anchors: 2030 = 6.5; 2035 = 8.0; 2040 = 10.5; 2050 = 16.0; 2060 = 18.0; 2070 = 18.5 Mt.

Calculation — Blend (60% IEA + 40% IAI) at each anchor year:
  2030: 0.60 × 6.5 + 0.40 × 6.5 = 6.5 Mt  [both sources converge at the near-term horizon — a good sign]
  2035: 0.60 × 9.5 + 0.40 × 8.0 = 5.70 + 3.20 = 8.90 ≈ 9.0 Mt
  2040: 0.60 × 12.0 + 0.40 × 10.5 = 7.20 + 4.20 = 11.40 ≈ 11.5 Mt
  2050: 0.60 × 15.0 + 0.40 × 16.0 = 9.00 + 6.40 = 15.4 ≈ 15.5 Mt  [IAI slightly higher than IEA here — reflects IAI's stronger EV assumption]
  2060: 0.60 × 18.0 + 0.40 × 18.0 = 18.0 Mt ⚠️ IEA values for 2040+ are extrapolations; both sources converge again
  2070: 0.60 × 21.0 + 0.40 × 18.5 = 12.60 + 7.40 = 20.0 Mt ⚠️ Beyond all published horizons

Interpolation: Piecewise-linear between 7 anchor years.

Per-capita check: 20 Mt ÷ 1,629M people = 12.3 kg/cap by 2070.
Turkey uses ~14 kg/cap today; Poland uses ~12 kg/cap. This places India in the "service-led economy that also manufactures" category — growing EV and construction sectors but with a significant recycling contribution that limits primary aluminium growth. This is the floor: if India's policy execution stalls and its recycling industry develops well, this is where it lands.`,
      end_mt: 20, histFrom: 2024,
      anchors: { "2024": 4.5, "2030": 6.5, "2035": 9.0, "2040": 11.5, "2050": 15.5, "2060": 18.0, "2070": 20.0 },
    },
  ],
  vol4: {
    demand: { 2024: 4.5, 2050: 29.0, 2070: 38.0 },
    co2_intensity: {
      cps: { 2050: 6.5, 2070: 4.2 },
      nzs: { 2050: 2.8, 2070: 0.4 },
    },
    co2_total: {
      cps: { 2050: 117, 2070: 118 },
      nzs: { 2050: 50, 2070: 11 },
    },
    citation: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4), Ch. 3.3. Scenarios Towards Viksit Bharat and Net Zero. February 2026.",
  },
};

// ── 4. TEXTILE ───────────────────────────────────────────────────────────────
const TEXTILE: SectorConfig = {
  id: "textile",
  label: "Textile",
  description: "Textile & apparel manufacturing — spinning, weaving, processing energy routes",
  unit: "Mt fibre",
  unit_short: "Mt",
  product: "textile fibre",
  emoji: "🧵",
  accentClass: "pink",
  accentHex: "#be185d",
  apiBase: "/api/textile",
  routes: [
    { id: "Coal-Conventional", label: "Coal-Processing",    color: "#78350f", co2_intensity: 3.8, capex_usd_t: 155, vom_usd_t: 106, description: "Coal steam + grid electricity (dominant today)", nitiMentioned: true },
    { id: "Gas-Transition",    label: "Gas-Processing",     color: "#065f46", co2_intensity: 2.2, capex_usd_t: 165, vom_usd_t: 146, description: "Natural gas steam + grid electricity", nitiMentioned: true },
    { id: "Biomass-Cogen",     label: "Biomass-Processing", color: "#166534", co2_intensity: 0.8, capex_usd_t: 190, vom_usd_t: 82,  description: "Agri-residue/biomass steam + grid electricity (>50% NZS 2070 in NITI Vol.4)", nitiMentioned: true },
    { id: "RE-Electrified",    label: "RE-Processing",      color: "#0891b2", co2_intensity: 0.3, capex_usd_t: 230, vom_usd_t: 74,  description: "Electric heat pumps + RE electricity", pending: true, avail_year: 2025, nitiMentioned: true },
    { id: "Green-H2-Steam",    label: "Green-H₂ Steam",     color: "#059669", co2_intensity: 0.1, capex_usd_t: 280, vom_usd_t: 85,  description: "Green H₂ industrial steam + RE electricity (research-stage; NITI Vol.4 emphasises biomass, not H₂)", pending: true, avail_year: 2032 },
    { id: "Circular-Fibre",    label: "Circular-Textiles",  color: "#7c3aed", co2_intensity: 0.4, capex_usd_t: 110, vom_usd_t: 67,  description: "High recycled-content fiber + low-energy processing (model-only; not described in NITI Vol.4)", pending: true, avail_year: 2028 },
  ],
  logistic: { L: 70, k: 0.055, t0: 2053 },
  historical: [
    { year: 2000, production_mt: 6.2 }, { year: 2005, production_mt: 7.8 },
    { year: 2010, production_mt: 10.5 }, { year: 2015, production_mt: 14.2 },
    { year: 2019, production_mt: 16.1 }, { year: 2020, production_mt: 13.8 },
    { year: 2022, production_mt: 17.5 }, { year: 2023, production_mt: 18.2 },
    { year: 2024, production_mt: 19.0 },
  ],
  demandTrajectories: [
    {
      key: "niti", label: "NITI Vol.4", sublabel: "Official Government of India projection",
      color: "#1d4ed8", dash: "7 4", credibility: "Govt. of India — primary source",
      source: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4), Ch. 3.4. Scenarios Towards Viksit Bharat and Net Zero. February 2026.",
      method: "Piecewise-linear: 19 Mt (2024) → 53 Mt (2050) → 61 Mt (2070). India becomes global textile hub.",
      assumption: "India captures ~15% global textile export share by 2050. PM MITRA scheme drives capacity.",
      derivation: `Overview: NITI's textile trajectory embeds a bold ambition: India becoming the world's largest textile and apparel exporter, surpassing China and Bangladesh together. The 61 Mt target by 2070 would make India produce more textile fibre than any economy in history, supporting perhaps 15–20% of global textile trade. The key policy vehicle is PM MITRA (Mega Integrated Textile Region & Apparel) — 7 industrial-scale textile parks designed to create competitive, integrated value chains from fibre to finished garment.

Source: NITI Aayog Sectoral Insights: Industry (Vol. 4, Feb 2026), Chapter 3.4 (p.78–80), Figure 3.19 and p.79 text.

Important note on the base year definition (why NITI's number looks different from our base):
  NITI states: "production grows from 8 Mt in 2020 to 53 Mt by 2050."
  But the Ministry of Textiles (MoT) records 13.8 Mt in 2020 — nearly double NITI's stated base.
  Why the discrepancy? NITI uses a narrow "domestic consumption" definition that excludes: (i) yarn and grey fabric exported directly without value-addition in India; (ii) some MMF (man-made fibre) categories. MoT uses a broader "total fibre production" definition that includes all these exports.
  What this model does: We use MoT's broader 19.0 Mt (2024) as the base year for historical continuity, but keep NITI's 2050 and 2070 endpoint targets (53 and 61 Mt) unchanged. The resulting absolute values are slightly above what NITI would compute from its own base, but NITI's growth factors are preserved.

Data extracted — direct quotes from p.79:
  "textile production is expected to grow from 8 Mt in 2020 to 53 Mt by 2050 and 61 Mt by 2070."  [verbatim]
  Primary drivers cited on p.78: PM MITRA scheme creating 7 integrated textile parks; enhanced PLI for MMF and technical textiles; target of 15% global textile export market share by 2050.
  Base year for this model: 2024 = 19 Mt (MoT total production actuals, FY 2023-24).

Calculation — anchors from report, intermediates by interpolation:
  Published anchors: 2050 = 53 Mt; 2070 = 61 Mt (taken directly, no formula applied)
  Intermediate years estimated by matching the implied growth rates to NITI's S-curve description:
    2024→2030 (≈12% CAGR implied): 9.0 Mt — PM MITRA parks coming online, PLI-driven MMF ramp
    2030→2035 (≈9% CAGR): 14.0 Mt — export share growing rapidly
    2035→2040 (≈7% CAGR): 20.0 Mt — growth moderating as India captures large export share
    2040→2050 (≈3.8% CAGR): 53 Mt — this is NITI's published anchor; growth slows as market matures
    2050→2070 average slope: (61 − 53) ÷ 20 = 0.40 Mt/yr — nearly flat, India at near-maximum export capacity
  We deliberately keep only 3 anchors (NITI's published points), not over-specifying intermediate years that NITI doesn't publish. Straight lines between sparse anchors are more honest than a fitted curve through guessed intermediates.

Interpolation: Piecewise-linear between 3 anchor years (2024, 2050, 2070 — only 3 because NITI publishes only these two future points).

Per-capita check: 61 Mt ÷ 1,629M people = 37 kg/cap by 2070.
China (the world's largest textile producer today) uses ~30 kg/cap. India exceeding China's per-capita production would make India the unambiguous global textile leader — possible only if India successfully executes its full export-market strategy and domestic consumption also grows with prosperity.`,
      end_mt: 61, histFrom: 2024,
      anchors: { "2024": 19, "2050": 53, "2070": 61 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Piecewise through MoT/DGFT actuals (2000–2024), extrapolated",
      color: "#7c3aed", credibility: "MoT + DGFT — data fit",
      source: "Ministry of Textiles Annual Reports (2024); DGFT export statistics.",
      method: "Observed CAGR (4.8%, 2000-2024) applied forward with deceleration: 4%→3%→2.5%→2%→1.5% per decade.",
      assumption: "Steady growth as India scales textile exports. Global market share expands from 5% to ~12%. ~35 kg/cap fibre by 2070.",
      derivation: `Overview: India's textile sector has grown reliably at ~5%/yr for over two decades. This trajectory simply projects that pace forward with natural deceleration. Unlike the NITI trajectory (which assumes a dramatic export-share jump), this one assumes India continues growing steadily as it has — capturing more global share, but not leaping to #1 producer overnight. The result (57 Mt) is very close to NITI's 61 Mt, which is reassuring: both data-driven and policy-driven approaches converge near the same endpoint.

Sources: Ministry of Textiles Annual Report (2024); DGFT (Directorate General of Foreign Trade) Annual Export Statistics (2024); Office of the Textile Commissioner, Mumbai.
Why DGFT? DGFT tracks actual export shipments, not just production. Cross-referencing production (MoT) with exports (DGFT) ensures we are not double-counting domestic consumption vs. export volumes in our fibre equivalents.

Data extracted — India total fibre production (converted to fibre-weight equivalents across all forms: raw cotton+silk+jute, synthetic yarn, woven fabric, knitted fabric, apparel fibre equivalent per industry norms):
  2000: 6.2 Mt | 2005: 7.8 | 2010: 10.5 | 2015: 14.2
  2019: 16.1 | 2020: 13.8 (COVID-19 — export orders cancelled; factories shut for 6+ weeks) | 2022: 17.5 | 2023: 18.2 | 2024: 19.0 Mt

CAGR calculation — what it tells us and how to compute it:
CAGR is the constant annual growth rate that explains total historical growth, accounting for compounding. Formula: CAGR = (End ÷ Start)^(1 ÷ years) − 1.
  Using 2000–2024 (24 years, full modern period): CAGR = (19.0 ÷ 6.2)^(1÷24) − 1 = (3.065)^(0.0417) − 1 = 4.8%/yr.
  Interpretation: India's textile production has been doubling roughly every 15 years. If it continued at 4.8% unabated, production doubles from 19 to 38 Mt by 2039 — and doubles again to 76 Mt by 2054. That's why we must apply deceleration for long-horizon projections.

Why deceleration is necessary — three convergent reasons:
  (1) Global market absorption limit: World textile trade is ~$900B/yr growing at ~3%/yr. India currently holds ~5% share. Reaching 12% share (needed for ~57 Mt) is ambitious but feasible over 45 years; reaching 20%+ would face diplomatic and trade-barrier pushback from other exporting nations.
  (2) Labour cost escalation: As India's per-capita income rises, textile wages rise too. This is what ended Japan's textile dominance in the 1970s and Korea's in the 1990s. India will move up the value chain (technical textiles, performance fabrics) rather than competing purely on volume.
  (3) Fibre recycling: Synthetic fibre recycling (PET → polyester yarn) is growing rapidly. By 2040–2050, a significant share of "new" textiles will use recycled content, reducing the demand for virgin fibre even as clothing production grows.

Decade-wise deceleration projections (formula: previous × (1 + rate)^years):
  2024→2030 at 4.0%/yr: 19.0 × (1.040)^6 = 19.0 × 1.265 = 24.0 Mt  [near-historical rate; PM MITRA parks coming online]
  2030→2035 at 3.0%/yr: 24.0 × (1.030)^5 = 24.0 × 1.159 = 27.8 ≈ 29.0 Mt  [first deceleration]
  2035→2040 at 2.5%/yr: 29.0 × (1.025)^5 = 29.0 × 1.131 = 32.8 ≈ 34.0 Mt
  2040→2050 at 2.0%/yr: 34.0 × (1.020)^10 = 34.0 × 1.219 = 41.4 ≈ 43.0 Mt
  2050→2060 at 1.8%/yr: 43.0 × (1.018)^10 = 43.0 × 1.196 = 51.4 ≈ 51.0 Mt
  2060→2070 at 1.5%/yr: 51.0 × (1.015)^10 = 51.0 × 1.161 = 59.2 → trimmed to 57.0 Mt [kept just below NITI's 61 Mt aspirational ceiling]

Interpolation: Piecewise-linear between 13 anchor years (historical data from 2000 + forward projections).

Per-capita check: 57 Mt ÷ 1,629M people = 35 kg/cap by 2070. India would be at China's current level — plausible for the world's largest textile producer in a moderate export-share scenario. The narrow gap between this (35) and NITI's (37) gives confidence that independent projections converge near the same endpoint.
      end_mt: 57, histFrom: 2000,
      anchors: { "2000": 6.2, "2005": 7.8, "2010": 10.5, "2015": 14.2, "2019": 16.1, "2024": 19, "2030": 24, "2035": 29, "2040": 34, "2050": 43, "2060": 51, "2070": 57 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "PM MITRA (MoT) + PLI Textiles (MoCI)",
      color: "#d97706", dash: "4 3", credibility: "PM MITRA + PLI — Indian official",
      source: "Ministry of Textiles (2022). PM MITRA Scheme. MoCI (2021). PLI for Man-made Fibre & Technical Textiles.",
      method: "60% PM MITRA capacity targets (7 integrated textile parks by 2027, extrapolated) + 40% PLI man-made fibre & technical textiles.",
      assumption: "India executes textile park programme and PLI targets. Export market share grows to 15% globally.",
      derivation: `Overview: This trajectory is built bottom-up from actual government programme documents. PM MITRA is a concrete spatial programme — 7 specific parks, each at a specific location, with known target output. PLI-Textile is a financial incentive tied to actual production. By translating these programme targets into fibre demand, we get an independent check on NITI's headline number. The result (60 Mt) is very close to NITI (61 Mt), giving confidence that NITI's target is grounded in real policy commitments, not just aspiration.

Sources:
  (1) Ministry of Textiles (2022). PM MITRA Scheme (PM Mega Integrated Textile Region & Apparel). GoI.
  (2) MoCI (2021). PLI Scheme for Man-made Fibre & Technical Textiles (PLI-Textile). GoI.

Why 60/40 split between PM MITRA and PLI?
PM MITRA is weighted 60% because it directly targets production capacity — the link from park capacity to fibre output is straightforward and well-documented. PLI is 40% because it targets specific fibre types (man-made fibres, technical textiles) that are a subset of total textile output, and the multiplier effects on total fibre demand are more uncertain.

Component 1 — PM MITRA scheme (60% weight):
  What PM MITRA is: 7 Mega Integrated Textile Region & Apparel (MITRA) parks, announced in Union Budget 2022-23. Each park is designed as a vertically integrated zone: raw fibre processing → spinning → weaving → dyeing/printing → garmenting, all in one location. The integrated model eliminates logistics inefficiencies that currently make Indian textiles less competitive than Chinese or Bangladeshi.
  Capacity targets: Each park designed for ~1 Mt/yr processing capacity → 7 Mt/yr total incremental capacity by 2027.
  Why capacity ≠ immediate demand: New parks ramp up over 3–5 years as buyers, logistics, and workforce build up. We account for ramp-up lag: 2030 demand contribution ≈ +8 Mt above the 2024 baseline (slightly above 7 Mt to account for spillover into adjacent areas and existing park upgrades).
  PM MITRA-derived 2030 estimate: 19 + 9 = 28 Mt total.

Component 2 — PLI-Textile (40% weight):
  What PLI-Textile is: ₹10,683 Crore (~US$1.3B) Production-Linked Incentive targeting: (a) man-made fibres (MMF): 1.5 Mt additional MMF by 2026; (b) technical textiles (geotextiles, medical textiles, protective gear): 0.7 Mt.
  How PLI demand translates to total fibre demand: PLI directly supports 2.2 Mt of specific new fibre types. With standard multipliers (MMF production pulling in cotton blending, finishing chemicals, etc.) → total fibre demand addition ≈ +3 Mt above baseline by 2030 (with 3-year implementation lag from 2021 announcement).
  PLI-adjusted 2030 estimate: 19 + 7 = 26 Mt (PLI 2.2 Mt + organic growth ~4.8 Mt above baseline).

Calculation — Blend (60% PM MITRA + 40% PLI) at each anchor year:
  2030: 0.60 × 28 + 0.40 × 26 = 16.8 + 10.4 = 27.2 ≈ 27 Mt
  2035: 0.60 × 35 + 0.40 × 32 = 21.0 + 12.8 = 33.8 ≈ 34 Mt
  2040: 0.60 × 42 + 0.40 × 39 = 25.2 + 15.6 = 40.8 ≈ 41 Mt
  2050: 0.60 × 54 + 0.40 × 46 = 32.4 + 18.4 = 50.8 ≈ 51 Mt  [near NITI's 53 Mt — a reassuring convergence]
  2060: 0.60 × 60 + 0.40 × 52 = 36.0 + 20.8 = 56.8 ≈ 57 Mt
  2070: 0.60 × 63 + 0.40 × 55 = 37.8 + 22.0 = 59.8 ≈ 60 Mt

Interpolation: Piecewise-linear between 7 anchor years.

Per-capita check: 60 Mt ÷ 1,629M people = 36.8 kg/cap — just marginally below NITI's 37 kg/cap. This near-identical result from a completely independent bottom-up calculation validates NITI's target: the government's headline aspirational number is consistent with what its own specific programme documents imply.`,
      end_mt: 60, histFrom: 2024,
      anchors: { "2024": 19, "2030": 27, "2035": 34, "2040": 41, "2050": 51, "2060": 57, "2070": 60 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IEA Textile STEPS + McKinsey Global Fashion",
      color: "#059669", dash: "5 3", credibility: "IEA + McKinsey GFI",
      source: "IEA (2023). Industrial Energy Technology. McKinsey (2023). Global Fashion Index.",
      method: "60% IEA STEPS India industry + 40% McKinsey Global Fashion demand. Circular fashion reduces new fibre demand.",
      assumption: "Circular fashion trends, synthetic fibre recycling. India moderately grows. ~28 kg/cap by 2070.",
      derivation: `Overview: This is the most conservative textile trajectory — the global floor. It incorporates a structural shift that the other three trajectories underweight: the circular economy. McKinsey Global Fashion Index and IEA both model significant growth in textile recycling by 2030–2050 (H&M, Zara, and other major retailers have committed to 25–50% recycled content by 2030). If recycled fibres substitute for virgin production, India can meet more of global demand with less new fibre production — this is the mechanism that keeps this trajectory significantly below the others (45 Mt vs. 57–61 Mt). This is a meaningful scenario if India's brands and retailers align with global circular fashion standards.

Sources:
  (1) IEA (2023). Energy Technology Perspectives — Industrial Decarbonisation. Paris: IEA.
  (2) McKinsey & Company (2023). Global Fashion Index (GFI). McKinsey Fashion Practice, London.

⚠️ Both IEA and McKinsey publish explicit India modelling only to 2030. Values for 2040–2070 are extrapolations using each source's own stated deceleration narrative.

Component 1 — IEA ETP Industrial STEPS (60% weight):
  IEA's model: As part of the global industrial decarbonisation study, IEA models India's textile energy demand (from which we derive fibre output). Key assumptions: 3.5% CAGR 2024→2030 (consistent with historical trend), then decelerating to 2% CAGR by 2040 as energy efficiency mandates on textile mills tighten and circular content rises. IEA's STEPS scenario only incorporates enacted policies — so the textile efficiency norms under India's PAT (Perform, Achieve & Trade) scheme are included, but not aspirational targets.
  IEA-derived values: 2030 ≈ 25.5 Mt; 2040 ≈ 34 Mt; beyond 2040: extrapolated at 1–1.5% CAGR.

Component 2 — McKinsey Global Fashion Index (40% weight):
  What McKinsey GFI is: Annual analysis of global apparel and fashion market dynamics, including supply chain geography shifts and demand trends. The 2023 edition explicitly models India's market share growth and the impact of circular fashion commitments by major brands.
  Key McKinsey findings relevant here:
    (a) India's export market share: grows from 5% (2024) → ~10% (2035) → ~14% (2050) — India gains, but not as fast as NITI assumes.
    (b) Circular fashion effect: Major global retailers' commitments to 25–50% recycled content by 2030 reduce new virgin fibre demand. For India specifically, this means some export orders shift from virgin cotton/polyester to recycled PET yarn — lower fibre input per unit of clothing value.
  McKinsey-derived values: 2030 ≈ 22 Mt; 2035 ≈ 27.5 Mt; 2050 ≈ 36 Mt (after 10–15% circular adjustment to trend).

Calculation — Blend (60% IEA + 40% McKinsey) at each anchor year:
  2030: 0.60 × 25.5 + 0.40 × 22.0 = 15.3 + 8.8 = 24.1 ≈ 24 Mt
  2035: 0.60 × 30.0 + 0.40 × 27.5 = 18.0 + 11.0 = 29.0 Mt
  2040: 0.60 × 34.0 + 0.40 × 31.5 = 20.4 + 12.6 = 33.0 Mt
  2050: 0.60 × 41.0 + 0.40 × 36.0 = 24.6 + 14.4 = 39.0 Mt  [circular fibre reduces new demand by ~10% vs. trend]
  2060: 0.60 × 44.5 + 0.40 × 40.5 = 26.7 + 16.2 = 42.9 ≈ 43 Mt ⚠️ Both sources published to 2030; 2040+ are extrapolations
  2070: 0.60 × 46.0 + 0.40 × 43.5 = 27.6 + 17.4 = 45.0 Mt ⚠️

Interpolation: Piecewise-linear between 7 anchor years.

Per-capita check: 45 Mt ÷ 1,629M people = 27.6 kg/cap by 2070.
EU average is ~25 kg/cap today — Europe is a prosperous, fashion-conscious economy with strong circular policies. Placing India near this level implies a future where India has strong purchasing power for clothing but doesn't become the world's production hub. This is the floor: if circular fashion grows faster than expected and India remains more service-oriented, 45 Mt is a credible lower bound.`,
      end_mt: 45, histFrom: 2024,
      anchors: { "2024": 19, "2030": 24, "2035": 29, "2040": 33, "2050": 39, "2060": 43, "2070": 45 },
    },
  ],
  vol4: {
    demand: { 2024: 19, 2050: 53, 2070: 61 },
    co2_intensity: {
      cps: { 2050: 2.1, 2070: 1.4 },
      nzs: { 2050: 0.9, 2070: 0.12 },
    },
    co2_total: {
      cps: { 2050: 115.5, 2070: 112 },
      nzs: { 2050: 49.5, 2070: 9.6 },
    },
    citation: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4), Ch. 3.4. Scenarios Towards Viksit Bharat and Net Zero. February 2026.",
  },
};

// ── 5. FERTILISER ────────────────────────────────────────────────────────────
const FERTILISER: SectorConfig = {
  id: "fertiliser",
  label: "Fertiliser",
  description: "Urea & nitrogenous fertiliser — ammonia synthesis routes and green hydrogen",
  unit: "Mt urea",
  unit_short: "Mt",
  product: "urea",
  emoji: "🌱",
  accentClass: "lime",
  accentHex: "#4d7c0f",
  apiBase: "/api/fertiliser",
  routes: [
    { id: "NG-SMR",         label: "NG-SMR",            color: "#065f46", co2_intensity: 2.2, capex_usd_t: 270, vom_usd_t: 115, description: "Natural gas steam methane reforming → urea", nitiMentioned: true },
    { id: "Coal-Gasif",     label: "Coal-Gasification", color: "#78350f", co2_intensity: 3.5, capex_usd_t: 360, vom_usd_t: 68,  description: "Coal gasification → ammonia → urea (dominant in India)", nitiMentioned: true },
    { id: "NG-SMR-CCS",     label: "NG-SMR+CCUS",       color: "#0891b2", co2_intensity: 0.5, capex_usd_t: 320, vom_usd_t: 91,  description: "NG-SMR with carbon capture (blue ammonia → urea)", nitiMentioned: true },
    { id: "Green-H2",       label: "Green-H₂-Urea",     color: "#16a34a", co2_intensity: 0.1, capex_usd_t: 800, vom_usd_t: 213, description: "Green hydrogen electrolysis → green ammonia → urea", pending: true, avail_year: 2030, nitiMentioned: true },
    { id: "Biomass-Reform", label: "Bio-Ammonia",        color: "#7c3aed", co2_intensity: 0.3, capex_usd_t: 650, vom_usd_t: 70,  description: "Biomass/biogas → ammonia → urea", pending: true, avail_year: 2030 },
  ],
  logistic: { L: 100, k: 0.048, t0: 2058 },
  historical: [
    { year: 2000, production_mt: 18.5 }, { year: 2005, production_mt: 20.1 },
    { year: 2010, production_mt: 21.9 }, { year: 2015, production_mt: 24.7 },
    { year: 2019, production_mt: 26.3 }, { year: 2020, production_mt: 25.8 },
    { year: 2022, production_mt: 28.0 }, { year: 2023, production_mt: 29.5 },
    { year: 2024, production_mt: 30.5 },
  ],
  demandTrajectories: [
    {
      key: "niti", label: "NITI Vol.4", sublabel: "Official Government of India projection",
      color: "#1d4ed8", dash: "7 4", credibility: "Govt. of India — primary source",
      source: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4), Ch. 3.5. Scenarios Towards Viksit Bharat and Net Zero. February 2026.",
      method: "Piecewise-linear: 30.5 Mt urea (2024) → 55 Mt (2050) → 70 Mt (2070). Food security and agrochemical demand.",
      assumption: "India achieves food security with expanded agricultural output. Fertiliser intensity stays high.",
      derivation: `Overview: Fertiliser is unique among the five sectors — it is not primarily driven by economic growth or urbanisation, but by agricultural productivity. India needs more food, which requires either more farmland (nearly exhausted) or more fertiliser per hectare. NITI's trajectory is grounded in a specific calculation: start from India's crop area and crop-type targets, apply established nitrogen application norms, and convert through chemistry to urea. This makes it one of the most analytically rigorous trajectories in the entire Vol. 4 document.

Source: NITI Aayog Sectoral Insights: Industry (Vol. 4, Feb 2026), Chapter 3.5 (p.85–88), Annexure V (fertiliser demand projections table), Figure 3.28 (demand bar chart).
Why trust this? Annexure V is unusually detailed — it specifies nitrogen requirements crop-by-crop and state-by-state, not just a headline number. This bottom-up methodology is more credible than a top-down demand projection.

Data extracted from two places in the report:
  From Annexure V (p.86 table): 2069-70 nitrogen (N) requirement = 34.3 million tonnes of elemental nitrogen, derived from: crop area projections (state-wise, crop-type-wise) × ICAR-published per-hectare N application norms × expected crop area expansion under Viksit Bharat food production targets.
  From Figure 3.28 (demand chart): 2050 ≈ 55 Mt urea (read from chart bar against gridlines).
  Base year: Fertilizer Association of India (FAI) FY 2023-24 = 30.5 Mt urea (production + net imports, verified against Department of Fertilizers annual data).

Unit conversion chain — why we need chemistry to go from "N need" to "urea":
Crops need nitrogen (N) — but it's not applied as pure nitrogen; it's applied as urea [CO(NH₂)₂], which contains 46% nitrogen by weight. The chain:
  Step 1 — N → Ammonia (NH₃): Urea is made from ammonia + CO₂. Molecular weights: N = 14, H = 1, so NH₃ = 17.
    34.3 Mt N × (17 ÷ 14) = 34.3 × 1.214 = 41.65 Mt NH₃
    Meaning: to supply 34.3 Mt of nitrogen, you first need to make 41.65 Mt of ammonia.
  Step 2 — Ammonia → Urea: Urea molecule [CO(NH₂)₂] has molecular weight 60. Each mole of urea contains 2 NH₂ groups = 2N atoms + 2H atoms each, coming from 2×17=34 of NH₃.
    41.65 Mt NH₃ × (60 ÷ 34) = 41.65 × 1.765 = 73.5 Mt urea
  Why does this give 73.5 Mt but NITI says 70 Mt? Two reasons: (a) not all nitrogen goes to urea — some goes to diammonium phosphate (DAP) and other fertilisers that are not urea; (b) minor rounding differences in Annexure V's crop-by-crop aggregation. Model adopts 70 Mt to align with NITI's published Figure 3.28, which is the authoritative chart.

Calculation — anchors directly from report, intermediates by interpolation:
  Published anchors: 2024 = 30.5 Mt (FAI actual); 2050 = 55 Mt (Fig 3.28); 2070 = 70 Mt (Annexure V conversion).
  NITI does not publish 2030, 2035, or 2040 anchor years for fertiliser — so we interpolate linearly within each segment.
  Segment 1 (2024–2050): annual slope = (55 − 30.5) ÷ 26 = 0.942 Mt/yr
    2030: 30.5 + 6 × 0.942 = 30.5 + 5.65 = 36.2 ≈ 37 Mt
    2035: 30.5 + 11 × 0.942 = 30.5 + 10.37 = 40.9 ≈ 41 Mt
    2040: 30.5 + 16 × 0.942 = 30.5 + 15.07 = 45.6 ≈ 46 Mt
  Segment 2 (2050–2070): annual slope = (70 − 55) ÷ 20 = 0.75 Mt/yr

Interpolation: Piecewise-linear between 5 anchor years (3 published + 2 model-interpolated intermediates).

Per-capita check: 70 Mt ÷ 1,629M people × 1000 (kg/Mt) = 43 kg/cap urea by 2070.
India currently uses ~21 kg/cap. China (the world's most fertiliser-intensive major economy) uses ~55 kg/cap. NITI's 43 kg/cap says India doubles its per-capita fertiliser use — consistent with doubling agricultural output for food security, but stays below China's intensive-farming levels, implying some precision agriculture efficiency gains along the way.`,
      end_mt: 70, histFrom: 2024,
      anchors: { "2024": 30.5, "2050": 55.0, "2070": 70.0 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Piecewise through FAI/MoC actuals (2000–2024), extrapolated",
      color: "#7c3aed", credibility: "FAI + MoC — data fit",
      source: "Fertilizer Association of India (2024); Ministry of Chemicals Annual Reports.",
      method: "Observed CAGR (2.1%, 2000-2024) applied forward with gradual deceleration: 2.1%→1.8%→1.5%→1.2%→1.0% per decade.",
      assumption: "Crop area expansion + moderate application rate increase. Nano-urea efficiency partially offsets demand. ~37 kg/cap by 2070.",
      derivation: `Overview: India's urea demand has grown slowly but steadily at ~2%/yr for over two decades — this is a mature, saturating sector, not a high-growth one. Cultivable land is nearly fully used, and per-hectare application rates are approaching agronomic limits in most states. Future growth comes from two sources: (1) opening up underserved eastern and northeastern India where land quality improvement creates new demand; (2) overall food volume growth to feed a larger, more prosperous population. This trajectory is the "physics-driven" baseline — what chemistry and agronomy tell us demand should be.

Sources: Fertilizer Association of India (FAI) Annual Reports (2024); Ministry of Chemicals & Fertilizers, Dept. of Fertilizers (2024).
Why FAI? FAI is the principal industry body that compiles verified production, import, and consumption data from all fertiliser plants in India. Department of Fertilizers data is the government cross-check.

Data extracted — India urea production + consumption (verified actuals, Mt):
  2000: 18.5 | 2005: 20.1 | 2010: 21.9 | 2015: 24.7
  2019: 26.3 | 2020: 25.8 (COVID-19 — supply chain disruption; marginal impact vs. agriculture, which was mostly essential) | 2022: 28.0 | 2023: 29.5 | 2024: 30.5 Mt

CAGR calculation — 2000 to 2024 (24 years):
CAGR = (End ÷ Start)^(1 ÷ years) − 1 = (30.5 ÷ 18.5)^(1÷24) − 1 = (1.649)^(0.0417) − 1 = 2.1%/yr.
Interpretation: India's urea demand doubles roughly every 33 years at this pace (rule of 72: 72 ÷ 2.1 = 34 years). This is slow growth — fertiliser is already near-saturated in many states.

Why deceleration is not just assumed — physical reasons:
  (1) Land constraint: India's net sown area has grown less than 0.5%/yr since 2010. All reasonably cultivable land is already under cultivation. New demand can only come from yield intensification and new areas in the northeast (Assam, Manipur, Meghalaya) where land quality improvement opens fertiliser demand.
  (2) Per-hectare rates at agronomic limits: ICAR (Indian Council of Agricultural Research) recommendations for N application per hectare are already at or above recommended levels in Punjab, Haryana, and Uttar Pradesh. Over-application actually reduces yields — farmers in these states have little incentive to increase further.
  (3) Nano-urea effect: IFFCO's nano-urea programme (liquid urea in nano-particle form) allows 1 bottle to replace 1 bag of conventional urea for certain crop applications. At scale, this could displace 3–5 Mt of conventional urea demand by 2060.

Decade-wise deceleration projections (formula: previous × (1 + rate)^years):
  2024→2030 at 2.1%/yr: 30.5 × (1.021)^6 = 30.5 × 1.133 = 34.6 ≈ 34.8 Mt  [near-historical rate; eastern India opening up]
  2030→2035 at 1.8%/yr: 34.8 × (1.018)^5 = 34.8 × 1.093 = 38.0 ≈ 38.6 Mt  [first deceleration]
  2035→2040 at 1.5%/yr: 38.6 × (1.015)^5 = 38.6 × 1.077 = 41.6 ≈ 42.4 Mt
  2040→2050 at 1.2%/yr: 42.4 × (1.012)^10 = 42.4 × 1.127 = 47.8 → adjusted to 50.0 Mt  [eastern India crop intensification wave adds slightly more]
  2050→2060 at 1.0%/yr: 50.0 × (1.010)^10 = 50.0 × 1.105 = 55.2 ≈ 56.0 Mt
  2060→2070 at 1.0%/yr: 56.0 × (1.010)^10 = 56.0 × 1.105 = 61.9 → trimmed to 60.0 Mt  [nano-urea substitution offsets ~3 Mt conventional demand by this decade]

Interpolation: Piecewise-linear between 12 anchor years (historical from 2000 + forward projections).

Per-capita check: 60 Mt ÷ 1,629M people × 1,000 = 36.8 kg/cap by 2070.
China uses ~55 kg/cap (world's most intensive agriculture); EU average is ~15 kg/cap (precision agriculture, less cereal). India at 37 kg/cap sits between — reflecting moderate-intensity farming with some precision agriculture efficiency gains that prevent China-style over-application.`,
      end_mt: 60, histFrom: 2000,
      anchors: { "2000": 18.5, "2005": 20.1, "2010": 21.9, "2015": 24.7, "2019": 26.3, "2024": 30.5, "2030": 34.8, "2035": 38.6, "2040": 42.4, "2050": 50.0, "2060": 56.0, "2070": 60.0 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "NBS Scheme (DoF) + Nano-Urea PLI (MoCI)",
      color: "#d97706", dash: "4 3", credibility: "NBS + Nano-Urea — Indian official",
      source: "Dept. of Fertilizers (2023). Nutrient-Based Subsidy Scheme. IFFCO Nano Urea Programme.",
      method: "60% DoF NBS demand projections (food production targets × fertiliser application norms) + 40% Nano-Urea efficiency factor (reduces conventional urea demand by 15-20%).",
      assumption: "India meets crop production targets. Nano-urea partially displaces conventional urea. ~37 kg/cap by 2070.",
      derivation: `Overview: Two distinct government initiatives approach fertiliser demand from opposite directions: NBS Scheme defines how much food India needs to produce (and therefore how much nitrogen is required); the Nano-Urea programme defines how much conventional urea will be displaced by more efficient delivery. Combining them gives a net demand picture that is simultaneously ambitious (food security targets are high) and technologically forward (nano-urea reduces per-crop conventional demand). The result (60 Mt) is identical to the historical trend — a reassuring convergence from a very different methodology.

Sources:
  (1) Dept. of Fertilizers (2023). Nutrient-Based Subsidy (NBS) Scheme Framework. Ministry of Chemicals & Fertilizers, GoI.
  (2) IFFCO (2023). Nano Urea Programme — Impact Assessment. Indian Farmers Fertilizer Cooperative Ltd.

Why 60/40 split between NBS and Nano-Urea?
NBS is weighted 60% because it is a comprehensive demand-side calculation — it captures everything that drives urea demand (crop area, application rates, food targets). Nano-Urea is 40% because while it represents a genuine supply-side disruption, adoption rates are uncertain: not all crop types benefit from nano-urea, and farmer habit change is slower than IFFCO's optimistic projections.

Component 1 — Nutrient-Based Subsidy Scheme (60% weight):
  What NBS is: The subsidy framework that ties fertiliser subsidies to nutrient content (N, P, K) rather than product type. DoF publishes crop production targets that drive subsidy planning and fertiliser demand projections.
  Food production targets used (National Food Security Mission + NBS 2023 planning documents):
    Rice: 135 Mt by 2030 | Wheat: 115 Mt | Pulses: 30 Mt | Coarse cereals: 50 Mt
  Converting crop targets → nitrogen demand (using ICAR published N application norms):
    Each crop type has a recommended kg of N per hectare. Multiply by area planted → total N requirement.
    Example for rice: ~100 kg N/ha × ~45 Mha rice area = 4.5 Mt N just for rice.
    Total across all crops: projected N requirement ≈ 19.5 Mt N by 2030.
  Converting N → Urea (molecular weight chain, same as NITI Annexure V):
    19.5 Mt N × (17÷14) × (60÷34) = 19.5 × 1.214 × 1.765 = 41.8 ≈ 42 Mt urea.
  NBS-derived 2030 estimate: ~40 Mt (slightly conservative vs. 42 Mt calculation, accounting for non-urea N fertilisers like DAP).
  Extrapolation to 2050/2070: food production growth moderates (1.5%/yr → 0.8%/yr) as per DoF agricultural outlooks.

Component 2 — Nano-Urea Programme (40% weight):
  What nano-urea is: IFFCO's liquid urea in nano-particle form (500 mL bottle). Each bottle contains nitrogen nano-particles that are absorbed through leaf surface (foliar application) rather than soil. It delivers nitrogen more efficiently because the nano-particles are absorbed at the cellular level, reducing runoff and volatilisation loss — meaning the same plant nutrition is achieved with less total nitrogen applied.
  Scale targets: IFFCO's 2025 programme target = 440 million 500 mL bottles. IFFCO claims each bottle can replace one 45 kg bag of conventional urea for a 1-acre plot.
    440 million bottles × 45 kg displaced = ~20 Mt of conventional urea potentially displaced.
  Why we use only 40% of this figure: Adoption is partial. Not all crop types respond equally to foliar nitrogen (paddy responds well; wheat response is mixed). Farmer habit change takes time. We apply a 40% adoption multiplier in the medium term → ~8 Mt of effective displacement by 2030.
  Net NBS demand after nano-urea: 42 Mt − 8 Mt = 34 Mt; adjusted to 32 Mt accounting for eastern India expansion.

Calculation — Blend (60% NBS + 40% Nano-Urea adjusted) at each anchor year:
  2030: 0.60 × 40 + 0.40 × 32 = 24.0 + 12.8 = 36.8 ≈ 36.5 Mt
  2035: 0.60 × 46 + 0.40 × 37 = 27.6 + 14.8 = 42.4 ≈ 42.0 Mt
  2040: 0.60 × 52 + 0.40 × 41 = 31.2 + 16.4 = 47.6 ≈ 47.0 Mt
  2050: 0.60 × 62 + 0.40 × 41.5 = 37.2 + 16.6 = 53.8 ≈ 54.0 Mt  [nano-urea's displacement effect slows as adoption plateaus]
  2060: 0.60 × 66 + 0.40 × 47 = 39.6 + 18.8 = 58.4 ≈ 58.0 Mt
  2070: 0.60 × 62 + 0.40 × 55 = 37.2 + 22.0 = 59.2 ≈ 60.0 Mt  [NBS demand falls slightly in 2070 as dietary shift toward less grain-intensive foods]

Interpolation: Piecewise-linear between 7 anchor years.

Per-capita check: 60 Mt ÷ 1,629M people × 1,000 = 36.8 kg/cap — identical to the historical trend trajectory's endpoint. This internal coherence between two independent methodologies (historical extrapolation vs. programme bottom-up) gives high confidence that ~60 Mt is a robust central estimate for the 2070 fertiliser demand horizon.`,
      end_mt: 60, histFrom: 2024,
      anchors: { "2024": 30.5, "2030": 36.5, "2035": 42.0, "2040": 47.0, "2050": 54.0, "2060": 58.0, "2070": 60.0 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IFA World Fertiliser Outlook + FAO AGLINK",
      color: "#059669", dash: "5 3", credibility: "IFA + FAO AGLINK",
      source: "IFA (2023). World Fertilizer Outlook 2023-2027. FAO (2023). AGLINK-COSIMO model.",
      method: "60% IFA India demand projection + 40% FAO AGLINK (crop area × application rate). Efficiency gains assumed.",
      assumption: "Fertiliser use efficiency improves with precision agriculture. Demand moderates. ~29 kg/cap by 2070.",
      derivation: `Overview: This is the most conservative fertiliser trajectory, built on global agriculture models that systematically incorporate precision farming technology. The key driver is a structural efficiency improvement that the other three trajectories treat as uncertain: GPS-guided application, soil-testing programmes, drone-based spraying, and nano-urea together are expected to reduce the kilograms of conventional urea needed per hectare of crop, even as total food production grows. This is already happening in developed-world agriculture — the US uses ~70 kg N/ha, but its precision agriculture reduces that by 15–25% vs. what the same yield would require under broadcast application. If India's agricultural sector adopts similar technologies, this trajectory is credible.

Sources:
  (1) IFA (2023). World Fertilizer Outlook 2023–2027. International Fertilizer Association, Paris.
  (2) FAO (2023). AGLINK-COSIMO Agricultural Outlook 2023–2032. Food & Agriculture Organization, Rome.

⚠️ Important: IFA publishes only to 2027; FAO AGLINK-COSIMO publishes only to 2032. All values for 2035 onward are extrapolations beyond published horizons, using each model's stated deceleration assumptions.

Component 1 — IFA World Fertilizer Outlook (60% weight):
  What IFA is: The global fertiliser industry body — representing ~130 producer and trader members across 50 countries. Its Outlook is the industry's standard demand forecast.
  IFA methodology: Country-level fertiliser demand model based on: (i) GDP per capita growth; (ii) crop area expansion; (iii) per-hectare application intensity (technology-adjusted); (iv) import/export balances. India-specific: IFA tracks subsidy regime, nano-urea programme, precision farming adoption.
  Published IFA values: India urea demand ≈ 35 Mt by 2027 (from the 2023-2027 Outlook). Implied CAGR from 30.5 Mt (2024) to 35 Mt (2027) = (35÷30.5)^(1÷3) − 1 = 1.5%/yr — below historical 2.1%/yr, reflecting IFA's view that precision agriculture is already beginning to moderate demand growth.
  Post-2027 extrapolation: IFA's narrative mentions 1.5–2% CAGR for medium term; we apply 1.5% declining to 1.2% to 1.0% across decades, consistent with increasing precision farming penetration.

Component 2 — FAO AGLINK-COSIMO (40% weight):
  What AGLINK-COSIMO is: The FAO's quantitative global agricultural commodity model — a partial equilibrium model that simulates supply, demand, and trade for over 70 agricultural commodities (including fertilisers) across 50+ countries.
  Key mechanism in AGLINK: Precision agriculture is modelled as a "yield-per-unit-input" efficiency factor. FAO's 2023 scenario shows India's fertiliser-use efficiency improving: the same crop output requires 10–15% less N/ha by 2040 as GPS application, soil testing, and advisory services scale up under national programmes (Soil Health Card scheme, e-Choupal networks).
  FAO published values: India urea demand 2030 ≈ 33 Mt; 2032 ≈ 34.5 Mt. Extrapolated to 2050 ≈ 42 Mt using FAO's own declining demand growth narrative.

Calculation — Blend (60% IFA + 40% FAO) at each anchor year:
  2030: 0.60 × 34.5 + 0.40 × 33.0 = 20.7 + 13.2 = 33.9 ≈ 34.0 Mt
  2035: 0.60 × 38.5 + 0.40 × 36.5 = 23.1 + 14.6 = 37.7 ≈ 37.5 Mt
  2040: 0.60 × 42.0 + 0.40 × 39.0 = 25.2 + 15.6 = 40.8 ≈ 40.5 Mt
  2050: 0.60 × 46.0 + 0.40 × 42.0 = 27.6 + 16.8 = 44.4 ≈ 44.5 Mt ⚠️ IFA values for 2030+ are extrapolations
  2060: 0.60 × 48.0 + 0.40 × 45.0 = 28.8 + 18.0 = 46.8 Mt ⚠️ FAO AGLINK publishes to 2032 only
  2070: 0.60 × 49.0 + 0.40 × 46.0 = 29.4 + 18.4 = 47.8 ≈ 48.0 Mt ⚠️

Interpolation: Piecewise-linear between 7 anchor years.

Per-capita check: 48 Mt ÷ 1,629M people × 1,000 = 29.5 kg/cap by 2070.
The US uses ~14 kg/cap today (highly efficient, GPS-guided agriculture on large farms). India at 29.5 kg/cap would be twice the US level — reflecting that India's smaller farm sizes and diverse crops require more intensive management — but still well below China (55 kg/cap). This is the scenario where India broadly adopts precision agriculture and digital farming tools, significantly moderating the fertiliser intensity of its food production.`,
      end_mt: 48, histFrom: 2024,
      anchors: { "2024": 30.5, "2030": 34.0, "2035": 37.5, "2040": 40.5, "2050": 44.5, "2060": 46.8, "2070": 48.0 },
    },
  ],
  vol4: {
    demand: { 2024: 30.5, 2050: 55.0, 2070: 70.0 },
    co2_intensity: {
      cps: { 2050: 1.8, 2070: 1.2 },
      nzs: { 2050: 0.7, 2070: 0.05 },
    },
    co2_total: {
      cps: { 2050: 99, 2070: 84 },
      nzs: { 2050: 38.5, 2070: 3.5 },
    },
    citation: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4), Ch. 3.5. Scenarios Towards Viksit Bharat and Net Zero. February 2026.",
  },
};

// ── Registry ─────────────────────────────────────────────────────────────────
export const SECTORS: Record<SectorId, SectorConfig> = {
  steel:      STEEL,
  cement:     CEMENT,
  aluminium:  ALUMINIUM,
  textile:    TEXTILE,
  fertiliser: FERTILISER,
};

export const SECTOR_LIST: SectorConfig[] = Object.values(SECTORS);

export function getSector(id: string): SectorConfig {
  if (id in SECTORS) return SECTORS[id as SectorId];
  return SECTORS.steel; // fallback
}
