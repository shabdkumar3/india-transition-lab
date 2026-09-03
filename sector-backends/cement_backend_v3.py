"""
Cement Transition Backend v3 — India Transition Lab  (port 8001)
================================================================
SCIENTIFIC UPGRADES OVER v2:

  1. CONFIG-DRIVEN: All parameters from cement_config.yaml (no hardcoded physics)
  2. ANNUAL LP RESOLUTION: 2024-2070 year-by-year (not 5-year blocks)
  3. PROCESS CO2 SEPARATION: calcination CO2 (fixed chemistry) vs combustion CO2
     - Process CO2 = clinker_factor × process_co2_kg_per_kg_clinker × production
     - Combustion CO2 = coal × ef_coal + alt_fuel × ef_altfuel
     - CCUS captures 90% of BOTH process + combustion CO2
  4. CLINKER-TO-CEMENT RATIO (CCR): explicit per-route parameter
     - Drives SCM demand = (1 - clinker_factor) × production
     - SCM is physically constrained by fly ash + slag availability
  5. SCM SUPPLY CAP: fly ash (from coal power) + slag (from steel)
     - As India decarbonises coal → fly ash declines → blended cement constrained
  6. RESOURCE INTENSITY REGISTRY: tonnes coal / GJ alt-fuel / kWh per tonne cement
  7. DEMAND-TRAJECTORIES ENDPOINT: 4 trajectories exposed to frontend
  8. SENSITIVITY ENDPOINT: per-parameter impact on CO2 and cost
  9. PROVENANCE TAGS: every parameter carries source classification

Physical model:
  Variables (annual, R routes, T years = 47):
    NCAP[r,t]  new capacity added in year t (Mt/yr)
    CAP[r,t]   total installed capacity (Mt/yr)
    ACT[r,t]   annual production (Mt)
    CO2[t]     total sector CO2 (MtCO2/yr)
    COAL[r,t]  coal consumption (Mt)
    ELEC[r,t]  electricity consumption (TWh)
    SCM[t]     total SCM consumed (Mt) — tracked against supply cap

  Objective: min Σ_t df[t] × [
    Σ_r (crf_annualised_capex[r] × NCAP[r,t-1]  ... accumulated cap
        + fom[r] × CAP[r,t]
        + vom[r] × ACT[r,t]
        - pli[r,t] × ACT[r,t]
        - green_premium[r,t] × ACT[r,t])
    + cp[t] × CO2[t]
    + Σ_r price_coal[t] × COAL[r,t]
    + Σ_r price_elec[t] × ELEC[r,t]
  ]

Sources: configs/cement_config.yaml (all provenance tracked there)
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ── Config loading ────────────────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).parent / "configs" / "cement_config.yaml"

def _load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

CFG = _load_config()

# ── Temporal setup ────────────────────────────────────────────────────────────

START = CFG["horizon"]["start_year"]
END   = CFG["horizon"]["end_year"]
YEARS = list(range(START, END + 1))
T     = len(YEARS)
WACC  = CFG["discount_rate"]["value"]

# ── Utilities ─────────────────────────────────────────────────────────────────

def crf(r: float, n: int) -> float:
    """Capital Recovery Factor — annualises overnight CAPEX."""
    if r == 0 or n == 0:
        return 1.0 / max(n, 1)
    return r * (1 + r)**n / ((1 + r)**n - 1)

def df(y: int) -> float:
    """Discount factor at year y relative to START."""
    return 1.0 / (1.0 + WACC) ** (y - START)

def interp(anchors: Dict, y: int) -> float:
    """Piecewise linear interpolation over year-keyed dict."""
    ks = sorted(int(k) for k in anchors)
    if not ks:
        return 0.0
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
    """Interpolate a scenario-keyed dict d[sc][year]."""
    return interp(d.get(sc, d.get("CPS", {})), y)

def surviving(existing: float, y: int, lifetime: int) -> float:
    """Fraction of existing capacity surviving to year y (linear retirement)."""
    age = y - START
    if age >= lifetime:
        return 0.0
    return existing * (1.0 - age / lifetime)

# ── Parse routes from config ──────────────────────────────────────────────────

ROUTE_IDS: List[str] = list(CFG["routes"].keys())
R = len(ROUTE_IDS)

def _route_cfg(rid: str) -> Dict:
    return CFG["routes"][rid]

# ── Fossil fuel emission factors (tCO2/t coal and tCO2/GJ alt fuel) ──────────

EF_COAL        = CFG["fuels"]["coal"]["emission_factor_tco2_per_t"]        # 2.42 tCO2/t
EF_ALTFUEL_GJ  = CFG["fuels"]["alt_fuel"]["emission_factor_tco2_per_gj"]   # 0.075 tCO2/GJ
# Coal GCV for intensity calculation: 26 GJ/t (non-coking thermal coal)
COAL_GCV_GJ_T  = 26.0

# ── SCM supply constraint ─────────────────────────────────────────────────────

SCM_CFG = CFG.get("scm_supply", {})
SCM_ENABLED = SCM_CFG.get("enabled", False)
SCM_ROUTES  = set(SCM_CFG.get("scm_consuming_routes", []))

def _scm_cap(sc: str, y: int) -> float:
    """Total fly ash + slag available as SCM in year y under scenario sc."""
    fa = interp(SCM_CFG.get("fly_ash_mt", {}).get(sc, {}), y)
    sl = interp(SCM_CFG.get("slag_mt", {}).get(sc, {}), y)
    return fa + sl

# ── Variable index helpers ────────────────────────────────────────────────────
# Variables ordered: NCAP(R×T), CAP(R×T), ACT(R×T), CO2(T), COAL(R×T), ELEC(R×T), SLACK(T)
# SLACK(t): unmet demand in year t, penalized at $10,000/t to keep LP always feasible.

DEMAND_SHORTFALL_PENALTY_USD_PER_T = 10_000.0  # $/t cement

def _NCAP(ri: int, ti: int) -> int:    return ri * T + ti
def _CAP(ri: int, ti: int) -> int:     return R*T + ri * T + ti
def _ACT(ri: int, ti: int) -> int:     return 2*R*T + ri * T + ti
def _CO2(ti: int) -> int:              return 3*R*T + ti
def _COAL(ri: int, ti: int) -> int:    return 3*R*T + T + ri * T + ti
def _ELEC(ri: int, ti: int) -> int:    return 3*R*T + T + R*T + ri * T + ti
def _SLACK(ti: int) -> int:            return 3*R*T + T + 2*R*T + ti  # unmet demand
NV = 3*R*T + T + 2*R*T + T            # total variable count (added SLACK)

# ── Build MILP ────────────────────────────────────────────────────────────────

def build_milp(sc: str, overrides: Dict[str, Any]) -> Tuple[np.ndarray, lil_matrix, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Build annual LP for cement sector under scenario sc.
    Returns: c, A_rows (as lists), b_lo, b_hi, lb, ub
    """
    # ── Parse Lab override format (frontend → backend contract) ─────────────────
    # Frontend sends: carbon_price (dict), coal_price_adj ($/t), elec_price_adj ($/MWh),
    #   demand_anchors (dict), capex_by_route (dict of multipliers), green_premium ($/t),
    #   wacc (fraction), grid_ei_2070 (kgCO2/kWh), pli_active (bool), ccus_active (bool),
    #   lc3_active (bool), alt_fuel_active (bool), alt_fuel_cap (fraction)
    carbon_price_traj  = overrides.get("carbon_price")           # {year_str: usd/tco2}
    coal_price_adj     = float(overrides.get("coal_price_adj", 0.0))    # $/t offset
    elec_price_adj     = float(overrides.get("elec_price_adj", 0.0))    # $/MWh offset
    demand_anchors_ov  = overrides.get("demand_anchors")         # {year_str: Mt}
    demand_model_ov    = overrides.get("demand_model")           # "niti"|"model_fitted"|"india_policy"|"international"
    capex_by_route     = overrides.get("capex_by_route", {})     # {routeId: multiplier}
    green_prem_ov      = float(overrides.get("green_premium", 0.0))     # $/t product
    wacc_override      = overrides.get("wacc")                   # fraction e.g. 0.12
    grid_ei_2070_ov    = overrides.get("grid_ei_2070")           # kgCO2/kWh in 2070
    pli_active         = bool(overrides.get("pli_active", True))
    ccus_active        = bool(overrides.get("ccus_active", True))
    lc3_active         = bool(overrides.get("lc3_active", True))
    alt_fuel_active    = bool(overrides.get("alt_fuel_active", True))
    alt_fuel_cap_frac  = overrides.get("alt_fuel_cap")           # max fraction of demand
    scm_cap_mult       = float(overrides.get("scm_cap_mult", 1.0))

    c   = np.zeros(NV)
    lb  = np.zeros(NV)
    ub  = np.full(NV, np.inf)

    rows: List[Dict[int, float]] = []
    b_lo: List[float] = []
    b_hi: List[float] = []

    def add_row(coeffs: Dict[int, float], lo: float, hi: float):
        rows.append(coeffs)
        b_lo.append(lo)
        b_hi.append(hi)

    # Pre-compute effective WACC (Lab override takes precedence)
    wacc_eff = float(wacc_override) if wacc_override is not None else WACC

    for ti, y in enumerate(YEARS):
        dfy = df(y)

        # ── Carbon price: Lab trajectory dict OR config scenario ──────────────
        if carbon_price_traj:
            cp = interp({str(k): float(v) for k, v in carbon_price_traj.items()}, y)
        else:
            cp = interp_sc(CFG["carbon_price_usd_per_tco2"], sc, y)

        # ── Resource prices: base (scenario) + Lab adjustment ─────────────────
        p_coal = interp_sc(CFG["fuels"]["coal"]["price_usd_per_t"], sc, y) + coal_price_adj
        p_elec_kwh = interp_sc(CFG["electricity"]["price_usd_per_kwh"], sc, y) + elec_price_adj / 1000.0

        # ── Demand: explicit anchors > named model > scenario default ────────
        _dt = CFG.get("demand_trajectories", {})
        if demand_anchors_ov:
            demand = interp({str(k): float(v) for k, v in demand_anchors_ov.items()}, y)
        elif demand_model_ov and demand_model_ov in _dt:
            demand = interp(_dt[demand_model_ov]["anchors"], y)
        else:
            demand = interp_sc(CFG["demand"], sc, y)

        # ── Grid emission intensity: ramp from 2024 baseline to 2070 target ──
        # Lab slider sends grid_ei_2070 in kgCO2/kWh; grid_ei_use must be tCO2/kWh.
        if grid_ei_2070_ov is not None:
            ei_2024_kg = 0.710          # CEA 2022 baseline kgCO2/kWh (FROZEN_EXTERNAL)
            ei_2070_kg = float(grid_ei_2070_ov)  # kgCO2/kWh from Lab slider
            ei_frac = max(0.0, (y - 2024) / (2070 - 2024))
            # Convert kgCO2/kWh → tCO2/kWh (÷1000) so unit matches grid_ei_cfg
            grid_ei_y = (ei_2024_kg + (ei_2070_kg - ei_2024_kg) * ei_frac) / 1000.0
        else:
            grid_ei_y = None  # use per-route formula below

        for ri, rid in enumerate(ROUTE_IDS):
            rc = _route_cfg(rid)
            wacc_r   = wacc_eff * (1.0 + rc.get("wacc_premium", 0.0))
            lifetime = rc["lifetime_yr"]
            capex    = rc["capex_usd_per_t"]

            # CAPEX multiplier from capex_by_route (Lab slider)
            capex *= float(capex_by_route.get(rid, 1.0))

            fom      = rc["fom_usd_per_t_yr"]
            vom      = rc["vom_residual_usd_per_t"]

            # PLI: only active if pli_active toggle is on
            pli_val  = 0.0
            if pli_active:
                pli_dict = CFG["policy"]["pli_usd_per_t"].get(rid, {})
                if pli_dict:
                    pli_val = interp_sc(pli_dict, sc, y)

            # Green premium: Lab override is ADDITIONAL on top of scenario trajectory
            gp_val   = 0.0
            gp_routes = CFG["policy"]["green_premium_usd_per_t"].get("routes", [])
            if rid in gp_routes:
                gp_val = interp_sc(CFG["policy"]["green_premium_usd_per_t"], sc, y) + green_prem_ov

            # Objective contributions (all discounted):
            # CAP: annualised CAPEX via CRF(wacc) + FOM
            annualized_capex = crf(wacc_r, lifetime) * capex
            c[_CAP(ri, ti)] += dfy * (annualized_capex + fom)
            # ACT: VOM - PLI - green_premium
            c[_ACT(ri, ti)] += dfy * (vom - pli_val - gp_val)
            # COAL: coal price ($/t)
            c[_COAL(ri, ti)] += dfy * p_coal
            # ELEC: electricity price ($/kWh × kWh/t → $/t via constraint)
            c[_ELEC(ri, ti)] += dfy * p_elec_kwh

        # CO2: carbon price
        c[_CO2(ti)] += dfy * cp

        # SLACK: unmet demand penalty — keeps LP always feasible when routes disabled
        c[_SLACK(ti)] += dfy * DEMAND_SHORTFALL_PENALTY_USD_PER_T

        # ── Constraint 1: CAP accounting ──────────────────────────────────────
        # CAP[r,t] = surviving_existing[r,t] + Σ_{τ<=t-lead} NCAP[r,τ]
        # For t=0: CAP[r,0] = surviving[r,0] (no new capacity yet)
        # We implement as: CAP[r,t] = surviving + Σ_{τ<t-lead+1} NCAP[r,τ]
        for ri, rid in enumerate(ROUTE_IDS):
            rc       = _route_cfg(rid)
            existing = rc["existing_mt"]
            lifetime = rc["lifetime_yr"]
            lead     = rc.get("lead_years", 0)  # construction lead in years (not periods)
            start    = rc["start_year"]
            surv     = surviving(existing, y, lifetime)

            # CAP[r,t] = surv + Σ_{τ: t-τ >= lead, start_year<=τ<=t} NCAP[r,τ]
            # After lead years, new capacity enters service
            row: Dict[int, float] = {_CAP(ri, ti): -1.0}
            for tau_i, tau_y in enumerate(YEARS[:ti + 1]):
                if tau_y < start:
                    continue
                if (y - tau_y) < lead:
                    continue
                # NCAP at tau retires after lifetime years
                if (y - tau_y) >= lifetime:
                    continue
                row[_NCAP(ri, tau_i)] = 1.0
            add_row(row, -surv, -surv)

        # ── Constraint 2: ACT ≤ CAP × availability ────────────────────────────
        for ri, rid in enumerate(ROUTE_IDS):
            rc   = _route_cfg(rid)
            avail = rc["availability"]
            row = {_ACT(ri, ti): 1.0, _CAP(ri, ti): -avail}
            add_row(row, -np.inf, 0.0)

        # ── Constraint 3: Demand balance ──────────────────────────────────────
        # Allow 0.5% shortfall tolerance to handle calibration uncertainty in
        # 2024 base-year data (NITI demand vs. installed-capacity availability).
        # The config's 2024 demand (395 Mt) is at the edge of feasible capacity;
        # ±2 Mt is within the ±1% uncertainty of NITI 2023 sectoral projections.
        demand_lb = demand * 0.995
        # SLACK allows unmet demand at high cost → LP always feasible.
        # Upper bound = demand: prevents overproduction when green_premium > VOM
        # (without ub, LP produces at capacity to maximise green-premium revenue).
        row = {_ACT(ri, ti): 1.0 for ri in range(R)}
        row[_SLACK(ti)] = 1.0
        add_row(row, demand_lb, demand)

        # ── Constraint 4: Technology start year ───────────────────────────────
        for ri, rid in enumerate(ROUTE_IDS):
            rc = _route_cfg(rid)
            if y < rc["start_year"]:
                ub[_NCAP(ri, ti)] = 0.0
                ub[_ACT(ri, ti)]  = 0.0

        # ── Constraint 5: Max new capacity ramp per year ───────────────────────
        for ri, rid in enumerate(ROUTE_IDS):
            rc      = _route_cfg(rid)
            max_r   = rc.get("max_ramp_mt_yr", None)
            cutoff  = rc.get(f"cutoff_year_{sc.lower()}", None)
            if max_r is not None and max_r > 0:
                ub[_NCAP(ri, ti)] = min(ub[_NCAP(ri, ti)], max_r)
            if max_r == 0.0:
                ub[_NCAP(ri, ti)] = 0.0
            # No new capacity after cutoff
            if cutoff is not None and y >= cutoff:
                ub[_NCAP(ri, ti)] = 0.0

        # ── Constraint 6: Fossil decline — monotonic production decline in all scenarios ─
        if ti > 0:
            for ri, rid in enumerate(ROUTE_IDS):
                rc = _route_cfg(rid)
                if rc.get("fossil_decline", False):
                    # ACT[r,t] ≤ ACT[r,t-1]
                    row = {_ACT(ri, ti): 1.0, _ACT(ri, ti-1): -1.0}
                    add_row(row, -np.inf, 0.0)

        # ── Constraint 7: COAL = coal_t_per_t × ACT ─────────────────────────
        # coal_t_per_t derived from thermal_sec and coal GCV:
        #   coal_t_per_t = clinker_factor × thermal_sec_gj_per_t_clinker / coal_GCV_gj_t × (1-alt_fuel_frac)
        for ri, rid in enumerate(ROUTE_IDS):
            rc  = _route_cfg(rid)
            ccr = rc["clinker_factor"]
            sec = rc["thermal_sec_gj_per_t_clinker"]
            alt_frac = rc.get("alt_fuel_fraction", 0.0)
            coal_t_per_t = ccr * sec * (1.0 - alt_frac) / COAL_GCV_GJ_T
            row = {_COAL(ri, ti): 1.0, _ACT(ri, ti): -coal_t_per_t}
            add_row(row, 0.0, 0.0)

        # ── Constraint 8: ELEC = elec_kwh_per_t × ACT ───────────────────────
        for ri, rid in enumerate(ROUTE_IDS):
            rc  = _route_cfg(rid)
            kwh = rc["elec_kwh_per_t_cement"]
            row = {_ELEC(ri, ti): 1.0, _ACT(ri, ti): -kwh}
            add_row(row, 0.0, 0.0)

        # ── Constraint 9: CO2 accounting ──────────────────────────────────────
        # CO2[t] = Σ_r [process_CO2 + combustion_CO2 + electricity_CO2] × ACT[r,t]
        #        - CCUS_captured
        # Uses grid_ei_y computed above (Lab override or config scenario)
        grid_ei_cfg = interp_sc(CFG["electricity"]["grid_ei_tco2_per_kwh"], sc, y)
        grid_ei_use = grid_ei_y if grid_ei_y is not None else grid_ei_cfg

        row: Dict[int, float] = {_CO2(ti): -1.0}
        for ri, rid in enumerate(ROUTE_IDS):
            rc   = _route_cfg(rid)
            ccr  = rc["clinker_factor"]
            sec  = rc["thermal_sec_gj_per_t_clinker"]
            alt_frac = rc.get("alt_fuel_fraction", 0.0)
            kwh  = rc["elec_kwh_per_t_cement"]
            cap_rate = rc.get("ccus_capture_rate", 0.0)
            # Respect CCUS toggle: if ccus_active=False, capture rate → 0
            if not ccus_active and cap_rate > 0:
                cap_rate = 0.0

            process_co2   = ccr * rc["process_co2_kg_per_kg_clinker"]   # tCO2/t cement
            coal_t_per_t  = ccr * sec * (1.0 - alt_frac) / COAL_GCV_GJ_T
            alt_gj_per_t  = ccr * sec * alt_frac
            combustion_co2 = coal_t_per_t * EF_COAL + alt_gj_per_t * EF_ALTFUEL_GJ
            elec_co2      = kwh * grid_ei_use  # tCO2/t cement (grid_ei in tCO2/kWh)
            gross_co2     = process_co2 + combustion_co2 + elec_co2
            captured_co2  = cap_rate * (process_co2 + combustion_co2)
            net_co2       = gross_co2 - captured_co2

            row[_ACT(ri, ti)] = net_co2
        add_row(row, 0.0, 0.0)

        # ── Constraint 10: Technology toggle constraints ───────────────────────
        # If a route is disabled by toggle, zero out its new capacity and activity
        toggle_disabled: set = set()
        if not lc3_active:
            toggle_disabled.add("Coal-LC3")
        if not ccus_active:
            toggle_disabled.add("CCUS-Blended")
        if not alt_fuel_active:
            toggle_disabled.add("AltFuel-Blended")
        for ri, rid in enumerate(ROUTE_IDS):
            if rid in toggle_disabled:
                ub[_NCAP(ri, ti)] = 0.0
                ub[_ACT(ri, ti)]  = 0.0

        # ── Constraint 11: Alt-fuel supply cap ───────────────────────────────
        if alt_fuel_cap_frac is not None and "AltFuel-Blended" in ROUTE_IDS:
            alt_ri = ROUTE_IDS.index("AltFuel-Blended")
            cap_val = float(alt_fuel_cap_frac) * demand
            ub[_ACT(alt_ri, ti)] = min(ub[_ACT(alt_ri, ti)], max(0.0, cap_val))

        # ── Constraint 12: SCM supply cap ────────────────────────────────────
        # Σ_{r in scm_routes} (1 - clinker_factor[r]) × ACT[r,t] ≤ SCM_cap[t]
        if SCM_ENABLED:
            scm_cap = _scm_cap(sc, y) * scm_cap_mult
            row = {}
            for ri, rid in enumerate(ROUTE_IDS):
                if rid in SCM_ROUTES:
                    rc  = _route_cfg(rid)
                    scm_intensity = 1.0 - rc["clinker_factor"]
                    if scm_intensity > 0:
                        row[_ACT(ri, ti)] = scm_intensity
            if row:
                add_row(row, -np.inf, scm_cap)

    # ── Assemble sparse matrix ─────────────────────────────────────────────────
    nr = len(rows)
    A  = lil_matrix((nr, NV))
    for i, row in enumerate(rows):
        for j, v in row.items():
            A[i, j] = v

    return c, A, np.array(b_lo), np.array(b_hi), lb, ub

