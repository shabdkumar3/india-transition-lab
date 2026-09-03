"""
Universal Sector Transition Backend
====================================
FastAPI analytical transition model for non-steel sectors.
Produces realistic decarbonisation pathways calibrated to NITI Aayog Vol.4 targets.

Usage:
    python sector_backend.py cement          # port 8001
    python sector_backend.py aluminium       # port 8002
    python sector_backend.py textile         # port 8003
    python sector_backend.py fertiliser      # port 8004
"""

import sys
from typing import Any, Dict, Optional
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Sector Configuration ──────────────────────────────────────────────────────

SECTOR_CONFIGS: Dict[str, Any] = {

    "cement": {
        "port": 8001,
        "label": "Cement",
        "unit_short": "Mt",
        "demand_niti":          {2024:395, 2030:490, 2035:560, 2040:615, 2050:700, 2060:780, 2070:850},
        "demand_model_fitted":  {2024:395, 2030:447, 2035:494, 2040:519, 2050:551, 2060:567, 2070:572},
        "demand_india_policy":  {2024:395, 2030:462, 2035:524, 2040:578, 2050:647, 2060:696, 2070:730},
        "demand_international": {2024:395, 2030:442, 2035:482, 2040:512, 2050:558, 2060:593, 2070:620},
        "routes": [
            # CPS 2070 intensities: process efficiency gains, same fuel mix
            # NZS 2070 intensities: low due to CCUS near-zero capture
            {"id":"Coal-OPC",        "co2_2024":0.83, "co2_cps_2070":0.72, "co2_nzs_2070":0.70},
            {"id":"Coal-Blended",    "co2_2024":0.62, "co2_cps_2070":0.50, "co2_nzs_2070":0.44},
            {"id":"Coal-LC3",        "co2_2024":0.48, "co2_cps_2070":0.38, "co2_nzs_2070":0.33},
            {"id":"AltFuel-Blended", "co2_2024":0.42, "co2_cps_2070":0.32, "co2_nzs_2070":0.27},
            {"id":"CCUS-Blended",    "co2_2024":0.10, "co2_cps_2070":0.08, "co2_nzs_2070":0.025},
        ],
        # 2024 actual: ~40% OPC, ~45% PPC/PSC blended, small CCUS
        "shares_2024":    [0.40, 0.45, 0.05, 0.08, 0.02],
        # CPS 2070: shift to blended/LC3, moderate CCUS — calibrated to 0.40 tCO2/t
        "shares_cps_2070":[0.07, 0.32, 0.30, 0.22, 0.09],
        # NZS 2070: CCUS-Blended dominant — calibrated to 0.08 tCO2/t
        "shares_nzs_2070":[0.01, 0.03, 0.08, 0.05, 0.83],
        "vol4_co2_cps": {2050:0.52, 2070:0.40},
        "vol4_co2_nzs": {2050:0.35, 2070:0.08},
        "cost_base": 55,
    },

    "aluminium": {
        "port": 8002,
        "label": "Aluminium",
        "unit_short": "Mt",
        "demand_niti":          {2024:4.5,  2030:7.5,  2035:11.0, 2040:14.0, 2050:18.0, 2060:24.0, 2070:28.0},
        "demand_model_fitted":  {2024:4.5,  2030:6.8,  2035:9.5,  2040:12.8, 2050:18.5, 2060:21.2, 2070:22.4},
        "demand_india_policy":  {2024:4.5,  2030:8.5,  2035:12.0, 2040:15.5, 2050:20.0, 2060:22.5, 2070:24.0},
        "demand_international": {2024:4.5,  2030:6.5,  2035:9.0,  2040:11.5, 2050:15.5, 2060:18.0, 2070:20.0},
        "routes": [
            # Grid-Electrolysis: co2 drops with grid decarbonisation (baked into 2070 values)
            # NZS: grid → 0.05 kgCO2/kWh so Grid-Electrolysis ~0.5 tCO2/t
            {"id":"Coal-CPP",          "co2_2024":14.5, "co2_cps_2070":12.0, "co2_nzs_2070":11.0},
            {"id":"Grid-Electrolysis", "co2_2024": 8.0, "co2_cps_2070": 2.5, "co2_nzs_2070": 0.5},
            {"id":"RE-Electrolysis",   "co2_2024": 1.2, "co2_cps_2070": 0.9, "co2_nzs_2070": 0.2},
            {"id":"Inert-Anode",       "co2_2024": 0.5, "co2_cps_2070": 0.4, "co2_nzs_2070": 0.1},
            {"id":"Secondary-Al",      "co2_2024": 0.6, "co2_cps_2070": 0.4, "co2_nzs_2070": 0.2},
        ],
        "shares_2024":    [0.80, 0.10, 0.05, 0.00, 0.05],
        # CPS 2070: partial shift to grid/RE — calibrated to 4.2 tCO2/t
        "shares_cps_2070":[0.28, 0.25, 0.25, 0.06, 0.16],
        # NZS 2070: RE + Inert-Anode dominant — calibrated to ~0.4 tCO2/t
        "shares_nzs_2070":[0.02, 0.05, 0.52, 0.19, 0.22],
        "vol4_co2_cps": {2050:6.5, 2070:4.2},
        "vol4_co2_nzs": {2050:2.8, 2070:0.4},
        "cost_base": 1800,
    },

    "textile": {
        "port": 8003,
        "label": "Textile",
        "unit_short": "Mt",
        "demand_niti":          {2024:19, 2030:26, 2035:34, 2040:43, 2050:55, 2060:67, 2070:80},
        "demand_model_fitted":  {2024:19, 2030:23, 2035:27, 2040:30, 2050:35, 2060:37, 2070:38},
        "demand_india_policy":  {2024:19, 2030:27, 2035:34, 2040:41, 2050:51, 2060:57, 2070:60},
        "demand_international": {2024:19, 2030:24, 2035:29, 2040:33, 2050:39, 2060:43, 2070:45},
        "routes": [
            # RE-Processing NZS 2070: near-zero with 100% RE electricity
            # Circular-Textiles: low intensity with recycled fibre
            {"id":"Coal-Processing",    "co2_2024":3.8, "co2_cps_2070":3.2, "co2_nzs_2070":3.0},
            {"id":"Gas-Processing",     "co2_2024":2.2, "co2_cps_2070":1.8, "co2_nzs_2070":1.5},
            {"id":"Biomass-Processing", "co2_2024":0.8, "co2_cps_2070":0.6, "co2_nzs_2070":0.45},
            {"id":"RE-Processing",      "co2_2024":0.3, "co2_cps_2070":0.22,"co2_nzs_2070":0.025},
            {"id":"Circular-Textiles",  "co2_2024":0.4, "co2_cps_2070":0.25,"co2_nzs_2070":0.04},
        ],
        "shares_2024":    [0.60, 0.20, 0.10, 0.05, 0.05],
        # CPS 2070: moderate shift — calibrated to 1.4 tCO2/t
        "shares_cps_2070":[0.22, 0.28, 0.22, 0.17, 0.11],
        # NZS 2070: RE-Processing + Circular dominant — calibrated to 0.12 tCO2/t
        "shares_nzs_2070":[0.005, 0.02, 0.10, 0.60, 0.275],
        "vol4_co2_cps": {2050:2.1, 2070:1.4},
        "vol4_co2_nzs": {2050:0.9, 2070:0.12},
        "cost_base": 1200,
    },

    "fertiliser": {
        "port": 8004,
        "label": "Fertiliser",
        "unit_short": "Mt",
        "demand_niti":          {2024:30.5, 2030:35.5, 2035:40.5, 2040:45.5, 2050:55.0, 2060:62.5, 2070:70.0},
        "demand_model_fitted":  {2024:30.5, 2030:35.2, 2035:39.8, 2040:43.5, 2050:48.5, 2060:51.2, 2070:52.4},
        "demand_india_policy":  {2024:30.5, 2030:36.5, 2035:42.0, 2040:47.0, 2050:54.0, 2060:58.0, 2070:60.0},
        "demand_international": {2024:30.5, 2030:34.0, 2035:37.5, 2040:40.5, 2050:44.5, 2060:46.8, 2070:48.0},
        "routes": [
            # NG-SMR-CCUS and Green-H2 are key decarbonisation routes
            {"id":"Coal-Gasification","co2_2024":3.5, "co2_cps_2070":3.0, "co2_nzs_2070":2.5},
            {"id":"NG-SMR",           "co2_2024":2.2, "co2_cps_2070":2.0, "co2_nzs_2070":1.5},
            {"id":"NG-SMR-CCUS",      "co2_2024":0.5, "co2_cps_2070":0.35,"co2_nzs_2070":0.05},
            {"id":"Green-H2-Urea",    "co2_2024":0.1, "co2_cps_2070":0.08,"co2_nzs_2070":0.01},
            {"id":"Bio-Ammonia",      "co2_2024":0.3, "co2_cps_2070":0.20,"co2_nzs_2070":0.04},
        ],
        "shares_2024":    [0.70, 0.25, 0.03, 0.01, 0.01],
        # CPS 2070: some NG shift + CCUS — calibrated to 1.2 tCO2/t
        "shares_cps_2070":[0.18, 0.28, 0.30, 0.18, 0.06],
        # NZS 2070: Green-H2 dominant (>85%) — calibrated to ~0.05 tCO2/t
        "shares_nzs_2070":[0.005, 0.02, 0.05, 0.88, 0.045],
        "vol4_co2_cps": {2050:1.8, 2070:1.2},
        "vol4_co2_nzs": {2050:0.7, 2070:0.05},
        "cost_base": 280,
    },
}

