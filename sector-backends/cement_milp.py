"""
Cement MILP Backend — India Transition Lab (port 8001)

Capacity-expansion Linear Programme for India's cement sector (2024-2070).
Solver: scipy.optimize.milp (HiGHS, same as steel MILP).

Technology routes (matching lib/sectors.ts IDs exactly):
  Coal-OPC        — Coal kiln, Ordinary Portland Cement        0.83 tCO2/t
  Coal-Blended    — Coal kiln, blended PPC/PSC                 0.62 tCO2/t
  Coal-LC3        — Coal kiln, LC3 cement                      0.50 tCO2/t
  AltFuel-Blended — Alternative-fuel kiln, blended cement      0.42 tCO2/t
  CCUS-Blended    — Coal kiln + CCS, blended cement            0.10 tCO2/t

Scenario calibration (NITI Vol.4):
  CPS 2070: 0.40 tCO2/t cement (demand 850 Mt → 340 Mt CO2)
  NZS 2070: 0.08 tCO2/t cement (demand 820 Mt →  66 Mt CO2)
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

# ════════════════════════════════════════════════════════════════════════════
# CEMENT SECTOR PARAMETERS
# ════════════════════════════════════════════════════════════════════════════

ROUTES: List[Dict[str, Any]] = [
    # id              existing_2024  co2_2024  co2_cps_2050  co2_cps_2070  co2_nzs_2050  co2_nzs_2070
    # capex_ann(USD/t·yr)  opex_vom(USD/t)  avail  start_year  max_ramp_mt_yr  cutoff_cps  cutoff_nzs
    {
        "id": "Coal-OPC",
        "existing": 130.0,       # Mt capacity 2024 — dominant old wet/semi-dry kilns
        "co2_2024": 0.83,
        "co2_cps_2050": 0.80, "co2_cps_2070": 0.78,
        "co2_nzs_2050": 0.78, "co2_nzs_2070": 0.76,
        "capex": 18.0,           # USD/t/yr annualised (25yr lifetime)
        "opex": 42.0,            # USD/t opex + VOM
        "avail": 0.90,
        "start": 2024,
        "max_ramp": 15.0,        # Mt/yr max new capacity
        "cutoff_cps": 2034,      # no new Coal-OPC after 2034 in CPS
        "cutoff_nzs": 2027,      # no new Coal-OPC after 2027 in NZS
    },
    {
        "id": "Coal-Blended",
        "existing": 195.0,       # dominant modern dry kilns
        "co2_2024": 0.62,
        "co2_cps_2050": 0.57, "co2_cps_2070": 0.52,
        "co2_nzs_2050": 0.50, "co2_nzs_2070": 0.45,
        "capex": 16.0,
        "opex": 38.0,
        "avail": 0.90,
        "start": 2024,
        "max_ramp": 25.0,
        "cutoff_cps": 2048,
        "cutoff_nzs": 2034,
    },
    {
        "id": "Coal-LC3",
        "existing": 20.0,        # nascent LC3 plants (clinker factor ~0.50)
        "co2_2024": 0.50,
        "co2_cps_2050": 0.44, "co2_cps_2070": 0.40,
        "co2_nzs_2050": 0.40, "co2_nzs_2070": 0.36,
        "capex": 17.0,
        "opex": 36.0,
        "avail": 0.90,
        "start": 2025,
        "max_ramp": 30.0,
        "cutoff_cps": None,
        "cutoff_nzs": 2038,
    },
    {
        "id": "AltFuel-Blended",
        "existing": 50.0,        # waste heat / TDF / biomass co-firing
        "co2_2024": 0.42,
        "co2_cps_2050": 0.36, "co2_cps_2070": 0.30,
        "co2_nzs_2050": 0.28, "co2_nzs_2070": 0.22,
        "capex": 20.0,
        "opex": 40.0,
        "avail": 0.88,
        "start": 2024,
        "max_ramp": 30.0,
        "cutoff_cps": None,
        "cutoff_nzs": None,
    },
    {
        "id": "CCUS-Blended",
        "existing": 0.0,
        "co2_2024": 0.10,
        "co2_cps_2050": 0.09, "co2_cps_2070": 0.08,
        "co2_nzs_2050": 0.08, "co2_nzs_2070": 0.06,
        "capex": 55.0,
        "opex": 52.0,
        "avail": 0.85,
        "start": 2030,
        "max_ramp": 30.0,
        "cutoff_cps": None,
        "cutoff_nzs": None,
    },
]

# Demand anchors (Mt/yr) for standard scenarios — NITI Vol.4
DEMAND: Dict[str, Dict[int, float]] = {
    "CPS": {2024: 395, 2030: 468, 2040: 590, 2050: 700, 2060: 790, 2070: 850},
    "NZS": {2024: 395, 2030: 462, 2040: 578, 2050: 685, 2060: 760, 2070: 820},
}

# Vol.4 CO2 intensity ceilings — enforced as hard LP constraints in /api/run
# (ensures optimizer always hits the published targets exactly)
CO2_CEILING: Dict[str, Dict[int, float]] = {
    "CPS": {2050: 0.52, 2070: 0.40},
    "NZS": {2050: 0.35, 2070: 0.08},
}

# Carbon price trajectory (USD/tCO2) — shapes relative route economics
CARBON_PRICE: Dict[str, Dict[int, float]] = {
    "CPS": {2024: 5, 2030: 15, 2040: 32, 2050: 55, 2060: 65, 2070: 75},
    "NZS": {2024: 12, 2030: 45, 2040: 110, 2050: 190, 2060: 225, 2070: 260},
}

# Green premium for qualifying routes (USD/t cement) — export premium for low-carbon product
GREEN_PREMIUM_ROUTES = {"AltFuel-Blended", "CCUS-Blended"}
GREEN_PREMIUM: Dict[str, Dict[int, float]] = {
    "CPS": {2024: 0, 2040: 3, 2050: 6, 2070: 12},
    "NZS": {2024: 5, 2030: 15, 2040: 30, 2050: 55, 2070: 80},
}

DISCOUNT_RATE = 0.08
PLANT_LIFETIME = 25   # years


# ════════════════════════════════════════════════════════════════════════════
# LP ENGINE
# ════════════════════════════════════════════════════════════════════════════

YEARS = list(range(2024, 2071))   # 47 years
T = len(YEARS)
R = len(ROUTES)
YEAR_IDX = {y: i for i, y in enumerate(YEARS)}


def _interp(anchors: Dict[int, float], y: int) -> float:
    """Piecewise linear interpolation over integer-keyed anchor dict."""
    ys = sorted(anchors)
    if y <= ys[0]:
        return anchors[ys[0]]
    if y >= ys[-1]:
        return anchors[ys[-1]]
    for lo, hi in zip(ys, ys[1:]):
        if lo <= y <= hi:
            f = (y - lo) / (hi - lo)
            return anchors[lo] + f * (anchors[hi] - anchors[lo])
    return anchors[ys[-1]]


def _co2(route: Dict, scenario: str, y: int) -> float:
    """CO2 intensity for route at year y, piecewise through 2024/2050/2070."""
    c24 = route["co2_2024"]
    c50 = route[f"co2_{scenario.lower()}_2050"]
    c70 = route[f"co2_{scenario.lower()}_2070"]
    if y <= 2024:
        return c24
    elif y <= 2050:
        f = (y - 2024) / 26.0
        return c24 + f * (c50 - c24)
    else:
        f = (y - 2050) / 20.0
        return c50 + f * (c70 - c50)


def _remaining(route: Dict, y: int) -> float:
    """Surviving existing capacity (linear retirement over PLANT_LIFETIME)."""
    age = y - 2024
    if age >= PLANT_LIFETIME:
        return 0.0
    return route["existing"] * (1.0 - age / PLANT_LIFETIME)


def act_idx(i: int, t: int) -> int:
    return i * T + t


def ncap_idx(i: int, t: int) -> int:
    return R * T + i * T + t


def solve(
    scenario: str,
    demand_anchors: Optional[Dict[int, float]] = None,
    carbon_price_anchors: Optional[Dict[int, float]] = None,
    green_premium_val: Optional[float] = None,
    capex_mult: float = 1.0,
    h2_cost_adj: float = 0.0,
    wacc_adj_pct: float = 0.0,
    enforce_co2_ceiling: bool = True,
) -> Tuple[Optional[np.ndarray], int, str]:
    """
    Solve the cement LP.

    Returns (x_opt, status, message):
      x_opt: solution vector of length 2*R*T, or None on failure
      status: 0=optimal, 1=infeasible, 2=time-limit, -1=other
      message: human-readable status
    """
    n_vars = 2 * R * T

    # ── Demand ────────────────────────────────────────────────────────────
    d_anchors = demand_anchors or DEMAND.get(scenario, DEMAND["CPS"])
    demand = {y: _interp(d_anchors, y) for y in YEARS}

    # ── Carbon price ──────────────────────────────────────────────────────
    cp_anchors = carbon_price_anchors or CARBON_PRICE.get(scenario, CARBON_PRICE["CPS"])

    # ── Green premium ─────────────────────────────────────────────────────
    if green_premium_val is not None:
        gp_anchors: Dict[int, float] = {2024: green_premium_val, 2070: green_premium_val}
    else:
        gp_anchors = GREEN_PREMIUM.get(scenario, GREEN_PREMIUM["CPS"])

    # ── Objective ─────────────────────────────────────────────────────────
    c_obj = np.zeros(n_vars)
    for i, route in enumerate(ROUTES):
        capex = route["capex"] * capex_mult
        # WACC premium: increases effective capex for each percentage point above 8%
        if wacc_adj_pct > 0:
            capex *= (1 + wacc_adj_pct / 100.0)
        opex = route["opex"]
        for t, y in enumerate(YEARS):
            disc = (1.0 / (1.0 + DISCOUNT_RATE)) ** (y - 2024)
            co2 = _co2(route, scenario, y)
            cp = _interp(cp_anchors, y)
            gp = _interp(gp_anchors, y) if route["id"] in GREEN_PREMIUM_ROUTES else 0.0

            c_obj[ncap_idx(i, t)] = disc * capex
            c_obj[act_idx(i, t)] = disc * (opex + co2 * cp - gp)

    # ── Constraints ───────────────────────────────────────────────────────
    rows: List[Tuple[float, float, Dict[int, float]]] = []

    # 1. Demand balance (equality): Σ_i act[i,t] = demand[t]
    for t, y in enumerate(YEARS):
        row: Dict[int, float] = {act_idx(i, t): 1.0 for i in range(R)}
        rows.append((demand[y], demand[y], row))

    # 2. Activity cap: act[i,t] - avail[i] * Σ_{s≤t} ncap[i,s] ≤ avail[i] * remaining[i,t]
    for i, route in enumerate(ROUTES):
        avail = route["avail"]
        for t, y in enumerate(YEARS):
            row = {act_idx(i, t): 1.0}
            for s in range(t + 1):
                row[ncap_idx(i, s)] = -avail
            ub = avail * _remaining(route, y)
            rows.append((-np.inf, ub, row))

    # 3. CO2 ceiling at target years (Vol.4 — only in /api/run, not Lab)
    if enforce_co2_ceiling:
        for target_y, target_int in CO2_CEILING.get(scenario, {}).items():
            if target_y not in YEAR_IDX:
                continue
            t = YEAR_IDX[target_y]
            row = {act_idx(i, t): _co2(ROUTES[i], scenario, target_y) for i in range(R)}
            rows.append((-np.inf, target_int * demand[target_y], row))

    # Build sparse matrix
    n_con = len(rows)
    A_lil = lil_matrix((n_con, n_vars))
    lb_arr = np.full(n_con, -np.inf)
    ub_arr = np.zeros(n_con)
    for c_i, (lb_v, ub_v, row_d) in enumerate(rows):
        for col, val in row_d.items():
            A_lil[c_i, col] = val
        lb_arr[c_i] = lb_v
        ub_arr[c_i] = ub_v

    constraints = LinearConstraint(A_lil.tocsr(), lb_arr, ub_arr)

    # ── Variable bounds ───────────────────────────────────────────────────
    lb_v = np.zeros(n_vars)
    ub_v = np.full(n_vars, np.inf)

    for i, route in enumerate(ROUTES):
        start_y = route["start"]
        max_ramp = route["max_ramp"]
        cutoff = route.get(f"cutoff_{scenario.lower()}")
        for t, y in enumerate(YEARS):
            if y < start_y:
                ub_v[ncap_idx(i, t)] = 0.0
            elif cutoff is not None and y > cutoff:
                ub_v[ncap_idx(i, t)] = 0.0
            else:
                ub_v[ncap_idx(i, t)] = max_ramp

    bounds = Bounds(lb=lb_v, ub=ub_v)

    # ── Solve ─────────────────────────────────────────────────────────────
    result = milp(
        c_obj,
        constraints=constraints,
        integrality=np.zeros(n_vars),
        bounds=bounds,
        options={"time_limit": 60.0, "disp": False},
    )

    if result.status == 0:
        return result.x, 0, "optimal"
    elif result.status == 2:
        return result.x, 2, "time_limit_feasible"
    elif result.status == 3:
        return None, 1, "infeasible"
    else:
        return None, -1, f"solver_status_{result.status}: {result.message}"


def extract_results(
    x: np.ndarray,
    scenario: str,
    demand_anchors: Optional[Dict[int, float]] = None,
    carbon_price_anchors: Optional[Dict[int, float]] = None,
) -> Dict[int, Dict]:
    """Parse LP solution vector into yearly result dicts."""
    d_anchors = demand_anchors or DEMAND.get(scenario, DEMAND["CPS"])
    cp_anchors = carbon_price_anchors or CARBON_PRICE.get(scenario, CARBON_PRICE["CPS"])
    demand = {y: _interp(d_anchors, y) for y in YEARS}

    yearly: Dict[int, Dict] = {}
    for t, y in enumerate(YEARS):
        prod_by_route: Dict[str, float] = {}
        total = 0.0
        co2_total = 0.0
        for i, route in enumerate(ROUTES):
            act = float(x[act_idx(i, t)])
            act = max(0.0, act)
            prod_by_route[route["id"]] = round(act, 3)
            total += act
            co2_total += act * _co2(route, scenario, y)
        intensity = co2_total / total if total > 0 else 0.0
        total_cost = sum(
            float(x[act_idx(i, t)]) * (ROUTES[i]["opex"] + _co2(ROUTES[i], scenario, y) * _interp(cp_anchors, y))
            + float(x[ncap_idx(i, t)]) * ROUTES[i]["capex"]
            for i in range(R)
        )
        yearly[y] = {
            "year": y,
            "total_production": round(total, 2),
            "co2_intensity": round(intensity, 4),
            "co2_total": round(co2_total, 2),
            "production_by_route": prod_by_route,
            "cost_usd_million": round(total_cost, 1),
        }
    return yearly


# ════════════════════════════════════════════════════════════════════════════
# FastAPI APPLICATION
# ════════════════════════════════════════════════════════════════════════════

app = FastAPI(title="Cement MILP Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "sector": "cement", "model": "HiGHS LP", "port": 8001}


@app.get("/api/scenarios")
def scenarios():
    return {
        "scenarios": [
            {"key": "CPS", "label": "Current Policy Scenario", "description": "Existing policies extended"},
            {"key": "NZS", "label": "Net Zero Scenario", "description": "Aggressive decarbonisation"},
        ]
    }


@app.get("/api/demand-trajectories")
def demand_trajectories():
    """Return piecewise demand trajectories for the frontend Demand Explorer."""
    result = {}
    for sc, anchors in DEMAND.items():
        result[sc] = {str(y): _interp(anchors, y) for y in range(2024, 2071)}
    return result


@app.post("/api/run")
async def run_scenario(payload: dict):
    scenario = payload.get("scenario", "CPS").upper()
    if scenario not in ("CPS", "NZS"):
        return {"status": "error", "message": f"Unknown scenario: {scenario}"}

    x, status_code, msg = solve(scenario, enforce_co2_ceiling=True)

    if x is None:
        return {
            "status": "infeasible",
            "message": msg,
            "sector": "cement",
            "scenario": scenario,
        }

    yearly = extract_results(x, scenario)
    yr_2070 = yearly[2070]
    yr_2050 = yearly[2050]
    cum_co2 = sum(yr["co2_total"] for yr in yearly.values())

    return {
        "status": "optimal" if status_code == 0 else "feasible",
        "message": msg,
        "sector": "cement",
        "scenario": scenario,
        "years": YEARS,
        "yearly_results": {str(y): v for y, v in yearly.items()},
        "summary": {
            "co2_intensity_2070": yr_2070["co2_intensity"],
            "co2_intensity_2050": yr_2050["co2_intensity"],
            "co2_total_2070": yr_2070["co2_total"],
            "production_2070": yr_2070["total_production"],
            "cumulative_co2_mt": round(cum_co2, 1),
            "vol4_cps_2070": 0.40,
            "vol4_nzs_2070": 0.08,
        },
    }


@app.post("/api/lab/run")
async def lab_run(payload: dict):
    """Lab mode: user-controlled parameters, no Vol.4 CO2 ceiling constraint."""
    scenario = payload.get("scenario", "CPS").upper()

    # Carbon price anchors from lab sliders
    cp_raw = payload.get("carbon_price", {})
    cp_anchors: Dict[int, float] = {}
    for k, v in cp_raw.items():
        try:
            cp_anchors[int(k)] = float(v)
        except (ValueError, TypeError):
            pass
    if not cp_anchors:
        cp_anchors = CARBON_PRICE.get(scenario, CARBON_PRICE["CPS"])

    # Demand from lab selector
    demand_raw = payload.get("demand_anchors", {})
    d_anchors: Optional[Dict[int, float]] = None
    if demand_raw:
        d_anchors = {}
        for k, v in demand_raw.items():
            try:
                d_anchors[int(k)] = float(v)
            except (ValueError, TypeError):
                pass

    capex_mult = float(payload.get("capex_multiplier", 1.0))
    green_prem = payload.get("green_premium")
    wacc_adj = float(payload.get("wacc_pct", 0.0))
    h2_adj = float(payload.get("h2_cost_adj", 0.0))

    green_val: Optional[float] = None
    if green_prem is not None:
        try:
            green_val = float(green_prem)
        except (ValueError, TypeError):
            pass

    x, status_code, msg = solve(
        scenario,
        demand_anchors=d_anchors,
        carbon_price_anchors=cp_anchors,
        green_premium_val=green_val,
        capex_mult=capex_mult,
        h2_cost_adj=h2_adj,
        wacc_adj_pct=wacc_adj,
        enforce_co2_ceiling=False,   # Lab: free optimization
    )

    if x is None:
        return {
            "status": "infeasible",
            "message": msg,
            "sector": "cement",
            "scenario": scenario,
        }

    yearly = extract_results(x, scenario, d_anchors, cp_anchors)
    cum_co2 = sum(yr["co2_total"] for yr in yearly.values())

    return {
        "status": "optimal" if status_code == 0 else "feasible",
        "message": msg,
        "sector": "cement",
        "scenario": f"LAB-{scenario}",
        "years": YEARS,
        "yearly_results": {str(y): v for y, v in yearly.items()},
        "summary": {
            "co2_intensity_2070": yearly[2070]["co2_intensity"],
            "co2_intensity_2050": yearly[2050]["co2_intensity"],
            "co2_total_2070": yearly[2070]["co2_total"],
            "production_2070": yearly[2070]["total_production"],
            "cumulative_co2_mt": round(cum_co2, 1),
            "vol4_cps_2070": 0.40,
            "vol4_nzs_2070": 0.08,
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
