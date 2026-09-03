"""
Aluminium Transition Backend v2 — India Transition Lab  (port 8002)
====================================================================
Steel-grade LP. Key physics: electricity is the dominant cost
(electrolysis = 13 000–14 500 kWh/t Al). Two electricity resources:
  coal_elec — captive coal power plant (Coal-CPP route)
  grid_elec — India grid, whose emissions intensity declines with RE rollout
  re_elec   — captive/wheeled renewable electricity, price falls faster in NZS
Secondary aluminium uses far less energy (700 kWh/t) and is scrap-supply limited.

Upgrades over v1 (shared milp_sector_backend.py):
  1. CRF-annualised CAPEX on CAP per period
  2. WACC per route (Inert-Anode 25% premium; RE-Electrolysis 10%)
  3. Three electricity resources with scenario-specific price trajectories
  4. Explicit CO2[t] variable; grid-connected routes automatically benefit
     from India's grid decarbonisation via GRID_EI trajectory
  5. PLI subsidies — National Aluminium Mission / Green Hydrogen Mission
  6. Lead time: Inert-Anode 2 periods (greenfield + pilot)
  7. Monotonic Coal-CPP production decline in NZS (post-2030)

Sources: IEA Al Roadmap 2022; World Aluminium 2023; Aluminium Association of India 2023;
         CEEW India aluminium energy benchmarks 2023; MNRE solar/wind cost forecasts 2023.
"""
from __future__ import annotations
import sys
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

YEARS     = [2024 + 5 * i for i in range(10)]
ALL_YEARS = list(range(2024, 2071))
DT  = 5
BASE = 2024
WACC = 0.08
SECTOR = "aluminium"
PORT   = 8002

def crf(r: float, n: int) -> float:
    if r == 0 or n == 0: return 1.0 / max(n, 1)
    return r * (1 + r)**n / ((1 + r)**n - 1)

def interp(anchors: Dict[int, float], y: int) -> float:
    ks = sorted(anchors)
    if not ks: return 0.0
    if y <= ks[0]: return anchors[ks[0]]
    if y >= ks[-1]: return anchors[ks[-1]]
    for lo, hi in zip(ks, ks[1:]):
        if lo <= y <= hi:
            f = (y - lo) / (hi - lo)
            return anchors[lo] + f * (anchors[hi] - anchors[lo])
    return anchors[ks[-1]]

def surviving(existing: float, y: int, lifetime: int) -> float:
    age = y - BASE
    if age >= lifetime: return 0.0
    return existing * (1.0 - age / lifetime)

# Grid EI trajectory (tCO2/kWh) — affects Grid-Electrolysis CO2 intensity
GRID_EI: Dict[str, Dict[int, float]] = {
    "CPS": {2024: 0.710, 2030: 0.620, 2040: 0.475, 2050: 0.370, 2060: 0.270, 2070: 0.195},
    "NZS": {2024: 0.710, 2030: 0.530, 2040: 0.295, 2050: 0.140, 2060: 0.055, 2070: 0.018},
}

# ── ROUTE DATA ────────────────────────────────────────────────────────────────
# Electricity intensities (kWh/t Al):
#   Coal-CPP:           14 500 (captive coal power plant, Hall-Héroult)
#   Grid-Electrolysis:  13 500 (grid-connected Hall-Héroult, improving over time)
#   RE-Electrolysis:    13 800 (renewable captive/wheeled, slightly higher due to curtailment)
#   Inert-Anode:        12 500 (inert anode → no CO2 from anode oxidation, lower energy)
#   Secondary-Al:           700 (remelting; only ~5% of primary energy)
#
# Coal intensity (t coal/t Al) for Coal-CPP:
#   14 500 kWh × 3.6 MJ/kWh / (0.35 efficiency) / (25 GJ/t coal) = 5.97 t coal/t Al ≈ 6.0
# EF baseline for Grid-Electrolysis includes grid EI at 2024 (0.71 tCO2/kWh):
#   13 500 × 0.71 / 1000 = 9.6... but Vol.4 / AAI say 2.8 tCO2/t in 2024.
#   Reason: AAI uses lower grid EI (0.56 kg/kWh average plant mix); also anode CO2 adds ~1.5 t.
#   We use calibrated ef_2024 matching AAI benchmark and let GRID_EI shape the decline.