# ── Historical data ───────────────────────────────────────────────────────────
HISTORICAL: Dict[str, list] = {
    "cement":    [{"year":y,"production_mt":v} for y,v in [(1995,68),(2000,101),(2005,142),(2010,210),(2015,280),(2019,337),(2020,294),(2022,355),(2023,381),(2024,395)]],
    "aluminium": [{"year":y,"production_mt":v} for y,v in [(2000,.59),(2005,.89),(2010,1.55),(2015,2.4),(2019,3.6),(2020,3.4),(2022,4.0),(2023,4.2),(2024,4.5)]],
    "textile":   [{"year":y,"production_mt":v} for y,v in [(2000,6.2),(2005,7.8),(2010,10.5),(2015,14.2),(2019,16.1),(2020,13.8),(2022,17.5),(2023,18.2),(2024,19.0)]],
    "fertiliser":[{"year":y,"production_mt":v} for y,v in [(2000,18.5),(2005,20.1),(2010,21.9),(2015,24.7),(2019,26.3),(2020,25.8),(2022,28.0),(2023,29.5),(2024,30.5)]],
}

# ── Math helpers ──────────────────────────────────────────────────────────────

def piecewise(anchors: dict, year: int) -> float:
    years = sorted(anchors.keys())
    if year <= years[0]:  return float(anchors[years[0]])
    if year >= years[-1]: return float(anchors[years[-1]])
    for i in range(len(years) - 1):
        lo, hi = years[i], years[i + 1]
        if lo <= year <= hi:
            frac = (year - lo) / (hi - lo)
            return anchors[lo] + frac * (anchors[hi] - anchors[lo])
    return float(anchors[years[-1]])

