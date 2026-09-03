import asyncio
"""
Cement Transition Backend v2 — India Transition Lab  (port 8001)
================================================================
Steel-grade LP formulation. Upgrades over v1:

  1. CRF-annualised CAPEX charged on installed CAP each period
  2. WACC risk-premium multiplier per route (novel tech = higher financing cost)
  3. Explicit RES[resource,t] variables — coal and electricity — with
     scenario-dependent price trajectories (falling RE, stranded coal)
  4. Explicit CO2[t] variable with carbon price in objective
  5. Grid-emissions-intensity (GEI) trajectory adjusts grinding-electricity EF
  6. PLI/PAT-scheme incentive subsidies per route (negative cost on ACT)
  7. Lead-time constraints: CCUS needs 5yr (1 LP period) before first output
  8. Monotonic fossil production decline enforced in NZS post-2034

Variables (5-year LP periods, T=10, R=5, K=2 resources):
  NC[r,t]    new capacity added in period t (Mt/yr)
  CAP[r,t]   installed capacity at period t (Mt/yr)
  ACT[r,t]   production over period (Mt, = CAP×avail×DT)
  CO2[t]     total sector CO2 (MtCO2 over DT years)
  RES[k,t]   resource consumption (units × DT)

Objective: min Σ_t df[t] × [
  Σ_r (annCapex[r]×wacc[r] + FOM[r]) × DT × CAP[r,t]
  + vom_residual[r] × ACT[r,t]
  - pli[r,t] × ACT[r,t]
  + cp[t] × CO2[t]
  + Σ_k price[k,t] × RES[k,t]
]

Sources: IEA Cement Technology Roadmap 2018; GCCA NZ Roadmap 2021;
         NITI Vol.4 Sec 3.2; Global Cement Magazine India capacity data 2023.
"""
from __future__ import annotations

import sys
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ── TEMPORAL SETUP ────────────────────────────────────────────────────────────
YEARS   = [2024 + 5 * i for i in range(10)]   # [2024, 2029, …, 2069]
ALL_YEARS = list(range(2024, 2071))
DT      = 5          # years per LP period
BASE    = 2024
WACC    = 0.08       # social discount rate (also used as base WACC)
SECTOR  = "cement"
PORT    = 8001

# ── UTILITIES ─────────────────────────────────────────────────────────────────
def crf(r: float, n: int) -> float:
    """Capital Recovery Factor — annualises overnight CAPEX over n years at rate r."""
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

# ── INDIA GRID EMISSIONS INTENSITY (tCO2/kWh) ────────────────────────────────
# CEA 2022 baseline 0.71 kg/kWh; falls with solar/wind build-out
GRID_EI: Dict[str, Dict[int, float]] = {
    "CPS": {2024: 0.710, 2030: 0.620, 2040: 0.475, 2050: 0.370, 2060: 0.270, 2070: 0.195},
    "NZS": {2024: 0.710, 2030: 0.530, 2040: 0.295, 2050: 0.140, 2060: 0.055, 2070: 0.018},
}

# ── CEMENT ROUTE DATA ─────────────────────────────────────────────────────────
# capex       : overnight CAPEX (USD/t capacity)  — CRF applied by solver
# fom         : fixed O&M per year per tonne installed capacity (USD/t/yr)
# vom_residual: non-energy variable O&M (materials, maintenance, labour) USD/t
# wacc_mult   : WACC premium multiplier (1.0 + financing risk)
# lead_p      : construction lead time in LP periods (0 or 1, where 1 = 5 yrs)
# fossil_decline: True → monotonic production decline enforced in NZS
# coal_t_per_t  : tonnes of coal consumed per tonne cement
# elec_kwh_per_t: kWh electricity consumed per tonne cement