ROUTES: List[Dict[str, Any]] = [
    {
        "id": "Coal-CPP",
        "existing": 3.90,           # Mt capacity 2024 (NALCO, HINDALCO captive)
        "lifetime": 30,
        "capex": 820.0,             # USD/t (smelter + dedicated coal power plant)
        "fom": 65.0,
        "vom_residual": 35.0,       # non-energy VOM (anode paste, alumina handling, labour)
        "wacc_mult": 1.00,
        "lead_p": 0,
        "fossil_decline": True,
        "avail": 0.88,
        "start": 2024,
        "max_ramp": 0.8,
        "cutoff_cps": None,
        "cutoff_nzs": 2030,
        "ef_2024": 4.60, "ef_cps_2050": 3.80, "ef_cps_2070": 3.20,
                         "ef_nzs_2050": 2.80, "ef_nzs_2070": 2.00,
        # Resources: coal only (captive plant)
        "coal_t_per_t": 6.0,
        "grid_kwh_per_t": 0.0,
        "re_kwh_per_t": 0.0,
    },
    {
        "id": "Grid-Electrolysis",
        "existing": 0.30,
        "lifetime": 30,
        "capex": 760.0,             # USD/t (greenfield smelter, grid connected)
        "fom": 58.0,
        "vom_residual": 20.0,
        "wacc_mult": 1.00,
        "lead_p": 0,
        "fossil_decline": True,     # grid mix still high-carbon; decline as grid greens
        "avail": 0.88,
        "start": 2024,
        "max_ramp": 1.5,
        "cutoff_cps": None,
        "cutoff_nzs": 2040,
        "ef_2024": 2.80, "ef_cps_2050": 2.00, "ef_cps_2070": 1.60,
                         "ef_nzs_2050": 1.00, "ef_nzs_2070": 0.40,
        "coal_t_per_t": 0.0,
        "grid_kwh_per_t": 13500.0,  # kWh/t Al (grid electricity)
        "re_kwh_per_t": 0.0,
        "grid_ei_route": True,      # CO2 EF dynamically adjusts with GRID_EI trajectory
    },
    {
        "id": "RE-Electrolysis",
        "existing": 0.15,
        "lifetime": 25,
        "capex": 950.0,             # USD/t (smelter + dedicated RE park + wheeling infra)
        "fom": 70.0,
        "vom_residual": 22.0,
        "wacc_mult": 1.10,          # RE project finance premium in India
        "lead_p": 0,
        "fossil_decline": False,
        "avail": 0.85,
        "start": 2024,
        "max_ramp": 2.0,
        "cutoff_cps": None,
        "cutoff_nzs": None,
        "ef_2024": 0.30, "ef_cps_2050": 0.22, "ef_cps_2070": 0.18,
                         "ef_nzs_2050": 0.15, "ef_nzs_2070": 0.10,
        "coal_t_per_t": 0.0,
        "grid_kwh_per_t": 0.0,
        "re_kwh_per_t": 13800.0,    # captive/wheeled RE electricity
    },
    {
        "id": "Inert-Anode",
        "existing": 0.0,
        "lifetime": 25,
        "capex": 1400.0,            # USD/t (novel electrolyser + inert anode retrofit)
        "fom": 90.0,
        "vom_residual": 30.0,       # reduced anode paste vs Hall-Héroult
        "wacc_mult": 1.25,          # early-mover risk premium (pre-commercial in India)
        "lead_p": 1,                # 2 periods: pilot (2029) → commercial (2034)
        "fossil_decline": False,
        "avail": 0.82,
        "start": 2034,              # earliest commercial availability
        "max_ramp": 1.5,
        "cutoff_cps": None,
        "cutoff_nzs": None,
        "ef_2024": 0.08, "ef_cps_2050": 0.06, "ef_cps_2070": 0.04,
                         "ef_nzs_2050": 0.04, "ef_nzs_2070": 0.02,
        "coal_t_per_t": 0.0,
        "grid_kwh_per_t": 0.0,
        "re_kwh_per_t": 12500.0,    # uses RE (lower energy than Hall-Héroult)
    },
    {
        "id": "Secondary-Al",
        "existing": 0.80,
        "lifetime": 20,
        "capex": 220.0,
        "fom": 22.0,
        "vom_residual": 30.0,       # scrap sorting, de-lacquering, alloying
        "wacc_mult": 1.00,
        "lead_p": 0,
        "fossil_decline": False,
        "avail": 0.88,
        "start": 2024,
        "max_ramp": 1.0,
        "cutoff_cps": None,
        "cutoff_nzs": None,
        "ef_2024": 0.52, "ef_cps_2050": 0.40, "ef_cps_2070": 0.32,
                         "ef_nzs_2050": 0.28, "ef_nzs_2070": 0.18,
        "coal_t_per_t": 0.0,
        "grid_kwh_per_t": 700.0,    # remelting electricity
        "re_kwh_per_t": 0.0,
        "scrap_frac_cap": {2024: 0.16, 2030: 0.20, 2040: 0.28, 2050: 0.36, 2070: 0.45},
    },
]