def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

def interp_year(v_2024: float, v_2070: float, year: int) -> float:
    t = smoothstep((year - 2024) / 46.0)
    return v_2024 + t * (v_2070 - v_2024)

# ── Core model ────────────────────────────────────────────────────────────────

def compute_run(sector_id: str, scenario: str, overrides: dict) -> dict:
    cfg = SECTOR_CONFIGS[sector_id]
    routes = cfg["routes"]
    s = scenario.upper()
    lab = (s == "LAB")

    # ── Demand ──
    if lab and overrides.get("demand_anchors"):
        da = {int(k): float(v) for k, v in overrides["demand_anchors"].items()}
    else:
        da = cfg["demand_niti"]

    # ── Target shares at 2070 ──
    if lab:
        cp2070 = float((overrides.get("carbon_price") or {}).get("2070", 200))
        alpha = min(1.0, max(0.0, cp2070 / 300.0))
        h2_2050 = float((overrides.get("h2_cost") or {}).get("2050", 1.5))
        h2_factor = max(0.0, (3.0 - h2_2050) / 2.5)
        gp = float(overrides.get("green_premium", 0))
        shares_2070 = []
        for i, r in enumerate(routes):
            s_val = cfg["shares_cps_2070"][i] + alpha * (cfg["shares_nzs_2070"][i] - cfg["shares_cps_2070"][i])
            if any(k in r["id"] for k in ["H2","Green","CCUS","Inert","RE-","Circular","Bio"]):
                s_val *= (1 + h2_factor * 0.35 + gp / 300.0)
            shares_2070.append(s_val)
        use_nzs_co2 = (alpha > 0.5)
    elif s == "NZS":
        shares_2070 = list(cfg["shares_nzs_2070"])
        use_nzs_co2 = True
    else:  # CPS
        shares_2070 = list(cfg["shares_cps_2070"])
        use_nzs_co2 = False

    # Normalise
    tot = sum(shares_2070)
    shares_2070 = [x / tot for x in shares_2070]

    # ── Carbon price (for cost) ──
    if lab:
        cp_raw = overrides.get("carbon_price") or {}
        cp_anch = {int(k): float(v) for k, v in cp_raw.items()} if cp_raw else {2024:5,2030:10,2050:100,2070:200}
    elif s == "NZS":
        cp_anch = {2024:5, 2030:30, 2040:80, 2050:150, 2060:200, 2070:250}
    else:
        cp_anch = {2024:2, 2030:10, 2040:25, 2050:50, 2070:80}

    capex_mult = float(overrides.get("capex_multiplier", 1.0)) if lab else 1.0
    wacc       = float(overrides.get("wacc", 0.12)) if lab else 0.12

    yearly_results = {}
    for yr in range(2024, 2071):
        demand = piecewise(da, yr)
        cp     = piecewise(cp_anch, yr)

        # Shares — smoothstep transition
        shares = [interp_year(s0, s1, yr) for s0, s1 in zip(cfg["shares_2024"], shares_2070)]
        tot2 = sum(shares); shares = [x / tot2 for x in shares]

        prod_by = {}
        co2_by  = {}
        for i, r in enumerate(routes):
            prod = demand * shares[i]
            prod_by[r["id"]] = round(prod, 4)

            # Route CO2 intensity evolves over time
            if use_nzs_co2:
                co2_2070 = r["co2_nzs_2070"]
            else:
                co2_2070 = r["co2_cps_2070"]
            co2_int = interp_year(r["co2_2024"], co2_2070, yr)

            co2_by[r["id"]] = prod * co2_int

        total_co2 = sum(co2_by.values())
        co2_int_total = total_co2 / demand if demand > 0 else 0

        # Cost: base × learning + carbon abatement
        learning = max(0.65, 1.0 - 0.25 * smoothstep((yr - 2024) / 46.0))
        cost = demand * cfg["cost_base"] * learning * capex_mult + total_co2 * cp

        yearly_results[yr] = {
            "year":               yr,
            "total_production":   round(demand, 3),
            "production_by_route": prod_by,
            "capacity_by_route":   {k: round(v * 1.12, 4) for k, v in prod_by.items()},
            "investment_by_route": {k: round(v * 45 * capex_mult * (1 + wacc - 0.12), 2) for k, v in prod_by.items()},
            "co2_intensity":       round(co2_int_total, 4),
            "co2_total":           round(total_co2, 3),
            "total_cost":          round(cost, 1),
        }

    return {
        "status":   "ok",
        "scenario": scenario,
        "sector":   sector_id,
        "years":    list(range(2024, 2071)),
        "yearly_results": yearly_results,
        "summary": {
            "total_cost_bn":       round(sum(r["total_cost"] for r in yearly_results.values()) / 1e3, 1),
            "total_co2_mt":        round(sum(r["co2_total"] for r in yearly_results.values()), 1),
            "final_co2_intensity": round(yearly_results[2070]["co2_intensity"], 4),
            "final_year_demand":   round(yearly_results[2070]["total_production"], 1),
        },
    }