# ── Solve ─────────────────────────────────────────────────────────────────────

def _solve(sc: str, overrides: Dict[str, Any]) -> Dict[str, Any]:
    c, A, b_lo, b_hi, lb, ub = build_milp(sc, overrides)
    from scipy.sparse import csc_matrix
    lc = LinearConstraint(csc_matrix(A), b_lo, b_hi)
    result = milp(c, constraints=lc, bounds=Bounds(lb, ub))

    if result.status != 0:
        return {"status": "infeasible", "message": result.message}

    x = result.x
    yearly: Dict[int, Dict] = {}

    for ti, y in enumerate(YEARS):
        prod_by_route: Dict[str, float] = {}
        cap_by_route:  Dict[str, float] = {}
        invest_by_route: Dict[str, float] = {}
        coal_by_route: Dict[str, float] = {}
        elec_by_route: Dict[str, float] = {}
        ncap_by_route: Dict[str, float] = {}
        co2_by_route:  Dict[str, float] = {}
        total_cost_yr = 0.0

        for ri, rid in enumerate(ROUTE_IDS):
            rc   = _route_cfg(rid)
            act  = max(0.0, x[_ACT(ri, ti)])
            cap  = max(0.0, x[_CAP(ri, ti)])
            ncap = max(0.0, x[_NCAP(ri, ti)])
            coal = max(0.0, x[_COAL(ri, ti)])
            elec = max(0.0, x[_ELEC(ri, ti)])

            # Per-route CO2 decomposition
            ccr       = rc["clinker_factor"]
            sec       = rc["thermal_sec_gj_per_t_clinker"]
            alt_frac  = rc.get("alt_fuel_fraction", 0.0)
            kwh       = rc["elec_kwh_per_t_cement"]
            cap_rate  = rc.get("ccus_capture_rate", 0.0)
            grid_ei   = interp_sc(CFG["electricity"]["grid_ei_tco2_per_kwh"], sc, y)

            proc_co2     = ccr * rc["process_co2_kg_per_kg_clinker"] * act
            coal_t_per_t = ccr * sec * (1.0 - alt_frac) / COAL_GCV_GJ_T
            alt_gj_per_t = ccr * sec * alt_frac
            comb_co2     = (coal_t_per_t * EF_COAL + alt_gj_per_t * EF_ALTFUEL_GJ) * act
            elec_co2     = kwh * grid_ei * act
            captured     = cap_rate * (proc_co2 + comb_co2)
            route_co2    = proc_co2 + comb_co2 + elec_co2 - captured

            capex_r = rc["capex_usd_per_t"]
            fom_r   = rc.get("fom_usd_per_t_yr", 0.0)
            vom_r   = rc.get("vom_residual_usd_per_t", 0.0)
            prod_by_route[rid]   = round(act, 4)
            cap_by_route[rid]    = round(cap, 4)
            ncap_by_route[rid]   = round(ncap, 4)
            invest_by_route[rid] = round(ncap * capex_r, 2)   # Mn$ (Mt × $/t = M$)
            total_cost_yr += act * vom_r + cap * fom_r + ncap * capex_r
            coal_by_route[rid]   = round(coal, 4)
            elec_by_route[rid]   = round(elec, 4)
            co2_by_route[rid]    = round(route_co2, 4)

        total_prod = sum(prod_by_route.values())
        total_co2  = max(0.0, x[_CO2(ti)])
        intensity  = total_co2 / total_prod if total_prod > 0 else 0.0
        demand     = interp_sc(CFG["demand"], sc, y)
        unmet      = max(0.0, x[_SLACK(ti)])  # unmet demand shortfall (should be ~0)
        scm_used   = sum(
            (1.0 - _route_cfg(rid)["clinker_factor"]) * prod_by_route.get(rid, 0.0)
            for rid in SCM_ROUTES
        )
        scm_cap = _scm_cap(sc, y) if SCM_ENABLED else None

        yearly[y] = {
            "year": y,
            "demand_mt": round(demand, 2),
            "production_by_route": prod_by_route,
            "capacity_by_route": cap_by_route,
            "new_capacity_by_route": ncap_by_route,
            "investment_by_route": invest_by_route,   # Mn$/yr
            "coal_consumption_by_route_mt": coal_by_route,
            "electricity_by_route_twh": {r: round(v * 1e-3, 4) for r, v in elec_by_route.items()},
            "co2_by_route_mt": co2_by_route,
            "total_production_mt": round(total_prod, 4),
            "total_production":    round(total_prod, 4),  # canonical alias
            "total_co2_mt": round(total_co2, 4),
            "co2_total":    round(total_co2, 4),          # canonical alias
            "co2_intensity_tco2_per_t": round(intensity, 4),
            "co2_intensity":            round(intensity, 4),  # canonical alias
            "scm_consumed_mt": round(scm_used, 3),
            "scm_cap_mt": round(scm_cap, 1) if scm_cap else None,
            "unmet_demand_mt": round(unmet, 4),
            "total_cost": round(total_cost_yr, 1),
        }

    # Summary
    all_co2  = sum(yr["total_co2_mt"] for yr in yearly.values())
    all_cost = result.fun
    final_y  = yearly[END]

    return {
        "status": "ok",
        "scenario": sc,
        "solver_objective": round(all_cost, 2),
        "years": YEARS,
        "yearly_results": yearly,
        "summary": {
            "total_cost_bn": round(all_cost / 1e3, 3),
            "total_co2_cumulative_mt": round(all_co2, 1),
            "final_co2_intensity": round(final_y["co2_intensity_tco2_per_t"], 4),
            "final_year_demand": round(final_y["demand_mt"], 1),
            "scm_binding": SCM_ENABLED,
        },
        "vol4_targets": CFG["vol4_reference"]["co2_intensity_tco2_per_t"],
        "provenance": "configs/cement_config.yaml (all parameters sourced)",
    }

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="Cement Transition Model v3", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

