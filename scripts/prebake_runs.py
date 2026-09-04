"""
prebake_runs.py — pre-compute LP runs and save as static JSON.

Generates ~6,200 runs covering:
  • 40  canonical        (5 sectors × 2 scenarios × 4 demand)
  • ~2,200 single sweeps (8 key params × 8-10 levels, sector-appropriate)
  • ~3,900 2D grids      (carbon×H2, carbon×WACC, carbon×GreenPremium)

Output: unified-frontend/public/static-runs/{filename}.json
         unified-frontend/public/static-runs/manifest.json   ← lookup index

Run once per model-param change:
    pip install httpx
    python scripts/prebake_runs.py

Commit the output files — frontend serves them as static assets.

FILE NAMING (MUST match lib/static-lookup.ts exactly):
  Canonical:    {sector}_{scen}_{demand}.json
  Single sweep: {sector}_{scen}_{demand}_{sweepKey}{levelIdx}.json
  2D sweep:     {sector}_{scen}_{demand}_{key1}{i}_{key2}{j}.json

  Sweep key abbreviations:
    cs   = carbon_scale   h2a  = h2_cost_2030   h2b  = h2_cost_2050
    wacc = wacc           gp   = green_premium   ei   = grid_ei_2070
    io   = iron_ore       ng   = nat_gas         cc   = coking_coal
    co   = coal
"""

import asyncio
import json
import time
from itertools import product
from pathlib import Path

import httpx  # pip install httpx

import os
RAILWAY = os.environ.get("BACKEND_URL", "https://india-transition-lab-production.up.railway.app")
OUT_DIR = Path(__file__).resolve().parents[1] / "unified-frontend" / "public" / "static-runs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SCENARIOS = ["CPS", "NZS"]
DEMAND_KEYS = ["niti", "model_fitted", "india_policy", "international"]

# ── Carbon price bases per scenario ──────────────────────────────────────────
CARBON_BASE: dict[str, dict[str, float]] = {
    "CPS": {"2024": 5.0, "2030": 15.0,  "2050": 65.0,  "2070": 110.0},
    "NZS": {"2024": 5.0, "2030": 30.0,  "2050": 120.0, "2070": 185.0},
}

# ── Steel demand anchors (Mt) ─────────────────────────────────────────────────
STEEL_ANCHORS: dict[str, dict[str, float]] = {
    "niti":          {"2024": 144.29, "2050": 624.0,  "2070": 821.0},
    "model_fitted":  {"2024": 144.8,  "2030": 193.1,  "2035": 241.5, "2040": 297.0,
                      "2050": 423.5,  "2060": 554.2,  "2070": 668.6},
    "india_policy":  {"2024": 144.0,  "2030": 222.0,  "2035": 280.0, "2040": 332.0,
                      "2050": 458.0,  "2060": 524.0,  "2070": 580.0},
    "international": {"2024": 144.0,  "2030": 196.0,  "2035": 246.0, "2040": 296.0,
                      "2050": 392.0,  "2060": 455.0,  "2070": 496.0},
}

# ── Sector registry ───────────────────────────────────────────────────────────
# (path_prefix, is_steel, has_h2, lab_endpoint)
SECTORS: dict[str, tuple[str, bool, bool, str]] = {
    "steel":      ("steel",      True,  True,  "/api/lab/run"),
    "cement":     ("cement",     False, False, "/api/lab"),
    "aluminium":  ("aluminium",  False, False, "/api/lab"),
    "textile":    ("textile",    False, False, "/api/lab"),
    "fertiliser": ("fertiliser", False, True,  "/api/lab"),
}

# ── Default Lab toggles per sector ───────────────────────────────────────────
DEFAULT_TOGGLES: dict[str, dict[str, bool]] = {
    "steel":      {"use_dynamic_scrap": True, "use_endogenous_learning": True,
                   "ccus": False, "use_deployment_dynamics": False},
    "cement":     {"pli_active": True, "lc3_active": True, "alt_fuel_active": True, "ccus_active": False},
    "aluminium":  {"pli_active": True, "inert_anode_active": True},
    "textile":    {"pli_active": True, "gas_active": True, "biomass_active": True, "circular_active": True},
    "fertiliser": {"pli_active": True, "ccus_active": True, "bio_ammonia_active": True, "ng_smr_active": True},
}