# ── RESOURCES ─────────────────────────────────────────────────────────────────
# K=0: coal electricity (USD/t coal — Coal-CPP only)
# K=1: grid electricity (USD/kWh — Grid-Electrolysis, Secondary-Al)
# K=2: renewable electricity (USD/kWh — RE-Electrolysis, Inert-Anode)
RESOURCES: List[Dict[str, Any]] = [
    {
        "id": "coal_power",
        "name": "Thermal coal for captive CPP (USD/t)",
        "price": {
            "CPS": {2024:100, 2030:92, 2040:78, 2050:63, 2060:52, 2070:44},
            "NZS": {2024:100, 2030:82, 2040:58, 2050:38, 2060:28, 2070:18},
        },
        "int_key": "coal_t_per_t",
    },
    {
        "id": "grid_elec",
        "name": "India grid electricity (USD/kWh)",
        "price": {
            "CPS": {2024:0.068, 2030:0.065, 2040:0.058, 2050:0.050, 2060:0.043, 2070:0.037},
            "NZS": {2024:0.068, 2030:0.060, 2040:0.044, 2050:0.032, 2060:0.023, 2070:0.016},
        },
        "int_key": "grid_kwh_per_t",
    },
    {
        "id": "re_elec",
        "name": "Captive / wheeled renewable electricity (USD/kWh)",
        "price": {
            # Solar + wind LCOE trajectory; significant learning-curve decline in NZS
            "CPS": {2024:0.038, 2030:0.032, 2040:0.024, 2050:0.019, 2060:0.016, 2070:0.014},
            "NZS": {2024:0.038, 2030:0.028, 2040:0.018, 2050:0.012, 2060:0.009, 2070:0.007},
        },
        "int_key": "re_kwh_per_t",
    },
]
K = len(RESOURCES)

# PLI: National Aluminium Mission + Green Hydrogen Mission (USD/t Al)
PLI: Dict[str, Dict[int, float]] = {
    "RE-Electrolysis": {2024:0, 2030: 20, 2035: 50, 2040: 80, 2050: 100, 2070: 80},
    "Inert-Anode":     {2024:0, 2030:  0, 2035: 30, 2040: 80, 2050:150, 2070:130},
    "Secondary-Al":    {2024:0, 2030:  5, 2040: 15, 2050: 25, 2070: 30},
}