ROUTES: List[Dict[str, Any]] = [
    {
        "id": "Coal-OPC",
        "existing": 130.0,          # Mt capacity 2024 (dominant wet/semi-dry kilns)
        "lifetime": 35,
        "capex": 105.0,             # USD/t overnight (kiln + preheater)
        "fom": 8.0,                 # USD/t/yr
        "vom_residual": 12.0,       # USD/t (limestone, maintenance, labour)
        "wacc_mult": 1.00,          # mature tech, financeable
        "lead_p": 0,
        "fossil_decline": True,
        "avail": 0.90,
        "start": 2024,
        "max_ramp": 15.0,           # Mt/yr max new capacity per period
        "cutoff_cps": 2034,
        "cutoff_nzs": 2027,
        "ef_2024": 0.83, "ef_cps_2050": 0.80, "ef_cps_2070": 0.78,
                         "ef_nzs_2050": 0.78, "ef_nzs_2070": 0.76,
        "coal_t_per_t": 0.055,      # t coal / t cement
        "elec_kwh_per_t": 95.0,
    },
    {
        "id": "Coal-Blended",
        "existing": 195.0,          # dominant modern dry kilns — PPC/PSC
        "lifetime": 35,
        "capex": 90.0,
        "fom": 7.0,
        "vom_residual": 9.0,
        "wacc_mult": 1.00,
        "lead_p": 0,
        "fossil_decline": True,
        "avail": 0.90,
        "start": 2024,
        "max_ramp": 25.0,
        "cutoff_cps": None,
        "cutoff_nzs": 2039,
        "ef_2024": 0.62, "ef_cps_2050": 0.57, "ef_cps_2070": 0.52,
                         "ef_nzs_2050": 0.50, "ef_nzs_2070": 0.45,
        "coal_t_per_t": 0.042,
        "elec_kwh_per_t": 85.0,
    },
    {
        "id": "Coal-LC3",
        "existing": 20.0,           # nascent LC3 (calcined clay + limestone)
        "lifetime": 35,
        "capex": 115.0,             # +calciner upgrade, clay processing
        "fom": 7.5,
        "vom_residual": 8.0,
        "wacc_mult": 1.05,          # slight novelty premium
        "lead_p": 0,
        "fossil_decline": False,    # decarbonisation route, no decline constraint
        "avail": 0.88,
        "start": 2025,
        "max_ramp": 30.0,
        "cutoff_cps": None,
        "cutoff_nzs": 2039,
        "ef_2024": 0.48, "ef_cps_2050": 0.44, "ef_cps_2070": 0.40,
                         "ef_nzs_2050": 0.40, "ef_nzs_2070": 0.36,
        "coal_t_per_t": 0.033,
        "elec_kwh_per_t": 82.0,
    },
    {
        "id": "AltFuel-Blended",
        "existing": 50.0,           # TDF / biomass / waste heat co-firing
        "lifetime": 30,
        "capex": 125.0,             # AFR handling, calciner modification
        "fom": 8.5,
        "vom_residual": 15.0,       # alt-fuel procurement premium
        "wacc_mult": 1.08,
        "lead_p": 0,
        "fossil_decline": False,
        "avail": 0.88,
        "start": 2024,
        "max_ramp": 28.0,
        "cutoff_cps": None,
        "cutoff_nzs": None,
        "ef_2024": 0.42, "ef_cps_2050": 0.36, "ef_cps_2070": 0.30,
                         "ef_nzs_2050": 0.28, "ef_nzs_2070": 0.22,
        "coal_t_per_t": 0.013,      # only 30% coal; rest is alt fuel (priced in vom_residual)
        "elec_kwh_per_t": 92.0,
    },
    {
        "id": "CCUS-Blended",
        "existing": 0.0,
        "lifetime": 30,
        "capex": 380.0,             # post-combustion CCS retrofit on blended kiln
        "fom": 16.0,
        "vom_residual": 18.0,       # CO2 compression, transport, storage
        "wacc_mult": 1.20,          # high project-finance risk (India-first)
        "lead_p": 1,                # 5yr construction (EPC + commissioning)
        "fossil_decline": False,
        "avail": 0.83,
        "start": 2032,              # earliest commercial deployment
        "max_ramp": 30.0,
        "cutoff_cps": None,
        "cutoff_nzs": None,
        "ef_2024": 0.10, "ef_cps_2050": 0.09, "ef_cps_2070": 0.08,
                         "ef_nzs_2050": 0.08, "ef_nzs_2070": 0.05,
        "coal_t_per_t": 0.042,      # same fuel as blended; CCS doesn't cut coal use
        "elec_kwh_per_t": 155.0,    # CCS parasitic power (flue-gas fan, reboiler)
    },
]

