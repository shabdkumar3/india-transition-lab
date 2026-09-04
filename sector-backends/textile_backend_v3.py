"""
Textile Transition Backend v3 — India Transition Lab (port 8003)
===============================================================
SCIENTIFIC UPGRADES OVER v2:

  1. CONFIG-DRIVEN from textile_config.yaml (provenance-tagged)
  2. ANNUAL LP RESOLUTION: 2024-2070
  3. MULTI-FUEL CO2 ACCOUNTING:
       coal_co2  = coal_gj_per_t × ef_coal (94.2 kgCO2/GJ IPCC 2006)
       gas_co2   = gas_gj_per_t × ef_gas (56.1 kgCO2/GJ IPCC 2006)
       biomass   = 0 (biogenic carbon; lifecycle accounting)
       elec_co2  = elec_kwh_per_t × grid_ei
  4. BIOMASS SUPPLY CAP: limits Biomass-Cogen route
  5. RECYCLED FIBRE SUPPLY CAP: limits Circular-Fibre route
  6. PROCESS DISAGGREGATION: spinning + dyeing/finishing tracked as energy sub-components
     (reflected in route energy intensities per config)
  7. DEMAND TRAJECTORIES ENDPOINT
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import yaml
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix, csc_matrix
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

CONFIG_PATH = Path(__file__).parent / "configs" / "textile_config.yaml"

def _load() -> Dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

CFG = _load()

START = CFG["horizon"]["start_year"]
END   = CFG["horizon"]["end_year"]
YEARS = list(range(START, END + 1))
T     = len(YEARS)
WACC  = CFG["discount_rate"]["value"]

ROUTE_IDS: List[str] = list(CFG["routes"].keys())
R = len(ROUTE_IDS)

# Emission factors (FROZEN_EXTERNAL)
EF_COAL_T_CO2_PER_GJ = 0.0942   # tCO2/GJ bituminous (IPCC 2006 Table 1.4)
EF_GAS_T_CO2_PER_GJ  = 0.0561   # tCO2/GJ natural gas (IPCC 2006)

def crf(r, n):
    if r == 0 or n == 0: return 1.0/max(n,1)
    return r*(1+r)**n/((1+r)**n-1)

def df(y): return 1.0/(1.0+WACC)**(y-START)

def interp(anchors: Dict, y: int) -> float:
    if not anchors: return 0.0
    ks = sorted(int(k) for k in anchors)
    if y <= ks[0]: return float(anchors.get(str(ks[0]), anchors.get(ks[0], 0)))
    if y >= ks[-1]: k=ks[-1]; return float(anchors.get(str(k), anchors.get(k, 0)))
    for lo, hi in zip(ks, ks[1:]):
        if lo <= y <= hi:
            vlo = float(anchors.get(str(lo), anchors.get(lo, 0)))
            vhi = float(anchors.get(str(hi), anchors.get(hi, 0)))
            return vlo + (vhi-vlo)*(y-lo)/(hi-lo)
    return 0.0

def interp_sc(d: Dict, sc: str, y: int) -> float:
    return interp(d.get(sc, d.get("CPS", {})), y)

def surviving(existing, y, lifetime):
    age = y - START
    return 0.0 if age >= lifetime else existing*(1.0-age/lifetime)

def _route(rid): return CFG["routes"][rid]

def route_co2_intensity(rid: str, sc: str, y: int) -> float:
    """
    CO2 intensity (tCO2/t fibre) for route in year y.
    Coal/gas CO2 from fuel use + electricity scope 2 CO2.
    Biomass combustion CO2 = zero (biogenic lifecycle accounting).
    """
    rc      = _route(rid)
    grid_ei = interp_sc(CFG["electricity"]["grid_ei_tco2_per_kwh"], sc, y)
    kwh     = rc.get("elec_kwh_per_t", 2800)

    elec_co2 = kwh * grid_ei

    if rid == "Coal-Conventional":
        coal_gj = rc.get("coal_gj_per_t", 16.0)
        coal_co2 = coal_gj * EF_COAL_T_CO2_PER_GJ
        return coal_co2 + elec_co2

    elif rid == "Gas-Transition":
        gas_gj = rc.get("gas_gj_per_t", 14.5)
        gas_co2 = gas_gj * EF_GAS_T_CO2_PER_GJ
        return gas_co2 + elec_co2

    elif rid == "Biomass-Cogen":
        # biomass CO2 = 0 (biogenic); only electricity scope 2
        return elec_co2

    elif rid == "RE-Electrified":
        # Uses RE electricity; near-zero if RE powered
        # In the model we still track grid EI for the portion on grid
        # (simplified: assume 80% RE + 20% grid for RE-Electrified)
        re_frac = 0.80
        elec_co2_blended = kwh * (grid_ei * (1.0 - re_frac) + 0.0 * re_frac)
        return elec_co2_blended

    elif rid == "Green-H2-Steam":
        h2_kg  = rc.get("h2_kg_per_t", 280)
        # H2 combustion CO2 = zero (green H2 produced from RE water splitting)
        # Electricity still grid EI
        return elec_co2

    elif rid == "Circular-Fibre":
        return elec_co2  # electricity-dominated; no fossil fuel use

    return elec_co2

def _NCAP(ri, ti): return ri * T + ti
def _CAP(ri, ti):  return R*T + ri * T + ti
def _ACT(ri, ti):  return 2*R*T + ri * T + ti
def _CO2(ti):      return 3*R*T + ti
def _SLACK(ti):    return 4*R*T + ti   # unmet demand slack variable
NV = 4*R*T + T

DEMAND_SHORTFALL_PENALTY_USD_PER_T = 10_000.0  # $/t fibre: exceeds any production cost

def build_lp(sc: str, overrides: Dict[str, Any]):
    # ── Parse Lab override format (frontend → backend contract) ──────────────
    carbon_price_traj = overrides.get("carbon_price")           # {year_str: usd/tco2}
    coal_price_adj    = float(overrides.get("coal_price_adj", 0.0))   # $/t offset
    gas_price_adj     = float(overrides.get("gas_price_adj", 0.0))    # $/MMBtu offset
    biomass_price_adj = float(overrides.get("biomass_price_adj", 0.0))# $/GJ offset
    re_price_adj      = float(overrides.get("re_price_adj", 0.0))     # $/MWh offset
    demand_anchors_ov = overrides.get("demand_anchors")          # {year_str: Mt}
    demand_model_ov   = overrides.get("demand_model")            # "niti"|"model_fitted"|"export_driven"|"circular_economy"|"india_policy"|"international"
    capex_by_route    = overrides.get("capex_by_route", {})     # {routeId: multiplier}
    green_prem_ov     = float(overrides.get("green_premium", 0.0))    # $/t fibre
    wacc_override     = overrides.get("wacc")                   # fraction
    grid_ei_2070_ov   = overrides.get("grid_ei_2070")           # kgCO2/kWh
    pli_active        = bool(overrides.get("pli_active", True))
    gas_active        = bool(overrides.get("gas_active", True))
    biomass_active    = bool(overrides.get("biomass_active", True))
    circular_active   = bool(overrides.get("circular_active", True))
    biomass_cap_frac  = overrides.get("biomass_cap")            # fraction of demand
    circular_cap_frac = overrides.get("circular_cap")           # fraction of demand
    bio_cap_mult      = float(overrides.get("biomass_cap_mult", 1.0))
    rec_cap_mult      = float(overrides.get("recycled_cap_mult", 1.0))

    c   = np.zeros(NV)
    lb  = np.zeros(NV)
    ub  = np.full(NV, np.inf)
    rows, b_lo, b_hi = [], [], []

    def add(coeffs, lo, hi):
        rows.append(coeffs); b_lo.append(lo); b_hi.append(hi)

    wacc_eff = float(wacc_override) if wacc_override is not None else WACC

    for ti, y in enumerate(YEARS):
        dfy    = df(y)

        # Carbon price: Lab trajectory or scenario config
        if carbon_price_traj:
            cp = interp({str(k): float(v) for k, v in carbon_price_traj.items()}, y)
        else:
            cp = interp_sc(CFG["carbon_price_usd_per_tco2"], sc, y)

        # Demand: explicit anchors > named model > default niti
        # Alias: frontend "india_policy"→"export_driven", "international"→"circular_economy"
        _dt = CFG.get("demand_trajectories", {})
        _ALIAS = {"india_policy": "export_driven", "international": "circular_economy"}
        if demand_anchors_ov:
            demand = interp({str(k): float(v) for k, v in demand_anchors_ov.items()}, y)
        elif demand_model_ov:
            _key = _ALIAS.get(demand_model_ov, demand_model_ov) if demand_model_ov not in _dt else demand_model_ov
            _anchors = _dt.get(_key, _dt.get("niti", {})).get("anchors") or {2024: 9.5, 2040: 15.0, 2070: 25.0}
            demand = interp(_anchors, y)
        else:
            _anchors = _dt.get("niti", {}).get("anchors") or {2024: 9.5, 2040: 15.0, 2070: 25.0}
            demand = interp(_anchors, y)

        # Grid EI override
        # Lab slider sends kgCO2/kWh; grid_ei_use must be tCO2/kWh → divide by 1000
        if grid_ei_2070_ov is not None:
            ei_2024_kg = 0.710          # CEA 2022 baseline kgCO2/kWh (FROZEN_EXTERNAL)
            ei_2070_kg = float(grid_ei_2070_ov)
            ei_frac = max(0.0, (y - 2024) / (2070 - 2024))
            grid_ei_y = (ei_2024_kg + (ei_2070_kg - ei_2024_kg) * ei_frac) / 1000.0
        else:
            grid_ei_y = None

        # Fuel/energy prices: base + adj
        p_coal_gj = interp_sc(CFG["coal_price_usd_per_gj"], sc, y) + coal_price_adj / 29.3  # $/t → $/GJ (bituminous ~29.3 GJ/t)
        p_gas_gj  = interp_sc(CFG["natural_gas_price_usd_per_gj"], sc, y) + gas_price_adj / 1.055  # $/MMBtu → $/GJ
        p_elec    = interp_sc(CFG["electricity"]["price_usd_per_kwh"], sc, y)
        p_re      = interp_sc(CFG["electricity"]["re_price_usd_per_kwh"], sc, y) + re_price_adj / 1000.0
        p_h2_kg   = interp_sc(CFG["h2_price_usd_per_kg"], sc, y)
        _bio_base = CFG["feedstocks"]["biomass"]["price_usd_per_gj"] if "feedstocks" in CFG else {"CPS": {2024: 2.5}, "NZS": {2024: 2.5}}
        p_bio_gj  = interp_sc(_bio_base, sc, y) + biomass_price_adj

        for ri, rid in enumerate(ROUTE_IDS):
            rc       = _route(rid)
            wacc_r   = wacc_eff * (1.0 + rc.get("wacc_premium", 0.0))
            lifetime = rc["lifetime_yr"]
            capex    = rc["capex_usd_per_t"] * float(capex_by_route.get(rid, 1.0))
            fom      = rc["fom_usd_per_t_yr"]
            vom      = rc["vom_residual_usd_per_t"]

            pli_val = 0.0
            if pli_active:
                pli_d = CFG["policy"]["pli_usd_per_t"].get(rid, {})
                if pli_d: pli_val = interp_sc(pli_d, sc, y)
            gp_val = 0.0
            gp_routes = CFG["policy"]["green_premium_usd_per_t"].get("routes", [])
            if rid in gp_routes:
                gp_val = interp_sc(CFG["policy"]["green_premium_usd_per_t"], sc, y) + green_prem_ov

            # Fuel cost
            fuel_cost = 0.0
            if rid == "Coal-Conventional":
                fuel_cost = rc.get("coal_gj_per_t", 16.0) * p_coal_gj
            elif rid == "Gas-Transition":
                fuel_cost = rc.get("gas_gj_per_t", 14.5) * p_gas_gj
            elif rid == "Biomass-Cogen":
                fuel_cost = rc.get("biomass_gj_per_t", 18.0) * p_bio_gj
            elif rid == "Green-H2-Steam":
                fuel_cost = rc.get("h2_kg_per_t", 280) * p_h2_kg

            kwh = rc.get("elec_kwh_per_t", 2800)
            if rc.get("elec_is_re", False) or rid == "RE-Electrified":
                elec_cost = kwh * p_re
            else:
                elec_cost = kwh * p_elec

            # CO2 intensity with optional grid EI override
            co2_int = route_co2_intensity(rid, sc, y)
            if grid_ei_y is not None:
                cfg_ei = interp_sc(CFG["electricity"]["grid_ei_tco2_per_kwh"], sc, y)
                if cfg_ei > 0 and rc.get("elec_kwh_per_t", 0) > 0:
                    # Adjust the electricity portion of CO2
                    elec_co2_base = rc.get("elec_kwh_per_t", 0) * cfg_ei
                    elec_co2_new  = rc.get("elec_kwh_per_t", 0) * grid_ei_y
                    co2_int = co2_int - elec_co2_base + elec_co2_new

            ann_cap = crf(wacc_r, lifetime) * capex
            c[_CAP(ri, ti)] += dfy * (ann_cap + fom)
            c[_ACT(ri, ti)] += dfy * (vom + fuel_cost + elec_cost
                                       - pli_val - gp_val
                                       + co2_int * cp)

        # CAP accounting
        for ri, rid in enumerate(ROUTE_IDS):
            rc = _route(rid)
            surv = surviving(rc["existing_mt"], y, rc["lifetime_yr"])
            lead = rc.get("lead_years", 0)
            row = {_CAP(ri, ti): -1.0}
            for tau_i, tau_y in enumerate(YEARS[:ti+1]):
                if tau_y < rc["start_year"] or (y-tau_y) < lead or (y-tau_y) >= rc["lifetime_yr"]: continue
                row[_NCAP(ri, tau_i)] = 1.0
            add(row, -surv, -surv)

        for ri, rid in enumerate(ROUTE_IDS):
            add({_ACT(ri, ti): 1.0, _CAP(ri, ti): -_route(rid)["availability"]}, -np.inf, 0.0)

        # Elastic demand: production + slack ≥ demand (slack penalised at $10k/t)
        c[_SLACK(ti)] += dfy * DEMAND_SHORTFALL_PENALTY_USD_PER_T * 1e3
        row_d = {_ACT(ri, ti): 1.0 for ri in range(R)}
        row_d[_SLACK(ti)] = 1.0
        add(row_d, demand, demand)  # ub=demand: prevent overproduction when green_premium > VOM

        for ri, rid in enumerate(ROUTE_IDS):
            rc = _route(rid)
            if y < rc["start_year"]:
                ub[_NCAP(ri, ti)] = 0.0; ub[_ACT(ri, ti)] = 0.0
            max_r = rc.get("max_ramp_mt_yr", None)
            if max_r is not None:
                ub[_NCAP(ri, ti)] = min(ub[_NCAP(ri, ti)], max_r) if max_r > 0 else 0.0
            cutoff = rc.get(f"cutoff_year_{sc.lower()}", None)
            if cutoff and y >= cutoff:
                ub[_NCAP(ri, ti)] = 0.0

        if ti > 0:
            for ri, rid in enumerate(ROUTE_IDS):
                if _route(rid).get("fossil_decline", False):
                    add({_ACT(ri, ti): 1.0, _ACT(ri, ti-1): -1.0}, -np.inf, 0.0)

        # CO2 tracking (with optional grid EI override)
        row = {_CO2(ti): -1.0}
        for ri, rid in enumerate(ROUTE_IDS):
            co2_i = route_co2_intensity(rid, sc, y)
            if grid_ei_y is not None:
                cfg_ei = interp_sc(CFG["electricity"]["grid_ei_tco2_per_kwh"], sc, y)
                rc_i = _route(rid)
                kwh_i = rc_i.get("elec_kwh_per_t", 0)
                if cfg_ei > 0 and kwh_i > 0:
                    co2_i = co2_i - kwh_i * cfg_ei + kwh_i * grid_ei_y
            row[_ACT(ri, ti)] = co2_i
        add(row, 0.0, 0.0)

        # Toggle constraints: disable routes if toggle is off
        toggle_disabled: set = set()
        if not gas_active:
            toggle_disabled.add("Gas-Transition")
        if not biomass_active:
            toggle_disabled.add("Biomass-Cogen")
        if not circular_active:
            toggle_disabled.add("Circular-Fibre")
        for ri, rid in enumerate(ROUTE_IDS):
            if rid in toggle_disabled:
                ub[_NCAP(ri, ti)] = 0.0
                ub[_ACT(ri, ti)]  = 0.0

        # Biomass supply cap (Lab override or config)
        bio_ri = next((ri for ri, rid in enumerate(ROUTE_IDS) if rid == "Biomass-Cogen"), None)
        if bio_ri is not None and "Biomass-Cogen" not in toggle_disabled:
            if biomass_cap_frac is not None:
                cap_val = float(biomass_cap_frac) * demand
                ub[_ACT(bio_ri, ti)] = min(ub[_ACT(bio_ri, ti)], max(0.0, cap_val))
            elif CFG.get("biomass_supply", {}).get("enabled"):
                bio_gj = interp_sc(CFG["biomass_supply"]["textile_share_gj_yr"], sc, y) * bio_cap_mult
                bio_gj_per_t = _route("Biomass-Cogen").get("biomass_gj_per_t", 18.0)
                add({_ACT(bio_ri, ti): 1.0}, -np.inf, bio_gj / bio_gj_per_t if bio_gj_per_t > 0 else np.inf)

        # Recycled fibre supply cap (Lab override or config)
        rec_ri = next((ri for ri, rid in enumerate(ROUTE_IDS) if rid == "Circular-Fibre"), None)
        if rec_ri is not None and "Circular-Fibre" not in toggle_disabled:
            if circular_cap_frac is not None:
                cap_val = float(circular_cap_frac) * demand
                ub[_ACT(rec_ri, ti)] = min(ub[_ACT(rec_ri, ti)], max(0.0, cap_val))
            elif CFG.get("recycled_supply", {}).get("enabled"):
                rec_avail = interp_sc(CFG["recycled_supply"]["available_mt"], sc, y)
                rec_yield  = CFG["recycled_supply"].get("recycling_yield", 0.65)
                rec_cap = rec_avail * rec_yield * rec_cap_mult
                add({_ACT(rec_ri, ti): 1.0}, -np.inf, rec_cap)

    nr = len(rows)
    A  = lil_matrix((nr, NV))
    for i, row in enumerate(rows):
        for j, v in row.items(): A[i, j] = v
    return c, A, np.array(b_lo), np.array(b_hi), lb, ub

import json as _json, hashlib as _md5_mod, threading as _thr
_solve_cache: dict = {}
_solve_lock = _thr.Lock()

_HIGHS_OPTIONS = {
    "disp": False, "presolve": True, "time_limit": 300.0,
}

def _cache_key(sc: str, ov: dict) -> str:
    h = _md5_mod.md5(_json.dumps(ov, sort_keys=True).encode(), usedforsecurity=False).hexdigest()[:8]
    return f"{sc}:{h}"

def _solve(sc: str, overrides: Dict[str, Any]) -> Dict:
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
            prod_r[rid] = round(act, 4); cap_r[rid] = round(cap, 4)
            ncap_r[rid] = round(ncap, 4); co2_r[rid] = round(co2, 4)

        total_prod = sum(prod_r.values())
        total_co2  = max(0.0, x[_CO2(ti)])
        intensity  = total_co2 / total_prod if total_prod > 0 else 0.0
        unmet_demand = max(0.0, x[_SLACK(ti)])
        _dt = CFG.get("demand_trajectories", {})
        _anchors = _dt.get("niti", {}).get("anchors") or _dt.get("model_fitted", {}).get("anchors") or {2024: 9.5, 2040: 15.0, 2070: 25.0}
        demand = interp(_anchors, y)
        yearly[y] = {
            "year": y, "demand_mt": round(demand, 2),
            "unmet_demand_mt": round(unmet_demand, 4),
            "production_by_route": prod_r, "capacity_by_route": cap_r,
            "new_capacity_by_route": ncap_r, "co2_by_route_mt": co2_r,
            "total_production_mt": round(total_prod, 4),
            "total_production":    round(total_prod, 4),   # canonical alias
            "total_co2_mt": round(total_co2, 4),
            "co2_total":    round(total_co2, 4),           # canonical alias
            "co2_intensity_tco2_per_t": round(intensity, 4),
            "co2_intensity":            round(intensity, 4),  # canonical alias
            "investment_by_route": inv_r,
            "total_cost": round(total_cost_yr, 1),
        }

    all_co2 = sum(yr["total_co2_mt"] for yr in yearly.values())
    out = {
        "status": "ok", "scenario": sc,
        "solver_objective": round(result.fun, 2),
        "yearly_results": yearly,
        "summary": {
            "total_cost_bn": round(result.fun / 1e3, 3),
            "total_co2_cumulative_mt": round(all_co2, 1),
            "final_co2_intensity": round(yearly[END]["co2_intensity_tco2_per_t"], 4),
        },
        "vol4_targets": CFG["vol4_reference"]["co2_intensity_tco2_per_t_fibre"],
        "provenance": "configs/textile_config.yaml",
    }
    with _solve_lock:
        _solve_cache[key] = out
    return out

from contextlib import asynccontextmanager

@asynccontextmanager
async def _textile_lifespan(application):
    import threading, logging as _lg
    _log = _lg.getLogger("textile.backend")
    def _warm(sc):
        _log.info("Textile pre-warm: %s", sc)
        try:
            _solve(sc, {})
            _log.info("Textile pre-warm done: %s", sc)
        except Exception as exc:
            _log.warning("Textile pre-warm failed (%s): %s", sc, exc)
    for sc in ("CPS", "NZS"):
        threading.Thread(target=_warm, args=(sc,), daemon=True, name=f"textile-prewarm-{sc}").start()
    yield

app = FastAPI(title="Textile Transition Model v3", version="3.0.0", lifespan=_textile_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class RunRequest(BaseModel):
    scenario: str = "CPS"
    overrides: Dict[str, Any] = {}

@app.get("/health")
def health():
    return {"status": "ok", "sector": "textile", "model_version": "v3",
            "routes": ROUTE_IDS, "years": f"{START}-{END}",
            "biomass_cap_enabled": CFG.get("biomass_supply", {}).get("enabled", False),
            "recycled_cap_enabled": CFG.get("recycled_supply", {}).get("enabled", False)}

@app.get("/api/routes")
def get_routes():
    return {"routes": [{"id": rid,
                         "existing_mt": _route(rid)["existing_mt"],
                         "capex_usd_per_t": _route(rid)["capex_usd_per_t"],
                         "ef_2024_tco2_per_t": round(route_co2_intensity(rid, "CPS", 2024), 3),
                         "ef_source": _route(rid).get("energy_intensity_provenance", "")}
                        for rid in ROUTE_IDS]}

@app.get("/api/demand-trajectories")
def get_demand_trajectories():
    historical = [
        {"year": 2005, "production_mt": 5.5}, {"year": 2010, "production_mt": 6.8},
        {"year": 2015, "production_mt": 7.8}, {"year": 2019, "production_mt": 9.0},
        {"year": 2022, "production_mt": 9.3}, {"year": 2024, "production_mt": 9.5},
    ]
    out = {}
    for key, tc in CFG.get("demand_trajectories", {}).items():
        series = {y: interp(tc["anchors"], y) for y in range(2024, 2071)}
        out[key] = {"label": tc["label"], "annual_series": series,
                    "end_value": series[2070], "source": tc["source"]}
    return {**out, "historical": historical}

@app.post("/api/run")
def run_scenario(req: RunRequest):
    sc = req.scenario.upper()
    if sc not in ("CPS", "NZS"): return {"status": "error", "message": f"Unknown: {sc}"}
    return _solve(sc, req.overrides)

@app.post("/api/lab")
def run_lab(req: RunRequest):
    sc = req.scenario.upper() if req.scenario.upper() in ("CPS", "NZS") else "CPS"
    return _solve(sc, req.overrides)

@app.get("/api/sensitivity")
def sensitivity():
    base = _solve("NZS", {})
    if base["status"] != "ok": return {"status": "infeasible"}
    b_co2, b_cost = base["summary"]["total_co2_cumulative_mt"], base["summary"]["total_cost_bn"]
    results = {}
    for p, (lo, hi) in {
        "carbon_price_mult": (0.8, 1.2), "coal_price_mult": (0.8, 1.2),
        "elec_price_mult": (0.8, 1.2), "demand_mult": (0.8, 1.2),
        "biomass_cap_mult": (0.7, 1.3), "recycled_cap_mult": (0.7, 1.3),
    }.items():
        r_lo = _solve("NZS", {p: lo}); r_hi = _solve("NZS", {p: hi})
        results[p] = {
            "co2_delta_lo": round((r_lo["summary"]["total_co2_cumulative_mt"]-b_co2)/b_co2*100,2) if r_lo["status"]=="ok" else None,
            "co2_delta_hi": round((r_hi["summary"]["total_co2_cumulative_mt"]-b_co2)/b_co2*100,2) if r_hi["status"]=="ok" else None,
        }
    return {"sensitivity": results, "base_co2_mt": b_co2, "base_cost_bn": b_cost}

if __name__ == "__main__":
    uvicorn.run("textile_backend_v3:app", host="0.0.0.0", port=CFG.get("port", 8003), reload=False)