GREEN_PREMIUM_ROUTES = {"RE-Electrolysis", "Inert-Anode"}
GREEN_PREMIUM: Dict[str, Dict[int, float]] = {
    "CPS": {2024: 0, 2070: 0},
    "NZS": {2024: 100, 2030: 250, 2040: 500, 2050: 800, 2070:1100},
}

DEMAND: Dict[str, Dict[int, float]] = {
    "CPS": {2024: 4.5, 2030: 7.5, 2040: 13.0, 2050: 18.0, 2060: 23.0, 2070: 28.0},
    "NZS": {2024: 4.5, 2030: 7.2, 2040: 12.5, 2050: 17.5, 2060: 22.0, 2070: 26.0},
}
CARBON_PRICE: Dict[str, Dict[int, float]] = {
    "CPS": {2024:  3, 2030: 12, 2040: 28, 2050:  50, 2060:  62, 2070:  75},
    "NZS": {2024: 15, 2030: 65, 2040:160, 2050: 270, 2060: 330, 2070: 380},
}

VOL4 = {"cps_2050": 6.5, "cps_2070": 4.2, "nzs_2050": 2.8, "nzs_2070": 0.4}
CO2_CEILING: Dict[str, Dict[int, float]] = {
    # tCO2/tAl; Coal-CPP ef_2024=4.6→ef_cps_2070=3.2; CPS: slow coal lock-in, gradual grid clean
    "CPS": {2054: 3.5, 2069: 2.8},
    "NZS": {2054: 1.5, 2069: 0.5},
}
CO2_FLOOR: Dict[str, Dict[int, float]] = {
    # CPS floor: ensures policy-inertia trajectory (coal CPP lock-in, grid reform lag)
    "CPS": {2054: 2.2, 2069: 1.6},
    "NZS": {},
}

R = len(ROUTES)
T = len(YEARS)

def _NC(r,t):  return r*T + t
def _CAP(r,t): return R*T + r*T + t
def _ACT(r,t): return 2*R*T + r*T + t
def _CO2(t):   return 3*R*T + t
def _RES(k,t): return 3*R*T + T + k*T + t
NV = 3*R*T + T + K*T

def _ef(route: Dict, sc: str, y: int) -> float:
    """EF for route. Grid-connected routes automatically adjusted via GRID_EI."""
    s = sc.lower()
    if f"ef_{s}_2050" not in route: s = "cps"
    e0, e5, e7 = route["ef_2024"], route[f"ef_{s}_2050"], route[f"ef_{s}_2070"]
    if y <= BASE: base_ef = e0
    elif y <= 2050: base_ef = e0 + (y - BASE) / 26.0 * (e5 - e0)
    else: base_ef = e5 + (y - 2050) / 20.0 * (e7 - e5)

    # Grid-EI dynamic adjustment for grid-connected routes
    if route.get("grid_ei_route") and route.get("grid_kwh_per_t", 0) > 0:
        sc_key = sc.upper() if sc.upper() in GRID_EI else "CPS"
        ei_2024 = interp(GRID_EI["CPS"], BASE)
        ei_y    = interp(GRID_EI[sc_key], y)
        # Extra EF change from grid decarbonisation (t CO2 per t Al per kWh × t CO2/kWh)
        delta = (ei_y - ei_2024) * route["grid_kwh_per_t"] / 1000.0
        return base_ef + delta
    return base_ef

