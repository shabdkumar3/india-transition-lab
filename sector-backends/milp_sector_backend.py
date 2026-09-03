"""
Multi-Sector MILP Backend - India Transition Lab
Sectors: cement (8001), aluminium (8002), textile (8003), fertiliser (8004)
Solver: scipy.optimize.milp (HiGHS) - pure economics-driven LP optimisation.
Usage:  python milp_sector_backend.py cement|aluminium|textile|fertiliser
"""
from __future__ import annotations
import sys
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

YEARS = [2024 + 5 * i for i in range(10)]
DT = 5
ALL_YEARS = list(range(2024, 2071))
DISCOUNT_RATE = 0.08


def _interp(anchors: Dict[int, float], y: int) -> float:
    ks = sorted(anchors)
    if not ks: return 0.0
    if y <= ks[0]: return anchors[ks[0]]
    if y >= ks[-1]: return anchors[ks[-1]]
    for lo, hi in zip(ks, ks[1:]):
        if lo <= y <= hi:
            f = (y - lo) / (hi - lo)
            return anchors[lo] + f * (anchors[hi] - anchors[lo])
    return anchors[ks[-1]]


def _ef(route: Dict, scenario: str, y: int) -> float:
    # Normalize: map any unknown scenario (e.g. "LAB") to CPS
    sc = scenario.lower()
    if f"ef_{sc}_2050" not in route:
        sc = "cps"
    e0, e5, e7 = route["ef_2024"], route[f"ef_{sc}_2050"], route[f"ef_{sc}_2070"]
    if y <= 2024: return e0
    if y <= 2050: return e0 + (y - 2024) / 26.0 * (e5 - e0)
    return e5 + (y - 2050) / 20.0 * (e7 - e5)


def _surviving(existing: float, y: int, lifetime: int) -> float:
    age = y - 2024
    if age >= lifetime: return 0.0
    return existing * (1.0 - age / lifetime)


# ── CEMENT ────────────────────────────────────────────────────────────────
# Sources: IEA Cement Roadmap 2020; GCCA NZ Roadmap 2021; NITI Vol.4 Sec 3.2
# VOM = vom + fuel_cost from existing cement model
# Existing scaled so avail x existing = demand_2024 x share
CEMENT_ROUTES: List[Dict[str, Any]] = [
    {"id": "Coal-OPC", "existing": 125.0,
     "ef_2024": 0.82, "ef_cps_2050": 0.79, "ef_cps_2070": 0.77,
     "ef_nzs_2050": 0.77, "ef_nzs_2070": 0.75,
     "capex": 55.0, "fom": 12.0, "vom_total": 25.0,
     "avail": 0.85, "start": 2024, "max_ramp": 15.0, "lifetime": 35,
     "cutoff_cps": 2044, "cutoff_nzs": 2029},
    {"id": "Coal-Blended", "existing": 303.0,
     "ef_2024": 0.52, "ef_cps_2050": 0.49, "ef_cps_2070": 0.46,
     "ef_nzs_2050": 0.47, "ef_nzs_2070": 0.44,
     "capex": 50.0, "fom": 11.0, "vom_total": 19.0,
     "avail": 0.85, "start": 2024, "max_ramp": 25.0, "lifetime": 35,
     "cutoff_cps": None, "cutoff_nzs": 2039},
    {"id": "Coal-LC3", "existing": 0.5,
     "ef_2024": 0.40, "ef_cps_2050": 0.37, "ef_cps_2070": 0.34,
     "ef_nzs_2050": 0.35, "ef_nzs_2070": 0.30,
     "capex": 58.0, "fom": 12.0, "vom_total": 17.0,
     "avail": 0.82, "start": 2030, "max_ramp": 30.0, "lifetime": 35,
     "cutoff_cps": None, "cutoff_nzs": None},
    {"id": "AltFuel-Blended", "existing": 36.0,
     "ef_2024": 0.38, "ef_cps_2050": 0.33, "ef_cps_2070": 0.28,
     "ef_nzs_2050": 0.27, "ef_nzs_2070": 0.18,
     "capex": 52.0, "fom": 13.0, "vom_total": 23.0,
     "avail": 0.82, "start": 2024, "max_ramp": 25.0, "lifetime": 30,
     "cutoff_cps": None, "cutoff_nzs": None},
    {"id": "CCUS-Blended", "existing": 0.0,
     "ef_2024": 0.08, "ef_cps_2050": 0.07, "ef_cps_2070": 0.06,
     "ef_nzs_2050": 0.06, "ef_nzs_2070": 0.04,
     "capex": 110.0, "fom": 22.0, "vom_total": 28.0,
     "avail": 0.80, "start": 2040, "max_ramp": 30.0, "lifetime": 30,
     "cutoff_cps": None, "cutoff_nzs": None},
]