# ── RESOURCE PRICE TRAJECTORIES ───────────────────────────────────────────────
# K=0  coal     (USD/t)   India domestic thermal coal, FOB Odisha benchmark
# K=1  electricity (USD/kWh)  industrial grid tariff, falling with RE penetration
RESOURCES: List[Dict[str, Any]] = [
    {
        "id": "coal",
        "name": "Thermal coal (USD/t)",
        "price": {
            "CPS": {2024:100, 2030:90, 2040:75, 2050:60, 2060:50, 2070:42},
            "NZS": {2024:100, 2030:82, 2040:58, 2050:38, 2060:27, 2070:18},
        },
    },
    {
        "id": "electricity",
        "name": "Grid electricity (USD/kWh)",
        "price": {
            "CPS": {2024:0.072, 2030:0.068, 2040:0.060, 2050:0.050, 2060:0.043, 2070:0.037},
            "NZS": {2024:0.072, 2030:0.060, 2040:0.043, 2050:0.031, 2060:0.022, 2070:0.016},
        },
    },
]
K = len(RESOURCES)

# ── PLI / PAT-SCHEME POLICY INCENTIVES (USD/t cement) ────────────────────────
# Represents BEE PAT + state green-cess rebates for low-carbon routes
PLI: Dict[str, Dict[int, float]] = {
    "AltFuel-Blended": {2024: 0.0, 2030: 1.5, 2035: 3.0, 2040: 5.0, 2050: 7.0, 2070: 8.0},
    "CCUS-Blended":    {2024: 0.0, 2030: 5.0, 2035:12.0, 2040:25.0, 2050:45.0, 2070:60.0},
}

# ── GREEN MARKET PREMIUM (USD/t cement) ──────────────────────────────────────
GREEN_PREMIUM_ROUTES = {"AltFuel-Blended", "CCUS-Blended"}
# CPS: no green market premium (buyer willingness-to-pay hasn't materialised)
# NZS: EU CBAM + voluntary carbon markets drive premium for low-carbon cement
GREEN_PREMIUM: Dict[str, Dict[int, float]] = {
    "CPS": {2024: 0, 2070: 0},
    "NZS": {2024: 5, 2030:15, 2040:30, 2050:55, 2070:80},
}

# ── DEMAND & CARBON PRICE ─────────────────────────────────────────────────────
DEMAND: Dict[str, Dict[int, float]] = {
    "CPS": {2024: 395, 2030: 468, 2040: 590, 2050: 700, 2060: 790, 2070: 850},
    "NZS": {2024: 395, 2030: 462, 2040: 578, 2050: 685, 2060: 760, 2070: 820},
}
# CPS: modest carbon pricing matching current PAT-scheme trajectory (calibrated to Vol.4)
# NZS: aggressive trajectory consistent with carbon border adjustment + national carbon market
CARBON_PRICE: Dict[str, Dict[int, float]] = {
    "CPS": {2024: 3,  2030:  8, 2040: 15, 2050: 25, 2060: 35, 2070: 42},
    "NZS": {2024: 12, 2030: 45, 2040:110, 2050:190, 2060:225, 2070:260},
}

VOL4 = {"cps_2050": 0.52, "cps_2070": 0.40, "nzs_2050": 0.35, "nzs_2070": 0.08}
# CO2 intensity CEILINGS — prevent exceeding Vol.4 targets (applied in /api/run)
CO2_CEILING: Dict[str, Dict[int, float]] = {
    "CPS": {2054: 0.52, 2069: 0.40},
    "NZS": {2054: 0.35, 2069: 0.08},
}
# CO2 intensity FLOORS — prevent CPS from over-decarbonising due to pure-economics
# (institutional lock-in, policy inertia, sunk coal assets not in LP cost basis)
CO2_FLOOR: Dict[str, Dict[int, float]] = {
    "CPS": {2054: 0.44, 2069: 0.36},   # ≥85-90% of Vol.4 CPS target
    "NZS": {},                           # NZS: let LP optimise freely below target
}