def solve(
    scenario: str,
    demand_anchors: Optional[Dict[int,float]] = None,
    carbon_price_anchors: Optional[Dict[int,float]] = None,
    green_premium_val: Optional[float] = None,
    capex_mult: float = 1.0,
    wacc_adj_pct: float = 0.0,
    h2_cost_adj: float = 0.0,      # unused; kept for API compat
    enforce_co2_ceiling: bool = True,
    monotonic_fossil: bool = True,
    coal_price_adj:    float = 0.0,   # ±USD/MWh coal power (K=0: coal_power)
    re_price_adj:      float = 0.0,   # ±USD/kWh RE elec (K=2: re_elec)
    grid_price_adj:    float = 0.0,   # ±USD/MWh grid elec (K=1: grid_elec)
    pli_active:        bool  = True,
    inert_anode_active:bool  = True,  # allow inert anode route
    secondary_cap_pct: float = 0.45,  # max Secondary-Al as fraction of demand
    capex_by_route:    Optional[Dict[str, float]] = None,
    discount_rate_adj: float = 0.0,
) -> Tuple[Optional[np.ndarray], int, str]:
    sc = scenario.upper() if scenario.upper() in ("CPS","NZS") else "CPS"

    d_anch  = demand_anchors or DEMAND.get(sc, DEMAND["CPS"])
    cp_anch = carbon_price_anchors or CARBON_PRICE.get(sc, CARBON_PRICE["CPS"])
    gp_anch = ({y: green_premium_val for y in [BASE,2069]}
               if green_premium_val is not None
               else GREEN_PREMIUM.get(sc, GREEN_PREMIUM["CPS"]))

    demand = {y: interp(d_anch, y) for y in YEARS}
    eff_wacc = max(0.01, WACC + discount_rate_adj / 100.0)
    df     = {y: (1.0/(1.0+eff_wacc))**(y-BASE) for y in YEARS}
    _cbr = capex_by_route or {}

    c = np.zeros(NV)

    for ri, route in enumerate(ROUTES):
        lt      = route["lifetime"]
        route_capex_m = _cbr.get(route["id"], capex_mult)
        ann_cap = route["capex"] * route_capex_m * crf(eff_wacc, lt)
        wacc_m  = route["wacc_mult"] * (1.0 + wacc_adj_pct/100.0)
        fom     = route["fom"]
        vom_r   = route["vom_residual"]
        pli_d   = PLI.get(route["id"], {})

        for ti, y in enumerate(YEARS):
            d  = df[y]
            gp = interp(gp_anch, y) if route["id"] in GREEN_PREMIUM_ROUTES else 0.0
            pl = interp(pli_d, y) if (sc == "NZS" or pli_active) else 0.0
            ia_pen = 0.0 if inert_anode_active else (300.0 if route["id"] == "Inert-Anode" else 0.0)
            c[_CAP(ri,ti)] += d * (ann_cap * wacc_m + fom) * DT
            c[_ACT(ri,ti)] += d * (vom_r - pl - gp + ia_pen) * DT

    for ti, y in enumerate(YEARS):
        c[_CO2(ti)] += df[y] * interp(cp_anch, y)

    # K=0: coal_power, K=1: grid_elec, K=2: re_elec
    _res_adj = {0: coal_price_adj, 1: grid_price_adj, 2: re_price_adj}
    for ki, res in enumerate(RESOURCES):
        price_t = res["price"].get(sc, res["price"]["CPS"])
        adj = _res_adj.get(ki, 0.0)
        for ti, y in enumerate(YEARS):
            c[_RES(ki,ti)] += df[y] * (interp(price_t, y) + adj)

    rows: List[Tuple[float, float, Dict[int,float]]] = []
    def add(lb, ub, d): rows.append((lb, ub, d))

    # 1. Demand balance
    for ti, y in enumerate(YEARS):
        rhs = demand[y] * DT
        add(rhs, rhs, {_ACT(ri,ti): 1.0 for ri in range(R)})

    # 2. Capacity utilisation
    for ri, route in enumerate(ROUTES):
        for ti in range(T):
            add(-np.inf, 0.0, {_ACT(ri,ti): 1.0, _CAP(ri,ti): -route["avail"]*DT})

    # 3. Capacity balance (with lead time)
    for ri, route in enumerate(ROUTES):
        lt, lead_p = route["lifetime"], route["lead_p"]
        for ti, y in enumerate(YEARS):
            surv = surviving(route["existing"], y, lt)
            if ti == 0:
                row = {_CAP(ri,0): 1.0}
                if lead_p == 0: row[_NC(ri,0)] = -1.0
                add(surv, surv, row)
            else:
                delta = surv - surviving(route["existing"], YEARS[ti-1], lt)
                row = {_CAP(ri,ti): 1.0, _CAP(ri,ti-1): -1.0}
                nc_ti = ti - lead_p
                if nc_ti >= 0: row[_NC(ri,nc_ti)] = -1.0
                add(delta, delta, row)

    # 4. CO2 definition
    for ti, y in enumerate(YEARS):
        row: Dict[int,float] = {_CO2(ti): 1.0}
        for ri, route in enumerate(ROUTES):
            row[_ACT(ri,ti)] = -_ef(route, sc, y)
        add(0.0, 0.0, row)

    # 5. Resource definitions (coal, grid_elec, re_elec)
    for ki, res in enumerate(RESOURCES):
        int_key = res["int_key"]
        for ti in range(T):
            row = {_RES(ki,ti): 1.0}
            for ri, route in enumerate(ROUTES):
                intensity = route.get(int_key, 0.0)
                if intensity: row[_ACT(ri,ti)] = -intensity
            add(0.0, 0.0, row)

    # 6. Scrap fraction caps (Secondary-Al) — overridable via secondary_cap_pct
    for ri, route in enumerate(ROUTES):
        scrap_cap = route.get("scrap_frac_cap")
        if scrap_cap:
            for ti, y in enumerate(YEARS):
                base_cap = interp(scrap_cap, y)
                eff_cap = min(base_cap, secondary_cap_pct)  # user can tighten the cap
                add(-np.inf, eff_cap*demand[y]*DT, {_ACT(ri,ti): 1.0})

    # 7. CO2 ceilings + floors anchored to NITI Vol.4
    if enforce_co2_ceiling:
        for target_y, target_int in CO2_CEILING.get(sc, {}).items():
            if target_y in YEARS:
                ti = YEARS.index(target_y)
                add(-np.inf, target_int * demand[target_y] * DT, {_CO2(ti): 1.0})
        for target_y, floor_int in CO2_FLOOR.get(sc, {}).items():
            if target_y in YEARS and floor_int > 0:
                ti = YEARS.index(target_y)
                add(floor_int * demand[target_y] * DT, np.inf, {_CO2(ti): 1.0})

    # 8. Monotonic fossil decline in NZS
    if monotonic_fossil and sc == "NZS":
        start_ti = next((i for i,y in enumerate(YEARS) if y >= 2030), T-1)
        for ri, route in enumerate(ROUTES):
            if route["fossil_decline"]:
                for ti in range(start_ti, T):
                    add(-np.inf, 0.0, {_ACT(ri,ti): 1.0, _ACT(ri,ti-1): -1.0})

    # Variable bounds
    lb = np.zeros(NV)
    ub = np.full(NV, np.inf)
    for ri, route in enumerate(ROUTES):
        cutoff = route.get(f"cutoff_{sc.lower()}")
        for ti, y in enumerate(YEARS):
            if y < route["start"] or (cutoff is not None and y > cutoff):
                ub[_NC(ri,ti)] = 0.0
            else:
                ub[_NC(ri,ti)] = route["max_ramp"]*DT

    n_con = len(rows)
    A = lil_matrix((n_con, NV))
    lb_arr = np.empty(n_con); ub_arr = np.empty(n_con)
    for ci,(lo,hi,d) in enumerate(rows):
        lb_arr[ci]=lo; ub_arr[ci]=hi
        for col,val in d.items(): A[ci,col]=val

    res = milp(c, constraints=LinearConstraint(A.tocsr(), lb_arr, ub_arr),
               integrality=np.zeros(NV), bounds=Bounds(lb=lb, ub=ub),
               options={"time_limit":60.0,"disp":False})

    if res.status==0: return res.x, 0, "optimal"
    if res.status==1: return (res.x,2,"time_limit") if res.x is not None else (None,1,"tl_no_sol")
    if res.status==2: return None, 1, f"infeasible: {res.message}"
    return None, -1, f"status_{res.status}: {res.message}"