# ── ALUMINIUM ─────────────────────────────────────────────────────────────
# Sources: IEA Al Roadmap 2022; World Aluminium 2023; AAI 2023
# VOM includes electricity: Coal-CPP=52+14500x0.04=632; RE=38+13500x0.035=511
# Grid ef falls as India grid decarbonises (faster in NZS)
ALUMINIUM_ROUTES: List[Dict[str, Any]] = [
    {"id": "Coal-CPP", "existing": 3.90,
     "ef_2024": 4.60, "ef_cps_2050": 3.80, "ef_cps_2070": 3.20,
     "ef_nzs_2050": 2.80, "ef_nzs_2070": 2.00,
     "capex": 820.0, "fom": 65.0, "vom_total": 632.0,
     "avail": 0.88, "start": 2024, "max_ramp": 0.8, "lifetime": 30,
     "cutoff_cps": None, "cutoff_nzs": 2030},
    {"id": "Grid-Electrolysis", "existing": 0.30,
     "ef_2024": 2.80, "ef_cps_2050": 2.00, "ef_cps_2070": 1.60,
     "ef_nzs_2050": 1.00, "ef_nzs_2070": 0.40,
     "capex": 760.0, "fom": 58.0, "vom_total": 991.0,
     "avail": 0.88, "start": 2024, "max_ramp": 1.5, "lifetime": 30,
     "cutoff_cps": None, "cutoff_nzs": 2040},
    {"id": "RE-Electrolysis", "existing": 0.15,
     "ef_2024": 0.30, "ef_cps_2050": 0.22, "ef_cps_2070": 0.18,
     "ef_nzs_2050": 0.15, "ef_nzs_2070": 0.10,
     "capex": 950.0, "fom": 70.0, "vom_total": 511.0,
     "avail": 0.85, "start": 2024, "max_ramp": 2.0, "lifetime": 25,
     "cutoff_cps": None, "cutoff_nzs": None},
    {"id": "Inert-Anode", "existing": 0.0,
     "ef_2024": 0.08, "ef_cps_2050": 0.06, "ef_cps_2070": 0.04,
     "ef_nzs_2050": 0.04, "ef_nzs_2070": 0.02,
     "capex": 1400.0, "fom": 90.0, "vom_total": 480.0,
     "avail": 0.82, "start": 2035, "max_ramp": 1.5, "lifetime": 25,
     "cutoff_cps": None, "cutoff_nzs": None},
    {"id": "Secondary-Al", "existing": 0.80,
     "ef_2024": 0.52, "ef_cps_2050": 0.40, "ef_cps_2070": 0.32,
     "ef_nzs_2050": 0.28, "ef_nzs_2070": 0.18,
     "capex": 220.0, "fom": 22.0, "vom_total": 84.0,
     "avail": 0.88, "start": 2024, "max_ramp": 1.0, "lifetime": 20,
     "scrap_frac_cap": {2024: 0.16, 2030: 0.20, 2040: 0.28, 2050: 0.36, 2070: 0.45},
     "cutoff_cps": None, "cutoff_nzs": None},
]

# ── TEXTILE ───────────────────────────────────────────────────────────────
# Sources: UNIDO 2021; Ministry of Textiles 2023; Vol.4 Sec 3.4
# VOM includes energy: Coal=28+26x3.0=106; Gas=25+22x5.5=146; Biomass=22+24x2.5=82
TEXTILE_ROUTES: List[Dict[str, Any]] = [
    {"id": "Coal-Processing", "existing": 15.4,
     "ef_2024": 2.80, "ef_cps_2050": 2.40, "ef_cps_2070": 2.10,
     "ef_nzs_2050": 2.10, "ef_nzs_2070": 1.80,
     "capex": 155.0, "fom": 16.0, "vom_total": 106.0,
     "avail": 0.85, "start": 2024, "max_ramp": 4.0, "lifetime": 25,
     "cutoff_cps": None, "cutoff_nzs": 2033},
    {"id": "Gas-Processing", "existing": 4.1,
     "ef_2024": 1.55, "ef_cps_2050": 1.35, "ef_cps_2070": 1.15,
     "ef_nzs_2050": 1.10, "ef_nzs_2070": 0.80,
     "capex": 165.0, "fom": 17.0, "vom_total": 146.0,
     "avail": 0.85, "start": 2024, "max_ramp": 5.0, "lifetime": 25,
     "cutoff_cps": None, "cutoff_nzs": 2040},
    {"id": "Biomass-Processing", "existing": 1.85,
     "ef_2024": 0.35, "ef_cps_2050": 0.28, "ef_cps_2070": 0.22,
     "ef_nzs_2050": 0.22, "ef_nzs_2070": 0.14,
     "capex": 190.0, "fom": 19.0, "vom_total": 82.0,
     "avail": 0.82, "start": 2024, "max_ramp": 5.0, "lifetime": 20,
     "cutoff_cps": None, "cutoff_nzs": None},
    {"id": "RE-Processing", "existing": 0.28,
     "ef_2024": 0.12, "ef_cps_2050": 0.08, "ef_cps_2070": 0.05,
     "ef_nzs_2050": 0.05, "ef_nzs_2070": 0.02,
     "capex": 230.0, "fom": 22.0, "vom_total": 74.0,
     "avail": 0.82, "start": 2025, "max_ramp": 6.0, "lifetime": 20,
     "cutoff_cps": None, "cutoff_nzs": None},
    {"id": "Circular-Textiles", "existing": 0.64,
     "ef_2024": 0.22, "ef_cps_2050": 0.16, "ef_cps_2070": 0.12,
     "ef_nzs_2050": 0.12, "ef_nzs_2070": 0.06,
     "capex": 110.0, "fom": 13.0, "vom_total": 67.0,
     "avail": 0.85, "start": 2024, "max_ramp": 5.0, "lifetime": 20,
     "scrap_frac_cap": {2024: 0.04, 2030: 0.08, 2040: 0.18, 2050: 0.30, 2070: 0.45},
     "cutoff_cps": None, "cutoff_nzs": None},
]