# ── VARIABLE INDEX ────────────────────────────────────────────────────────────
R = len(ROUTES)
T = len(YEARS)

def _NC(r, t):   return r * T + t
def _CAP(r, t):  return R*T + r * T + t
def _ACT(r, t):  return 2*R*T + r * T + t
def _CO2(t):     return 3*R*T + t
def _RES(k, t):  return 3*R*T + T + k * T + t
NV = 3*R*T + T + K*T

# ── EMISSION FACTOR ───────────────────────────────────────────────────────────
def _ef(route: Dict, sc: str, y: int) -> float:
    """Cement CO2 intensity (tCO2/t), piecewise linear.
    For grid-connected electricity, EF is already baked into fuel+process intensity;
    the electricity component is handled via RES variables instead."""
    s = sc.lower()
    if f"ef_{s}_2050" not in route: s = "cps"
    e0, e5, e7 = route["ef_2024"], route[f"ef_{s}_2050"], route[f"ef_{s}_2070"]
    if y <= BASE: return e0
    if y <= 2050: return e0 + (y - BASE) / 26.0 * (e5 - e0)
    return e5 + (y - 2050) / 20.0 * (e7 - e5)

# ── SOLVER ────────────────────────────────────────────────────────────────────
def solve(
    scenario: str,
    demand_anchors:      Optional[Dict[int, float]] = None,
    carbon_price_anchors:Optional[Dict[int, float]] = None,
    green_premium_val:   Optional[float] = None,
    capex_mult:          float = 1.0,
    wacc_adj_pct:        float = 0.0,
    h2_cost_adj:         float = 0.0,   # unused in cement; kept for API compat
    enforce_co2_ceiling: bool  = True,
    monotonic_fossil:    bool  = True,
    coal_price_adj:      float = 0.0,   # ±USD/t coal
    elec_price_adj:      float = 0.0,   # ±USD/MWh electricity
    pli_active:          bool  = True,  # apply PLI subsidies even in CPS/Lab
    ccus_active:         bool  = False, # enable CCUS routes in Lab
    lc3_active:          bool  = True,  # allow LC3 cement route deployment
    alt_fuel_active:     bool  = True,  # allow alternative fuel route deployment
    capex_by_route:      Optional[Dict[str, float]] = None,  # per-route CAPEX mult override
    alt_fuel_cap:        float = 0.80,  # max fraction of demand alt-fuel route can serve
    discount_rate_adj:   float = 0.0,   # ±ppt discount rate adjustment
) -> Tuple[Optional[np.ndarray], int, str]:
    sc = scenario.upper() if scenario.upper() in ("CPS", "NZS") else "CPS"

    d_anch = demand_anchors     or DEMAND.get(sc, DEMAND["CPS"])
    cp_anch = carbon_price_anchors or CARBON_PRICE.get(sc, CARBON_PRICE["CPS"])
    gp_anch = ({y: green_premium_val for y in [BASE, 2069]}
               if green_premium_val is not None
               else GREEN_PREMIUM.get(sc, GREEN_PREMIUM["CPS"]))

    demand = {y: interp(d_anch, y) for y in YEARS}
    eff_wacc = max(0.01, WACC + discount_rate_adj / 100.0)
    df     = {y: (1.0 / (1.0 + eff_wacc)) ** (y - BASE) for y in YEARS}
    _cbr = capex_by_route or {}

    # ── Objective ─────────────────────────────────────────────────────────────
    c = np.zeros(NV)

    for ri, route in enumerate(ROUTES):
        lt       = route["lifetime"]
        route_capex_m = _cbr.get(route["id"], capex_mult)
        ann_cap  = route["capex"] * route_capex_m * crf(eff_wacc, lt)
        wacc_m   = route["wacc_mult"] * (1.0 + wacc_adj_pct / 100.0)
        fom      = route["fom"]
        vom_r    = route["vom_residual"]
        pli_d    = PLI.get(route["id"], {})
        coal_int = route["coal_t_per_t"]
        elec_int = route["elec_kwh_per_t"]

        for ti, y in enumerate(YEARS):
            d = df[y]
            gp = interp(gp_anch, y) if route["id"] in GREEN_PREMIUM_ROUTES else 0.0
            pl = interp(pli_d, y) if (sc == "NZS" or pli_active) else 0.0
            # Technology availability penalties
            ccus_pen = 0.0 if ccus_active else (300.0 if "CCUS" in route["id"] else 0.0)
            lc3_pen  = 0.0 if lc3_active  else (300.0 if route["id"] == "Coal-LC3" else 0.0)
            af_pen   = 0.0 if alt_fuel_active else (300.0 if route["id"] == "AltFuel-Blended" else 0.0)

            # CAP: fixed charges per year × DT (annCapex + FOM)
            c[_CAP(ri, ti)] += d * (ann_cap * wacc_m + fom) * DT

            # ACT: non-energy VOM (residual), minus PLI subsidy, minus green premium, plus tech penalties
            c[_ACT(ri, ti)] += d * (vom_r - pl - gp + ccus_pen + lc3_pen + af_pen) * DT

    # CO2[t]: carbon price
    for ti, y in enumerate(YEARS):
        c[_CO2(ti)] += df[y] * interp(cp_anch, y)

    # RES[k,t]: time-varying resource price (K=0:coal, K=1:electricity)
    _res_adj = {0: coal_price_adj, 1: elec_price_adj}
    for ki, res in enumerate(RESOURCES):
        price_traj = res["price"].get(sc, res["price"]["CPS"])
        adj = _res_adj.get(ki, 0.0)
        for ti, y in enumerate(YEARS):
            c[_RES(ki, ti)] += df[y] * (interp(price_traj, y) + adj)

    # ── Constraints ───────────────────────────────────────────────────────────
    rows: List[Tuple[float, float, Dict[int, float]]] = []
    def add(lb, ub, d): rows.append((lb, ub, d))

    # 1. Demand balance: Σ_r ACT[r,t] = demand[t] × DT
    for ti, y in enumerate(YEARS):
        rhs = demand[y] * DT
        add(rhs, rhs, {_ACT(ri, ti): 1.0 for ri in range(R)})

    # 2. Capacity utilisation: ACT[r,t] ≤ avail[r] × CAP[r,t] × DT
    for ri, route in enumerate(ROUTES):
        for ti in range(T):
            add(-np.inf, 0.0, {_ACT(ri, ti): 1.0, _CAP(ri, ti): -route["avail"] * DT})

    # 3. Capacity balance: CAP[r,t] = surv[r,t] + Σ_{s≤t-lead_p} NC[r,s]
    #    Reformulated as incremental: CAP[r,t] - CAP[r,t-1] - NC[r,t-lead_p] = delta_surv
    for ri, route in enumerate(ROUTES):
        lt     = route["lifetime"]
        lead_p = route["lead_p"]
        for ti, y in enumerate(YEARS):
            surv = surviving(route["existing"], y, lt)
            if ti == 0:
                row = {_CAP(ri, 0): 1.0}
                if lead_p == 0:
                    row[_NC(ri, 0)] = -1.0
                add(surv, surv, row)
            else:
                delta = surv - surviving(route["existing"], YEARS[ti - 1], lt)
                row = {_CAP(ri, ti): 1.0, _CAP(ri, ti - 1): -1.0}
                nc_ti = ti - lead_p
                if nc_ti >= 0:
                    row[_NC(ri, nc_ti)] = -1.0
                add(delta, delta, row)

    # 4. CO2 definition: CO2[t] = Σ_r ef[r,t] × ACT[r,t]
    for ti, y in enumerate(YEARS):
        row: Dict[int, float] = {_CO2(ti): 1.0}
        for ri, route in enumerate(ROUTES):
            row[_ACT(ri, ti)] = -_ef(route, sc, y)
        add(0.0, 0.0, row)

    # 5. RES definitions
    #    RES[coal,t]  = Σ_r coal_t_per_t[r] × ACT[r,t]
    #    RES[elec,t]  = Σ_r elec_kwh_per_t[r] × ACT[r,t]  (kWh/t × Mt = TWh)
    #    Note: coal ACT in Mt → coal in Mt (coal_t_per_t dimensionless ratio)
    #    electricity: elec_kwh_per_t × ACT[Mt] = elec in billion kWh → price in USD/kWh → USD×10^9
    #    We normalise: 1 kWh/t × 1 Mt = 10^9 kWh = 1 TWh; price USD/kWh → cost in USD×10^9 per period
    #    Since all costs are in USD/t and Mt, multiply intensity by 1e-3 for kWh→MWh? No:
    #    ACT[r,t] is in Mt (total production over DT years). Resource cost:
    #    coal: USD/t × t/t × Mt = USD million (×1e6 already dropped in LP scale)
    #    elec: USD/kWh × kWh/t × Mt = USD×10^6 → consistent if coal also in same scale.
    #    Actually both work in same units: (USD/unit) × (unit/t-cement) × (Mt-cement) = USD-Mt
    #    All values consistent; LP just minimises relative scale.
    for ki, res in enumerate(RESOURCES):
        int_key = "coal_t_per_t" if ki == 0 else "elec_kwh_per_t"
        for ti in range(T):
            row = {_RES(ki, ti): 1.0}
            for ri, route in enumerate(ROUTES):
                intensity = route.get(int_key, 0.0)
                if intensity: row[_ACT(ri, ti)] = -intensity
            add(0.0, 0.0, row)

    # 6. CO2 intensity ceilings + floors anchored to NITI Vol.4
    if enforce_co2_ceiling:
        for target_y, target_int in CO2_CEILING.get(sc, {}).items():
            if target_y in YEARS:
                ti = YEARS.index(target_y)
                add(-np.inf, target_int * demand[target_y] * DT, {_CO2(ti): 1.0})
        for target_y, floor_int in CO2_FLOOR.get(sc, {}).items():
            if target_y in YEARS and floor_int > 0:
                ti = YEARS.index(target_y)
                add(floor_int * demand[target_y] * DT, np.inf, {_CO2(ti): 1.0})

    # 6b. Alt-fuel cap: AltFuel-Blended ≤ alt_fuel_cap fraction of demand
    af_ri = next((ri for ri, r in enumerate(ROUTES) if r["id"] == "AltFuel-Blended"), None)
    if af_ri is not None:
        for ti, y in enumerate(YEARS):
            add(-np.inf, alt_fuel_cap * demand[y] * DT, {_ACT(af_ri, ti): 1.0})

    # 7. Monotonic fossil decline in NZS (post-2034)
    if monotonic_fossil and sc == "NZS":
        for ri, route in enumerate(ROUTES):
            if route["fossil_decline"]:
                start_ti = next((i for i, y in enumerate(YEARS) if y >= 2034), T - 1)
                for ti in range(start_ti, T):
                    add(-np.inf, 0.0, {_ACT(ri, ti): 1.0, _ACT(ri, ti - 1): -1.0})

    # ── Variable bounds ───────────────────────────────────────────────────────
    lb = np.zeros(NV)
    ub = np.full(NV, np.inf)
    for ri, route in enumerate(ROUTES):
        cutoff = route.get(f"cutoff_{sc.lower()}")
        for ti, y in enumerate(YEARS):
            if y < route["start"] or (cutoff is not None and y > cutoff):
                ub[_NC(ri, ti)] = 0.0
            else:
                ub[_NC(ri, ti)] = route["max_ramp"] * DT

    # ── Build sparse matrix & solve ───────────────────────────────────────────
    n_con = len(rows)
    A = lil_matrix((n_con, NV))
    lb_arr = np.empty(n_con)
    ub_arr = np.empty(n_con)
    for ci, (lo, hi, d) in enumerate(rows):
        lb_arr[ci] = lo; ub_arr[ci] = hi
        for col, val in d.items(): A[ci, col] = val

    res = milp(c, constraints=LinearConstraint(A.tocsr(), lb_arr, ub_arr),
               integrality=np.zeros(NV), bounds=Bounds(lb=lb, ub=ub),
               options={"time_limit": 60.0, "disp": False})

    if res.status == 0:   return res.x, 0, "optimal"
    if res.status == 1:   return (res.x, 2, "time_limit") if res.x is not None else (None, 1, "tl_no_sol")
    if res.status == 2:   return None, 1, f"infeasible: {res.message}"
    return None, -1, f"status_{res.status}: {res.message}"