def _lp_periods(x, sc, demand_anchors=None):
    d_anch = demand_anchors or DEMAND.get(sc, DEMAND["CPS"])
    lp={}
    for ti,y in enumerate(YEARS):
        pbr={}; total=co2=0.0
        for ri,route in enumerate(ROUTES):
            prod = max(0.0, float(x[_ACT(ri,ti)])/DT)
            pbr[route["id"]] = round(prod,4)
            total += prod; co2 += prod*_ef(route,sc,y)
        lp[y]={"year":y,"total_production":round(total,3),
               "co2_intensity":round(co2/total,4) if total>0 else 0.0,
               "co2_total":round(co2,3),"production_by_route":pbr}
    return lp

def extract_yearly(x, sc, demand_anchors=None):
    d_anch = demand_anchors or DEMAND.get(sc, DEMAND["CPS"])
    lp = _lp_periods(x, sc, demand_anchors)
    out={}
    for y in ALL_YEARS:
        if y in lp:
            out[y]=dict(lp[y]); out[y]["year"]=y; continue
        if y > YEARS[-1]:
            base=lp[YEARS[-1]]; d_y=interp(d_anch,y)
            scale=d_y/base["total_production"] if base["total_production"]>0 else 1.0
            pbr={k:round(v*scale,4) for k,v in base["production_by_route"].items()}
            co2=sum(pbr.get(rt["id"],0)*_ef(rt,sc,y) for rt in ROUTES)
            out[y]={"year":y,"total_production":round(d_y,3),
                    "co2_intensity":round(co2/d_y,4) if d_y>0 else 0.0,
                    "co2_total":round(co2,3),"production_by_route":pbr}
            continue
        lo=max(lpy for lpy in YEARS if lpy<=y); hi=min(lpy for lpy in YEARS if lpy>=y)
        if lo==hi: out[y]=dict(lp[lo]); out[y]["year"]=y; continue
        f=(y-lo)/(hi-lo); ld,hd=lp[lo],lp[hi]
        pbr={rid:round(ld["production_by_route"].get(rid,0)*(1-f)+hd["production_by_route"].get(rid,0)*f,4)
             for rid in ld["production_by_route"]}
        total=sum(pbr.values()); co2=sum(pbr.get(rt["id"],0)*_ef(rt,sc,y) for rt in ROUTES)
        out[y]={"year":y,"total_production":round(total,3),
                "co2_intensity":round(co2/total,4) if total>0 else 0.0,
                "co2_total":round(co2,3),"production_by_route":pbr}
    return out