# ── Default CAPEX multipliers per sector ─────────────────────────────────────
DEFAULT_CAPEX: dict[str, dict[str, float]] = {
    "steel":      {"H2-DRI-EAF": 1.0, "NG-DRI-EAF": 1.0, "Scrap-EAF": 1.0},
    "cement":     {"CCUS-Blended": 1.0, "Coal-LC3": 1.0, "AltFuel-Blended": 1.0},
    "aluminium":  {"RE-Primary": 1.0, "Inert-Anode": 1.0, "Secondary-Al": 1.0},
    "textile":    {"RE-Electrified": 1.0, "Circular-Fibre": 1.0, "Biomass-Cogen": 1.0, "Green-H2-Steam": 1.0},
    "fertiliser": {"Green-H2": 1.0, "Biomass-Reform": 1.0, "NG-SMR-CCS": 1.0},
}

# ── Default supply caps per sector ────────────────────────────────────────────
DEFAULT_SUPPLY: dict[str, dict[str, float]] = {
    "cement":     {"alt_fuel_cap": 0.80},
    "aluminium":  {"secondary_cap_pct": 0.45},
    "textile":    {"biomass_cap": 0.50, "circular_cap": 0.40},
    "fertiliser": {"bio_cap": 0.35},
    "steel":      {},
}

# ── SWEEP LEVELS — MUST match lib/static-lookup.ts exactly ───────────────────
SWEEP_LEVELS: dict[str, list[float]] = {
    # Carbon price scale factors (applied to each scenario's 2030/2050/2070 base)
    "cs":   [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0],  # 10 levels
    # H2 cost $/kg at 2030
    "h2a":  [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],    # 10 levels (default idx=5 → 4.0)
    # H2 cost $/kg at 2050
    "h2b":  [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0],  # 10 levels (default idx=4 → 1.5)
    # WACC (decimal) — 6% to 25%
    "wacc": [0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.22, 0.25],  # 10 levels (default idx=2)
    # Green premium $/t
    "gp":   [0, 10, 25, 50, 75, 100, 150, 200, 300, 500],             # 10 levels (default idx=0)
    # Grid EI 2070 kgCO2/kWh (0 = scenario auto)
    "ei":   [0.02, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.40],        # 8 levels
    # Iron ore $/t (steel only, absolute)
    "io":   [40, 60, 80, 100, 120, 140, 160, 200],                    # 8 levels (default=80 → idx=2)
    # Nat gas $/MMBtu (steel only, absolute)
    "ng":   [2, 4, 6, 8, 10, 12, 15, 20],                             # 8 levels (default=6 → idx=2)
    # Coking coal $/t (steel only, absolute)
    "cc":   [80, 100, 120, 140, 160, 180, 200, 250],                  # 8 levels (default=140 → idx=3)
    # Coal $/t (cement/textile/fertiliser, absolute)
    "co":   [50, 70, 90, 110, 130, 150, 170, 200],                    # 8 levels (default≈90 → idx=2)
}

# ── Payload builders ──────────────────────────────────────────────────────────

def base_carbon(scenario: str, scale: float) -> dict[str, float]:
    b = CARBON_BASE[scenario]
    return {
        "2024": b["2024"],
        "2030": round(b["2030"] * scale, 2),
        "2050": round(b["2050"] * scale, 2),
        "2070": round(b["2070"] * scale, 2),
    }


def build_canonical_payload(sector: str, is_steel: bool, scenario: str, demand_key: str) -> dict:
    """Original /api/run payload for canonical 40 runs."""
    if is_steel:
        return {"scenario": scenario, "overrides": {"demand_anchors": STEEL_ANCHORS[demand_key]}}
    else:
        return {"scenario": scenario, "overrides": {"demand_model": demand_key}}


