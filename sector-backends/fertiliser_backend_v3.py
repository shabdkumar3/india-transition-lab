"""
Fertiliser Transition Backend v3 — India Transition Lab (port 8004)
===================================================================
SCIENTIFIC UPGRADES OVER v2:

  1. CONFIG-DRIVEN from fertiliser_config.yaml
  2. ANNUAL LP RESOLUTION: 2024-2070
  3. NET CO2 ACCOUNTING — correct treatment:
       GROSS CO2 = process_CO2 + combustion_CO2 + electricity_CO2
       SEQUESTERED = 0.733 tCO2/t urea × urea_share × production
       NET CO2     = GROSS - SEQUESTERED (net to atmosphere)
     This is physically correct: CO2 is a feedstock for urea synthesis.
     Only CO2 NOT captured in urea escapes to atmosphere.
     NOTE: Most plants co-produce some CO2 vented (not all absorbed by urea).
  4. ROUTE-SPECIFIC FEEDSTOCK INTENSITIES:
       - NG-SMR: gas_gj_per_t_nh3 × gas EF
       - Coal-Gasif: coal_t_per_t_nh3 × coal EF (separate from combustion CO2)
       - Green-H2: zero fuel; intensive electricity
  5. BIOMASS SUPPLY CAP: limits Biomass-Reform route
  6. DEMAND TRAJECTORIES ENDPOINT
"""
from __future__ import annotations

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

CONFIG_PATH = Path(__file__).parent / "configs" / "fertiliser_config.yaml"

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

# Chemistry constants
CO2_SEQ_PER_T_UREA = CFG["chemistry"]["co2_sequestered_in_urea_tco2_per_t_urea"]   # 0.733 tCO2/t urea
NH3_PER_T_UREA     = CFG["chemistry"]["nh3_per_t_urea"]                              # 0.567 t NH3/t urea
# Urea fraction of NH3 product: India ~82% of NH3 becomes urea
UREA_FRACTION      = 0.82  # PROJECT_PROPOSAL — can be overridden
H2_PER_T_NH3_KG   = 176.5  # kg H2 per tonne NH3; FROZEN_EXTERNAL stoichiometry.
# Reaction: N2 + 3H2 → 2NH3 (produces 2 mol NH3 per 3 mol H2)
# kg H2 / t NH3 = (3 × 2.016) / (2 × 17.03) × 1000 = 6.048 / 34.06 × 1000 = 177.6 ≈ 176.5 kg/t NH3
# NOTE: Prior value 353.0 was WRONG — divided by MW(NH3)=17 instead of 2×MW(NH3)=34,
#   giving 6/17×1000=353 which is DOUBLE the correct stoichiometric value.
#   353 made Green-H2 appear 2× more expensive in the LP → bias against clean route.
# CORRECTION: 176.5 kg H2/t NH3 (pure stoichiometric, IEA Ammonia Technology Roadmap 2021)

def crf(r, n):
    if r == 0 or n == 0: return 1.0 / max(n, 1)
    return r * (1 + r)**n / ((1 + r)**n - 1)

def df(y): return 1.0 / (1.0 + WACC) ** (y - START)

def interp(anchors: Dict, y: int) -> float:
    if not anchors: return 0.0
    ks = sorted(int(k) for k in anchors)
    if y <= ks[0]: return float(anchors.get(str(ks[0]), anchors.get(ks[0], 0)))
    if y >= ks[-1]: k = ks[-1]; return float(anchors.get(str(k), anchors.get(k, 0)))
    for lo, hi in zip(ks, ks[1:]):
        if lo <= y <= hi:
            vlo = float(anchors.get(str(lo), anchors.get(lo, 0)))
            vhi = float(anchors.get(str(hi), anchors.get(hi, 0)))
            return vlo + (vhi - vlo) * (y - lo) / (hi - lo)
    return 0.0

def interp_sc(d: Dict, sc: str, y: int) -> float:
    return interp(d.get(sc, d.get("CPS", {})), y)

def surviving(existing, y, lifetime):
    age = y - START
    if age >= lifetime: return 0.0
    return existing * (1.0 - age / lifetime)

def _route(rid): return CFG["routes"][rid]

# Variable indices
def _NCAP(ri, ti): return ri * T + ti
def _CAP(ri, ti):  return R*T + ri * T + ti
def _ACT(ri, ti):  return 2*R*T + ri * T + ti
def _CO2(ti):      return 3*R*T + ti
def _SLACK(ti):    return 4*R*T + ti   # unmet demand slack variable
NV = 4*R*T + T