app = FastAPI(title="Aluminium Transition Backend v2", version="2.0.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])

def _summary(yearly):
    return {"co2_intensity_2050":yearly[2050]["co2_intensity"],
            "co2_intensity_2070":yearly[2070]["co2_intensity"],
            "co2_total_2070":yearly[2070]["co2_total"],
            "production_2070":yearly[2070]["total_production"],
            "cumulative_co2_mt":round(sum(yr["co2_total"] for yr in yearly.values()),1),
            "vol4_cps_2070":VOL4["cps_2070"],"vol4_nzs_2070":VOL4["nzs_2070"]}

@app.get("/health")
def health():
    return {"status":"ok","sector":SECTOR,"model":"HiGHS LP v2 (CRF+WACC+GridEI+PLI)",
            "port":PORT,**VOL4}

@app.get("/api/scenarios")
def scenarios():
    return {"scenarios":[{"key":"CPS","label":"Current Policy Scenario"},
                          {"key":"NZS","label":"Net Zero Scenario"}]}

@app.get("/api/demand-trajectories")
def demand_trajectories():
    return {sc:{str(y):interp(anch,y) for y in ALL_YEARS} for sc,anch in DEMAND.items()}

@app.post("/api/run")
async def run_scenario(payload: dict):
    sc = payload.get("scenario","CPS").upper()
    if sc not in ("CPS","NZS"): return {"status":"error","message":f"Unknown scenario: {sc}"}
    d_anch=None
    if payload.get("demand_anchors"):
        d_anch={int(k):float(v) for k,v in payload["demand_anchors"].items() if v is not None}
    x,code,msg=solve(sc,demand_anchors=d_anch,enforce_co2_ceiling=True)
    if x is None: return {"status":"infeasible","message":msg,"sector":SECTOR,"scenario":sc}
    yearly=extract_yearly(x,sc,d_anch)
    return {"status":"optimal" if code==0 else "feasible","message":msg,
            "sector":SECTOR,"scenario":sc,"years":ALL_YEARS,
            "yearly_results":{str(y):v for y,v in yearly.items()},"summary":_summary(yearly)}

@app.post("/api/lab/run")
async def lab_run(payload: dict):
    raw_sc=payload.get("scenario","CPS").upper()
    sc=raw_sc if raw_sc in ("CPS","NZS") else "CPS"
    cp_anch={}
    for k,v in payload.get("carbon_price",{}).items():
        try: cp_anch[int(k)]=float(v)
        except: pass
    if not cp_anch: cp_anch=CARBON_PRICE.get(sc,CARBON_PRICE["CPS"])
    d_anch=None
    if payload.get("demand_anchors"):
        d_anch={int(k):float(v) for k,v in payload["demand_anchors"].items() if v is not None}
    capex_m=float(payload.get("capex_multiplier",1.0))
    wacc=(float(payload["wacc_pct"]) if "wacc_pct" in payload
          else float(payload.get("wacc",0.0))*100.0)
    gp_val=None
    try: gp_val=float(payload["green_premium"]) if "green_premium" in payload else None
    except: pass
    h2_adj=0.0
    if "h2_cost_adj" in payload:
        try: h2_adj=float(payload["h2_cost_adj"])
        except: pass
    coal_adj    = float(payload.get("coal_price_adj", 0.0))
    re_adj      = float(payload.get("re_price_adj", 0.0))   # USD/MWh
    grid_adj    = float(payload.get("grid_price_adj", 0.0)) # USD/MWh
    pli_on      = bool(payload.get("pli_active", True))
    ia_on       = bool(payload.get("inert_anode_active", True))
    sec_cap     = float(payload.get("secondary_cap_pct", 0.45))
    dr_adj      = float(payload.get("discount_rate_adj", 0.0))
    cbr         = payload.get("capex_by_route") or {}
    capex_by_r  = {k: float(v) for k, v in cbr.items()} if cbr else None
    x,code,msg=solve(sc,demand_anchors=d_anch,carbon_price_anchors=cp_anch,
                      green_premium_val=gp_val,capex_mult=capex_m,wacc_adj_pct=wacc,
                      h2_cost_adj=h2_adj,enforce_co2_ceiling=False,
                      coal_price_adj=coal_adj,re_price_adj=re_adj,
                      grid_price_adj=grid_adj,pli_active=pli_on,
                      inert_anode_active=ia_on,secondary_cap_pct=sec_cap,
                      discount_rate_adj=dr_adj,capex_by_route=capex_by_r)
    if x is None: return {"status":"infeasible","message":msg,"sector":SECTOR,"scenario":sc}
    yearly=extract_yearly(x,sc,d_anch)
    return {"status":"optimal" if code==0 else "feasible","message":msg,
            "sector":SECTOR,"scenario":f"LAB-{sc}","years":ALL_YEARS,
            "yearly_results":{str(y):v for y,v in yearly.items()},"summary":_summary(yearly)}

if __name__=="__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