# ── FERTILISER ────────────────────────────────────────────────────────────
# Sources: IEA Ammonia Roadmap 2021; CEEW 2024; FAI 2023; Vol.4 Sec 3.2.8
# EF is NET of CO2 sink in urea synthesis (~0.51 tCO2/t already deducted)
# Route mapping: NG-SMR=Gas-SMR; NG-SMR-CCUS=Efficient-SMR; Green-H2-Urea=RE-GH2
FERTILISER_ROUTES: List[Dict[str, Any]] = [
    {"id": "Coal-Gasification", "existing": 2.42,
     "ef_2024": 1.20, "ef_cps_2050": 1.00, "ef_cps_2070": 0.88,
     "ef_nzs_2050": 0.88, "ef_nzs_2070": 0.75,
     "capex": 360.0, "fom": 32.0, "vom_total": 68.0,
     "avail": 0.88, "start": 2024, "max_ramp": 0.5, "lifetime": 25,
     "cutoff_cps": 2029, "cutoff_nzs": 2025},
    {"id": "NG-SMR", "existing": 25.3,
     "ef_2024": 0.55, "ef_cps_2050": 0.46, "ef_cps_2070": 0.40,
     "ef_nzs_2050": 0.40, "ef_nzs_2070": 0.30,
     "capex": 270.0, "fom": 26.0, "vom_total": 115.0,
     "avail": 0.88, "start": 2024, "max_ramp": 3.0, "lifetime": 25,
     "cutoff_cps": None, "cutoff_nzs": 2040},
    {"id": "NG-SMR-CCUS", "existing": 5.02,
     "ef_2024": 0.35, "ef_cps_2050": 0.28, "ef_cps_2070": 0.22,
     "ef_nzs_2050": 0.22, "ef_nzs_2070": 0.15,
     "capex": 320.0, "fom": 29.0, "vom_total": 91.0,
     "avail": 0.85, "start": 2024, "max_ramp": 3.0, "lifetime": 25,
     "cutoff_cps": None, "cutoff_nzs": None},
    {"id": "Green-H2-Urea", "existing": 0.0,
     "ef_2024": -0.35, "ef_cps_2050": -0.35, "ef_cps_2070": -0.35,
     "ef_nzs_2050": -0.35, "ef_nzs_2070": -0.35,
     "capex": 800.0, "fom": 62.0, "vom_total": 213.0,
     "avail": 0.82, "start": 2030, "max_ramp": 4.0, "lifetime": 20,
     "h2_route": True,
     "scrap_frac_cap": {2024: 0.00, 2030: 0.02, 2040: 0.18, 2050: 0.48, 2060: 0.72, 2070: 0.90},
     "cutoff_cps": None, "cutoff_nzs": None},
    {"id": "Bio-Ammonia", "existing": 2.29,
     "ef_2024": 0.20, "ef_cps_2050": 0.16, "ef_cps_2070": 0.12,
     "ef_nzs_2050": 0.12, "ef_nzs_2070": 0.08,
     "capex": 650.0, "fom": 50.0, "vom_total": 70.0,
     "avail": 0.80, "start": 2024, "max_ramp": 2.0, "lifetime": 20,
     "scrap_frac_cap": {2024: 0.08, 2030: 0.12, 2040: 0.22, 2050: 0.35, 2070: 0.50},
     "cutoff_cps": None, "cutoff_nzs": None},
]