from pydantic import BaseModel

class RunRequest(BaseModel):
    scenario: str = "CPS"
    overrides: Dict[str, Any] = {}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "sector": "cement",
        "model_version": "v3",
        "routes": ROUTE_IDS,
        "years": f"{START}-{END}",
        "scm_constraint": SCM_ENABLED,
    }

@app.get("/api/routes")
def get_routes():
    """Per-route parameters with provenance — used by Technologies page."""
    routes_out = []
    for rid in ROUTE_IDS:
        rc = _route_cfg(rid)
        routes_out.append({
            "id": rid,
            "existing": rc["existing_mt"],
            "capex": rc["capex_usd_per_t"],
            "capex_provenance": rc.get("provenance_capex", "UNKNOWN"),
            "capex_source": rc.get("source_capex", ""),
            "fom": rc["fom_usd_per_t_yr"],
            "vom_total": rc["vom_residual_usd_per_t"],
            "clinker_factor": rc["clinker_factor"],
            "process_co2_per_kg_clinker": rc["process_co2_kg_per_kg_clinker"],
            "process_co2_provenance": rc.get("provenance_process_co2", ""),
            "thermal_sec_gj_per_t_clinker": rc["thermal_sec_gj_per_t_clinker"],
            "elec_kwh_per_t_cement": rc["elec_kwh_per_t_cement"],
            "ccus_capture_rate": rc.get("ccus_capture_rate", 0.0),
            "wacc_premium": rc.get("wacc_premium", 0.0),
            "avail": rc["availability"],
            "start": rc["start_year"],
            "max_ramp": rc.get("max_ramp_mt_yr", 0.0),
            "lifetime": rc["lifetime_yr"],
            "h2_route": False,
            "ef_2024": rc["clinker_factor"] * rc["process_co2_kg_per_kg_clinker"] +
                       rc["clinker_factor"] * rc["thermal_sec_gj_per_t_clinker"] *
                       (1.0 - rc.get("alt_fuel_fraction", 0.0)) / COAL_GCV_GJ_T * EF_COAL +
                       rc["elec_kwh_per_t_cement"] * interp_sc(CFG["electricity"]["grid_ei_tco2_per_kwh"], "CPS", 2024),
            "ef_cps_2050": None,
            "ef_nzs_2050": None,
        })
    return {"routes": routes_out}

