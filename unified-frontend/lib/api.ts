/**
 * Generic sector API client.
 * Each sector's backend runs at a different port but exposes the same REST surface as steel.
 *
 * Optimizations vs original:
 *  1. localStorage result cache (6h TTL) — repeat visits are instant
 *  2. Stale-while-revalidate — returns cached data immediately, refreshes in background
 *  3. 60-second fetch timeout — never hangs the page indefinitely
 *  4. Faster retry: 1s → 2s → 4s with max 3 attempts (vs old 2s→4s→8s→16s × 5)
 *  5. Pre-warm helper — call on app mount to wake Railway backend early
 */

import { SectorConfig } from "./sectors";
import { buildCacheKey, buildLabCacheKey, cacheGet, cacheSet } from "./cache";
import { findStaticRunUrl, fetchStaticRun, STEEL_ANCHOR_2070, LabLookupParams } from "./static-lookup";

export interface RunResult {
  status: "ok" | "infeasible" | "not_available";
  message?: string;
  years?: number[];
  yearly_results?: Record<number, YearlyResult>;
  summary?: RunSummary;
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

// ── Base URL resolution ───────────────────────────────────────────────────────
// In production (non-localhost), call Railway directly to bypass Vercel's 10s proxy timeout.
// CORS is enabled on Railway (allow_origins=["*"]) so browser can call directly.

const RAILWAY_URL = "https://india-transition-lab-production.up.railway.app";

function resolveBase(apiBase: string): string {
  if (typeof window !== "undefined" && !window.location.hostname.includes("localhost")) {
    const sector = apiBase.replace(/^\/api\//, "");
    return `${RAILWAY_URL}/${sector}`;
  }
  return apiBase;
}

// ── Fetch with timeout ────────────────────────────────────────────────────────
// 60 seconds: generous enough for a cold Railway start, never hangs forever.

const FETCH_TIMEOUT_MS = 60_000;

async function timedFetch(url: string, init: RequestInit = {}): Promise<Response> {
  // Merge caller's signal with our timeout signal (whichever fires first)
  const timeoutSignal = AbortSignal.timeout(FETCH_TIMEOUT_MS);
  const callerSignal  = init.signal as AbortSignal | undefined;

  // Use AbortSignal.any if available (modern browsers), else just use timeout
  const signal =
    callerSignal && typeof AbortSignal.any === "function"
      ? AbortSignal.any([timeoutSignal, callerSignal])
      : timeoutSignal;

  return fetch(url, { ...init, signal });
}

// ── Core fetch wrapper ────────────────────────────────────────────────────────

async function apiFetch<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const resolvedBase = resolveBase(base);
  const res = await timedFetch(`${resolvedBase}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const err = await res.text().catch(() => res.statusText);
    throw new Error(`API ${path} — ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

// ── Retry helper ─────────────────────────────────────────────────────────────
// Faster than original: 1s → 2s → 4s (3 attempts total).
// Empirically: Railway wakes within 20-30s so attempt 1 (after 0s wait) or 2 (after 1s) succeeds.

async function apiFetchWithRetry<T>(
  base: string,
  path: string,
  init: RequestInit,
  maxAttempts = 3,
  baseDelayMs = 1000
): Promise<T> {
  let lastErr: unknown;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (attempt > 0) {
      await new Promise((r) => setTimeout(r, baseDelayMs * Math.pow(2, attempt - 1)));
    }
    try {
      const resolvedBase = resolveBase(base);
      const res = await timedFetch(`${resolvedBase}${path}`, {
        headers: { "Content-Type": "application/json" },
        ...init,
      });
      if (!res.ok) {
        const err = await res.text().catch(() => res.statusText);
        throw new Error(`API ${path} — ${res.status}: ${err}`);
      }
      const data = (await res.json()) as T;
      const d = data as Record<string, unknown>;
      if (d?.status === "error" && typeof d?.message === "string" && d.message.includes("busy")) {
        lastErr = new Error(d.message as string);
        continue;
      }
      return data;
    } catch (err) {
      lastErr = err;
      if (err instanceof Error && err.message.includes("422")) throw err;
    }
  }
  throw lastErr;
}

// ── Health check ─────────────────────────────────────────────────────────────

export async function checkHealth(sector: SectorConfig): Promise<boolean> {
  try {
    const base = resolveBase(sector.apiBase);
    const res = await timedFetch(`${base}/health`, { signal: AbortSignal.timeout(5000) });
    return res.ok;
  } catch {
    return false;
  }
}

// ── Demand trajectories ───────────────────────────────────────────────────────

export async function fetchDemandTrajectories(
  sector: SectorConfig
): Promise<DemandTrajectoriesResponse | null> {
  try {
    return await apiFetch<DemandTrajectoriesResponse>(sector.apiBase, "/api/demand-trajectories");
  } catch {
    return null;
  }
}

// ── Route details ─────────────────────────────────────────────────────────────

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

// ── Scenarios ─────────────────────────────────────────────────────────────────

export async function fetchScenarios(sector: SectorConfig): Promise<string[]> {
  try {
    const data = await apiFetch<{ scenarios: string[] }>(sector.apiBase, "/api/scenarios");
    return data.scenarios;
  } catch {
    return ["CPS", "NZS"];
  }
}

// ── Response normalization ────────────────────────────────────────────────────

function normalizeYearlyResult(yr: Record<string, unknown>): YearlyResult {
  const prodByRoute = yr.production_by_route as Record<string, number> | undefined;
  const derivedTotal = prodByRoute
    ? Object.values(prodByRoute).reduce((a, b) => a + (b ?? 0), 0)
    : 0;
  return {
    ...yr,
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

// ── Run optimization — static-first → cache → backend ────────────────────────
//
// Fetch order:
//  1. Static pre-baked file (Vercel CDN edge, ~20ms)  → background backend refresh
//  2. localStorage cache   (instant, zero-network)    → background refresh
//  3. Railway backend      (5-30s cold start)

export async function runScenario(
  sector: SectorConfig,
  scenario: string,
  overrides: Record<string, unknown> = {}
): Promise<RunResult> {
  const cKey = buildCacheKey(sector.id, scenario, overrides);

  // ── 1. Static pre-baked file (canonical & demand-model variants) ──────────
  const staticUrl = _canonicalStaticUrl(sector.id, scenario, overrides);
  if (staticUrl) {
    const staticData = await fetchStaticRun(staticUrl);
    if (staticData) {
      const staticResult = normalizeResult(staticData as RunResult);
      // Save to cache + background refresh for freshness
      if (cKey && staticResult.status === "ok") cacheSet(cKey, staticResult);
      _freshRun(sector, scenario, overrides, cKey).catch(() => {});
      return staticResult;
    }
  }

  // ── 2. localStorage cache hit ─────────────────────────────────────────────
  if (cKey) {
    const cached = cacheGet<RunResult>(cKey);
    if (cached) {
      _freshRun(sector, scenario, overrides, cKey).catch(() => {});
      return cached;
    }
  }

  // ── 3. Fresh backend run ──────────────────────────────────────────────────
  return _freshRun(sector, scenario, overrides, cKey);
}

/** Map runScenario overrides to a static file URL (canonical 40 runs). */
function _canonicalStaticUrl(
  sectorId: string,
  scenario: string,
  overrides: Record<string, unknown>
): string | null {
  const keys = Object.keys(overrides);
  const base = `/static-runs/${sectorId}_${scenario}`;

  // No overrides → default demand (niti)
  if (keys.length === 0) {
    return `${base}_niti.json`;
  }

  // v3 backends: { demand_model: "niti" | ... }
  if (keys.length === 1 && keys[0] === "demand_model" && typeof overrides.demand_model === "string") {
    return `${base}_${overrides.demand_model}.json`;
  }

  // Steel: { demand_anchors: { 2024: x, 2070: y, ... } }
  if (keys.length === 1 && keys[0] === "demand_anchors") {
    const anchors = overrides.demand_anchors as Record<string, number>;
    const anchor2070 = anchors["2070"];
    const demandKey = STEEL_ANCHOR_2070[anchor2070] ?? null;
    if (demandKey) return `${base}_${demandKey}.json`;
  }

  return null;
}

async function _freshRun(
  sector: SectorConfig,
  scenario: string,
  overrides: Record<string, unknown>,
  cKey: string | null
): Promise<RunResult> {
  try {
    const body   = { scenario, overrides };
    const result = await apiFetchWithRetry<RunResult>(sector.apiBase, "/api/run", {
      method: "POST",
      body: JSON.stringify(body),
    });
    const normalized = normalizeResult(result);
    if (cKey && normalized.status === "ok") {
      cacheSet(cKey, normalized); // save to cache on success
    }
    return normalized;
  } catch (err) {
    return {
      status: "not_available",
      message: err instanceof Error ? err.message : "Backend unavailable",
    };
  }
}

// ── Pre-warm: call from app layout to wake Railway before user navigates ──────
// Fires both CPS and NZS for a given sector silently in the background.
// If Railway is cold, this shaves 20-30s off the first real user interaction.

export function prefetchScenarios(sector: SectorConfig): void {
  for (const scenario of ["CPS", "NZS"]) {
    runScenario(sector, scenario).catch(() => { /* background — ignore errors */ });
  }
}

// ── Warm ALL sector backends at once ─────────────────────────────────────────
// Call from the root layout (client component) so the first page load
// simultaneously wakes all 5 Railway backends.

export function warmAllBackends(sectors: SectorConfig[]): void {
  for (const sector of sectors) {
    // Health ping first (cheap — wakes the backend without waiting for a full solve)
    checkHealth(sector).catch(() => { /* ignore */ });
  }
}

// ── Lab (custom scenario) ─────────────────────────────────────────────────────
//
// Fetch order:
//  1. localStorage exact cache (instant — zero network)
//  2. Static pre-baked file    (instant — CDN/Vercel edge)  → background backend refresh
//  3. Railway backend          (5-30s, result saved to cache for next time)

export async function runLab(
  sector: SectorConfig,
  payload: Record<string, unknown>
): Promise<RunResult> {
  // ── Build cache key for exact payload ─────────────────────────────────────
  const cKey = buildLabCacheKey(sector.id, payload);

  // ── 1. Exact localStorage cache hit ───────────────────────────────────────
  if (cKey) {
    const cached = cacheGet<RunResult>(cKey);
    if (cached) {
      // Background refresh (fire-and-forget)
      _freshLabRun(sector, payload, cKey).catch(() => {});
      return cached;
    }
  }

  // ── 2. Static pre-baked file (nearest quantised level) ────────────────────
  const staticUrl = _extractStaticUrl(sector.id, payload);
  if (staticUrl) {
    const staticData = await fetchStaticRun(staticUrl);
    if (staticData) {
      const staticResult = normalizeResult(staticData as RunResult);
      // Background: fetch exact result from backend and save to localStorage
      _freshLabRun(sector, payload, cKey).catch(() => {});
      return staticResult;
    }
  }

  // ── 3. Fresh backend run ───────────────────────────────────────────────────
  return _freshLabRun(sector, payload, cKey);
}

async function _freshLabRun(
  sector: SectorConfig,
  payload: Record<string, unknown>,
  cKey: string | null
): Promise<RunResult> {
  try {
    let body: unknown;
    let labPath: string;

    if (sector.id === "steel") {
      body = payload;
      labPath = "/api/lab/run";
    } else {
      const { scenario, ...overrides } = payload;
      body = { scenario: scenario ?? "CPS", overrides };
      labPath = "/api/lab";
    }

    const result = await apiFetchWithRetry<RunResult>(sector.apiBase, labPath, {
      method: "POST",
      body: JSON.stringify(body),
    });
    const normalized = normalizeResult(result);
    if (cKey && normalized.status === "ok") {
      cacheSet(cKey, normalized);
    }
    return normalized;
  } catch (err) {
    return {
      status: "not_available",
      message: err instanceof Error ? err.message : "Backend unavailable",
    };
  }
}

/** Extract LabLookupParams from raw Lab payload and call findStaticRunUrl. */
function _extractStaticUrl(sectorId: string, payload: Record<string, unknown>): string | null {
  try {
    let params: LabLookupParams;

    if (sectorId === "steel") {
      const rp = (payload.resource_prices ?? {}) as Record<string, unknown>;
      params = {
        sectorId,
        scenario:     (payload.scenario as string) ?? "LAB",
        demandAnchors: payload.demand_anchors as Record<string, number>,
        carbonPrice:  (payload.carbon_price as Record<string, number>) ?? {},
        h2Cost:       (payload.h2_cost as Record<string, number>) ?? {},
        greenPremium: (payload.green_premium as number) ?? 0,
        waccDecimal:  (payload.wacc as number) ?? 0.10,
        gridEI2070:   (payload.grid_ei_2070 as number) ?? 0,
        ironOre:      typeof rp.iron_ore       === "number" ? rp.iron_ore       : undefined,
        natGas:       typeof rp.natural_gas    === "number" ? rp.natural_gas    : undefined,
        cokingCoal:   typeof rp.coking_coal    === "number" ? rp.coking_coal    : undefined,
      };
    } else {
      const ov = (payload.overrides ?? {}) as Record<string, unknown>;
      // Reconstruct coal absolute from delta adjustment
      const coalDelta = (ov.coal_price_adj as number | undefined);
      const coalBase  = sectorId === "fertiliser" ? 70 : 90;
      params = {
        sectorId,
        scenario:     (payload.scenario as string) ?? "CPS",
        demandModel:  (ov.demand_model as string) ?? "niti",
        carbonPrice:  (ov.carbon_price as Record<string, number>) ?? {},
        h2Cost:       (ov.h2_cost as Record<string, number>) ?? {},
        greenPremium: (ov.green_premium as number) ?? 0,
        waccDecimal:  (ov.wacc as number) ?? 0.10,
        gridEI2070:   (ov.grid_ei_2070 as number) ?? 0,
        coalAbs:      coalDelta !== undefined ? coalBase + coalDelta : undefined,
      };
    }

    return findStaticRunUrl(params);
  } catch {
    return null; // never crash the Lab on lookup failure
  }
}