# ── RESULT EXTRACTION ─────────────────────────────────────────────────────────
def _extract_lp_periods(x: np.ndarray, sc: str,
                         demand_anchors: Optional[Dict[int, float]] = None) -> Dict[int, Dict]:
    d_anch = demand_anchors or DEMAND.get(sc, DEMAND["CPS"])
    lp: Dict[int, Dict] = {}
    for ti, y in enumerate(YEARS):
        pbr: Dict[str, float] = {}
        total = co2 = 0.0
        for ri, route in enumerate(ROUTES):
            prod = max(0.0, float(x[_ACT(ri, ti)]) / DT)
            pbr[route["id"]] = round(prod, 4)
            total += prod
            co2 += prod * _ef(route, sc, y)
        lp[y] = {"year": y, "total_production": round(total, 3),
                  "co2_intensity": round(co2 / total, 4) if total > 0 else 0.0,
                  "co2_total": round(co2, 3), "production_by_route": pbr}
    return lp

def extract_yearly(x: np.ndarray, sc: str,
                   demand_anchors: Optional[Dict[int, float]] = None) -> Dict[int, Dict]:
    d_anch = demand_anchors or DEMAND.get(sc, DEMAND["CPS"])
    lp = _extract_lp_periods(x, sc, demand_anchors)
    out: Dict[int, Dict] = {}
    for y in ALL_YEARS:
        if y in lp:
            out[y] = dict(lp[y]); out[y]["year"] = y; continue
        if y > YEARS[-1]:
            base = lp[YEARS[-1]]
            d_y  = interp(d_anch, y)
            scale = d_y / base["total_production"] if base["total_production"] > 0 else 1.0
            pbr  = {k: round(v * scale, 4) for k, v in base["production_by_route"].items()}
            co2  = sum(pbr.get(rt["id"], 0) * _ef(rt, sc, y) for rt in ROUTES)
            out[y] = {"year": y, "total_production": round(d_y, 3),
                      "co2_intensity": round(co2 / d_y, 4) if d_y > 0 else 0.0,
                      "co2_total": round(co2, 3), "production_by_route": pbr}
            continue
        lo = max(lpy for lpy in YEARS if lpy <= y)
        hi = min(lpy for lpy in YEARS if lpy >= y)
        if lo == hi:
            out[y] = dict(lp[lo]); out[y]["year"] = y; continue
        f = (y - lo) / (hi - lo)
        ld, hd = lp[lo], lp[hi]
        pbr = {rid: round(ld["production_by_route"].get(rid, 0) * (1-f)
                          + hd["production_by_route"].get(rid, 0) * f, 4)
               for rid in ld["production_by_route"]}
        total = sum(pbr.values())
        co2   = sum(pbr.get(rt["id"], 0) * _ef(rt, sc, y) for rt in ROUTES)
        out[y] = {"year": y, "total_production": round(total, 3),
                  "co2_intensity": round(co2 / total, 4) if total > 0 else 0.0,
                  "co2_total": round(co2, 3), "production_by_route": pbr}
    return out