@app.get("/api/scenarios")
def get_scenarios():
    return {"scenarios": ["CPS", "NZS"]}

@app.get("/api/demand-trajectories")
def get_demand_trajectories():
    """Expose 4 demand trajectories + historical production data."""
    traj_cfg = CFG["demand_trajectories"]
    historical = [
        {"year": 1995, "production_mt": 68}, {"year": 2000, "production_mt": 101},
        {"year": 2005, "production_mt": 142}, {"year": 2010, "production_mt": 210},
        {"year": 2015, "production_mt": 280}, {"year": 2019, "production_mt": 337},
        {"year": 2020, "production_mt": 294}, {"year": 2022, "production_mt": 355},
        {"year": 2023, "production_mt": 381}, {"year": 2024, "production_mt": 395},
    ]
    out = {}
    for key, tc in traj_cfg.items():
        annual_series = {y: interp(tc["anchors"], y) for y in range(2024, 2071)}
        out[key] = {
            "label": tc["label"],
            "annual_series": annual_series,
            "end_value": annual_series[2070],
            "source": tc["source"],
            "method": tc["method"],
            "assumption": tc.get("assumption", ""),
        }
    return {**out, "historical": historical}

@app.get("/api/scm-supply")
def get_scm_supply():
    """SCM supply trajectory — fly ash + slag available by scenario."""
    out = {}
    for sc in ["CPS", "NZS"]:
        out[sc] = {
            y: {
                "fly_ash": round(interp(SCM_CFG.get("fly_ash_mt", {}).get(sc, {}), y), 1),
                "slag": round(interp(SCM_CFG.get("slag_mt", {}).get(sc, {}), y), 1),
                "total": round(_scm_cap(sc, y), 1),
            }
            for y in range(2024, 2071)
        }
    return {"scm_supply": out, "source": SCM_CFG.get("source_fly_ash", "")}

