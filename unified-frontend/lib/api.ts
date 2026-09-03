/**
 * Generic sector API client.
 * Each sector's backend runs at a different port but exposes the same REST surface as steel.
 * For sectors whose backend isn't built yet, all calls return a "not_available" flag.
 */

import { SectorConfig } from "./sectors";

export interface RunResult {
  status: "ok" | "infeasible" | "not_available";
  message?: string;
  years?: number[];
  yearly_results?: Record<number, YearlyResult>;
  summary?: RunSummary;
  // raw solver fields pass through
  [key: string]: unknown;
}

export interface YearlyResult {
  year: number;
  production_by_route: Record<string, number>;
  capacity_by_route: Record<string, number>;
  investment_by_route: Record<string, number>;
  total_production: number;
  total_cost: number;
  co2_intensity: number;
  co2_total: number;
  [key: string]: unknown;
}

export interface RunSummary {
  total_cost_bn: number;
  total_co2_mt: number;
  final_co2_intensity: number;
  final_year_demand: number;
  [key: string]: unknown;
}

export interface DemandTrajectoriesResponse {
  niti: TrajectoryBranch;
  model_fitted: TrajectoryBranch;
  india_policy: TrajectoryBranch;
  international: TrajectoryBranch;
  historical: { year: number; production_mt: number }[];
  _logistic_chart?: Record<string, number>;
}

export interface TrajectoryBranch {
  label: string;
  chart_series?: Record<string, number>;
  annual_series: Record<string, number>;
  end_value: number;
  source: string;
  method: string;
  assumption?: string;
}

// ── Core fetch wrapper ────────────────────────────────────────────────────────

// In production (non-localhost), call Railway directly to bypass Vercel's 10s proxy timeout.
// CORS is enabled on Railway (allow_origins=["*"]) so browser can call it directly.
// apiBase looks like "/api/steel" → strip "/api/" → append to Railway base URL.
const RAILWAY_URL = "https://india-transition-lab-production.up.railway.app";

function resolveBase(apiBase: string): string {
  // If running in the browser and not on localhost → call Railway directly
  if (typeof window !== "undefined" && !window.location.hostname.includes("localhost")) {
    const sector = apiBase.replace(/^\/api\//, "");
    return `${RAILWAY_URL}/${sector}`;
  }
  return apiBase; // local dev: use Next.js rewrite proxy (no CORS issue)
}

async function apiFetch<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const resolvedBase = resolveBase(base);
  const res = await fetch(`${resolvedBase}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const err = await res.text().catch(() => res.statusText);
    throw new Error(`API ${path} — ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

// ── Health check ─────────────────────────────────────────────────────────────

export async function checkHealth(sector: SectorConfig): Promise<boolean> {
  try {
    const base = resolveBase(sector.apiBase);
    const res = await fetch(`${base}/health`, { signal: AbortSignal.timeout(5000) });
    return res.ok;
  } catch {
    return false;
  }
}

// ── Demand trajectories ───────────────────────────────────────────────────────  // Steel backend exposes /api/demand-trajectories; other sectors use local config fallback.

export async function fetchDemandTrajectories(
  sector: SectorConfig
): Promise<DemandTrajectoriesResponse | null> {
  try {
    return await apiFetch<DemandTrajectoriesResponse>(sector.apiBase, "/api/demand-trajectories");
  } catch {
    return null; // caller handles with local config data
  }
}

// ── Route details (per-sector) ─────────────────────────────────────────────

export interface RouteDetail {
  id: string;
  existing: number;
  capex: number;
  fom: number;
  vom_total: number;
  ef_2024: number;
  ef_cps_2050: number | null;
  ef_nzs_2050: number | null;
  avail: number;
  start: number;
  max_ramp: number;
  lifetime: number;
  h2_route: boolean;
}

export async function fetchRoutes(sector: SectorConfig): Promise<RouteDetail[]> {
  try {
    const data = await apiFetch<{ routes: RouteDetail[] }>(sector.apiBase, "/api/routes");
    return data.routes;
  } catch {
    return [];
  }
}

// ── Scenarios (CPS / NZS / Lab) ──────────────────────────────────────────────

export async function fetchScenarios(sector: SectorConfig): Promise<string[]> {
  try {
    const data = await apiFetch<{ scenarios: string[] }>(sector.apiBase, "/api/scenarios");
    return data.scenarios;
  } catch {
    return ["CPS", "NZS"];
  }
}

// ── Response normalization ────────────────────────────────────────────────────
// v3 sector backends (cement/aluminium/textile/fertiliser) use verbose field names.
// Steel backend uses the canonical short names the frontend expects.
// This function maps verbose → canonical so all sectors are uniform.

function normalizeYearlyResult(yr: Record<string, unknown>): YearlyResult {
  // Derive total_production from production_by_route if the field is absent
  const prodByRoute = yr.production_by_route as Record<string, number> | undefined;
  const derivedTotal = prodByRoute
    ? Object.values(prodByRoute).reduce((a, b) => a + (b ?? 0), 0)
    : 0;
  return {
    ...yr,
    // Normalize: prefer canonical name, fall back to v3 verbose name, then sum routes
    total_production: (yr.total_production ?? yr.total_production_mt ?? derivedTotal) as number,
    co2_total:        (yr.co2_total        ?? yr.total_co2_mt            ?? 0) as number,
    co2_intensity:    (yr.co2_intensity    ?? yr.co2_intensity_tco2_per_t ?? 0) as number,
    investment_by_route: (yr.investment_by_route ?? yr.investment_by_route_usd_mn ?? {}) as Record<string, number>,
  } as YearlyResult;
}

function normalizeResult(result: RunResult): RunResult {
  if (!result.yearly_results) return result;
  const normalized: Record<number, YearlyResult> = {};
  for (const [yr, val] of Object.entries(result.yearly_results)) {
    normalized[Number(yr)] = normalizeYearlyResult(val as Record<string, unknown>);
  }
  return { ...result, yearly_results: normalized };
}

// ── Run optimization ──────────────────────────────────────────────────────────

export async function runScenario(
  sector: SectorConfig,
  scenario: string,
  overrides: Record<string, unknown> = {}
): Promise<RunResult> {
  try {
    // v3 backends expect { scenario, overrides: {} } — steel backend accepts flat spread too
    const body = { scenario, overrides };
    const result = await apiFetch<RunResult>(sector.apiBase, "/api/run", {
      method: "POST",
      body: JSON.stringify(body),
    });
    return normalizeResult(result);
  } catch (err) {
    return {
      status: "not_available",
      message: err instanceof Error ? err.message : "Backend unavailable",
    };
  }
}

// ── Lab (custom scenario) ─────────────────────────────────────────────────────

export async function runLab(
  sector: SectorConfig,
  payload: Record<string, unknown>
): Promise<RunResult> {
  try {
    let body: unknown;
    let labPath: string;

    if (sector.id === "steel") {
      // Steel backend: /api/lab/run with flat payload (existing convention)
      body = payload;
      labPath = "/api/lab/run";
    } else {
      // v3 sector backends: /api/lab with { scenario, overrides: { ...rest } }
      // RunRequest model: { scenario: str, overrides: Dict[str, Any] }
      const { scenario, ...overrides } = payload;
      body = { scenario: scenario ?? "CPS", overrides };
      labPath = "/api/lab";
    }

    const result = await apiFetch<RunResult>(sector.apiBase, labPath, {
      method: "POST",
      body: JSON.stringify(body),
    });
    return normalizeResult(result);
  } catch (err) {
    return {
      status: "not_available",
      message: err instanceof Error ? err.message : "Backend unavailable",
    };
  }
}