def build_lab_base(sector: str, is_steel: bool, scenario: str, demand_key: str) -> dict:
    """Fully-specified Lab payload at default param values."""
    carbon = base_carbon(scenario, 1.0)
    toggles = DEFAULT_TOGGLES.get(sector, {})
    capex   = DEFAULT_CAPEX.get(sector, {})
    supply  = DEFAULT_SUPPLY.get(sector, {})

    if is_steel:
        p: dict = {
            "scenario": "LAB",
            "carbon_price": carbon,
            "green_premium": 0,
            "wacc": 0.10,
            "demand_anchors": STEEL_ANCHORS[demand_key],
            "capex_by_route": capex,
            "h2_cost": {"2030": 4.0, "2050": 1.5, "2070": 1.0},
            "resource_prices": {
                "h2": {"2030": 4.0, "2050": 1.5, "2070": 1.0},
                "iron_ore": 80,
                "natural_gas": 6,
                "coking_coal": 140,
                "non_coking_coal": 70,
            },
            **toggles,
        }
        return p
    else:
        overrides: dict = {
            "demand_model": demand_key,
            "carbon_price": carbon,
            "green_premium": 0,
            "wacc": 0.10,
            "capex_by_route": capex,
            **supply,
            **toggles,
        }
        if sector in ("fertiliser",):
            overrides["h2_cost"] = {"2030": 4.0, "2050": 1.5, "2070": 1.0}
        return {"scenario": scenario, "overrides": overrides}


def apply_sweep(payload: dict, sector: str, is_steel: bool, scenario: str, sweep_key: str, level: float) -> dict:
    """Return a deep-ish copy of payload with one sweep param overridden."""
    import copy
    p = copy.deepcopy(payload)

    def ov(d: dict, key: str, val) -> None:  # mutate nested overrides
        if is_steel:
            d[key] = val
        else:
            d["overrides"][key] = val

    if sweep_key == "cs":
        carbon = base_carbon(scenario, level)
        if is_steel:
            p["carbon_price"] = carbon
        else:
            p["overrides"]["carbon_price"] = carbon

    elif sweep_key == "h2a":
        h2 = {"2030": level, "2050": 1.5, "2070": 1.0}
        if is_steel:
            p["h2_cost"] = h2
            p["resource_prices"]["h2"] = h2
            p["resource_prices"]["h2"]["2030"] = level
        else:
            p["overrides"]["h2_cost"] = h2

    elif sweep_key == "h2b":
        if is_steel:
            p["h2_cost"]["2050"] = level
            p["resource_prices"]["h2"]["2050"] = level
        else:
            ov_h2 = p.get("overrides", {}).get("h2_cost", {"2030": 4.0, "2050": 1.5, "2070": 1.0})
            ov_h2["2050"] = level
            if is_steel:
                p["h2_cost"] = ov_h2
            else:
                p["overrides"]["h2_cost"] = ov_h2

    elif sweep_key == "wacc":
        if is_steel:
            p["wacc"] = level
        else:
            p["overrides"]["wacc"] = level

    elif sweep_key == "gp":
        if is_steel:
            p["green_premium"] = level
        else:
            p["overrides"]["green_premium"] = level

    elif sweep_key == "ei":
        if is_steel:
            p["grid_ei_2070"] = level
        else:
            p["overrides"]["grid_ei_2070"] = level

    elif sweep_key == "io" and is_steel:
        p["resource_prices"]["iron_ore"] = level

    elif sweep_key == "ng" and is_steel:
        p["resource_prices"]["natural_gas"] = level

    elif sweep_key == "cc" and is_steel:
        p["resource_prices"]["coking_coal"] = level

    elif sweep_key == "co" and not is_steel:
        # sector-specific coal key
        if sector == "cement":
            p["overrides"]["coal_price_adj"] = level - 90
        elif sector == "textile":
            p["overrides"]["coal_price_adj"] = level - 90
        elif sector == "fertiliser":
            p["overrides"]["coal_price_adj"] = level - 70

    return p


# ── Response trimming ─────────────────────────────────────────────────────────

KEEP_PER_YEAR = {"production_by_route", "co2_intensity", "co2_total",
                 "total_production", "total_cost",
                 # Aliases used by some backends
                 "co2_intensity_tco2_per_t", "total_co2_mt", "total_production_mt"}

def trim_result(data: dict) -> dict:
    """Strip everything not needed by UI charts. Reduces ~100KB → ~8KB per run."""
    if data.get("status") not in ("ok", None):
        return data

    trimmed: dict = {
        "status": data.get("status", "ok"),
        "years":   data.get("years", []),
        "summary": data.get("summary", {}),
    }

    # yearly_results or annual_results — keep only UI-needed fields
    yr_raw: dict = data.get("yearly_results") or data.get("annual_results") or {}
    yr_out: dict = {}
    for year, vals in yr_raw.items():
        if not isinstance(vals, dict):
            continue
        yr_out[year] = {k: vals[k] for k in KEEP_PER_YEAR if k in vals}
    trimmed["yearly_results"] = yr_out

    return trimmed