SECTOR_CONFIGS: Dict[str, Dict[str, Any]] = {
    "cement": {
        "port": 8001, "routes": CEMENT_ROUTES,
        "demand": {
            "CPS": {2024: 395, 2030: 465, 2040: 588, 2050: 700, 2060: 790, 2070: 850},
            "NZS": {2024: 395, 2030: 460, 2040: 578, 2050: 685, 2060: 760, 2070: 820},
        },
        "carbon_price": {
            "CPS": {2024: 3, 2030: 8, 2040: 15, 2050: 25, 2070: 40},
            "NZS": {2024: 10, 2030: 45, 2040: 120, 2050: 200, 2070: 280},
        },
        "green_premium_routes": {"AltFuel-Blended", "CCUS-Blended"},
        "green_premium": {
            "CPS": {2024: 0, 2040: 2, 2050: 5, 2070: 10},
            "NZS": {2024: 5, 2030: 15, 2040: 40, 2050: 70, 2070: 110},
        },
        "nzs_co2_ceiling_2069": 0.10,
        "vol4": {"cps_2050": 0.52, "cps_2070": 0.40, "nzs_2050": 0.35, "nzs_2070": 0.08},
    },
    "aluminium": {
        "port": 8002, "routes": ALUMINIUM_ROUTES,
        "demand": {
            "CPS": {2024: 4.5, 2030: 7.5, 2040: 13.0, 2050: 18.0, 2060: 23.0, 2070: 28.0},
            "NZS": {2024: 4.5, 2030: 7.2, 2040: 12.5, 2050: 17.5, 2060: 22.0, 2070: 26.0},
        },
        "carbon_price": {
            "CPS": {2024: 3, 2030: 12, 2040: 28, 2050: 50, 2070: 75},
            "NZS": {2024: 15, 2030: 65, 2040: 160, 2050: 270, 2070: 380},
        },
        "green_premium_routes": {"RE-Electrolysis", "Inert-Anode"},
        "green_premium": {
            "CPS": {2024: 0, 2040: 50, 2050: 100, 2070: 150},
            "NZS": {2024: 100, 2030: 250, 2040: 500, 2050: 800, 2070: 1100},
        },
        "nzs_co2_ceiling_2069": 0.5,
        "vol4": {"cps_2050": 6.5, "cps_2070": 4.2, "nzs_2050": 2.8, "nzs_2070": 0.4},
    },
    "textile": {
        "port": 8003, "routes": TEXTILE_ROUTES,
        "demand": {
            "CPS": {2024: 19, 2030: 28, 2040: 42, 2050: 55, 2060: 70, 2070: 80},
            "NZS": {2024: 19, 2030: 27, 2040: 40, 2050: 53, 2060: 67, 2070: 77},
        },
        "carbon_price": {
            "CPS": {2024: 2, 2030: 6, 2040: 14, 2050: 25, 2070: 38},
            "NZS": {2024: 8, 2030: 35, 2040: 95, 2050: 165, 2070: 230},
        },
        "green_premium_routes": {"RE-Processing", "Circular-Textiles"},
        "green_premium": {
            "CPS": {2024: 0, 2040: 4, 2050: 8, 2070: 16},
            "NZS": {2024: 5, 2030: 18, 2040: 50, 2050: 90, 2070: 135},
        },
        "nzs_co2_ceiling_2069": 0.15,
        "vol4": {"cps_2050": 2.1, "cps_2070": 1.4, "nzs_2050": 0.9, "nzs_2070": 0.12},
    },
    "fertiliser": {
        "port": 8004, "routes": FERTILISER_ROUTES,
        "demand": {
            "CPS": {2024: 30.5, 2030: 36.5, 2040: 46.0, 2050: 55.0, 2060: 64.0, 2070: 70.0},
            "NZS": {2024: 30.5, 2030: 36.0, 2040: 44.0, 2050: 53.0, 2060: 61.0, 2070: 67.0},
        },
        "carbon_price": {
            "CPS": {2024: 2, 2030: 8, 2040: 18, 2050: 32, 2070: 50},
            "NZS": {2024: 10, 2030: 50, 2040: 135, 2050: 235, 2070: 330},
        },
        "green_premium_routes": {"Green-H2-Urea", "Bio-Ammonia"},
        "green_premium": {
            "CPS": {2024: 0, 2040: 10, 2050: 20, 2070: 35},
            "NZS": {2024: 15, 2030: 55, 2040: 130, 2050: 220, 2070: 310},
        },
        "nzs_co2_ceiling_2069": 0.05,
        "vol4": {"cps_2050": 1.8, "cps_2070": 1.2, "nzs_2050": 0.7, "nzs_2070": 0.05},
    },
}