def build_demand_trajectories(sector_id: str) -> dict:
    cfg = SECTOR_CONFIGS[sector_id]
    def pw(anchors, from_yr=2024):
        return {yr: round(piecewise(anchors, yr), 3)
                for yr in range(from_yr, 2071)}

    return {
        "niti":          {"label":"NITI Vol.4",            "annual_series":pw(cfg["demand_niti"]),          "end_value":cfg["demand_niti"][2070],          "source":"NITI Aayog Vol.4 (2023)",    "method":"Official GoI projection"},
        "model_fitted":  {"label":"Historical trend",      "annual_series":pw(cfg["demand_model_fitted"]),  "end_value":cfg["demand_model_fitted"][2070],  "source":"CMA / DPIIT actuals",        "method":"Logistic S-curve fit"},
        "india_policy":  {"label":"India Policy Consensus","annual_series":pw(cfg["demand_india_policy"]),  "end_value":cfg["demand_india_policy"][2070],  "source":"MoU schemes + NIP",          "method":"Blended GoI policy targets"},
        "international": {"label":"International Baseline","annual_series":pw(cfg["demand_international"]),"end_value":cfg["demand_international"][2070], "source":"IEA + World Bank",           "method":"IEA STEPS + urbanization"},
        "historical":    HISTORICAL[sector_id],
    }


