/**
 * Client-side localStorage cache for LP run results.
 *
 * LP solves are deterministic: same inputs → same outputs every time.
 * Caching for 6 hours means repeat visits / sector switches are instant.
 *
 * Cache key format:  itl_run_{sector}_{scenario}_{demandVariant}_v4
 * TTL:               6 hours
 * On localStorage full / disabled: silent no-op (page still works, just slower)
 */

const CACHE_VERSION = "v4";
const TTL_MS = 6 * 60 * 60 * 1000; // 6 hours

interface CacheEntry<T> {
  ts: number;
  data: T;
}

export function cacheGet<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(`itl_${key}_${CACHE_VERSION}`);
    if (!raw) return null;
    const entry: CacheEntry<T> = JSON.parse(raw);
    if (Date.now() - entry.ts > TTL_MS) {
      localStorage.removeItem(`itl_${key}_${CACHE_VERSION}`);
      return null;
    }
    return entry.data;
  } catch {
    return null;
  }
}

export function cacheSet<T>(key: string, data: T): void {
  if (typeof window === "undefined") return;
  try {
    const entry: CacheEntry<T> = { ts: Date.now(), data };
    localStorage.setItem(`itl_${key}_${CACHE_VERSION}`, JSON.stringify(entry));
  } catch {
    // localStorage full or disabled — silent fail, page still works
  }
}

/** Evict all ITL cache entries (useful on manual refresh or version bump). */
export function cacheClear(): void {
  if (typeof window === "undefined") return;
  try {
    const toDelete: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith("itl_")) toDelete.push(k);
    }
    toDelete.forEach((k) => localStorage.removeItem(k));
  } catch { /* silent */ }
}

/**
 * Build a stable cache key from the LP run parameters.
 * Returns null for complex Lab overrides that should NOT be cached.
 */
export function buildCacheKey(
  sectorId: string,
  scenario: string,
  overrides: Record<string, unknown>
): string | null {
  const keys = Object.keys(overrides);

  // No overrides → canonical run
  if (keys.length === 0) {
    return `run_${sectorId}_${scenario}_default`;
  }

  // v3 backends: { demand_model: "niti" | "model_fitted" | ... }
  if (keys.length === 1 && keys[0] === "demand_model" && typeof overrides.demand_model === "string") {
    return `run_${sectorId}_${scenario}_dm_${overrides.demand_model}`;
  }

  // Steel backend: { demand_anchors: { 2024: x, 2030: y, ... } }
  if (keys.length === 1 && keys[0] === "demand_anchors" && overrides.demand_anchors) {
    const hash = simpleHash(JSON.stringify(overrides.demand_anchors));
    return `run_${sectorId}_${scenario}_da_${hash}`;
  }

  // Complex Lab override — do not cache
  return null;
}

function simpleHash(str: string): string {
  let h = 5381;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) + h) ^ str.charCodeAt(i);
  }
  return (h >>> 0).toString(16);
}