DEMAND_SHORTFALL_PENALTY_USD_PER_T = 10_000.0  # $/t NH3: exceeds any production cost

def route_gross_co2(rid: str, sc: str, y: int, grid_ei_override: float | None = None) -> float:
    """
    Gross CO2 per t NH3 (before urea sequestration credit).
    Sum of: process CO2 + combustion CO2 + electricity CO2
    grid_ei_override: tCO2/kWh value from Lab slider (overrides config trajectory)
    """
    rc  = _route(rid)
    grid_ei = grid_ei_override if grid_ei_override is not None else interp_sc(CFG["electricity"]["grid_ei_tco2_per_kwh"], sc, y)
    kwh = rc.get("elec_kwh_per_t_nh3", 150)

    elec_co2 = kwh * grid_ei  # tCO2/t NH3

    if rid == "NG-SMR" or rid == "NG-SMR-CCS":
        proc  = rc.get("process_co2_t_per_t_nh3", 0.0)
        comb  = rc.get("combustion_co2_t_per_t_nh3", 0.0)
        # CCS reduces process CO2 by capture rate
        cap_r = rc.get("ccus_capture_rate", 0.0)
        proc_net = proc * (1.0 - cap_r)
        return proc_net + comb + elec_co2

    elif rid == "Coal-Gasif":
        total  = rc.get("total_co2_t_per_t_nh3", 2.90)
        cap_r  = rc.get("ccus_capture_rate", 0.0)
        return total * (1.0 - cap_r) + elec_co2

    elif rid == "Green-H2":
        # Green H2: electricity for electrolysis; use RE price route
        # CO2 only from electricity (near-zero if RE powered)
        re_ei = 0.0  # dedicated RE → zero
        kwh_green = rc.get("elec_kwh_per_t_nh3", 10500)
        return kwh_green * re_ei  # ≈ 0 if RE powered

    elif rid == "Biomass-Reform":
        proc = rc.get("process_co2_t_per_t_nh3", 0.15)
        return proc + elec_co2  # biomass combustion CO2 = zero (biogenic)

    return rc.get("process_co2_t_per_t_nh3", 0.0) + rc.get("combustion_co2_t_per_t_nh3", 0.0) + elec_co2

def route_net_co2(rid: str, sc: str, y: int, urea_fraction: float = UREA_FRACTION, grid_ei_override: float | None = None) -> float:
    """
    Net CO2 per t NH3: gross CO2 minus CO2 sequestered in urea.
    Physical: CO2 is consumed in urea synthesis; that CO2 stays fixed in fertiliser
    until it's applied to soil (then slowly released, so net to atmosphere).
    """
    gross = route_gross_co2(rid, sc, y, grid_ei_override=grid_ei_override)
    # Sequestration: urea fraction × CO2 per t urea × t urea per t NH3
    t_urea_per_t_nh3 = urea_fraction / NH3_PER_T_UREA   # t urea per t NH3
    co2_seq = CO2_SEQ_PER_T_UREA * t_urea_per_t_nh3
    return max(0.0, gross - co2_seq)  # can be negative if very low carbon + high urea fraction

