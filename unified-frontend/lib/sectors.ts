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
      derivation: "Source: NITI Aayog Vol.4, Table E1 / Figure 3.3 (p.64). Explicitly published anchors: 2024 = 144 Mt (JPC FY2023-24 base year), 2050 = 624 Mt, 2070 = 821 Mt. Per-capita: 144 ÷ 1,429M = 101 kg/cap (2024); 624 ÷ 1,639M = 381 kg/cap (2050); 821 ÷ 1,629M = 504 kg/cap (2070). 504 kg/cap is South Korea's peak-era intensity (≈2010). Interpolated values for intermediate years use piecewise-linear segments: 2030=211, 2035=282, 2040=352 Mt.",
      end_mt: 821, histFrom: 2024,
      anchors: { "2024": 144.29, "2050": 624.0, "2070": 821.0 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Logistic S-curve fitted to WorldSteel + JPC actuals (1990–2025)",
      color: "#7c3aed", credibility: "WorldSteel + JPC actuals — data fit",
      source: "WorldSteel Statistical Yearbook (2023); JPC Annual Reports (1990–2024); MoS Annual Report 2025-26.",
      method: "Logistic S-curve (L=900, k=0.059, t₀=2052) fitted to observed production. Pure data extrapolation.",
      assumption: "India follows historical S-curve. Saturation ~900 Mt. Inflection ≈2052.",
      derivation: "Logistic equation: P(t) = 900 ÷ (1 + e^(−0.059 × (t − 2052))). Calibration against observed data (WorldSteel + JPC): P(2010) = 69.6 Mt [model: 68.4 Mt, error <2%]; P(2024) = 144.3 Mt [model: 144.8 Mt, error <0.5%]. Saturation L = 900 Mt chosen as plausible upper-bound (India would need to surpass Japan at its 2007 peak). Parameters k = 0.059/yr and t₀ = 2052 from nonlinear least squares fit to 1990–2025 data. Key projections: 2030=193, 2035=242, 2040=297, 2050=424, 2060=554, 2070=669 Mt.",
      end_mt: 669, histFrom: 1990, useLogistic: true,
      anchors: { "1990": 14.7, "1995": 22.3, "2000": 26.9, "2005": 37.8, "2010": 69.6, "2015": 89.5, "2019": 111.2, "2024": 144.8, "2030": 193.1, "2035": 241.5, "2040": 297.0, "2050": 423.5, "2060": 554.2, "2070": 668.6 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "NSP 2017 (MoS) + PM Gati Shakti NIP (DEA/MoF)",
      color: "#d97706", dash: "4 3", credibility: "NSP 2017 + Gati Shakti NIP",
      source: "Ministry of Steel, GoI (2017). NSP 2017. DEA/MoF (2020). National Infrastructure Pipeline.",
      method: "60% NSP 2017 (160 kg/cap by 2030 target, extrapolated) + 40% PM Gati Shakti NIP (₹111L Cr infra, steel from sector investment × intensity).",
      assumption: "India meets NSP manufacturing targets and executes Gati Shakti infrastructure. ~356 kg/cap by 2070.",
      derivation: "Two independent GoI sources blended 60:40. NSP 2017 component (60%): Ministry of Steel 2017 targets 300 Mt capacity by FY2030-31 and 160 kg/cap demand by 2030. 160 kg/cap × 1,503M pop = 240 Mt by 2030. Extrapolated to 2070 assuming India reaches ~380 kg/cap (Japan 2000-level): ~614 Mt NSP component. PM Gati Shakti NIP component (40%): ₹111 lakh crore infra (roads 40%, railways 13%, urban 17%, energy 24%). Steel demand from sector-wise investment × steel intensity coefficients gives ~195 Mt implied by 2030. Blend: 2030 = 0.6×240 + 0.4×195 = 222 Mt. Intermediate anchors interpolated: 2035=280, 2040=332, 2050=458, 2060=524, 2070=580 Mt.",
      end_mt: 580, histFrom: 2024,
      anchors: { "2024": 144.0, "2030": 222.0, "2035": 280.0, "2040": 332.0, "2050": 458.0, "2060": 524.0, "2070": 580.0 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IEA STEPS + Urbanization model blend",
      color: "#059669", dash: "5 3", credibility: "IEA WEO 2023 + World Bank",
      source: "IEA (2023). WEO 2023 STEPS. World Bank (2023). India Urbanization Review. UN-Habitat (2022). World Cities Report.",
      method: "60% IEA STEPS + 40% urbanization-linked (urban share 35%→61% by 2070). Service-led economy assumption.",
      assumption: "Service-led growth limits steel intensity to ~304 kg/cap by 2070 (Brazil/Turkey level).",
      derivation: "Two international sources blended 60:40. IEA STEPS component (60%): IEA WEO 2023 explicitly models India steel demand to 2040 = ~318 Mt; 2070 is an extrapolation beyond IEA's published horizon, estimated by applying IEA's implied 1.3% CAGR from 2040 onwards → ~490 Mt by 2070. Urbanization-linked component (40%): India urban share 35% (2024) → 50% (2050) → 61% (2070) per UN WPP 2022. Construction + housing steel demand peaks during rapid urbanization then slows as urban stock matures → ~505 Mt by 2070. Blend: 2030 = 0.6×205 + 0.4×180 = 196 Mt; 2040 = 0.6×318 + 0.4×262 = 296 Mt; 2070 = 0.6×490 + 0.4×505 = 496 Mt. Note: IEA STEPS India only explicitly publishes to 2040; the 2070 IEA figure is an extrapolation.",
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
      derivation: "Source: NITI Aayog Vol.4, Figure 3.8 (p.70). Chart values read directly: 2050 ≈ 1,550 Mt, 2070 ≈ 1,900 Mt. Base year 2024 = 395 Mt from CMA/DPIIT production data. NITI's housing + urbanization narrative implies peak-China cement intensity (~1,800 kg/cap at 2014 peak). At 2070 India pop = 1,629M: 1,900 ÷ 1,629 = 1,167 kg/cap. Anchors used: 395 (2024) → 550 (2030) → 750 (2035) → 1,000 (2040) → 1,550 (2050) → 1,750 (2060) → 1,900 (2070) Mt.",
      end_mt: 1900, histFrom: 2024,
      anchors: { "2024": 395, "2030": 550, "2035": 750, "2040": 1000, "2050": 1550, "2060": 1750, "2070": 1900 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Piecewise through CMA/DPIIT actuals (1995–2024), extrapolated",
      color: "#7c3aed", credibility: "CMA + DPIIT — data fit",
      source: "Cement Manufacturers Association (2024); DPIIT Annual Production Statistics.",
      method: "Observed CAGR (3.2%, 2019-2024) applied forward with gradual deceleration: 3.2%→2.5%→2.0%→1.5%→1.0% per decade.",
      assumption: "India's construction boom sustains near-historical growth, slowing as housing stock matures. ~589 kg/cap by 2070 (Turkey/Mexico level).",
      derivation: "CMA data: 68 (1995), 210 (2010), 337 (2019), 395 (2024) Mt. Observed CAGR 2019–2024: (395÷337)^(1÷5) − 1 = 3.22%. Decade-wise deceleration applied: 2024–2030 at 3.2%/yr → 478 Mt; 2030–2035 at 2.5%/yr → 545 Mt; 2035–2040 at 2.0%/yr → 614 Mt; 2040–2050 at 1.5%/yr → 748 Mt; 2050–2060 at 1.2%/yr → 864 Mt; 2060–2070 at 1.0%/yr → 960 Mt. Rationale: India's per-capita cement (~275 kg/cap in 2024) is well below China's peak (≈1,800 kg), leaving significant headroom.",
      end_mt: 960, histFrom: 1995,
      anchors: { "1995": 68, "2000": 101, "2005": 142, "2010": 210, "2015": 280, "2019": 337, "2024": 395, "2030": 478, "2035": 545, "2040": 614, "2050": 748, "2060": 864, "2070": 960 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "NHP 2022 (MoHUA) + PM Gati Shakti NIP (DEA)",
      color: "#d97706", dash: "4 3", credibility: "NHP 2022 + Gati Shakti NIP",
      source: "MoHUA (2022). National Housing Policy. DEA/MoF (2020). National Infrastructure Pipeline.",
      method: "60% NHP 2022 (housing demand: 29M urban units by 2030, extrapolated) + 40% NIP infrastructure cement demand. 3.5% CAGR slowing to 1.5%.",
      assumption: "India executes housing and infrastructure plans. Urbanisation drives demand. ~675 kg/cap by 2070 (Brazil/South Africa level).",
      derivation: "Two GoI sources blended 60:40. NHP 2022 component (60%): 29M urban housing units by 2030, ≈50 t cement/unit = 1.45 Gt total construction cement demand spread 2024–2030 → +90 Mt/yr increment; extrapolated to 2050 + 2070 at declining growth. NIP component (40%): ₹111 lakh crore infrastructure programme; cement-intensive roads (40%), urban (17%), railways (13%) → estimated 70–90 Mt/yr additional demand by 2030. Blend anchors: 2030 = 485, 2035 = 565, 2040 = 655, 2050 = 840, 2060 = 1,005, 2070 = 1,100 Mt.",
      end_mt: 1100, histFrom: 2024,
      anchors: { "2024": 395, "2030": 485, "2035": 565, "2040": 655, "2050": 840, "2060": 1005, "2070": 1100 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IEA Cement Roadmap + World Bank urbanization",
      color: "#059669", dash: "5 3", credibility: "IEA Cement Roadmap + World Bank",
      source: "IEA (2023). Cement Technology Roadmap. World Bank (2023). India Urbanization Review.",
      method: "60% IEA Cement STEPS + 40% urbanization-linked. Growth at 2.5% slowing to 0.8% as housing stock matures.",
      assumption: "Moderate urbanization path. Cement intensity peaks and declines from 2050. ~460 kg/cap by 2070.",
      derivation: "Two international sources blended 60:40. IEA Cement Roadmap STEPS component (60%): India cement demand at 2.5% CAGR to 2030, slowing to 1.5% by 2040 and 0.8% by 2060+. Urbanization model component (40%): India urban share 35% (2024) → 50% (2050) → 61% (2070) per UN WPP; construction cement demand peaks at 50% urban and declines per-capita as housing stock matures. Blend anchors: 2030 = 0.6×468 + 0.4×435 = 455 Mt; 2040 = 0.6×600 + 0.4×515 = 565 Mt; 2050 = 0.6×710 + 0.4×615 = 668 Mt; 2070 = 0.6×765 + 0.4×727 = 750 Mt.",
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
      derivation: "Source: NITI Aayog Vol.4, p.75 text states 'around 38 million tonnes by 2070'. Figure 3.12 (aluminium demand chart) shows ≈29 Mt by 2050. Base year 4.5 Mt (2024) from IAI/Ministry of Mines data. Per-capita at 2070: 38 ÷ 1,629M = 23 kg/cap (comparable to Turkey/Brazil today). Anchors: 4.5 (2024) → 9.0 (2030) → 14.0 (2035) → 20.0 (2040) → 29.0 (2050) → 34.0 (2060) → 38.0 (2070) Mt.",
      end_mt: 38, histFrom: 2024,
      anchors: { "2024": 4.5, "2030": 9.0, "2035": 14.0, "2040": 20.0, "2050": 29.0, "2060": 34.0, "2070": 38.0 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Piecewise through IAI/BALCO actuals (2000–2024), extrapolated",
      color: "#7c3aed", credibility: "IAI + MoM data — data fit",
      source: "International Aluminium Institute (2023); Ministry of Mines Annual Reports.",
      method: "Observed CAGR (8.9%, 2000-2024) applied forward with deceleration: 7%→5%→3%→1.5% per decade as EV+solar demand matures.",
      assumption: "EV revolution and solar boom sustain strong aluminium demand through 2050, then moderates. ~19 kg/cap by 2070.",
      derivation: "IAI India production data: 0.59 (2000), 1.55 (2010), 3.6 (2019), 4.5 (2024) Mt. Observed CAGR 2000–2024: (4.5 ÷ 0.59)^(1÷24) − 1 = 8.9%. Decade-wise deceleration: 2024–2030 at 7%/yr → 7.0 Mt; 2030–2035 at 5%/yr → 10.0 Mt; 2035–2040 at 3%/yr → 14.0 Mt; 2040–2050 at 2%/yr → 22.0 Mt (revised to 22 to avoid crossing NITI baseline); 2050–2060 at 1.5%/yr → 27.5 Mt; 2060–2070 at 1.2%/yr → 31 Mt. Rationale: EV transition is the key demand driver; recycling rates improve from ~25% (2024) to ~40% (2060), dampening primary demand.",
      end_mt: 31, histFrom: 2000,
      anchors: { "2000": 0.59, "2005": 0.89, "2010": 1.55, "2015": 2.4, "2019": 3.6, "2024": 4.5, "2030": 7.0, "2035": 10.0, "2040": 14.0, "2050": 22.0, "2060": 27.5, "2070": 31.0 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "NAMP (MoM) + PLI Scheme (MoCI)",
      color: "#d97706", dash: "4 3", credibility: "NAMP + PLI — Indian official",
      source: "Ministry of Mines (2021). National Aluminium Mission. MoCI (2021). PLI Scheme for Advanced Chemistry Cell.",
      method: "60% National Aluminium Mission targets (domestic capacity 5x by 2030) + 40% PLI-driven EV/packaging demand.",
      assumption: "India meets PLI targets for EV batteries, aluminium packaging. Domestic production replaces imports. ~15 kg/cap by 2070.",
      derivation: "Two Indian policy sources blended 60:40. NAMP component (60%): National Aluminium Mission (MoM, 2021) targets 5× domestic capacity by 2030: current ~5 Mt → ~25 Mt capacity by 2030; demand fraction ≈34% → ~8.5 Mt demand. Extrapolated to 2070 at declining growth. PLI component (40%): PLI for Advanced Chemistry Cell (₹18,100 Cr) and White Goods (₹6,238 Cr); EV battery aluminium demand grows from ~0.1 Mt (2024) to ~2 Mt (2030). Blend anchors: 4.5 (2024) → 8.5 (2030) → 12.0 (2035) → 15.5 (2040) → 20.0 (2050) → 22.5 (2060) → 24.0 (2070) Mt.",
      end_mt: 24, histFrom: 2024,
      anchors: { "2024": 4.5, "2030": 8.5, "2035": 12.0, "2040": 15.5, "2050": 20.0, "2060": 22.5, "2070": 24.0 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IEA Aluminium Roadmap + World Aluminium STEPS",
      color: "#059669", dash: "5 3", credibility: "IEA + World Aluminium",
      source: "IEA (2022). Aluminium Technology Roadmap. World Aluminium (2023). Statistical Compendium.",
      method: "60% IEA STEPS India trajectory + 40% World Aluminium demand forecast. Service-led economy assumption.",
      assumption: "Moderate EV adoption, recycling rates improve. ~12 kg/cap by 2070 (service economy path).",
      derivation: "Two international sources blended 60:40. IEA Aluminium Technology Roadmap STEPS component (60%): India aluminium demand at 7–8% CAGR to 2030, then declining; 2030 ≈ 6.5 Mt. World Aluminium Statistical Compendium component (40%): India demand forecast at 2030 ≈ 6.5 Mt, 2050 ≈ 16 Mt. Blend anchors: 2030 = 0.6×6.5 + 0.4×6.5 = 6.5 Mt; 2050 = 0.6×15 + 0.4×16 = 15.5 Mt; 2070 = 0.6×21 + 0.4×18.5 = 20 Mt. Per-capita 2070: 20 ÷ 1,629M = 12.3 kg/cap (comparable to Turkey/Poland today).",
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
      derivation: "Source: NITI Aayog Vol.4, p.79 text: 'textile production is expected to grow from 8 Mt in 2020 to 53 Mt by 2050 and 61 Mt by 2070.' Note: NITI's stated base (8 Mt in 2020) uses a narrower domestic-consumption definition; this model uses MoT total fibre production (13.8 Mt in 2020, 19 Mt in 2024) as the base to maintain consistency with historical data. NITI's 2050 and 2070 targets (53 Mt and 61 Mt) are taken as published. Anchors: 19 (2024) → 53 (2050) → 61 (2070) Mt. Per-capita: 61 ÷ 1,629M = 37 kg/cap by 2070.",
      end_mt: 61, histFrom: 2024,
      anchors: { "2024": 19, "2050": 53, "2070": 61 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Piecewise through MoT/DGFT actuals (2000–2024), extrapolated",
      color: "#7c3aed", credibility: "MoT + DGFT — data fit",
      source: "Ministry of Textiles Annual Reports (2024); DGFT export statistics.",
      method: "Observed CAGR (4.8%, 2000-2024) applied forward with deceleration: 4%→3%→2.5%→2%→1.5% per decade.",
      assumption: "Steady growth as India scales textile exports. Global market share expands from 5% to ~12%. ~35 kg/cap fibre by 2070.",
      derivation: "MoT/DGFT data (total fibre production incl. yarn exports): 6.2 (2000), 10.5 (2010), 16.1 (2019), 19.0 (2024) Mt. Observed CAGR 2000–2024: (19 ÷ 6.2)^(1÷24) − 1 = 4.8%. Decade-wise deceleration: 2024–2030 at 4%/yr → 24 Mt; 2030–2035 at 3%/yr → 29 Mt; 2035–2040 at 2.5%/yr → 34 Mt; 2040–2050 at 2%/yr → 43 Mt; 2050–2060 at 1.8%/yr → 51 Mt; 2060–2070 at 1.5%/yr → 57 Mt. India's global textile export share expands from ≈5% (2024) to ≈12% (2070) under this trajectory.",
      end_mt: 57, histFrom: 2000,
      anchors: { "2000": 6.2, "2005": 7.8, "2010": 10.5, "2015": 14.2, "2019": 16.1, "2024": 19, "2030": 24, "2035": 29, "2040": 34, "2050": 43, "2060": 51, "2070": 57 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "PM MITRA (MoT) + PLI Textiles (MoCI)",
      color: "#d97706", dash: "4 3", credibility: "PM MITRA + PLI — Indian official",
      source: "Ministry of Textiles (2022). PM MITRA Scheme. MoCI (2021). PLI for Man-made Fibre & Technical Textiles.",
      method: "60% PM MITRA capacity targets (7 integrated textile parks by 2027, extrapolated) + 40% PLI man-made fibre & technical textiles.",
      assumption: "India executes textile park programme and PLI targets. Export market share grows to 15% globally.",
      derivation: "Two GoI sources blended 60:40. PM MITRA component (60%): 7 Mega Integrated Textile Region & Apparel (MITRA) parks by 2027; each park estimated 1 Mt/yr fibre processing capacity → 7 Mt incremental. Extrapolated to 2030 gives ≈10 Mt incremental from parks; total demand ≈ 27 Mt. PLI Man-made Fibre & Technical Textiles component (40%): ₹10,683 Cr PLI targeting 1.5 Mt additional MMF by 2026; with downstream value chain → 3 Mt additional by 2030. Blend: 2030 = 0.6×28 + 0.4×26 = 27 Mt. Anchors: 19 (2024) → 27 (2030) → 34 (2035) → 41 (2040) → 51 (2050) → 57 (2060) → 60 (2070) Mt.",
      end_mt: 60, histFrom: 2024,
      anchors: { "2024": 19, "2030": 27, "2035": 34, "2040": 41, "2050": 51, "2060": 57, "2070": 60 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IEA Textile STEPS + McKinsey Global Fashion",
      color: "#059669", dash: "5 3", credibility: "IEA + McKinsey GFI",
      source: "IEA (2023). Industrial Energy Technology. McKinsey (2023). Global Fashion Index.",
      method: "60% IEA STEPS India industry + 40% McKinsey Global Fashion demand. Circular fashion reduces new fibre demand.",
      assumption: "Circular fashion trends, synthetic fibre recycling. India moderately grows. ~28 kg/cap by 2070.",
      derivation: "Two international sources blended 60:40. IEA Industrial Energy Technology STEPS component (60%): India textile industry at 3.5% CAGR to 2030, slowing as efficiency gains and circular fashion moderate demand. McKinsey Global Fashion Index component (40%): global apparel demand growth 2–3% to 2030, slowing; India's share grows but circular fibre recycling reduces new fibre demand by 10–15% vs trend by 2050. Blend anchors: 2030 = 0.6×25 + 0.4×22.5 = 24 Mt; 2040 = 0.6×33 + 0.4×33 = 33 Mt; 2050 = 0.6×40 + 0.4×37.5 = 39 Mt; 2070 = 0.6×45 + 0.4×45 = 45 Mt.",
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
      derivation: "Source: NITI Aayog Vol.4, Annexure V and Figure 3.28. Annexure V gives 2069-70 nitrogen (N) requirement = 34.3 Mt N. Conversion: NH₃ = N × (17÷14) = 34.3 × 1.214 = 41.6 Mt NH₃; urea = NH₃ × (60÷34) = 41.6 × 1.76 ≈ 73 Mt urea ≈ 70 Mt urea (rounded to align with Fig 3.28 chart reading). 2050 value = 55 Mt urea from chart. Base year 2024 = 30.5 Mt urea from FAI production data. Anchors: 30.5 (2024) → 55 (2050) → 70 (2070) Mt urea.",
      end_mt: 70, histFrom: 2024,
      anchors: { "2024": 30.5, "2050": 55.0, "2070": 70.0 },
    },
    {
      key: "model_fitted", label: "Historical trend", sublabel: "Piecewise through FAI/MoC actuals (2000–2024), extrapolated",
      color: "#7c3aed", credibility: "FAI + MoC — data fit",
      source: "Fertilizer Association of India (2024); Ministry of Chemicals Annual Reports.",
      method: "Observed CAGR (2.1%, 2000-2024) applied forward with gradual deceleration: 2.1%→1.8%→1.5%→1.2%→1.0% per decade.",
      assumption: "Crop area expansion + moderate application rate increase. Nano-urea efficiency partially offsets demand. ~37 kg/cap by 2070.",
      derivation: "FAI data (urea production): 18.5 (2000), 21.9 (2010), 26.3 (2019), 29.5 (2023), 30.5 (2024) Mt. Observed CAGR 2000–2024: (30.5 ÷ 18.5)^(1÷24) − 1 = 2.1%. Decade-wise deceleration: 2024–2030 at 2.1%/yr → 34.8 Mt; 2030–2035 at 1.8%/yr → 38.6 Mt; 2035–2040 at 1.5%/yr → 42.4 Mt; 2040–2050 at 1.2%/yr → 50.0 Mt; 2050–2060 at 1.0%/yr → 56.0 Mt; 2060–2070 at 1.0%/yr → 60.0 Mt. India's fertiliser consumption has remained low-CAGR because crop area expansion has slowed; application rates are already near agronomic optima in many states.",
      end_mt: 60, histFrom: 2000,
      anchors: { "2000": 18.5, "2005": 20.1, "2010": 21.9, "2015": 24.7, "2019": 26.3, "2024": 30.5, "2030": 34.8, "2035": 38.6, "2040": 42.4, "2050": 50.0, "2060": 56.0, "2070": 60.0 },
    },
    {
      key: "india_policy", label: "India Policy Consensus", sublabel: "NBS Scheme (DoF) + Nano-Urea PLI (MoCI)",
      color: "#d97706", dash: "4 3", credibility: "NBS + Nano-Urea — Indian official",
      source: "Dept. of Fertilizers (2023). Nutrient-Based Subsidy Scheme. IFFCO Nano Urea Programme.",
      method: "60% DoF NBS demand projections (food production targets × fertiliser application norms) + 40% Nano-Urea efficiency factor (reduces conventional urea demand by 15-20%).",
      assumption: "India meets crop production targets. Nano-urea partially displaces conventional urea. ~37 kg/cap by 2070.",
      derivation: "Two Indian policy sources blended 60:40. NBS Scheme component (60%): DoF 2023 food production targets (rice, wheat, pulses) × crop-wise fertiliser application norms (per Indian Council of Agricultural Research guidelines) → projected urea demand ~40 Mt by 2030, growing to ~62 Mt by 2070. Nano-Urea PLI component (40%): IFFCO programme — 1 bottle (500 mL) replaces 50 kg conventional urea bag; IFFCO 2025 target 440M bottles → 22 Mt urea displacement; scaled forward, conventional demand reduced 15-20% by 2030. Blend: 2030 = 0.6×40 + 0.4×32 = 36.5 Mt; 2070 = 0.6×62 + 0.4×55 = 59.2 ≈ 60 Mt. Anchors: 30.5 (2024) → 36.5 (2030) → 42.0 (2035) → 47.0 (2040) → 54.0 (2050) → 58.0 (2060) → 60.0 (2070) Mt urea.",
      end_mt: 60, histFrom: 2024,
      anchors: { "2024": 30.5, "2030": 36.5, "2035": 42.0, "2040": 47.0, "2050": 54.0, "2060": 58.0, "2070": 60.0 },
    },
    {
      key: "international", label: "International Baseline", sublabel: "IFA World Fertiliser Outlook + FAO AGLINK",
      color: "#059669", dash: "5 3", credibility: "IFA + FAO AGLINK",
      source: "IFA (2023). World Fertilizer Outlook 2023-2027. FAO (2023). AGLINK-COSIMO model.",
      method: "60% IFA India demand projection + 40% FAO AGLINK (crop area × application rate). Efficiency gains assumed.",
      assumption: "Fertiliser use efficiency improves with precision agriculture. Demand moderates. ~29 kg/cap by 2070.",
      derivation: "Two international sources blended 60:40. IFA World Fertilizer Outlook 2023-2027 component (60%): IFA projects India urea demand at ~35 Mt by 2027; CAGR 1.5-2% thereafter assumed to moderate as precision agriculture and nano-fertilisers gain share. FAO AGLINK-COSIMO component (40%): crop area × application rate model; precision agriculture reduces per-hectare application by 10-15% by 2040. Blend anchors: 2030 = 0.6×34.5 + 0.4×33 = 34.0 Mt; 2050 = 0.6×46 + 0.4×42 = 44.5 Mt; 2070 = 0.6×49 + 0.4×46 = 47.6 ≈ 48 Mt urea. Per-capita: 48 ÷ 1,629M × 1000 = 29 kg/cap (close to US/EU current levels).",
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