# ── Async fetch ───────────────────────────────────────────────────────────────

async def fetch_run(
    client: httpx.AsyncClient,
    label: str,
    url: str,
    payload: dict,
    out_path: Path,
) -> tuple[str, bool, str]:
    """Returns (label, success, error_msg)."""
    if out_path.exists():
        return label, True, "cached"

    for attempt in range(4):
        if attempt > 0:
            wait = 2 ** attempt
            await asyncio.sleep(wait)
        try:
            resp = await client.post(url, json=payload, timeout=180.0)
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") not in ("ok", "optimal", "OPTIMAL", None, "infeasible"):
                err = data.get("message", "non-ok status")
                if attempt < 3:
                    continue
                return label, False, err

            trimmed = trim_result(data)
            out_path.write_text(json.dumps(trimmed, separators=(",", ":")), encoding="utf-8")
            return label, True, ""

        except Exception as exc:
            if attempt == 3:
                return label, False, str(exc)

    return label, False, "exhausted retries"


# ── Run plan builder ──────────────────────────────────────────────────────────

def build_run_plan() -> list[tuple[str, str, dict, Path]]:
    """
    Returns list of (label, url, payload, out_path) for every run to bake.
    Skips combinations that don't make sense (e.g., iron-ore sweep on cement).
    """
    plan: list[tuple[str, str, dict, Path]] = []

    for sector, (prefix, is_steel, has_h2, lab_ep) in SECTORS.items():
        canonical_ep = "/api/run"
        lab_url      = f"{RAILWAY}/{prefix}{lab_ep}"
        canon_url    = f"{RAILWAY}/{prefix}{canonical_ep}"

        for scenario in SCENARIOS:
            for demand_key in DEMAND_KEYS:
                base_fname = f"{sector}_{scenario}_{demand_key}"

                # ── 1. Canonical run ──────────────────────────────────────────
                canon_payload = build_canonical_payload(sector, is_steel, scenario, demand_key)
                plan.append((
                    f"{sector}/{scenario}/{demand_key}",
                    canon_url,
                    canon_payload,
                    OUT_DIR / f"{base_fname}.json",
                ))

                # ── 2. Single-dimension Lab sweeps ────────────────────────────
                lab_base = build_lab_base(sector, is_steel, scenario, demand_key)

                # Params available for all sectors
                universal_sweeps = ["cs", "wacc", "gp", "ei"]

                # H2 only for steel + fertiliser
                h2_sweeps = ["h2a", "h2b"] if has_h2 else []

                # Steel-only resource prices
                steel_sweeps = ["io", "ng", "cc"] if is_steel else []

                # Non-steel coal
                coal_sweep = ["co"] if (not is_steel and sector in ("cement", "textile", "fertiliser")) else []

                all_sweeps = universal_sweeps + h2_sweeps + steel_sweeps + coal_sweep

                for sw_key in all_sweeps:
                    levels = SWEEP_LEVELS[sw_key]
                    for idx, level in enumerate(levels):
                        p = apply_sweep(lab_base, sector, is_steel, scenario, sw_key, level)
                        fname = f"{base_fname}_{sw_key}{idx}.json"
                        plan.append((
                            f"{sector}/{scenario}/{demand_key}/{sw_key}={level}",
                            lab_url,
                            p,
                            OUT_DIR / fname,
                        ))

                # ── 3. 2D grids ───────────────────────────────────────────────

                # 3a. Carbon × H2 (steel + fertiliser, 8×8 first 8 of each)
                if has_h2:
                    cs_levels  = SWEEP_LEVELS["cs"][:8]
                    h2a_levels = SWEEP_LEVELS["h2a"][:8]
                    for ci, cs_val in enumerate(cs_levels):
                        for hi, h2_val in enumerate(h2a_levels):
                            p = apply_sweep(lab_base, sector, is_steel, scenario, "cs", cs_val)
                            p = apply_sweep(p, sector, is_steel, scenario, "h2a", h2_val)
                            fname = f"{base_fname}_cs{ci}_h2a{hi}.json"
                            plan.append((
                                f"{sector}/{scenario}/{demand_key}/cs={cs_val}×h2a={h2_val}",
                                lab_url,
                                p,
                                OUT_DIR / fname,
                            ))

                # 3b. Carbon × WACC (all sectors, 6×6)
                cs_6   = SWEEP_LEVELS["cs"][:6]
                wacc_6 = SWEEP_LEVELS["wacc"][:6]
                for ci, cs_val in enumerate(cs_6):
                    for wi, wacc_val in enumerate(wacc_6):
                        p = apply_sweep(lab_base, sector, is_steel, scenario, "cs", cs_val)
                        p = apply_sweep(p, sector, is_steel, scenario, "wacc", wacc_val)
                        fname = f"{base_fname}_cs{ci}_wacc{wi}.json"
                        plan.append((
                            f"{sector}/{scenario}/{demand_key}/cs={cs_val}×wacc={wacc_val}",
                            lab_url,
                            p,
                            OUT_DIR / fname,
                        ))

                # 3c. Carbon × Green Premium (all sectors, 6×6)
                gp_6 = SWEEP_LEVELS["gp"][:6]
                for ci, cs_val in enumerate(cs_6):
                    for gi, gp_val in enumerate(gp_6):
                        p = apply_sweep(lab_base, sector, is_steel, scenario, "cs", cs_val)
                        p = apply_sweep(p, sector, is_steel, scenario, "gp", gp_val)
                        fname = f"{base_fname}_cs{ci}_gp{gi}.json"
                        plan.append((
                            f"{sector}/{scenario}/{demand_key}/cs={cs_val}×gp={gp_val}",
                            lab_url,
                            p,
                            OUT_DIR / fname,
                        ))

    return plan


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    plan = build_run_plan()

    # Deduplicate by output path (safety)
    seen: set[Path] = set()
    deduped = []
    for item in plan:
        if item[3] not in seen:
            seen.add(item[3])
            deduped.append(item)
    plan = deduped

    # Count already-done
    already = sum(1 for *_, p in plan if p.exists())
    todo = len(plan) - already

    print(f"Pre-baking {len(plan)} runs against {RAILWAY}")
    print(f"  {already} already cached — {todo} to fetch\n")

    if todo == 0:
        print("All runs already baked. Nothing to do.")
        _write_manifest(plan)
        return

    t0 = time.time()
    ok_count = already
    fail_count = 0

    # Batch into groups of 20 concurrent requests (Railway rate limit)
    BATCH = 20
    pending = [(lbl, url, payload, path) for lbl, url, payload, path in plan if not path.exists()]

    for batch_start in range(0, len(pending), BATCH):
        batch = pending[batch_start:batch_start + BATCH]
        async with httpx.AsyncClient() as client:
            tasks = [
                fetch_run(client, lbl, url, payload, path)
                for lbl, url, payload, path in batch
            ]
            results = await asyncio.gather(*tasks)

        for label, success, err in results:
            if success:
                ok_count += 1
                if err != "cached":
                    size_kb = 0
                    # find the path
                    for lbl2, _, _, p2 in batch:
                        if lbl2 == label and p2.exists():
                            size_kb = p2.stat().st_size / 1024
                    print(f"  OK  {label}  ({size_kb:.0f}KB)")
            else:
                fail_count += 1
                print(f"  FAIL  {label}  -- {err}")

        done = batch_start + len(batch)
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 1
        eta = (len(pending) - done) / rate if rate > 0 else 0
        print(f"  [{done}/{len(pending)} fetched | ETA {eta/60:.1f} min]")

    _write_manifest(plan)

    elapsed = time.time() - t0
    total_size_mb = sum(p.stat().st_size for *_, p in plan if p.exists()) / (1024 * 1024)
    print(f"\nDone in {elapsed:.0f}s — {ok_count} saved, {fail_count} failed")
    print(f"Total static-runs size: {total_size_mb:.1f} MB")
    print(f"Output: {OUT_DIR}")
    if fail_count:
        print("\nFailed runs -> frontend falls back to live Railway backend.")


def _write_manifest(plan: list[tuple[str, str, dict, Path]]) -> None:
    """Write a manifest.json listing all available static files."""
    manifest = [p.name for _, _, _, p in plan if p.exists()]
    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nDone: manifest.json written ({len(manifest)} files)")


if __name__ == "__main__":
    asyncio.run(main())