def solve_sector_lp(
    sector_id: str, scenario: str,
    demand_anchors: Optional[Dict[int, float]] = None,
    carbon_price_anchors: Optional[Dict[int, float]] = None,
    green_premium_val: Optional[float] = None,
    capex_mult: float = 1.0,
    h2_cost_adj: float = 0.0,
    wacc_adj_pct: float = 0.0,
    enforce_co2_ceiling: bool = True,
    coal_price_adj: float = 0.0,   # $/t coal price adjustment
    gas_price_adj: float = 0.0,    # $/MMBtu gas price adjustment
    re_price_adj: float = 0.0,     # $/MWh RE electricity price adjustment
    biomass_price_adj: float = 0.0, # $/GJ biomass price adjustment
) -> Tuple[Optional[np.ndarray], int, str]:
    cfg = SECTOR_CONFIGS[sector_id]
    routes = cfg["routes"]
    R, T = len(routes), len(YEARS)
    NV = 3 * R * T

    def iNC(r, t):  return r * T + t
    def iCAP(r, t): return R * T + r * T + t
    def iACT(r, t): return 2 * R * T + r * T + t

    d_anch = demand_anchors or cfg["demand"].get(scenario, next(iter(cfg["demand"].values())))
    demand = {y: _interp(d_anch, y) for y in YEARS}
    cp_anch = carbon_price_anchors or cfg["carbon_price"].get(scenario, {})
    gp_anch = ({y: green_premium_val for y in [2024, 2069]}
                if green_premium_val is not None
                else cfg["green_premium"].get(scenario, {}))
    gp_routes = cfg.get("green_premium_routes", set())

    # Sector-specific fuel price adjustments (per tonne of product)
    # Approximate energy intensities by sector for price adjustment propagation
    _FUEL_INTENSITY: Dict[str, Dict[str, float]] = {
        "cement":     {"coal": 0.07, "gas": 0.0},     # ~70 kg coal/t cement (t thermal coal)
        "aluminium":  {"re": 13.5, "coal": 0.0},       # ~13.5 MWh/t Al electricity
        "textile":    {"coal": 0.026, "gas": 0.022, "biomass": 0.024},  # t fuel/t fibre
        "fertiliser": {"coal": 0.0, "gas": 0.085},    # 0.085 MMBtu/t urea (SMR)
    }
    fi = _FUEL_INTENSITY.get(sector_id, {})

    c = np.zeros(NV)
    for ri, route in enumerate(routes):
        capex = route["capex"] * capex_mult * (1.0 + wacc_adj_pct / 100.0)
        vom = route["vom_total"] + (h2_cost_adj if route.get("h2_route") else 0.0)
        # Apply fuel price adjustments to VOM based on route type
        rid = route["id"]
        if "Coal" in rid or "coal" in rid.lower():
            vom += coal_price_adj * fi.get("coal", 0.0)
        if "Gas" in rid or "NG" in rid or "gas" in rid.lower():
            vom += gas_price_adj * fi.get("gas", 0.0)
        if "RE" in rid or "re" in rid.lower():
            vom += re_price_adj * fi.get("re", 0.0)
        if "Biomass" in rid or "bio" in rid.lower():
            vom += biomass_price_adj * fi.get("biomass", 0.0)
        for ti, y in enumerate(YEARS):
            disc = (1.0 / (1.0 + DISCOUNT_RATE)) ** (y - 2024)
            ef = _ef(route, scenario, y)
            cp = _interp(cp_anch, y) if cp_anch else 0.0
            gp = _interp(gp_anch, y) if route["id"] in gp_routes else 0.0
            c[iNC(ri, ti)]  = disc * capex
            c[iCAP(ri, ti)] = disc * route["fom"] * DT
            c[iACT(ri, ti)] = disc * (vom + ef * cp - gp) * DT

    row_lb: List[float] = []
    row_ub: List[float] = []
    A_rows: List[Dict[int, float]] = []

    def add(lb, ub, d):
        row_lb.append(lb); row_ub.append(ub); A_rows.append(d)

    for ti, y in enumerate(YEARS):
        rhs = demand[y] * DT
        add(rhs, rhs, {iACT(ri, ti): 1.0 for ri in range(R)})
        for ri, route in enumerate(routes):
            lt = route["lifetime"]
            add(-np.inf, 0.0, {iACT(ri, ti): 1.0, iCAP(ri, ti): -route["avail"] * DT})
            surv = _surviving(route["existing"], y, lt)
            if ti == 0:
                add(surv, surv, {iCAP(ri, 0): 1.0, iNC(ri, 0): -1.0})
            else:
                delta = surv - _surviving(route["existing"], YEARS[ti - 1], lt)
                add(delta, delta, {iCAP(ri, ti): 1.0, iCAP(ri, ti-1): -1.0, iNC(ri, ti): -1.0})

    if enforce_co2_ceiling and scenario.upper() == "NZS":
        ceiling = cfg.get("nzs_co2_ceiling_2069")
        if ceiling is not None:
            ti69, y69 = T - 1, YEARS[-1]
            add(-np.inf, ceiling * demand[y69] * DT,
                {iACT(ri, ti69): _ef(routes[ri], scenario, y69) for ri in range(R)})

    for ri, route in enumerate(routes):
        cap_dict = route.get("scrap_frac_cap")
        if cap_dict:
            for ti, y in enumerate(YEARS):
                add(-np.inf, _interp(cap_dict, y) * demand[y] * DT, {iACT(ri, ti): 1.0})

    n_con = len(A_rows)
    A_lil = lil_matrix((n_con, NV))
    lb_arr = np.array(row_lb, dtype=float)
    ub_arr = np.array(row_ub, dtype=float)
    for ci, row_d in enumerate(A_rows):
        for col, val in row_d.items():
            A_lil[ci, col] = val
    constraints = LinearConstraint(A_lil.tocsr(), lb_arr, ub_arr)

    lb_v = np.zeros(NV)
    ub_v = np.full(NV, np.inf)
    for ri, route in enumerate(routes):
        sc_key = scenario.lower() if scenario.lower() in ("cps", "nzs") else "cps"
        cutoff = route.get(f"cutoff_{sc_key}")
        for ti, y in enumerate(YEARS):
            if y < route["start"] or (cutoff is not None and y > cutoff):
                ub_v[iNC(ri, ti)] = 0.0
            else:
                ub_v[iNC(ri, ti)] = route["max_ramp"] * DT
    bounds = Bounds(lb=lb_v, ub=ub_v)

    result = milp(c, constraints=constraints, integrality=np.zeros(NV),
                  bounds=bounds, options={"time_limit": 60.0, "disp": False})

    if result.status == 0:
        return result.x, 0, "optimal"
    elif result.status == 1:
        return (result.x, 2, "time_limit") if result.x is not None else (None, 1, "time_limit_no_sol")
    elif result.status == 2:
        return None, 1, f"infeasible: {result.message}"
    elif result.status == 3:
        return None, 1, f"unbounded: {result.message}"
    else:
        return None, -1, f"status_{result.status}: {result.message}"


