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
      end_mt: 821, histFrom: 2024,
      anchors: { "2024": 144.29, "2050": 624.0, "2070": 821.0 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Logistic S-curve fitted to WorldSteel + JPC actuals (1990–2025)",
      color: "#7c3aed", credibility: "WorldSteel + JPC actuals — data fit",
      source: "WorldSteel Statistical Yearbook (2023); JPC Annual Reports (1990–2024).",
      method: "Logistic S-curve (L=900, k=0.059, t₀=2052) fitted to observed production. Pure data extrapolation.",
      assumption: "India follows historical S-curve. Saturation ~900 Mt. Inflection ≈2052.",
      end_mt: 669, histFrom: 1990, useLogistic: true,
      anchors: { "1990": 14.7, "1995": 22.3, "2000": 26.9, "2005": 37.8, "2010": 69.6, "2015": 89.5, "2019": 111.2, "2024": 144.8, "2030": 193.1, "2035": 241.5, "2040": 297.0, "2050": 423.5, "2060": 554.2, "2070": 668.6 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "NSP 2017 (MoS) + PM Gati Shakti NIP (DEA/MoF)",
      color: "#d97706", dash: "4 3", credibility: "NSP 2017 + Gati Shakti NIP",
      source: "Ministry of Steel, GoI (2017). NSP 2017. DEA/MoF (2020). National Infrastructure Pipeline.",
      method: "60% NSP 2017 (160 kg/cap by 2030 target, extrapolated) + 40% PM Gati Shakti NIP (₹111L Cr infra, steel from sector investment × intensity).",
      assumption: "India meets NSP manufacturing targets and executes Gati Shakti infrastructure. ~356 kg/cap by 2070.",
      end_mt: 580, histFrom: 2024,
      anchors: { "2024": 144.0, "2030": 222.0, "2035": 280.0, "2040": 332.0, "2050": 458.0, "2060": 524.0, "2070": 580.0 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IEA STEPS + Urbanization model blend",
      color: "#059669", dash: "5 3", credibility: "IEA WEO 2023 + World Bank",
      source: "IEA (2023). WEO 2023 STEPS. World Bank (2023). India Urbanization Review.",
      method: "60% IEA STEPS + 40% urbanization-linked (urban share 35%→61% by 2070). Service-led economy assumption.",
      assumption: "Service-led growth limits steel intensity to ~304 kg/cap by 2070 (Brazil/Turkey level).",
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
      source: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4), Ch. 3.2. Scenarios Towards Viksit Bharat and Net Zero.",
      method: "Piecewise-linear: 451 Mt (2025) → 1,590 Mt (2050) → 1,985 Mt (2070). Based on housing, infrastructure and urban construction targets.",
      assumption: "India's construction boom sustains high cement intensity. Per-capita ~1,220 kg by 2070 (peak-China-level urbanization).",
      end_mt: 1985, histFrom: 2024,
      anchors: { "2025": 451, "2050": 1590, "2070": 1985 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Piecewise through CMA/DPIIT actuals (1995–2024), extrapolated",
      color: "#7c3aed", credibility: "CMA + DPIIT — data fit",
      source: "Cement Manufacturers Association (2024); DPIIT Annual Production Statistics.",
      method: "Observed CAGR (3.2%, 2019-2024) applied forward with gradual deceleration: 3.2%→2.5%→2.0%→1.5%→1.0% per decade.",
      assumption: "India's construction boom sustains near-historical growth, slowing as housing stock matures. ~570 kg/cap by 2070 (Turkey/Mexico level).",
      end_mt: 960, histFrom: 1995,
      anchors: { "1995": 68, "2000": 101, "2005": 142, "2010": 210, "2015": 280, "2019": 337, "2024": 395, "2030": 478, "2035": 545, "2040": 614, "2050": 748, "2060": 864, "2070": 960 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "NHP 2022 (MoHUA) + PM Gati Shakti NIP (DEA)",
      color: "#d97706", dash: "4 3", credibility: "NHP 2022 + Gati Shakti NIP",
      source: "MoHUA (2022). National Housing Policy. DEA/MoF (2020). National Infrastructure Pipeline.",
      method: "60% NHP 2022 (housing demand: 29M urban units by 2030, extrapolated) + 40% NIP infrastructure cement demand. 3.5% CAGR slowing to 1.5%.",
      assumption: "India executes housing and infrastructure plans. Urbanisation drives demand. ~650 kg/cap by 2070 (Brazil/South Africa level).",
      end_mt: 1100, histFrom: 2024,
      anchors: { "2024": 395, "2030": 485, "2035": 565, "2040": 655, "2050": 840, "2060": 1005, "2070": 1100 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IEA Cement Roadmap + World Bank urbanization",
      color: "#059669", dash: "5 3", credibility: "IEA Cement Roadmap + World Bank",
      source: "IEA (2023). Cement Technology Roadmap. World Bank (2023). India Urbanization Review.",
      method: "60% IEA Cement STEPS + 40% urbanization-linked. Growth at 2.5% slowing to 0.8% as housing stock matures.",
      assumption: "Moderate urbanization path. Cement intensity peaks and declines from 2050. ~440 kg/cap by 2070.",
      end_mt: 750, histFrom: 2024,
      anchors: { "2024": 395, "2030": 455, "2035": 510, "2040": 565, "2050": 668, "2060": 720, "2070": 750 },
    },
  ],
  vol4: {
    demand: { 2025: 451, 2050: 1590, 2070: 1985 },
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
      source: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4), Ch. 3.3. Scenarios Towards Viksit Bharat and Net Zero.",
      method: "Piecewise-linear: 4.5 Mt (2024) → 22 Mt (2050) → 38 Mt (2070). Driven by EVs, packaging, construction.",
      assumption: "India becomes major aluminium producer. EV battery demand drives consumption. ~23 kg/cap by 2070.",
      end_mt: 38, histFrom: 2024,
      anchors: { "2024": 4.5, "2050": 22.0, "2070": 38.0 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Piecewise through IAI/BALCO actuals (2000–2024), extrapolated",
      color: "#7c3aed", credibility: "IAI + MoM data — data fit",
      source: "International Aluminium Institute (2023); Ministry of Mines Annual Reports.",
      method: "Observed CAGR (8.9%, 2000-2024) applied forward with deceleration: 7%→5%→3%→1.5% per decade as EV+solar demand matures.",
      assumption: "EV revolution and solar boom sustain strong aluminium demand through 2050, then moderates. ~19 kg/cap by 2070.",
      end_mt: 31, histFrom: 2000,
      anchors: { "2000": 0.59, "2005": 0.89, "2010": 1.55, "2015": 2.4, "2019": 3.6, "2024": 4.5, "2030": 7.0, "2035": 10.0, "2040": 14.0, "2050": 22.0, "2060": 27.5, "2070": 31.0 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "NAMP (MoM) + PLI Scheme (MoCI)",
      color: "#d97706", dash: "4 3", credibility: "NAMP + PLI — Indian official",
      source: "Ministry of Mines (2021). National Aluminium Mission. MoCI (2021). PLI Scheme for Advanced Chemistry Cell.",
      method: "60% National Aluminium Mission targets (domestic capacity 5x by 2030) + 40% PLI-driven EV/packaging demand.",
      assumption: "India meets PLI targets for EV batteries, aluminium packaging. Domestic production replaces imports.",
      end_mt: 24, histFrom: 2024,
      anchors: { "2024": 4.5, "2030": 8.5, "2035": 12.0, "2040": 15.5, "2050": 20.0, "2060": 22.5, "2070": 24.0 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IEA Aluminium Roadmap + World Aluminium STEPS",
      color: "#059669", dash: "5 3", credibility: "IEA + World Aluminium",
      source: "IEA (2022). Aluminium Technology Roadmap. World Aluminium (2023). Statistical Compendium.",
      method: "60% IEA STEPS India trajectory + 40% World Aluminium demand forecast. Service-led economy assumption.",
      assumption: "Moderate EV adoption, recycling rates improve. ~12 kg/cap by 2070 (service economy path).",
      end_mt: 20, histFrom: 2024,
      anchors: { "2024": 4.5, "2030": 6.5, "2035": 9.0, "2040": 11.5, "2050": 15.5, "2060": 18.0, "2070": 20.0 },
    },
  ],
  vol4: {
    demand: { 2024: 4.5, 2050: 22.0, 2070: 38.0 },
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
      source: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4), Ch. 3.4. Scenarios Towards Viksit Bharat and Net Zero.",
      method: "Piecewise-linear: 19 Mt (2024) → 53 Mt (2050) → 61 Mt (2070). India becomes global textile hub.",
      assumption: "India captures ~15% global textile export share by 2050. PM MITRA scheme drives capacity.",
      end_mt: 61, histFrom: 2024,
      anchors: { "2024": 19, "2050": 53, "2070": 61 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Piecewise through MoT/DGFT actuals (2000–2024), extrapolated",
      color: "#7c3aed", credibility: "MoT + DGFT — data fit",
      source: "Ministry of Textiles Annual Reports (2024); DGFT export statistics.",
      method: "Observed CAGR (4.8%, 2000-2024) applied forward with deceleration: 4%→3%→2.5%→2%→1.5% per decade.",
      assumption: "Steady growth as India scales textile exports. Global market share expands from 5% to ~12%. ~34 kg/cap fibre by 2070.",
      end_mt: 57, histFrom: 2000,
      anchors: { "2000": 6.2, "2005": 7.8, "2010": 10.5, "2015": 14.2, "2019": 16.1, "2024": 19, "2030": 24, "2035": 29, "2040": 34, "2050": 43, "2060": 51, "2070": 57 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "PM MITRA (MoT) + PLI Textiles (MoCI)",
      color: "#d97706", dash: "4 3", credibility: "PM MITRA + PLI — Indian official",
      source: "Ministry of Textiles (2022). PM MITRA Scheme. MoCI (2021). PLI for Man-made Fibre & Technical Textiles.",
      method: "60% PM MITRA capacity targets (7 integrated textile parks by 2027, extrapolated) + 40% PLI man-made fibre & technical textiles.",
      assumption: "India executes textile park programme and PLI targets. Export market share grows to 15% globally.",
      end_mt: 60, histFrom: 2024,
      anchors: { "2024": 19, "2030": 27, "2035": 34, "2040": 41, "2050": 51, "2060": 57, "2070": 60 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IEA Textile STEPS + McKinsey Global Fashion",
      color: "#059669", dash: "5 3", credibility: "IEA + McKinsey GFI",
      source: "IEA (2023). Industrial Energy Technology. McKinsey (2023). Global Fashion Index.",
      method: "60% IEA STEPS India industry + 40% McKinsey Global Fashion demand. Circular fashion reduces new fibre demand.",
      assumption: "Circular fashion trends, synthetic fibre recycling. India moderately grows. ~45 Mt by 2070.",
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
      source: "NITI Aayog (2026). Sectoral Insights: Industry (Vol. 4), Ch. 3.5. Scenarios Towards Viksit Bharat and Net Zero.",
      method: "Piecewise-linear: 30.5 Mt (2024) → 55 Mt (2050) → 70 Mt (2070). Food security and agrochemical demand.",
      assumption: "India achieves food security with expanded agricultural output. Fertiliser intensity stays high.",
      end_mt: 70, histFrom: 2024,
      anchors: { "2024": 30.5, "2050": 55.0, "2070": 70.0 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Piecewise through FAI/MoC actuals (2000–2024), extrapolated",
      color: "#7c3aed", credibility: "FAI + MoC — data fit",
      source: "Fertilizer Association of India (2024); Ministry of Chemicals Annual Reports.",
      method: "Observed CAGR (2.1%, 2000-2024) applied forward with gradual deceleration: 2.1%→1.8%→1.5%→1.2%→1.0% per decade.",
      assumption: "Crop area expansion + moderate application rate increase. Nano-urea efficiency partially offsets demand. ~36 kg/cap by 2070.",
      end_mt: 60, histFrom: 2000,
      anchors: { "2000": 18.5, "2005": 20.1, "2010": 21.9, "2015": 24.7, "2019": 26.3, "2024": 30.5, "2030": 34.8, "2035": 38.6, "2040": 42.4, "2050": 50.0, "2060": 56.0, "2070": 60.0 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "NBS Scheme (DoF) + Nano-Urea PLI (MoCI)",
      color: "#d97706", dash: "4 3", credibility: "NBS + Nano-Urea — Indian official",
      source: "Dept. of Fertilizers (2023). Nutrient-Based Subsidy Scheme. IFFCO Nano Urea Programme.",
      method: "60% DoF NBS demand projections (food production targets × fertiliser application norms) + 40% Nano-Urea efficiency factor (reduces conventional urea demand by 15-20%).",
      assumption: "India meets crop production targets. Nano-urea partially displaces conventional urea. ~60 Mt by 2070.",
      end_mt: 60, histFrom: 2024,
      anchors: { "2024": 30.5, "2030": 36.5, "2035": 42.0, "2040": 47.0, "2050": 54.0, "2060": 58.0, "2070": 60.0 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IFA World Fertiliser Outlook + FAO AGLINK",
      color: "#059669", dash: "5 3", credibility: "IFA + FAO AGLINK",
      source: "IFA (2023). World Fertilizer Outlook 2023-2027. FAO (2023). AGLINK-COSIMO model.",
      method: "60% IFA India demand projection + 40% FAO AGLINK (crop area × application rate). Efficiency gains assumed.",
      assumption: "Fertiliser use efficiency improves with precision agriculture. Demand moderates. ~48 Mt by 2070.",
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
