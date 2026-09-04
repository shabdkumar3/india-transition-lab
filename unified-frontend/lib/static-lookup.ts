/**
 * static-lookup.ts — find the nearest pre-baked static run file for a Lab state.
 *
 * Pre-baked files live at /static-runs/{filename}.json (Next.js public dir).
 * This module mirrors the sweep levels and naming convention of prebake_runs.py —
 * BOTH MUST be kept in sync.
 *
 * Logic:
 *  1. If Lab state is at all-defaults → return canonical file URL.
 *  2. If exactly ONE param is non-default → single-sweep URL with nearest level index.
 *  3. If exactly TWO params from a known 2D grid pair → 2D file URL.
 *  4. Otherwise → null (frontend falls back to Railway).
 *
 * The returned URL is always approximate (nearest pre-baked level).
 * api.ts uses it for instant display, then refreshes from backend for exact result.
 */

// ── Sweep levels — MUST match prebake_runs.py SWEEP_LEVELS exactly ───────────
export const SWEEP_LEVELS = {
  cs:   [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0] as const,  // carbon scale
  h2a:  [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]   as const,  // h2 $/kg 2030
  h2b:  [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]  as const,  // h2 $/kg 2050
  wacc: [0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.22, 0.25] as const,
  gp:   [0, 10, 25, 50, 75, 100, 150, 200, 300, 500]            as const,  // green premium $/t
  ei:   [0.02, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.40]       as const,  // grid EI kgCO2/kWh
  io:   [40, 60, 80, 100, 120, 140, 160, 200]                   as const,  // iron ore $/t
  ng:   [2, 4, 6, 8, 10, 12, 15, 20]                            as const,  // nat gas $/MMBtu
  cc:   [80, 100, 120, 140, 160, 180, 200, 250]                 as const,  // coking coal $/t
  co:   [50, 70, 90, 110, 130, 150, 170, 200]                   as const,  // coal $/t
} as const;

type SweepKey = keyof typeof SWEEP_LEVELS;

// Carbon price bases per scenario (MUST match prebake_runs.py CARBON_BASE)
const CARBON_BASE: Record<string, Record<string, number>> = {
  CPS: { "2024": 5, "2030": 15,  "2050": 65,  "2070": 110 },
  NZS: { "2024": 5, "2030": 30,  "2050": 120, "2070": 185 },
  LAB: { "2024": 5, "2030": 15,  "2050": 65,  "2070": 110 }, // steel uses LAB; CPS base
};

// Steel demand anchor fingerprints → demand key
// Values are the 2070 anchor value (unique per key)
export const STEEL_ANCHOR_2070: Record<number, string> = {
  821.0: "niti",
  668.6: "model_fitted",
  580.0: "india_policy",
  496.0: "international",
};

// ── Nearest-index helper ───────────────────────────────────────────────────────
function nearestIdx(levels: readonly number[], value: number): number {
  let bestIdx = 0;
  let bestDist = Infinity;
  for (let i = 0; i < levels.length; i++) {
    const d = Math.abs(levels[i] - value);
    if (d < bestDist) { bestDist = d; bestIdx = i; }
  }
  return bestIdx;
}

// ── Scale factor from carbon price dict ──────────────────────────────────────
function carbonScale(carbonPrice: Record<string, number>, scenarioBase: Record<string, number>): number {
  const base2050 = scenarioBase["2050"] ?? 65;
  if (base2050 === 0) return 1.0;
  return (carbonPrice["2050"] ?? base2050) / base2050;
}

// ── Public API ────────────────────────────────────────────────────────────────

export interface LabLookupParams {
  sectorId:     string;
  /** "CPS" | "NZS" | "LAB" */
  scenario:     string;
  /** demand key or inferred from steel anchors */
  demandModel?: string;
  /** steel demand_anchors dict (if steel) */
  demandAnchors?: Record<string, number>;
  carbonPrice:  Record<string, number>;
  h2Cost:       Record<string, number>;
  greenPremium: number;
  waccDecimal:  number;  // e.g. 0.10
  gridEI2070:   number;  // 0 = auto (don't vary)
  ironOre?:     number;  // absolute $/t (steel only)
  natGas?:      number;  // absolute $/MMBtu (steel only)
  cokingCoal?:  number;  // absolute $/t (steel only)
  coalAbs?:     number;  // absolute $/t (non-steel coal sectors)
}

/**
 * Returns a URL like "/static-runs/steel_NZS_niti_cs3.json" if a pre-baked
 * file exists for this Lab state (or nearest quantized equivalent), else null.
 */