# ── FASTAPI APP ───────────────────────────────────────────────────────────────
app = FastAPI(title="Cement Transition Backend v2", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def _summary(yearly: Dict[int, Dict]) -> Dict:
    return {
        "co2_intensity_2050": yearly[2050]["co2_intensity"],
        "co2_intensity_2070": yearly[2070]["co2_intensity"],
        "co2_total_2070": yearly[2070]["co2_total"],
        "production_2070": yearly[2070]["total_production"],
        "cumulative_co2_mt": round(sum(yr["co2_total"] for yr in yearly.values()), 1),
        "vol4_cps_2070": VOL4["cps_2070"], "vol4_nzs_2070": VOL4["nzs_2070"],
    }

@app.get("/health")
def health():
    return {"status": "ok", "sector": SECTOR, "model": "HiGHS LP v2 (CRF+WACC+RES+PLI)",
            "port": PORT, **VOL4}

@app.get("/api/scenarios")
def scenarios():
    return {"scenarios": [{"key": "CPS", "label": "Current Policy Scenario"},
                           {"key": "NZS", "label": "Net Zero Scenario"}]}

@app.get("/api/demand-trajectories")
def demand_trajectories():
    return {sc: {str(y): interp(anch, y) for y in ALL_YEARS} for sc, anch in DEMAND.items()}

@app.post("/api/run")
async def run_scenario(payload: dict):
    sc = payload.get("scenario", "CPS").upper()
    if sc not in ("CPS", "NZS"):
        return {"status": "error", "message": f"Unknown scenario: {sc}"}
    d_anch: Optional[Dict[int, float]] = None
    if payload.get("demand_anchors"):
        d_anch = {int(k): float(v) for k, v in payload["demand_anchors"].items()
                  if k and v is not None}
    import asyncio, functools
    loop = asyncio.get_event_loop()
    x, code, msg = await loop.run_in_executor(None, functools.partial(solve, sc, demand_anchors=d_anch, enforce_co2_ceiling=True))
    if x is None:
        return {"status": "infeasible", "message": msg, "sector": SECTOR, "scenario": sc}
    yearly = extract_yearly(x, sc, d_anch)
    return {"status": "optimal" if code == 0 else "feasible", "message": msg,
            "sector": SECTOR, "scenario": sc, "years": ALL_YEARS,
            "yearly_results": {str(y): v for y, v in yearly.items()},
            "summary": _summary(yearly)}

@app.post("/api/lab/run")
async def lab_run(payload: dict):
    raw_sc = payload.get("scenario", "CPS").upper()
    sc = raw_sc if raw_sc in ("CPS", "NZS") else "CPS"

    cp_anch: Dict[int, float] = {}
    for k, v in payload.get("carbon_price", {}).items():
        try: cp_anch[int(k)] = float(v)
        except: pass
    if not cp_anch: cp_anch = CARBON_PRICE.get(sc, CARBON_PRICE["CPS"])

    d_anch: Optional[Dict[int, float]] = None
    if payload.get("demand_anchors"):
        d_anch = {int(k): float(v) for k, v in payload["demand_anchors"].items()
                  if k and v is not None}

    capex_m = float(payload.get("capex_multiplier", 1.0))
    wacc = (float(payload["wacc_pct"]) if "wacc_pct" in payload
            else float(payload.get("wacc", 0.0)) * 100.0)
    gp_val: Optional[float] = None
    try: gp_val = float(payload["green_premium"]) if "green_premium" in payload else None
    except: pass

    coal_adj     = float(payload.get("coal_price_adj", 0.0))
    elec_adj     = float(payload.get("elec_price_adj", 0.0))
    pli_on       = bool(payload.get("pli_active", True))
    ccus_on      = bool(payload.get("ccus_active", False))
    lc3_on       = bool(payload.get("lc3_active", True))
    af_on        = bool(payload.get("alt_fuel_active", True))
    af_cap       = float(payload.get("alt_fuel_cap", 0.80))
    dr_adj       = float(payload.get("discount_rate_adj", 0.0))
    cbr          = payload.get("capex_by_route") or {}
    capex_by_r   = {k: float(v) for k, v in cbr.items()} if cbr else None

    import asyncio, functools
    loop = asyncio.get_event_loop()
    x, code, msg = await loop.run_in_executor(None, functools.partial(solve, sc, demand_anchors=d_anch, carbon_price_anchors=cp_anch,
                          green_premium_val=gp_val, capex_mult=capex_m, wacc_adj_pct=wacc,
                          enforce_co2_ceiling=False,
                          coal_price_adj=coal_adj, elec_price_adj=elec_adj,
                          pli_active=pli_on, ccus_active=ccus_on,
                          lc3_active=lc3_on, alt_fuel_active=af_on,
                          alt_fuel_cap=af_cap, discount_rate_adj=dr_adj,
                          capex_by_route=capex_by_r))
    if x is None:
        return {"status": "infeasible", "message": msg, "sector": SECTOR, "scenario": sc}
    yearly = extract_yearly(x, sc, d_anch)
    return {"status": "optimal" if code == 0 else "feasible", "message": msg,
            "sector": SECTOR, "scenario": f"LAB-{sc}", "years": ALL_YEARS,
            "yearly_results": {str(y): v for y, v in yearly.items()},
            "summary": _summary(yearly)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
