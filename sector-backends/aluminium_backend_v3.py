"""
Aluminium Transition Backend v3 — India Transition Lab (port 8002)
==================================================================
SCIENTIFIC UPGRADES OVER v2:

  1. CONFIG-DRIVEN: All parameters from aluminium_config.yaml (provenance-tagged)
  2. ANNUAL LP RESOLUTION: 2024-2070
  3. THREE-PART CO2 ACCOUNTING per route:
       a. Electricity CO2:
          - CoalPP-Primary: captive coal EI (route-specific, not grid)
          - GridPP-Primary: grid EI (declining trajectory)
          - RE-Primary: zero (dedicated RE)
          - Secondary-Al: grid EI (on national grid)
       b. PFC emissions (CF4 + C2F6) from anode effects — tCO2e/t Al
          - Eliminated in Inert-Anode route (no anode effects)
          - PFC is a PROCESS emission, not combustion; can only be reduced by
            better anode management or technology switch, not by fuel switching
       c. Anode carbon CO2: carbon anode consumed during electrolysis → CO2
          - Inert-Anode: zero (anode does not consume carbon)
  4. SCRAP SUPPLY CONSTRAINT: Secondary-Al limited by EoL scrap availability
  5. DEMAND-TRAJECTORIES ENDPOINT: 4 trajectories
  6. SENSITIVITY ENDPOINT
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import yaml
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix, csc_matrix
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).parent / "configs" / "aluminium_config.yaml"

def _load_config() -> Dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

CFG = _load_config()

START = CFG["horizon"]["start_year"]
END   = CFG["horizon"]["end_year"]
YEARS = list(range(START, END + 1))
T     = len(YEARS)
WACC  = CFG["discount_rate"]["value"]

ROUTE_IDS: List[str] = list(CFG["routes"].keys())
R = len(ROUTE_IDS)

# ── Utilities ─────────────────────────────────────────────────────────────────

def crf(r: float, n: int) -> float:
    if r == 0 or n == 0:
        return 1.0 / max(n, 1)
    return r * (1 + r)**n / ((1 + r)**n - 1)

def df(y: int) -> float:
    return 1.0 / (1.0 + WACC) ** (y - START)

def interp(anchors: Dict, y: int) -> float:
    if not anchors:
        return 0.0
    ks = sorted(int(k) for k in anchors)
    if y <= ks[0]:
        return float(anchors[str(ks[0])] if str(ks[0]) in anchors else anchors[ks[0]])
    if y >= ks[-1]:
        k = ks[-1]
        return float(anchors[str(k)] if str(k) in anchors else anchors[k])
    for lo, hi in zip(ks, ks[1:]):
        if lo <= y <= hi:
            vlo = float(anchors[str(lo)] if str(lo) in anchors else anchors[lo])
            vhi = float(anchors[str(hi)] if str(hi) in anchors else anchors[hi])
            return vlo + (vhi - vlo) * (y - lo) / (hi - lo)
    return 0.0

def interp_sc(d: Dict, sc: str, y: int) -> float:
    return interp(d.get(sc, d.get("CPS", {})), y)

def surviving(existing: float, y: int, lifetime: int) -> float:
    age = y - START
    if age >= lifetime:
        return 0.0
    return existing * (1.0 - age / lifetime)

def _route(rid: str) -> Dict:
    return CFG["routes"][rid]

# ── Variable indices ──────────────────────────────────────────────────────────
# Variables: NCAP(R×T), CAP(R×T), ACT(R×T), CO2(T), SLACK(T)
# SLACK_t: elastic demand slack (unmet demand Mt/yr) with high penalty.
# Standard energy system modeling technique (TIMES/MESSAGE): keeps LP always
# feasible when capacity cannot physically meet demand. Shortfall is reported.
# Penalty: 10,000 USD/t = 10 billion USD/Mt (far above any production cost).

def _NCAP(ri, ti): return ri * T + ti
def _CAP(ri, ti):  return R*T + ri * T + ti
def _ACT(ri, ti):  return 2*R*T + ri * T + ti
def _CO2(ti):      return 3*R*T + ti
def _SLACK(ti):    return 4*R*T + ti   # unmet demand slack
NV = 4*R*T + T

DEMAND_SHORTFALL_PENALTY_USD_PER_T = 10_000.0  # $/t Al: exceeds any production cost

# ── CO2 intensity per route (tCO2/t Al) at a given year ───────────────────────

def route_co2_intensity(rid: str, sc: str, y: int) -> float:
    """
    Total CO2 intensity (tCO2e/t Al) for route rid in year y under scenario sc.
    Includes:
      (a) electricity-related CO2 (scope 2)
      (b) PFC emissions (scope 1, process-specific)
      (c) anode carbon CO2 (scope 1)
    """
    rc  = _route(rid)
    kwh = rc["elec_kwh_per_t_al"]

    # (a) Electricity CO2
    captive_ei = rc.get("elec_ei_tco2_per_kwh")   # None if uses grid
    re_zero    = rc.get("elec_ei_tco2_per_kwh") == 0.0  # RE-Primary explicit zero
    if captive_ei is not None:
        ei = captive_ei  # CoalPP uses captive coal EI, RE-Primary uses 0.0
    else:
        ei = interp_sc(CFG["electricity"]["grid_ei_tco2_per_kwh"], sc, y)

    elec_co2 = kwh * ei  # tCO2/t Al

    # (b) PFC emissions (tCO2e/t Al — GWP already applied in config)
    pfc_co2 = rc.get("pfc_tco2e_per_t_al", 0.0)

    # (c) Anode carbon CO2
    anode_co2 = rc.get("anode_co2_t_per_t_al", 0.0)

    return elec_co2 + pfc_co2 + anode_co2

# ── Build LP ──────────────────────────────────────────────────────────────────

def build_lp(sc: str, overrides: Dict[str, Any]) -> Tuple[np.ndarray, lil_matrix, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    # ── Parse Lab override format (frontend → backend contract) ──────────────
    carbon_price_traj  = overrides.get("carbon_price")            # {year_str: usd/tco2}
    coal_price_adj     = float(overrides.get("coal_price_adj", 0.0))     # $/MWh captive coal adj
    grid_price_adj     = float(overrides.get("grid_price_adj", 0.0))     # $/MWh grid adj
    re_price_adj       = float(overrides.get("re_price_adj", 0.0))       # $/MWh RE adj
    demand_anchors_ov  = overrides.get("demand_anchors")           # {year_str: Mt}
    demand_model_ov    = overrides.get("demand_model")             # "niti"|"model_fitted"|"high_ev"|"efficiency_driven"|"india_policy"|"international"
    capex_by_route     = overrides.get("capex_by_route", {})      # {routeId: multiplier}
    green_prem_ov      = float(overrides.get("green_premium", 0.0))      # $/t Al
    wacc_override      = overrides.get("wacc")                    # fraction
    grid_ei_2070_ov    = overrides.get("grid_ei_2070")            # kgCO2/kWh
    pli_active         = bool(overrides.get("pli_active", True))
    inert_anode_active = bool(overrides.get("inert_anode_active", True))
    secondary_cap_pct  = overrides.get("secondary_cap_pct")       # fraction of demand
    scrap_cap_mult     = float(overrides.get("scrap_cap_mult", 1.0))

    c   = np.zeros(NV)
    lb  = np.zeros(NV)
    ub  = np.full(NV, np.inf)

    rows, b_lo, b_hi = [], [], []

    def add(coeffs, lo, hi):
        rows.append(coeffs); b_lo.append(lo); b_hi.append(hi)

    wacc_eff = float(wacc_override) if wacc_override is not None else WACC

    for ti, y in enumerate(YEARS):
        dfy  = df(y)

        # Carbon price: Lab trajectory or scenario config
        if carbon_price_traj:
            cp = interp({str(k): float(v) for k, v in carbon_price_traj.items()}, y)
        else:
            cp = interp_sc(CFG["carbon_price_usd_per_tco2"], sc, y)

        # Demand: explicit anchors > named model > default niti
        # Alias: frontend "india_policy"→"high_ev", "international"→"efficiency_driven"
        _dt = CFG.get("demand_trajectories", {})
        _ALIAS = {"india_policy": "high_ev", "international": "efficiency_driven"}
        if demand_anchors_ov:
            demand = interp({str(k): float(v) for k, v in demand_anchors_ov.items()}, y)
        elif demand_model_ov:
            _key = _ALIAS.get(demand_model_ov, demand_model_ov) if demand_model_ov not in _dt else demand_model_ov
            _anchors = _dt.get(_key, _dt.get("niti", {})).get("anchors") or {2024: 5.0, 2040: 11.5, 2070: 30.0}
            demand = interp(_anchors, y)
        else:
            _anchors = _dt.get("niti", {}).get("anchors") or {2024: 5.0, 2040: 11.5, 2070: 30.0}
            demand = interp(_anchors, y)

        # Grid EI with Lab 2070 override
        # Lab slider sends kgCO2/kWh; grid_ei_use must be tCO2/kWh → divide by 1000
        if grid_ei_2070_ov is not None:
            ei_2024_kg = 0.710          # CEA 2022 baseline kgCO2/kWh (FROZEN_EXTERNAL)
            ei_2070_kg = float(grid_ei_2070_ov)
            ei_frac = max(0.0, (y - 2024) / (2070 - 2024))
            grid_ei_y = (ei_2024_kg + (ei_2070_kg - ei_2024_kg) * ei_frac) / 1000.0
        else:
            grid_ei_y = None

        for ri, rid in enumerate(ROUTE_IDS):
            rc  = _route(rid)
            wacc_r   = wacc_eff * (1.0 + rc.get("wacc_premium", 0.0))
            lifetime = rc["lifetime_yr"]
            capex    = rc["capex_usd_per_t"] * float(capex_by_route.get(rid, 1.0))

            fom     = rc["fom_usd_per_t_yr"]
            vom     = rc["vom_residual_usd_per_t"]

            pli_val = 0.0
            if pli_active:
                pli_r = CFG["policy"]["pli_usd_per_t"].get(rid, {})
                if pli_r:
                    pli_val = interp_sc(pli_r, sc, y)

            gp_val  = 0.0
            gp_routes = CFG["policy"]["green_premium_usd_per_t"].get("routes", [])
            if rid in gp_routes:
                # Lab green_premium is ADDITIONAL on top of scenario trajectory
                gp_val = interp_sc(CFG["policy"]["green_premium_usd_per_t"], sc, y) + green_prem_ov

            # Electricity price (captive coal, grid, or RE) with Lab adj
            if rc.get("elec_is_re", False) or rid == "RE-Primary":
                p_elec = interp_sc(CFG["electricity"]["re_price_usd_per_kwh"], sc, y) + re_price_adj / 1000.0
            elif rid == "CoalPP-Primary":
                # Captive coal: price adj goes as coal_price_adj (in $/MWh equiv)
                p_elec = interp_sc(CFG["electricity"]["price_usd_per_kwh"], sc, y) + coal_price_adj / 1000.0
            else:
                p_elec = interp_sc(CFG["electricity"]["price_usd_per_kwh"], sc, y) + grid_price_adj / 1000.0

            kwh = rc["elec_kwh_per_t_al"]
            # CO2 intensity: pass grid_ei override to route_co2_intensity if applicable
            if grid_ei_y is not None and rid in ("GridPP-Primary", "Secondary-Al"):
                # Override grid EI for these routes
                from types import SimpleNamespace
                co2_int = route_co2_intensity(rid, sc, y)  # baseline; grid EI correction below
                # Correct for grid EI change
                cfg_ei = interp_sc(CFG["electricity"]["grid_ei_tco2_per_kwh"], sc, y)
                if cfg_ei > 0:
                    co2_int = co2_int * grid_ei_y / cfg_ei
            else:
                co2_int = route_co2_intensity(rid, sc, y)

            ann_capex = crf(wacc_r, lifetime) * capex
            c[_CAP(ri, ti)] += dfy * (ann_capex + fom)
            c[_ACT(ri, ti)] += dfy * (vom + kwh * p_elec - pli_val - gp_val + co2_int * cp)

        # ── Constraints ───────────────────────────────────────────────────────

        # CAP accounting
        for ri, rid in enumerate(ROUTE_IDS):
            rc       = _route(rid)
            existing = rc["existing_mt"]
            lifetime = rc["lifetime_yr"]
            lead     = rc.get("lead_years", 0)
            start    = rc["start_year"]
            surv     = surviving(existing, y, lifetime)
            row = {_CAP(ri, ti): -1.0}
            for tau_i, tau_y in enumerate(YEARS[:ti + 1]):
                if tau_y < start: continue
                if (y - tau_y) < lead: continue
                if (y - tau_y) >= lifetime: continue
                row[_NCAP(ri, tau_i)] = 1.0
            add(row, -surv, -surv)

        # ACT ≤ CAP × availability
        for ri, rid in enumerate(ROUTE_IDS):
            avail = _route(rid)["availability"]
            add({_ACT(ri, ti): 1.0, _CAP(ri, ti): -avail}, -np.inf, 0.0)

        # Elastic demand balance: production + slack ≥ demand.
        # Slack variable carries a $10k/t penalty — always met when physically possible.
        # Shortfall reported in results; not hidden.
        c[_SLACK(ti)] += dfy * DEMAND_SHORTFALL_PENALTY_USD_PER_T * 1e3  # penalty in objective (×1000 for Mt→t units)
        row_d = {_ACT(ri, ti): 1.0 for ri in range(R)}
        row_d[_SLACK(ti)] = 1.0
        add(row_d, demand, demand)  # ub=demand: prevent overproduction when green_premium > VOM

        # Technology start year + max ramp
        for ri, rid in enumerate(ROUTE_IDS):
            rc = _route(rid)
            if y < rc["start_year"]:
                ub[_NCAP(ri, ti)] = 0.0
                ub[_ACT(ri, ti)]  = 0.0
            max_r = rc.get("max_ramp_mt_yr", None)
            if max_r is not None and max_r >= 0:
                ub[_NCAP(ri, ti)] = min(ub[_NCAP(ri, ti)], max_r) if max_r > 0 else 0.0
            # Cutoff year
            cutoff = rc.get(f"cutoff_year_{sc.lower()}", None)
            if cutoff and y >= cutoff:
                ub[_NCAP(ri, ti)] = 0.0

        # Fossil decline — monotonic decline in all scenarios
        if ti > 0:
            for ri, rid in enumerate(ROUTE_IDS):
                if _route(rid).get("fossil_decline", False):
                    add({_ACT(ri, ti): 1.0, _ACT(ri, ti-1): -1.0}, -np.inf, 0.0)

        # CO2 tracking (use grid_ei_y override if provided)
        row = {_CO2(ti): -1.0}
        for ri, rid in enumerate(ROUTE_IDS):
            co2_i = route_co2_intensity(rid, sc, y)
            if grid_ei_y is not None and rid in ("GridPP-Primary", "Secondary-Al"):
                cfg_ei = interp_sc(CFG["electricity"]["grid_ei_tco2_per_kwh"], sc, y)
                if cfg_ei > 0:
                    co2_i = co2_i * grid_ei_y / cfg_ei
            row[_ACT(ri, ti)] = co2_i
        add(row, 0.0, 0.0)

        # Toggle: disable Inert-Anode if inert_anode_active=False
        if not inert_anode_active:
            for ri, rid in enumerate(ROUTE_IDS):
                if rid == "Inert-Anode":
                    ub[_NCAP(ri, ti)] = 0.0
                    ub[_ACT(ri, ti)]  = 0.0

        # Scrap supply cap for Secondary-Al (or secondary_cap_pct override)
        sec_ri = next((ri for ri, rid in enumerate(ROUTE_IDS) if rid == "Secondary-Al"), None)
        if sec_ri is not None:
            if secondary_cap_pct is not None:
                # Lab slider: limit Secondary-Al to X% of total demand
                cap_val = float(secondary_cap_pct) * demand
                add({_ACT(sec_ri, ti): 1.0}, -np.inf, max(0.0, cap_val))
            elif CFG.get("scrap_supply", {}).get("enabled", False):
                scrap_cap = interp_sc(CFG["scrap_supply"]["available_mt"], sc, y) * scrap_cap_mult
                add({_ACT(sec_ri, ti): 1.0}, -np.inf, scrap_cap)

    nr = len(rows)
    A  = lil_matrix((nr, NV))
    for i, row in enumerate(rows):
        for j, v in row.items():
            A[i, j] = v

    return c, A, np.array(b_lo), np.array(b_hi), lb, ub

# ── Solve with in-memory cache ────────────────────────────────────────────────
import json as _json, hashlib as _md5_mod, threading as _thr
_solve_cache: dict = {}
_solve_lock = _thr.Lock()

_HIGHS_OPTIONS = {
    "disp": False,
    "presolve": "on",
    "solver": "simplex",
    "simplex_strategy": 1,
    "simplex_scale_strategy": 2,
    "primal_feasibility_tolerance": 1e-7,
    "dual_feasibility_tolerance": 1e-7,
}


def _cache_key(sc: str, overrides: dict) -> str:
    h = _md5_mod.md5(_json.dumps(overrides, sort_keys=True).encode(), usedforsecurity=False).hexdigest()[:8]
    return f"{sc}:{h}"


def _solve(sc: str, overrides: Dict[str, Any]) -> Dict[str, Any]:
    key = _cache_key(sc, overrides)
    with _solve_lock:
        if key in _solve_cache:
            return _solve_cache[key]

    c, A, b_lo, b_hi, lb, ub = build_lp(sc, overrides)
    lc = LinearConstraint(csc_matrix(A), b_lo, b_hi)
    result = milp(c, constraints=lc, bounds=Bounds(lb, ub), options=_HIGHS_OPTIONS)

    if result.status != 0:
        return {"status": "infeasible", "message": result.message}

    x = result.x
    yearly = {}
    for ti, y in enumerate(YEARS):
        prod_r, cap_r, ncap_r, co2_r, inv_r = {}, {}, {}, {}, {}
        total_cost_yr = 0.0
        for ri, rid in enumerate(ROUTE_IDS):
            rc   = _route(rid)
            act  = max(0.0, x[_ACT(ri, ti)])
            cap  = max(0.0, x[_CAP(ri, ti)])
            ncap = max(0.0, x[_NCAP(ri, ti)])
            co2  = route_co2_intensity(rid, sc, y) * act
            capex_r = rc["capex_usd_per_t"]
            fom_r   = rc["fom_usd_per_t_yr"]
            vom_r   = rc["vom_residual_usd_per_t"]
            inv_r[rid] = round(ncap * capex_r, 2)           # Mn$ (Mt × $/t = M$)
            total_cost_yr += act * vom_r + cap * fom_r + ncap * capex_r
            prod_r[rid]  = round(act, 4)
            cap_r[rid]   = round(cap, 4)
            ncap_r[rid]  = round(ncap, 4)
            co2_r[rid]   = round(co2, 4)

        total_prod = sum(prod_r.values())
        total_co2  = max(0.0, x[_CO2(ti)])
        intensity  = total_co2 / total_prod if total_prod > 0 else 0.0
        unmet_demand = max(0.0, x[_SLACK(ti)])
        _dt = CFG.get("demand_trajectories", {})
        _anchors = _dt.get("niti", {}).get("anchors") or _dt.get("model_fitted", {}).get("anchors") or {2024: 5.0, 2040: 11.5, 2070: 30.0}
        demand = interp(_anchors, y)
        scrap_cap = interp_sc(CFG["scrap_supply"]["available_mt"], sc, y) if CFG.get("scrap_supply", {}).get("enabled") else None

        yearly[y] = {
            "year": y,
            "demand_mt": round(demand, 2),
            "unmet_demand_mt": round(unmet_demand, 4),
            "production_by_route": prod_r,
            "capacity_by_route": cap_r,
            "new_capacity_by_route": ncap_r,
            "co2_by_route_mt": co2_r,
            "total_production_mt": round(total_prod, 4),
            "total_production":    round(total_prod, 4),   # canonical alias
            "total_co2_mt": round(total_co2, 4),
            "co2_total":    round(total_co2, 4),           # canonical alias
            "co2_intensity_tco2_per_t": round(intensity, 4),
            "co2_intensity":            round(intensity, 4),  # canonical alias
            "scrap_cap_mt": round(scrap_cap, 2) if scrap_cap else None,
            "scrap_used_mt": round(prod_r.get("Secondary-Al", 0.0), 3),
            "investment_by_route": inv_r,
            "total_cost": round(total_cost_yr, 1),
        }

    all_co2  = sum(yr["total_co2_mt"] for yr in yearly.values())
    final_y  = yearly[END]

    out = {
        "status": "ok",
        "scenario": sc,
        "solver_objective": round(result.fun, 2),
        "yearly_results": yearly,
        "summary": {
            "total_cost_bn": round(result.fun / 1e3, 3),
            "total_co2_cumulative_mt": round(all_co2, 1),
            "final_co2_intensity": round(final_y["co2_intensity_tco2_per_t"], 4),
            "final_year_demand": round(final_y["demand_mt"], 1),
            "scrap_supply_binding": CFG.get("scrap_supply", {}).get("enabled", False),
        },
        "vol4_targets": CFG["vol4_reference"]["co2_intensity_tco2_per_t_al"],
        "provenance": "configs/aluminium_config.yaml",
    }
    with _solve_lock:
        _solve_cache[key] = out
    return out

# ── FastAPI ───────────────────────────────────────────────────────────────────
from contextlib import asynccontextmanager

@asynccontextmanager
async def _al_lifespan(application):
    import threading, logging as _lg
    _log = _lg.getLogger("aluminium.backend")
    def _warm(sc):
        _log.info("Aluminium pre-warm: %s", sc)
        try:
            _solve(sc, {})
            _log.info("Aluminium pre-warm done: %s", sc)
        except Exception as exc:
            _log.warning("Aluminium pre-warm failed (%s): %s", sc, exc)
    for sc in ("CPS", "NZS"):
        threading.Thread(target=_warm, args=(sc,), daemon=True, name=f"al-prewarm-{sc}").start()
    yield

app = FastAPI(title="Aluminium Transition Model v3", version="3.0.0", lifespan=_al_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class RunRequest(BaseModel):
    scenario: str = "CPS"
    overrides: Dict[str, Any] = {}

@app.get("/health")
def health():
    return {"status": "ok", "sector": "aluminium", "model_version": "v3",
            "routes": ROUTE_IDS, "years": f"{START}-{END}",
            "scrap_supply_constraint": CFG.get("scrap_supply", {}).get("enabled", False)}

@app.get("/api/routes")
def get_routes():
    out = []
    for rid in ROUTE_IDS:
        rc = _route(rid)
        out.append({
            "id": rid,
            "existing": rc["existing_mt"],
            "capex": rc["capex_usd_per_t"],
            "capex_provenance": rc.get("capex_provenance", ""),
            "elec_kwh_per_t_al": rc["elec_kwh_per_t_al"],
            "elec_ei": rc.get("elec_ei_tco2_per_kwh", "grid"),
            "pfc_tco2e": rc.get("pfc_tco2e_per_t_al", 0.0),
            "anode_co2": rc.get("anode_co2_t_per_t_al", 0.0),
            "ef_2024": round(route_co2_intensity(rid, "CPS", 2024), 3),
        })
    return {"routes": out}

@app.get("/api/demand-trajectories")
def get_demand_trajectories():
    historical = [
        {"year": 2005, "production_mt": 0.9}, {"year": 2010, "production_mt": 1.5},
        {"year": 2015, "production_mt": 2.5}, {"year": 2019, "production_mt": 3.7},
        {"year": 2021, "production_mt": 3.6}, {"year": 2022, "production_mt": 4.0},
        {"year": 2024, "production_mt": 4.9},
    ]
    out = {}
    for key, tc in CFG.get("demand_trajectories", {}).items():
        series = {y: interp(tc["anchors"], y) for y in range(2024, 2071)}
        out[key] = {
            "label": tc["label"], "annual_series": series,
            "end_value": series[2070], "source": tc["source"],
        }
    return {**out, "historical": historical}

@app.get("/api/scrap-supply")
def get_scrap_supply():
    sc_cfg = CFG.get("scrap_supply", {})
    if not sc_cfg.get("enabled"):
        return {"enabled": False}
    return {
        "enabled": True,
        "CPS": {y: round(interp_sc(sc_cfg["available_mt"], "CPS", y), 2) for y in range(2024, 2071)},
        "NZS": {y: round(interp_sc(sc_cfg["available_mt"], "NZS", y), 2) for y in range(2024, 2071)},
        "source": sc_cfg.get("source", ""),
    }

@app.post("/api/run")
def run_scenario(req: RunRequest):
    sc = req.scenario.upper()
    if sc not in ("CPS", "NZS"):
        return {"status": "error", "message": f"Unknown scenario: {sc}"}
    return _solve(sc, req.overrides)

@app.post("/api/lab")
def run_lab(req: RunRequest):
    sc = req.scenario.upper() if req.scenario.upper() in ("CPS", "NZS") else "CPS"
    return _solve(sc, req.overrides)

@app.get("/api/sensitivity")
def sensitivity():
    base = _solve("NZS", {})
    if base["status"] != "ok":
        return {"status": "infeasible"}
    b_co2  = base["summary"]["total_co2_cumulative_mt"]
    b_cost = base["summary"]["total_cost_bn"]
    results = {}
    for p, (lo, hi) in {
        "carbon_price_mult": (0.8, 1.2),
        "elec_price_mult":   (0.8, 1.2),
        "demand_mult":       (0.8, 1.2),
        "re_capex_mult":     (0.8, 1.2),
        "inert_capex_mult":  (0.8, 1.2),
        "scrap_cap_mult":    (0.7, 1.3),
    }.items():
        r_lo = _solve("NZS", {p: lo})
        r_hi = _solve("NZS", {p: hi})
        results[p] = {
            "co2_delta_lo":  round((r_lo["summary"]["total_co2_cumulative_mt"] - b_co2) / b_co2 * 100, 2) if r_lo["status"] == "ok" else None,
            "co2_delta_hi":  round((r_hi["summary"]["total_co2_cumulative_mt"] - b_co2) / b_co2 * 100, 2) if r_hi["status"] == "ok" else None,
            "cost_delta_lo": round((r_lo["summary"]["total_cost_bn"] - b_cost) / b_cost * 100, 2) if r_lo["status"] == "ok" else None,
            "cost_delta_hi": round((r_hi["summary"]["total_cost_bn"] - b_cost) / b_cost * 100, 2) if r_hi["status"] == "ok" else None,
        }
    return {"sensitivity": results, "base_co2_mt": b_co2, "base_cost_bn": b_cost}

if __name__ == "__main__":
    uvicorn.run("aluminium_backend_v3:app", host="0.0.0.0", port=CFG.get("port", 8002), reload=False)