def extract_yearly(
    x: np.ndarray, sector_id: str, scenario: str,
    demand_anchors: Optional[Dict[int, float]] = None,
) -> Dict[int, Dict]:
    cfg = SECTOR_CONFIGS[sector_id]
    routes = cfg["routes"]
    R, T = len(routes), len(YEARS)

    def iNC(r, t):  return r * T + t
    def iCAP(r, t): return R * T + r * T + t
    def iACT(r, t): return 2 * R * T + r * T + t

    d_anch = demand_anchors or cfg["demand"].get(scenario, next(iter(cfg["demand"].values())))

    lp: Dict[int, Dict] = {}
    for ti, y in enumerate(YEARS):
        pbr: Dict[str, float] = {}
        inv_br: Dict[str, float] = {}
        total = co2 = total_cost = total_inv = 0.0
        for ri, route in enumerate(routes):
            prod     = max(0.0, float(x[iACT(ri, ti)]) / DT)   # Mt/yr
            cap      = max(0.0, float(x[iCAP(ri, ti)]))          # Mt/yr capacity
            ncap     = max(0.0, float(x[iNC(ri, ti)]))           # Mt/yr new capacity
            capex_r  = route["capex"]                             # $/t annualised
            vom_r    = route["vom_total"]                         # $/t
            fom_r    = route["fom"]                               # $/t/yr
            # Cost in M$/yr: prod[Mt/yr] × rate[$/t] = M$/yr (since 1 Mt × 1 $/t = 1 M$)
            route_vom   = prod   * vom_r
            route_fom   = cap    * fom_r
            route_capex = ncap   * capex_r
            route_cost  = route_vom + route_fom + route_capex
            pbr[route["id"]]     = round(prod, 4)
            inv_br[route["id"]]  = round(route_capex, 2)
            total += prod
            co2   += prod * _ef(route, scenario, y)
            total_cost += route_cost
            total_inv  += route_capex
        lp[y] = {
            "year": y,
            "total_production":  round(total, 3),
            "co2_intensity":     round(co2 / total, 4) if total > 0 else 0.0,
            "co2_total":         round(co2, 3),
            "production_by_route": pbr,
            "investment_by_route": inv_br,
            "total_cost":        round(total_cost, 1),
            "total_investment":  round(total_inv, 1),
        }

    yearly: Dict[int, Dict] = {}
    for y in ALL_YEARS:
        if y in lp:
            yearly[y] = dict(lp[y]); yearly[y]["year"] = y; continue
        if y > YEARS[-1]:
            base = lp[YEARS[-1]]
            d_y = _interp(d_anch, y)
            scale = d_y / base["total_production"] if base["total_production"] > 0 else 1.0
            pbr = {k: round(v * scale, 4) for k, v in base["production_by_route"].items()}
            co2 = sum(pbr.get(rt["id"], 0) * _ef(rt, scenario, y) for rt in routes)
            yearly[y] = {
                "year": y, "total_production": round(d_y, 3),
                "co2_intensity": round(co2/d_y, 4) if d_y > 0 else 0.0,
                "co2_total": round(co2, 3), "production_by_route": pbr,
                "investment_by_route": {k: 0.0 for k in pbr},
                "total_cost": round(sum(pbr.get(rt["id"], 0) * rt["vom_total"] for rt in routes), 1),
                "total_investment": 0.0,
            }
            continue
        lo = max(lpy for lpy in YEARS if lpy <= y)
        hi = min(lpy for lpy in YEARS if lpy >= y)
        if lo == hi:
            yearly[y] = dict(lp[lo]); yearly[y]["year"] = y; continue
        f = (y - lo) / (hi - lo)
        ld, hd = lp[lo], lp[hi]
        pbr = {rid: round(ld["production_by_route"].get(rid, 0) * (1-f)
                          + hd["production_by_route"].get(rid, 0) * f, 4)
               for rid in ld["production_by_route"]}
        total = sum(pbr.values())
        co2 = sum(pbr.get(rt["id"], 0) * _ef(rt, scenario, y) for rt in routes)
        inv_br = {rid: round(ld["investment_by_route"].get(rid, 0) * (1-f)
                             + hd["investment_by_route"].get(rid, 0) * f, 2)
                  for rid in ld["investment_by_route"]}
        tc = round(ld["total_cost"] * (1-f) + hd["total_cost"] * f, 1)
        ti_val = round(ld["total_investment"] * (1-f) + hd["total_investment"] * f, 1)
        yearly[y] = {
            "year": y, "total_production": round(total, 3),
            "co2_intensity": round(co2/total, 4) if total > 0 else 0.0,
            "co2_total": round(co2, 3), "production_by_route": pbr,
            "investment_by_route": inv_br, "total_cost": tc, "total_investment": ti_val,
        }
    return yearly