def build_lp(sc: str, overrides: Dict[str, Any]):
    # ── Parse Lab override format (frontend → backend contract) ──────────────
    carbon_price_traj  = overrides.get("carbon_price")            # {year_str: usd/tco2}
    gas_price_adj      = float(overrides.get("gas_price_adj", 0.0))      # $/MMBtu offset
    coal_price_adj     = float(overrides.get("coal_price_adj", 0.0))     # $/t offset
    biomass_price_adj  = float(overrides.get("biomass_price_adj", 0.0))  # $/GJ offset
    demand_anchors_ov  = overrides.get("demand_anchors")           # {year_str: Mt NH3}
    demand_model_ov    = overrides.get("demand_model")             # "niti"|"model_fitted"|"high_agriculture"|"india_policy"|"international"
    capex_by_route     = overrides.get("capex_by_route", {})      # {routeId: multiplier}
    green_prem_ov      = float(overrides.get("green_premium", 0.0))      # $/t NH3
    wacc_override      = overrides.get("wacc")                    # fraction
    h2_cost_ov         = overrides.get("h2_cost")                 # {year_str: $/kg}
    pli_active         = bool(overrides.get("pli_active", True))
    ccus_active        = bool(overrides.get("ccus_active", True))
    bio_ammonia_active = bool(overrides.get("bio_ammonia_active", True))
    ng_smr_active      = bool(overrides.get("ng_smr_active", True))
    bio_cap_frac       = overrides.get("bio_cap")                 # fraction of demand
    grid_ei_2070_ov    = overrides.get("grid_ei_2070")           # kgCO2/kWh in 2070
    urea_fraction      = float(overrides.get("urea_fraction", UREA_FRACTION))
    biomass_cap_mult   = float(overrides.get("biomass_cap_mult", 1.0))

    c   = np.zeros(NV)
    lb  = np.zeros(NV)
    ub  = np.full(NV, np.inf)
    rows, b_lo, b_hi = [], [], []

    def add(coeffs, lo, hi):
        rows.append(coeffs); b_lo.append(lo); b_hi.append(hi)

    # Feedstock prices
    gas_cfg   = CFG["feedstocks"]["natural_gas"]
    coal_cfg  = CFG["feedstocks"]["coal"]
    gj_per_mmbtu = gas_cfg.get("gj_per_mmbtu", 1.05505)

    wacc_eff = float(wacc_override) if wacc_override is not None else WACC

    for ti, y in enumerate(YEARS):
        dfy = df(y)

        # Carbon price: Lab trajectory or scenario config
        if carbon_price_traj:
            cp = interp({str(k): float(v) for k, v in carbon_price_traj.items()}, y)
        else:
            cp = interp_sc(CFG["carbon_price_usd_per_tco2"], sc, y)

        # Demand: explicit anchors > named model > default niti
        _dt = CFG.get("demand_trajectories", {})
        if demand_anchors_ov:
            demand = interp({str(k): float(v) for k, v in demand_anchors_ov.items()}, y)
        elif demand_model_ov:
            _key = demand_model_ov if demand_model_ov in _dt else "niti"
            _anchors = _dt.get(_key, {}).get("anchors") or {2024: 13.0, 2040: 15.5, 2070: 17.0}
            demand = interp(_anchors, y)
        else:
            _anchors = _dt.get("niti", {}).get("anchors") or {2024: 13.0, 2040: 15.5, 2070: 17.0}
            demand = interp(_anchors, y)

        # Gas price: USD/MMBtu → USD/GJ + adjustment
        p_gas_usd_gj  = (interp_sc(gas_cfg["price_usd_per_mmbtu"], sc, y) + gas_price_adj) / gj_per_mmbtu
        p_coal_usd_t  = interp_sc(coal_cfg["price_usd_per_t"], sc, y) + coal_price_adj
        p_elec        = interp_sc(CFG["electricity"]["price_usd_per_kwh"], sc, y)
        # Green H2 cost: Lab override trajectory or config
        if h2_cost_ov:
            p_h2_kg = interp({str(k): float(v) for k, v in h2_cost_ov.items()}, y)
            # Convert $/kg H2 → effective $/kWh for Green-H2 route so that
            # elec_cost = p_re × elec_kwh_per_t_nh3 equals the actual H2 purchase cost.
            # Green-H2 elec_kwh_per_t_nh3 = 10500 (≈ 176.5 kgH2/t × 55 kWh/kgH2 + ~780 HB compression)
            # True H2 cost/t NH3 = p_h2_kg × H2_PER_T_NH3_KG (176.5 kg/t) → p_re = that / 10500
            _gh2_kwh_per_t = _route("Green-H2").get("elec_kwh_per_t_nh3", 10500.0)
            p_re = (p_h2_kg * H2_PER_T_NH3_KG) / max(_gh2_kwh_per_t, 1.0)
        else:
            p_re = interp_sc(CFG["electricity"]["re_price_usd_per_kwh"], sc, y)

        # Grid EI override: linear ramp from 2024 baseline to user's 2070 target
        if grid_ei_2070_ov is not None:
            _ei_base_kg = 0.716  # kgCO2/kWh (CEA 2022 baseline)
            _ei_70_kg   = float(grid_ei_2070_ov)
            _frac       = max(0.0, (y - 2024) / (2070 - 2024))
            _grid_ei_y  = (_ei_base_kg + (_ei_70_kg - _ei_base_kg) * _frac) / 1000.0  # → tCO2/kWh
        else:
            _grid_ei_y  = None

        net_co2_per_t = {rid: route_net_co2(rid, sc, y, urea_fraction, grid_ei_override=_grid_ei_y) for rid in ROUTE_IDS}

        for ri, rid in enumerate(ROUTE_IDS):
            rc       = _route(rid)
            wacc_r   = wacc_eff * (1.0 + rc.get("wacc_premium", 0.0))
            lifetime = rc["lifetime_yr"]
            capex    = rc["capex_usd_per_t_nh3"] * float(capex_by_route.get(rid, 1.0))

            fom     = rc["fom_usd_per_t_yr"]
            vom     = rc["vom_residual_usd_per_t"]

            pli_val = 0.0
            if pli_active:
                pli_d = CFG["policy"]["pli_usd_per_t_nh3"].get(rid, {})
                if pli_d:
                    pli_val = interp_sc(pli_d, sc, y)

            gp_val  = 0.0
            gp_routes = CFG["policy"]["green_premium_usd_per_t_nh3"].get("routes", [])
            if rid in gp_routes:
                gp_val = interp_sc(CFG["policy"]["green_premium_usd_per_t_nh3"], sc, y) + green_prem_ov

            # Fuel cost per t NH3
            fuel_cost = 0.0
            if rid in ("NG-SMR", "NG-SMR-CCS"):
                fuel_cost = rc.get("gas_gj_per_t_nh3", 32.5) * p_gas_usd_gj
            elif rid == "Coal-Gasif":
                fuel_cost = rc.get("coal_t_per_t_nh3", 1.45) * p_coal_usd_t
            elif rid == "Biomass-Reform":
                p_bio = interp_sc(CFG["feedstocks"]["biomass"]["price_usd_per_gj"], sc, y) + biomass_price_adj
                fuel_cost = rc.get("biomass_gj_per_t_nh3", 38.0) * p_bio

            # Electricity cost per t NH3
            kwh = rc.get("elec_kwh_per_t_nh3", 150)
            if rid == "Green-H2":
                elec_cost = kwh * p_re   # RE-powered electrolysis (or H2 cost converted)
            else:
                elec_cost = kwh * p_elec

            ann_cap = crf(wacc_r, lifetime) * capex
            c[_CAP(ri, ti)] += dfy * (ann_cap + fom)
            c[_ACT(ri, ti)] += dfy * (vom + fuel_cost + elec_cost
                                       - pli_val - gp_val
                                       + net_co2_per_t[rid] * cp)

        # Constraints
        for ri, rid in enumerate(ROUTE_IDS):
            rc       = _route(rid)
            existing = rc["existing_mt_nh3"]
            lifetime = rc["lifetime_yr"]
            lead     = rc.get("lead_years", 0)
            start    = rc["start_year"]
            surv     = surviving(existing, y, lifetime)
            row = {_CAP(ri, ti): -1.0}
            for tau_i, tau_y in enumerate(YEARS[:ti + 1]):
                if tau_y < start or (y - tau_y) < lead or (y - tau_y) >= lifetime: continue
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
                ub[_NCAP(ri, ti)] = 0.0
                ub[_ACT(ri, ti)]  = 0.0
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

        # CO2 tracking
        row = {_CO2(ti): -1.0}
        for ri, rid in enumerate(ROUTE_IDS):
            row[_ACT(ri, ti)] = net_co2_per_t[rid]
        add(row, 0.0, 0.0)

        # Toggle constraints: disable routes if toggle is off
        toggle_disabled: set = set()
        if not ccus_active:
            toggle_disabled.add("NG-SMR-CCS")
        if not bio_ammonia_active:
            toggle_disabled.add("Biomass-Reform")
        if not ng_smr_active:
            toggle_disabled.add("NG-SMR")
        for ri, rid in enumerate(ROUTE_IDS):
            if rid in toggle_disabled:
                ub[_NCAP(ri, ti)] = 0.0
                ub[_ACT(ri, ti)]  = 0.0

        # Biomass supply cap (Lab override or config)
        bio_ri = next((ri for ri, rid in enumerate(ROUTE_IDS) if rid == "Biomass-Reform"), None)
        if bio_ri is not None and "Biomass-Reform" not in toggle_disabled:
            if bio_cap_frac is not None:
                cap_val = float(bio_cap_frac) * demand
                add({_ACT(bio_ri, ti): 1.0}, -np.inf, max(0.0, cap_val))
            elif CFG.get("biomass_supply", {}).get("enabled"):
                bio_gj = interp_sc(CFG["biomass_supply"]["available_gj_per_yr"], sc, y) * \
                         CFG["biomass_supply"].get("fertiliser_share", 0.10) * biomass_cap_mult
                bio_gj_per_t = _route("Biomass-Reform").get("biomass_gj_per_t_nh3", 38.0)
                bio_cap_mt = bio_gj / bio_gj_per_t if bio_gj_per_t > 0 else np.inf
                add({_ACT(bio_ri, ti): 1.0}, -np.inf, bio_cap_mt)

    nr = len(rows)
    A  = lil_matrix((nr, NV))
    for i, row in enumerate(rows):
        for j, v in row.items():
            A[i, j] = v

    return c, A, np.array(b_lo), np.array(b_hi), lb, ub