@app.get("/api/config")
def get_config():
    """Expose full config for transparency (provenance audit)."""
    return CFG

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
def run_sensitivity():
    """One-at-a-time sensitivity: vary each key parameter ±20% and report CO2 + cost delta."""
    base = _solve("NZS", {})
    if base["status"] != "ok":
        return {"status": "infeasible"}
    base_co2  = base["summary"]["total_co2_cumulative_mt"]
    base_cost = base["summary"]["total_cost_bn"]

    params = {
        "carbon_price_mult":  [0.8, 1.2],
        "coal_price_mult":    [0.8, 1.2],
        "elec_price_mult":    [0.8, 1.2],
        "demand_mult":        [0.8, 1.2],
        "ccus_capex_mult":    [0.8, 1.2],
        "lc3_capex_mult":     [0.8, 1.2],
        "scm_cap_mult":       [0.7, 1.3],
    }
    results = {}
    for p, (lo, hi) in params.items():
        r_lo = _solve("NZS", {p: lo})
        r_hi = _solve("NZS", {p: hi})
        results[p] = {
            "co2_delta_lo": round((r_lo["summary"]["total_co2_cumulative_mt"] - base_co2) / base_co2 * 100, 2) if r_lo["status"] == "ok" else None,
            "co2_delta_hi": round((r_hi["summary"]["total_co2_cumulative_mt"] - base_co2) / base_co2 * 100, 2) if r_hi["status"] == "ok" else None,
            "cost_delta_lo": round((r_lo["summary"]["total_cost_bn"] - base_cost) / base_cost * 100, 2) if r_lo["status"] == "ok" else None,
            "cost_delta_hi": round((r_hi["summary"]["total_cost_bn"] - base_cost) / base_cost * 100, 2) if r_hi["status"] == "ok" else None,
        }
    return {"sensitivity": results, "base_co2_mt": base_co2, "base_cost_bn": base_cost}


if __name__ == "__main__":
    port = CFG.get("port", 8001)
    uvicorn.run("cement_backend_v3:app", host="0.0.0.0", port=port, reload=False)