def make_app(sector_id: str) -> FastAPI:
    cfg = SECTOR_CONFIGS[sector_id]
    vol4 = cfg["vol4"]
    app = FastAPI(title=f"{sector_id.capitalize()} MILP Backend", version="3.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    def health():
        return {"status": "ok", "sector": sector_id, "model": "HiGHS LP",
                "port": cfg["port"], "vol4_cps_2070": vol4["cps_2070"],
                "vol4_nzs_2070": vol4["nzs_2070"]}

    @app.get("/api/scenarios")
    def scenarios():
        return {"scenarios": [{"key": "CPS", "label": "Current Policy Scenario"},
                               {"key": "NZS", "label": "Net Zero Scenario"}]}

    @app.get("/api/routes")
    def route_details():
        return {"routes": [{
            "id": r["id"],
            "existing": r["existing"],
            "capex": r["capex"],
            "fom": r["fom"],
            "vom_total": r["vom_total"],
            "ef_2024": r["ef_2024"],
            "ef_cps_2050": r.get("ef_cps_2050"),
            "ef_nzs_2050": r.get("ef_nzs_2050"),
            "avail": r["avail"],
            "start": r["start"],
            "max_ramp": r["max_ramp"],
            "lifetime": r["lifetime"],
            "h2_route": r.get("h2_route", False),
        } for r in cfg["routes"]]}

    @app.get("/api/demand-trajectories")
    def demand_trajectories():
        return {sc: {str(y): _interp(anch, y) for y in ALL_YEARS}
                for sc, anch in cfg["demand"].items()}

    @app.post("/api/run")
    async def run_scenario(payload: dict):
        scenario = payload.get("scenario", "CPS").upper()
        if scenario not in ("CPS", "NZS"):
            return {"status": "error", "message": f"Unknown scenario: {scenario}"}
        # Optional demand anchors override (for demand pathway selection in UI)
        d_anch: Optional[Dict[int, float]] = None
        if payload.get("demand_anchors"):
            d_anch = {}
            for k, v in payload["demand_anchors"].items():
                try: d_anch[int(k)] = float(v)
                except: pass
        import asyncio, functools
        loop = asyncio.get_event_loop()
        x, sc, msg = await loop.run_in_executor(None, functools.partial(solve_sector_lp, sector_id, scenario, enforce_co2_ceiling=True, demand_anchors=d_anch))
        if x is None:
            return {"status": "infeasible", "message": msg, "sector": sector_id, "scenario": scenario}
        yearly = extract_yearly(x, sector_id, scenario, d_anch)
        cum = sum(yr["co2_total"] for yr in yearly.values())
        return {"status": "optimal" if sc == 0 else "feasible", "message": msg,
                "sector": sector_id, "scenario": scenario, "years": ALL_YEARS,
                "yearly_results": {str(y): v for y, v in yearly.items()},
                "summary": {"co2_intensity_2070": yearly[2070]["co2_intensity"],
                             "co2_intensity_2050": yearly[2050]["co2_intensity"],
                             "co2_total_2070": yearly[2070]["co2_total"],
                             "production_2070": yearly[2070]["total_production"],
                             "cumulative_co2_mt": round(cum, 1),
                             "vol4_cps_2070": vol4["cps_2070"],
                             "vol4_nzs_2070": vol4["nzs_2070"]}}

    @app.post("/api/lab/run")
    async def lab_run(payload: dict):
        # Normalize scenario: "LAB" or unknown → "CPS"
        raw_sc = payload.get("scenario", "CPS").upper()
        scenario = raw_sc if raw_sc in ("CPS", "NZS") else "CPS"

        # Carbon price: accept dict {year: value} or scalar
        cp_anch: Dict[int, float] = {}
        for k, v in payload.get("carbon_price", {}).items():
            try: cp_anch[int(k)] = float(v)
            except: pass
        if not cp_anch:
            cp_anch = cfg["carbon_price"].get(scenario, {})

        # Demand anchors
        d_anch: Optional[Dict[int, float]] = None
        if payload.get("demand_anchors"):
            d_anch = {}
            for k, v in payload["demand_anchors"].items():
                try: d_anch[int(k)] = float(v)
                except: pass

        # Economics params — accept both key variants
        capex_m = float(payload.get("capex_multiplier", 1.0))
        # wacc: frontend may send "wacc" (fraction) or "wacc_pct" (percent)
        if "wacc_pct" in payload:
            wacc = float(payload["wacc_pct"])
        elif "wacc" in payload:
            wacc = float(payload["wacc"]) * 100.0  # convert fraction → pct
        else:
            wacc = 0.0
        # h2_cost: frontend sends dict {"2030": v, "2050": v} or scalar "h2_cost_adj"
        h2adj = 0.0
        if "h2_cost_adj" in payload:
            try: h2adj = float(payload["h2_cost_adj"])
            except: pass
        elif "h2_cost" in payload:
            # Average the h2 cost values as a simple scalar adjustment
            vals = [float(v) for v in payload["h2_cost"].values() if v is not None]
            h2adj = sum(vals) / len(vals) if vals else 0.0
        gp_val: Optional[float] = None
        if "green_premium" in payload:
            try: gp_val = float(payload["green_premium"])
            except: pass
        # Sector-specific fuel price adjustments
        coal_adj = float(payload.get("coal_price_adj", 0.0))
        gas_adj = float(payload.get("gas_price_adj", 0.0))
        re_adj = float(payload.get("re_price_adj", 0.0))
        biomass_adj = float(payload.get("biomass_price_adj", 0.0))

        import asyncio, functools
        loop = asyncio.get_event_loop()
        x, sc, msg = await loop.run_in_executor(None, functools.partial(solve_sector_lp, sector_id, scenario,
                                      demand_anchors=d_anch, carbon_price_anchors=cp_anch,
                                      green_premium_val=gp_val, capex_mult=capex_m,
                                      h2_cost_adj=h2adj, wacc_adj_pct=wacc,
                                      enforce_co2_ceiling=False,
                                      coal_price_adj=coal_adj, gas_price_adj=gas_adj,
                                      re_price_adj=re_adj, biomass_price_adj=biomass_adj))
        if x is None:
            return {"status": "infeasible", "message": msg, "sector": sector_id, "scenario": scenario}
        yearly = extract_yearly(x, sector_id, scenario, d_anch)
        cum = sum(yr["co2_total"] for yr in yearly.values())
        return {"status": "optimal" if sc == 0 else "feasible", "message": msg,
                "sector": sector_id, "scenario": f"LAB-{scenario}", "years": ALL_YEARS,
                "yearly_results": {str(y): v for y, v in yearly.items()},
                "summary": {"co2_intensity_2070": yearly[2070]["co2_intensity"],
                             "co2_intensity_2050": yearly[2050]["co2_intensity"],
                             "co2_total_2070": yearly[2070]["co2_total"],
                             "production_2070": yearly[2070]["total_production"],
                             "cumulative_co2_mt": round(cum, 1),
                             "vol4_cps_2070": vol4["cps_2070"],
                             "vol4_nzs_2070": vol4["nzs_2070"]}}

    return app


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in SECTOR_CONFIGS:
        print(f"Usage: python {sys.argv[0]} cement|aluminium|textile|fertiliser")
        sys.exit(1)
    sector = sys.argv[1]
    port = SECTOR_CONFIGS[sector]["port"]
    print(f"Starting {sector.capitalize()} MILP backend on port {port} ...")
    uvicorn.run(make_app(sector), host="0.0.0.0", port=port, log_level="info")