# ── FastAPI ───────────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    scenario: str = "CPS"
    carbon_price:      Optional[Dict[str, float]] = None
    h2_cost:           Optional[Dict[str, float]] = None
    capex_multiplier:  Optional[float] = None
    green_premium:     Optional[float] = None
    wacc:              Optional[float] = None
    grid_ei_2070:      Optional[float] = None
    demand_anchors:    Optional[Dict[str, float]] = None


def make_app(sector_id: str) -> FastAPI:
    cfg = SECTOR_CONFIGS[sector_id]
    app = FastAPI(title=f"{cfg['label']} Transition API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    def health():
        return {"status":"ok","sector":sector_id,"port":cfg["port"]}

    @app.get("/api/scenarios")
    def scenarios():
        return {"scenarios":["CPS","NZS"]}

    @app.get("/api/demand-trajectories")
    def demand_traj():
        return build_demand_trajectories(sector_id)

    def _overrides(req: RunRequest) -> dict:
        d = {}
        if req.carbon_price:      d["carbon_price"]      = req.carbon_price
        if req.h2_cost:           d["h2_cost"]           = req.h2_cost
        if req.capex_multiplier:  d["capex_multiplier"]  = req.capex_multiplier
        if req.green_premium is not None: d["green_premium"] = req.green_premium
        if req.wacc is not None:  d["wacc"]              = req.wacc
        if req.grid_ei_2070 is not None: d["grid_ei_2070"] = req.grid_ei_2070
        if req.demand_anchors:    d["demand_anchors"]    = req.demand_anchors
        return d

    @app.post("/api/run")
    def run_scenario(req: RunRequest):
        return compute_run(sector_id, req.scenario, _overrides(req))

    @app.post("/api/lab/run")
    def lab_run(req: RunRequest):
        return compute_run(sector_id, "LAB", _overrides(req))

    return app


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sector_backend.py <cement|aluminium|textile|fertiliser>")
        sys.exit(1)
    sector = sys.argv[1].lower()
    if sector not in SECTOR_CONFIGS:
        print(f"Unknown: {sector}")
        sys.exit(1)
    port = SECTOR_CONFIGS[sector]["port"]
    print(f"▶ {sector.capitalize()} backend → http://localhost:{port}")
    uvicorn.run(make_app(sector), host="0.0.0.0", port=port)