import json as _json, hashlib as _md5_mod, threading as _thr
_solve_cache: dict = {}
_solve_lock = _thr.Lock()

_HIGHS_OPTIONS = {
    "disp": False, "presolve": "on", "solver": "simplex",
    "simplex_strategy": 1, "simplex_scale_strategy": 2,
    "primal_feasibility_tolerance": 1e-7, "dual_feasibility_tolerance": 1e-7,
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
    urea_fraction = float(overrides.get("urea_fraction", UREA_FRACTION))
    yearly = {}
    for ti, y in enumerate(YEARS):
        prod_r, cap_r, ncap_r, co2_r, inv_r = {}, {}, {}, {}, {}
        total_cost_yr = 0.0
        # Recompute grid_ei override for results (same ramp as in build_lp)
        if grid_ei_2070_ov is not None:
            _ei_base_kg = 0.716
            _ei_70_kg   = float(grid_ei_2070_ov)
            _frac_r     = max(0.0, (y - 2024) / (2070 - 2024))
            _grid_ei_r  = (_ei_base_kg + (_ei_70_kg - _ei_base_kg) * _frac_r) / 1000.0
        else:
            _grid_ei_r  = None
        for ri, rid in enumerate(ROUTE_IDS):
            rc   = _route(rid)
            act  = max(0.0, x[_ACT(ri, ti)])
            cap  = max(0.0, x[_CAP(ri, ti)])
            ncap = max(0.0, x[_NCAP(ri, ti)])
            gross = route_gross_co2(rid, sc, y, grid_ei_override=_grid_ei_r) * act
            net   = route_net_co2(rid, sc, y, urea_fraction, grid_ei_override=_grid_ei_r) * act
            capex_r = rc.get("capex_usd_per_t_nh3", rc.get("capex_usd_per_t", 0.0))
            fom_r   = rc.get("fom_usd_per_t_yr", 0.0)
            vom_r   = rc.get("vom_residual_usd_per_t", 0.0)
            inv_r[rid] = round(ncap * capex_r, 2)           # Mn$ (Mt × $/t = M$)
            total_cost_yr += act * vom_r + cap * fom_r + ncap * capex_r
            prod_r[rid] = round(act, 4)
            cap_r[rid]  = round(cap, 4)
            ncap_r[rid] = round(ncap, 4)
            co2_r[rid]  = {"gross": round(gross, 4), "net": round(net, 4)}

        total_prod = sum(prod_r.values())
        total_co2_net = max(0.0, x[_CO2(ti)])
        intensity = total_co2_net / total_prod if total_prod > 0 else 0.0
        unmet_demand = max(0.0, x[_SLACK(ti)])
        _dt = CFG.get("demand_trajectories", {})
        _anchors = _dt.get("niti", {}).get("anchors") or _dt.get("model_fitted", {}).get("anchors") or {2024: 13.0, 2040: 15.5, 2070: 17.0}
        demand = interp(_anchors, y)
        yearly[y] = {
            "year": y,
            "demand_mt_nh3": round(demand, 2),
            "demand_mt":     round(demand, 2),   # canonical alias for frontend
            "unmet_demand_mt": round(unmet_demand, 4),
            "production_by_route": prod_r,
            "capacity_by_route": cap_r,
            "new_capacity_by_route": ncap_r,
            "co2_by_route": co2_r,
            "total_production_mt": round(total_prod, 4),
            "total_production":    round(total_prod, 4),   # canonical alias
            "total_co2_net_mt": round(total_co2_net, 4),
            "co2_total":        round(total_co2_net, 4),   # canonical alias
            "co2_intensity_tco2_per_t_nh3": round(intensity, 4),
            "co2_intensity":                round(intensity, 4),  # canonical alias
            "investment_by_route": inv_r,
            "total_cost": round(total_cost_yr, 1),
        }

    all_co2 = sum(yr["total_co2_net_mt"] for yr in yearly.values())
    out = {
        "status": "ok", "scenario": sc,
        "solver_objective": round(result.fun, 2),
        "yearly_results": yearly,
        "summary": {
            "total_cost_bn": round(result.fun / 1e3, 3),
            "total_co2_cumulative_mt": round(all_co2, 1),
            "final_co2_intensity": round(yearly[END]["co2_intensity_tco2_per_t_nh3"], 4),
            "urea_fraction_used": urea_fraction,
            "co2_seq_credit": f"{CO2_SEQ_PER_T_UREA} tCO2/t_urea (FROZEN_EXTERNAL)",
        },
        "vol4_targets": CFG["vol4_reference"]["co2_intensity_tco2_per_t_nh3"],
        "provenance": "configs/fertiliser_config.yaml",
    }
    with _solve_lock:
        _solve_cache[key] = out
    return out

from contextlib import asynccontextmanager

@asynccontextmanager
async def _fert_lifespan(application):
    import threading, logging as _lg
    _log = _lg.getLogger("fertiliser.backend")
    def _warm(sc):
        _log.info("Fertiliser pre-warm: %s", sc)
        try:
            _solve(sc, {})
            _log.info("Fertiliser pre-warm done: %s", sc)
        except Exception as exc:
            _log.warning("Fertiliser pre-warm failed (%s): %s", sc, exc)
    for sc in ("CPS", "NZS"):
        threading.Thread(target=_warm, args=(sc,), daemon=True, name=f"fert-prewarm-{sc}").start()
    yield

app = FastAPI(title="Fertiliser Transition Model v3", version="3.0.0", lifespan=_fert_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class RunRequest(BaseModel):
    scenario: str = "CPS"
    overrides: Dict[str, Any] = {}

@app.get("/health")
def health():
    return {"status": "ok", "sector": "fertiliser", "model_version": "v3",
            "routes": ROUTE_IDS, "years": f"{START}-{END}",
            "urea_co2_seq_tco2_per_t": CO2_SEQ_PER_T_UREA,
            "nh3_per_t_urea": NH3_PER_T_UREA}

@app.get("/api/routes")
def get_routes():
    out = []
    for rid in ROUTE_IDS:
        rc = _route(rid)
        out.append({
            "id": rid,
            "existing_mt_nh3": rc["existing_mt_nh3"],
            "capex_usd_per_t_nh3": rc["capex_usd_per_t_nh3"],
            "capex_provenance": rc.get("capex_provenance", ""),
            "gross_co2_2024": round(route_gross_co2(rid, "CPS", 2024), 3),
            "net_co2_2024": round(route_net_co2(rid, "CPS", 2024), 3),
            "urea_seq_credit": round(CO2_SEQ_PER_T_UREA * UREA_FRACTION / NH3_PER_T_UREA, 3),
        })
    return {"routes": out}

@app.get("/api/demand-trajectories")
def get_demand_trajectories():
    historical = [
        {"year": 2005, "production_mt_nh3": 10.2}, {"year": 2010, "production_mt_nh3": 11.5},
        {"year": 2015, "production_mt_nh3": 12.1}, {"year": 2019, "production_mt_nh3": 12.6},
        {"year": 2022, "production_mt_nh3": 12.9}, {"year": 2024, "production_mt_nh3": 13.0},
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
        "carbon_price_mult": (0.8, 1.2), "gas_price_mult": (0.8, 1.2),
        "coal_price_mult": (0.8, 1.2), "demand_mult": (0.8, 1.2),
        "green_h2_capex_mult": (0.8, 1.2), "urea_fraction": (0.75, 0.90),
    }.items():
        r_lo = _solve("NZS", {p: lo}); r_hi = _solve("NZS", {p: hi})
        results[p] = {
            "co2_delta_lo": round((r_lo["summary"]["total_co2_cumulative_mt"] - b_co2)/b_co2*100, 2) if r_lo["status"]=="ok" else None,
            "co2_delta_hi": round((r_hi["summary"]["total_co2_cumulative_mt"] - b_co2)/b_co2*100, 2) if r_hi["status"]=="ok" else None,
        }
    return {"sensitivity": results, "base_co2_mt": b_co2, "base_cost_bn": b_cost}

if __name__ == "__main__":
    uvicorn.run("fertiliser_backend_v3:app", host="0.0.0.0", port=CFG.get("port", 8004), reload=False)