export function findStaticRunUrl(params: LabLookupParams): string | null {
  const { sectorId, scenario, demandModel, demandAnchors } = params;

  // ── Resolve demand key ────────────────────────────────────────────────────
  let demandKey: string;
  if (sectorId === "steel" && demandAnchors) {
    const anchor2070 = demandAnchors["2070"];
    demandKey = STEEL_ANCHOR_2070[anchor2070] ?? "niti";
  } else {
    demandKey = demandModel ?? "niti";
  }

  // Effective scenario for file naming (steel sends "LAB" but CPS/NZS base differs)
  const effectiveScenario = (scenario === "LAB") ? "CPS" : scenario;
  const baseCarbon = CARBON_BASE[effectiveScenario] ?? CARBON_BASE["CPS"];
  const prefix = `/static-runs/${sectorId}_${effectiveScenario}_${demandKey}`;

  // ── Compute which params are non-default ──────────────────────────────────
  const cs     = carbonScale(params.carbonPrice, baseCarbon);
  const isDefaultCS     = Math.abs(cs - 1.0) < 0.03;
  const isDefaultH2a    = Math.abs((params.h2Cost["2030"] ?? 4.0) - 4.0) < 0.05;
  const isDefaultH2b    = Math.abs((params.h2Cost["2050"] ?? 1.5) - 1.5) < 0.05;
  const isDefaultWACC   = Math.abs(params.waccDecimal - 0.10) < 0.005;
  const isDefaultGP     = params.greenPremium === 0;
  const isDefaultEI     = params.gridEI2070 === 0;
  const isDefaultIO     = !params.ironOre    || Math.abs(params.ironOre    - 80)  < 1;
  const isDefaultNG     = !params.natGas     || Math.abs(params.natGas     - 6)   < 0.1;
  const isDefaultCC     = !params.cokingCoal || Math.abs(params.cokingCoal - 140) < 1;
  const isDefaultCoal   = !params.coalAbs    || Math.abs(params.coalAbs    - 90)  < 1;

  // Build list of non-default dimensions (key + raw value for quantisation)
  type Dim = { key: SweepKey; value: number };
  const nonDefault: Dim[] = [];
  if (!isDefaultCS)   nonDefault.push({ key: "cs",   value: cs });
  if (!isDefaultH2a)  nonDefault.push({ key: "h2a",  value: params.h2Cost["2030"] ?? 4.0 });
  if (!isDefaultH2b)  nonDefault.push({ key: "h2b",  value: params.h2Cost["2050"] ?? 1.5 });
  if (!isDefaultWACC) nonDefault.push({ key: "wacc", value: params.waccDecimal });
  if (!isDefaultGP)   nonDefault.push({ key: "gp",   value: params.greenPremium });
  if (!isDefaultEI)   nonDefault.push({ key: "ei",   value: params.gridEI2070 });
  if (!isDefaultIO)   nonDefault.push({ key: "io",   value: params.ironOre! });
  if (!isDefaultNG)   nonDefault.push({ key: "ng",   value: params.natGas! });
  if (!isDefaultCC)   nonDefault.push({ key: "cc",   value: params.cokingCoal! });
  if (!isDefaultCoal) nonDefault.push({ key: "co",   value: params.coalAbs! });

  // ── 0 non-defaults → canonical ────────────────────────────────────────────
  if (nonDefault.length === 0) {
    return `${prefix}.json`;
  }

  // ── 1 non-default → single sweep file ────────────────────────────────────
  if (nonDefault.length === 1) {
    const { key, value } = nonDefault[0];
    const idx = nearestIdx(SWEEP_LEVELS[key], value);
    return `${prefix}_${key}${idx}.json`;
  }

  // ── 2 non-defaults → check known 2D grid pairs ───────────────────────────
  if (nonDefault.length === 2) {
    const keys = nonDefault.map(d => d.key);
    const val  = (k: SweepKey) => nonDefault.find(d => d.key === k)!.value;

    // Carbon × H2 (only for steel/fertiliser which have h2 in file set)
    const hasH2 = sectorId === "steel" || sectorId === "fertiliser";
    if (hasH2 && keys.includes("cs") && keys.includes("h2a")) {
      const ci = nearestIdx(SWEEP_LEVELS.cs.slice(0, 8)   as unknown as readonly number[], val("cs"));
      const hi = nearestIdx(SWEEP_LEVELS.h2a.slice(0, 8)  as unknown as readonly number[], val("h2a"));
      return `${prefix}_cs${ci}_h2a${hi}.json`;
    }

    // Carbon × WACC (all sectors)
    if (keys.includes("cs") && keys.includes("wacc")) {
      const ci = nearestIdx(SWEEP_LEVELS.cs.slice(0, 6)   as unknown as readonly number[], val("cs"));
      const wi = nearestIdx(SWEEP_LEVELS.wacc.slice(0, 6) as unknown as readonly number[], val("wacc"));
      return `${prefix}_cs${ci}_wacc${wi}.json`;
    }

    // Carbon × Green Premium (all sectors)
    if (keys.includes("cs") && keys.includes("gp")) {
      const ci = nearestIdx(SWEEP_LEVELS.cs.slice(0, 6) as unknown as readonly number[], val("cs"));
      const gi = nearestIdx(SWEEP_LEVELS.gp.slice(0, 6) as unknown as readonly number[], val("gp"));
      return `${prefix}_cs${ci}_gp${gi}.json`;
    }
  }

  // ── 3+ non-defaults → no static match ────────────────────────────────────
  return null;
}

/**
 * Fetch a static pre-baked run file. Returns null on any error (404, network, etc.).
 * Designed to be called speculatively — caller falls back to backend on null.
 */
export async function fetchStaticRun(url: string): Promise<unknown | null> {
  try {
    const res = await fetch(url, { cache: "force-cache" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}
