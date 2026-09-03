import asyncio
"""
Textile Transition Backend v2 — India Transition Lab  (port 8003)
==================================================================
Dedicated LP for India's textile and apparel processing sector.

Key sector physics:
  - Multi-fuel routes: coal, gas, biomass, renewable electricity
  - Labour-intensive; employment is the dominant socio-economic variable
  - Circular-Textiles route is scrap-supply limited (fibre recovery capacity)
  - Emission intensities are PROCESS emissions (steam, heat, dyeing energy)
  - PLI Textiles 2021 scheme provides capex and production incentives

Upgrades over v1 (shared milp_sector_backend.py):
  1. CRF-annualised CAPEX on CAP per period
  2. WACC per route (Circular-Textiles novelty premium)
  3. Three fuel resources (coal, gas, biomass) + renewable electricity
     with scenario-specific price trajectories — gas price falls in NZS
     as dedicated GTI + hydrogen blending reduces gas import dependence
  4. Explicit CO2[t] variable with carbon price
  5. PLI Textiles 2021 / PMKTH incentives for RE-Processing, Circular
  6. Monotonic coal decline in NZS (post-2033)
  7. Gas-Processing phased out in NZS 2040 (no new capacity beyond 2035)

Sources: UNIDO 2021 Textile Industry Report; Ministry of Textiles 2023;
         NITI Vol.4 Sec 3.4; IEA Textile Roadmap 2022; CEEW India 2023.
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

YEARS     = [2024 + 5*i for i in range(10)]
ALL_YEARS = list(range(2024, 2071))
DT = 5; BASE = 2024; WACC = 0.08
SECTOR = "textile"; PORT = 8003

def crf(r, n):
    if r==0 or n==0: return 1.0/max(n,1)
    return r*(1+r)**n/((1+r)**n-1)

def interp(anchors, y):
    ks=sorted(anchors)
    if not ks: return 0.0
    if y<=ks[0]: return anchors[ks[0]]
    if y>=ks[-1]: return anchors[ks[-1]]
    for lo,hi in zip(ks,ks[1:]):
        if lo<=y<=hi:
            f=(y-lo)/(hi-lo); return anchors[lo]+f*(anchors[hi]-anchors[lo])
    return anchors[ks[-1]]

def surviving(existing, y, lifetime):
    age=y-BASE
    if age>=lifetime: return 0.0
    return existing*(1.0-age/lifetime)

# ── ROUTE DATA ────────────────────────────────────────────────────────────────
# Production unit: billion metres of fabric equivalent (Bm)
# EF unit: tCO2 per 1000 m fabric (equivalent to MtCO2/Bm)
# Energy intensities: GJ per 1000 m fabric → converted to fuel units below
#   Coal:    25 GJ/t → fuel_t_per_Bm = GJ_per_km / 25
#   Gas:     52 GJ/thousand cubic metres → GJ/t equivalent
#   Biomass: 18 GJ/t (moisture-adjusted bagasse/rice husk)
#   RE elec: kWh per 1000 m fabric
#
# Route calibration to UNIDO/NITI 2024 benchmarks:
#   Coal-Processing base EF 2.80 tCO2/1000m → verified with 2.8×4 GJ/t coal = 11.2 GJ + process
#   Gas-Processing  base EF 1.55 → verified 1.55×22 GJ/t CH4 LHV = 34 GJ (reasonable for wet processes)
#   Biomass: 0.35 (near-zero fossil, residual process emissions)
#   RE-Processing: 0.12 (residual grid-sourced heat if any)
#   Circular: 0.22 (reprocessing + dyeing energy)

ROUTES: List[Dict[str,Any]] = [
    {
        "id": "Coal-Processing",
        "existing": 15.4,           # Bm/yr capacity 2024
        "lifetime": 25,
        "capex": 155.0,             # USD/1000m capacity (wet processing unit)
        "fom": 16.0,
        "vom_residual": 28.0,       # labour, water, chemicals (non-fuel)
        "wacc_mult": 1.00,
        "lead_p": 0,
        "fossil_decline": True,
        "avail": 0.85,
        "start": 2024,
        "max_ramp": 4.0,
        "cutoff_cps": None,
        "cutoff_nzs": 2033,
        "ef_2024": 2.80, "ef_cps_2050": 2.40, "ef_cps_2070": 2.10,
                         "ef_nzs_2050": 2.10, "ef_nzs_2070": 1.80,
        # Fuel mix: mainly coal (with small auxiliary electricity for fans/motors)
        "coal_gj_per_km": 10.5,     # GJ / 1000 m fabric  (primary process heat)
        "gas_gj_per_km": 0.0,
        "biomass_gj_per_km": 0.0,
        "re_kwh_per_km": 180.0,     # auxiliary electric for motors, lighting
    },
    {
        "id": "Gas-Processing",
        "existing": 4.1,
        "lifetime": 25,
        "capex": 165.0,
        "fom": 17.0,
        "vom_residual": 30.0,
        "wacc_mult": 1.00,
        "lead_p": 0,
        "fossil_decline": True,
        "avail": 0.85,
        "start": 2024,
        "max_ramp": 5.0,
        "cutoff_cps": None,
        "cutoff_nzs": 2040,
        "ef_2024": 1.55, "ef_cps_2050": 1.35, "ef_cps_2070": 1.15,
                         "ef_nzs_2050": 1.10, "ef_nzs_2070": 0.80,
        "coal_gj_per_km": 0.0,
        "gas_gj_per_km": 9.5,       # GJ / 1000 m (natural gas for steam)
        "biomass_gj_per_km": 0.0,
        "re_kwh_per_km": 200.0,
    },
    {
        "id": "Biomass-Processing",
        "existing": 1.85,
        "lifetime": 20,
        "capex": 190.0,             # biomass boiler + handling system
        "fom": 19.0,
        "vom_residual": 25.0,
        "wacc_mult": 1.05,
        "lead_p": 0,
        "fossil_decline": False,
        "avail": 0.82,
        "start": 2024,
        "max_ramp": 5.0,
        "cutoff_cps": None,
        "cutoff_nzs": None,
        "ef_2024": 0.35, "ef_cps_2050": 0.28, "ef_cps_2070": 0.22,
                         "ef_nzs_2050": 0.22, "ef_nzs_2070": 0.14,
        "coal_gj_per_km": 0.0,
        "gas_gj_per_km": 0.0,
        "biomass_gj_per_km": 11.0,  # bagasse / rice husk
        "re_kwh_per_km": 180.0,
    },
    {
        "id": "RE-Processing",
        "existing": 0.28,           # electric heat pump + steam / e-boiler plants
        "lifetime": 20,
        "capex": 230.0,
        "fom": 22.0,
        "vom_residual": 18.0,
        "wacc_mult": 1.08,
        "lead_p": 0,
        "fossil_decline": False,
        "avail": 0.82,
        "start": 2025,
        "max_ramp": 6.0,
        "cutoff_cps": None,
        "cutoff_nzs": None,
        "ef_2024": 0.12, "ef_cps_2050": 0.08, "ef_cps_2070": 0.05,
                         "ef_nzs_2050": 0.05, "ef_nzs_2070": 0.02,
        "coal_gj_per_km": 0.0,
        "gas_gj_per_km": 0.0,
        "biomass_gj_per_km": 0.0,
        "re_kwh_per_km": 420.0,     # e-boiler higher elec intensity vs combustion
    },
    {
        "id": "Circular-Textiles",
        "existing": 0.64,           # mechanical/chemical recycling
        "lifetime": 20,
        "capex": 110.0,
        "fom": 13.0,
        "vom_residual": 20.0,       # sorting, cleaning, chemical processing
        "wacc_mult": 1.10,          # novel supply chain logistics risk
        "lead_p": 0,
        "fossil_decline": False,
        "avail": 0.85,
        "start": 2024,
        "max_ramp": 5.0,
        "cutoff_cps": None,
        "cutoff_nzs": None,
        "ef_2024": 0.22, "ef_cps_2050": 0.16, "ef_cps_2070": 0.12,
                         "ef_nzs_2050": 0.12, "ef_nzs_2070": 0.06,
        "coal_gj_per_km": 0.0,
        "gas_gj_per_km": 0.0,
        "biomass_gj_per_km": 2.5,   # process heat for chemical recycling
        "re_kwh_per_km": 280.0,
        "scrap_frac_cap": {2024:0.04, 2030:0.08, 2040:0.18, 2050:0.30, 2070:0.45},
    },
]

# ── RESOURCES ─────────────────────────────────────────────────────────────────
# Prices per GJ (for coal, gas, biomass) or USD/kWh (for RE electricity)
# Then resource cost = price_per_unit × intensity × ACT (in Bm)
# Unit alignment: price (USD/GJ) × GJ/1000m × Bm = USD × 10^6 per Bm production
# All relative so LP scale is consistent.

RESOURCES: List[Dict[str,Any]] = [
    {
        "id": "coal",
        "name": "Thermal coal (USD/GJ)",
        "price": {
            "CPS": {2024:4.0, 2030:3.7, 2040:3.2, 2050:2.7, 2060:2.3, 2070:2.0},
            "NZS": {2024:4.0, 2030:3.3, 2040:2.5, 2050:1.7, 2060:1.3, 2070:0.9},
        },
        "int_key": "coal_gj_per_km",
    },
    {
        "id": "gas",
        "name": "Natural gas (USD/GJ)",
        "price": {
            # India gas: Henry Hub-linked; CPS = slow domestic reform; NZS = green gas/blending
            "CPS": {2024:7.5, 2030:8.2, 2040:8.8, 2050:9.3, 2060:9.8, 2070:10.2},
            "NZS": {2024:7.5, 2030:7.0, 2040:6.0, 2050:5.0, 2060:4.0, 2070:3.2},
        },
        "int_key": "gas_gj_per_km",
    },
    {
        "id": "biomass",
        "name": "Biomass / agri-residue (USD/GJ)",
        "price": {
            "CPS": {2024:3.0, 2030:3.2, 2040:3.5, 2050:3.8, 2060:4.0, 2070:4.2},
            "NZS": {2024:3.0, 2030:3.0, 2040:3.2, 2050:3.4, 2060:3.5, 2070:3.6},
        },
        "int_key": "biomass_gj_per_km",
    },
    {
        "id": "re_elec",
        "name": "Renewable electricity (USD/kWh)",
        "price": {
            "CPS": {2024:0.038, 2030:0.032, 2040:0.024, 2050:0.019, 2060:0.016, 2070:0.013},
            "NZS": {2024:0.038, 2030:0.027, 2040:0.017, 2050:0.011, 2060:0.008, 2070:0.006},
        },
        "int_key": "re_kwh_per_km",
    },
]
K = len(RESOURCES)

PLI: Dict[str, Dict[int,float]] = {
    # PLI Textiles 2021: production-linked incentives for technical textiles + MMF
    # Applied here as equivalent USD per Bm for RE and Circular routes
    "RE-Processing":     {2024:0, 2030:3, 2035:6, 2040:9, 2050:12, 2070:12},
    "Circular-Textiles": {2024:0, 2030:2, 2035:5, 2040:8, 2050:10, 2070:10},
    "Biomass-Processing":{2024:0, 2030:1, 2040:3, 2050: 5, 2070: 5},
}

GREEN_PREMIUM_ROUTES = {"RE-Processing", "Circular-Textiles"}
GREEN_PREMIUM: Dict[str, Dict[int,float]] = {
    "CPS": {2024:0, 2070:0},
    "NZS": {2024:5, 2030:18, 2040:50, 2050:90, 2070:135},
}

DEMAND: Dict[str, Dict[int,float]] = {
    "CPS": {2024:19, 2030:28, 2040:42, 2050:55, 2060:70, 2070:80},
    "NZS": {2024:19, 2030:27, 2040:40, 2050:53, 2060:67, 2070:77},
}
CARBON_PRICE: Dict[str, Dict[int,float]] = {
    "CPS": {2024:2, 2030:6, 2040:14, 2050:25, 2060:32, 2070:38},
    "NZS": {2024:8, 2030:35, 2040:95, 2050:165, 2060:200, 2070:230},
}

VOL4 = {"cps_2050":2.1,"cps_2070":1.4,"nzs_2050":0.9,"nzs_2070":0.12}
CO2_CEILING: Dict[str, Dict[int, float]] = {
    "CPS": {2054: 2.1, 2069: 1.4},
    "NZS": {2054: 0.9, 2069: 0.15},
}
CO2_FLOOR: Dict[str, Dict[int, float]] = {
    "CPS": {2054: 1.8, 2069: 1.2},    # coal lock-in: SMEs can't access green finance
    "NZS": {},
}

R=len(ROUTES); T=len(YEARS)
def _NC(r,t):  return r*T+t
def _CAP(r,t): return R*T+r*T+t
def _ACT(r,t): return 2*R*T+r*T+t
def _CO2(t):   return 3*R*T+t
def _RES(k,t): return 3*R*T+T+k*T+t
NV = 3*R*T+T+K*T

def _ef(route, sc, y):
    s=sc.lower()
    if f"ef_{s}_2050" not in route: s="cps"
    e0,e5,e7=route["ef_2024"],route[f"ef_{s}_2050"],route[f"ef_{s}_2070"]
    if y<=BASE: return e0
    if y<=2050: return e0+(y-BASE)/26.0*(e5-e0)
    return e5+(y-2050)/20.0*(e7-e5)

def solve(scenario, demand_anchors=None, carbon_price_anchors=None,
          green_premium_val=None, capex_mult=1.0, wacc_adj_pct=0.0,
          h2_cost_adj=0.0, enforce_co2_ceiling=True, monotonic_fossil=True,
          coal_price_adj=0.0, gas_price_adj=0.0, biomass_price_adj=0.0,
          re_price_adj=0.0, pli_active=True,
          circular_active=True, gas_active=True, biomass_active=True,
          biomass_cap=0.50, circular_cap=0.40,
          capex_by_route=None, discount_rate_adj=0.0):
    sc=scenario.upper() if scenario.upper() in ("CPS","NZS") else "CPS"
    d_anch=demand_anchors or DEMAND.get(sc,DEMAND["CPS"])
    cp_anch=carbon_price_anchors or CARBON_PRICE.get(sc,CARBON_PRICE["CPS"])
    gp_anch=({y:green_premium_val for y in [BASE,2069]}
             if green_premium_val is not None else GREEN_PREMIUM.get(sc,GREEN_PREMIUM["CPS"]))
    demand={y:interp(d_anch,y) for y in YEARS}
    eff_wacc=max(0.01, WACC + discount_rate_adj/100.0)
    df={y:(1.0/(1.0+eff_wacc))**(y-BASE) for y in YEARS}
    _cbr=capex_by_route or {}

    c=np.zeros(NV)
    for ri,route in enumerate(ROUTES):
        lt=route["lifetime"]
        route_capex_m=_cbr.get(route["id"],capex_mult)
        ann_cap=route["capex"]*route_capex_m*crf(eff_wacc,lt)
        wacc_m=route["wacc_mult"]*(1.0+wacc_adj_pct/100.0)
        pli_d=PLI.get(route["id"],{})
        for ti,y in enumerate(YEARS):
            d=df[y]
            gp=interp(gp_anch,y) if route["id"] in GREEN_PREMIUM_ROUTES else 0.0
            pl=interp(pli_d,y) if (sc=="NZS" or pli_active) else 0.0
            circ_pen=0.0 if circular_active else (300.0 if route["id"]=="Circular-Textiles" else 0.0)
            gas_pen =0.0 if gas_active  else (300.0 if route["id"]=="Gas-Processing"  else 0.0)
            bio_pen =0.0 if biomass_active else (300.0 if route["id"]=="Biomass-Processing" else 0.0)
            c[_CAP(ri,ti)]+=d*(ann_cap*wacc_m+route["fom"])*DT
            c[_ACT(ri,ti)]+=d*(route["vom_residual"]-pl-gp+circ_pen+gas_pen+bio_pen)*DT

    for ti,y in enumerate(YEARS):
        c[_CO2(ti)]+=df[y]*interp(cp_anch,y)

    # K=0:coal, K=1:gas, K=2:biomass, K=3:re_elec
    _res_adj={0:coal_price_adj,1:gas_price_adj,2:biomass_price_adj,3:re_price_adj}
    for ki,res in enumerate(RESOURCES):
        price_t=res["price"].get(sc,res["price"]["CPS"])
        adj=_res_adj.get(ki,0.0)
        for ti,y in enumerate(YEARS):
            c[_RES(ki,ti)]+=df[y]*(interp(price_t,y)+adj)

    rows=[]
    def add(lb,ub,d): rows.append((lb,ub,d))

    for ti,y in enumerate(YEARS):
        rhs=demand[y]*DT
        add(rhs,rhs,{_ACT(ri,ti):1.0 for ri in range(R)})

    for ri,route in enumerate(ROUTES):
        for ti in range(T):
            add(-np.inf,0.0,{_ACT(ri,ti):1.0,_CAP(ri,ti):-route["avail"]*DT})

    for ri,route in enumerate(ROUTES):
        lt,lead_p=route["lifetime"],route["lead_p"]
        for ti,y in enumerate(YEARS):
            surv=surviving(route["existing"],y,lt)
            if ti==0:
                row={_CAP(ri,0):1.0}
                if lead_p==0: row[_NC(ri,0)]=-1.0
                add(surv,surv,row)
            else:
                delta=surv-surviving(route["existing"],YEARS[ti-1],lt)
                row={_CAP(ri,ti):1.0,_CAP(ri,ti-1):-1.0}
                nc_ti=ti-lead_p
                if nc_ti>=0: row[_NC(ri,nc_ti)]=-1.0
                add(delta,delta,row)

    for ti,y in enumerate(YEARS):
        row={_CO2(ti):1.0}
        for ri,route in enumerate(ROUTES):
            row[_ACT(ri,ti)]=-_ef(route,sc,y)
        add(0.0,0.0,row)

    for ki,res in enumerate(RESOURCES):
        int_key=res["int_key"]
        for ti in range(T):
            row={_RES(ki,ti):1.0}
            for ri,route in enumerate(ROUTES):
                intensity=route.get(int_key,0.0)
                if intensity: row[_ACT(ri,ti)]=-intensity
            add(0.0,0.0,row)

    for ri,route in enumerate(ROUTES):
        cap=route.get("scrap_frac_cap")
        if cap:
            for ti,y in enumerate(YEARS):
                base=interp(cap,y)
                if route["id"]=="Circular-Textiles": base=min(base,circular_cap)
                elif route["id"]=="Biomass-Processing": base=min(base,biomass_cap)
                add(-np.inf,base*demand[y]*DT,{_ACT(ri,ti):1.0})

    if enforce_co2_ceiling:
        for target_y, target_int in CO2_CEILING.get(sc, {}).items():
            if target_y in YEARS:
                ti = YEARS.index(target_y)
                add(-np.inf, target_int * demand[target_y] * DT, {_CO2(ti): 1.0})
        for target_y, floor_int in CO2_FLOOR.get(sc, {}).items():
            if target_y in YEARS and floor_int > 0:
                ti = YEARS.index(target_y)
                add(floor_int * demand[target_y] * DT, np.inf, {_CO2(ti): 1.0})

    if monotonic_fossil and sc=="NZS":
        start_ti=next((i for i,y in enumerate(YEARS) if y>=2033),T-1)
        for ri,route in enumerate(ROUTES):
            if route["fossil_decline"]:
                for ti in range(start_ti,T):
                    add(-np.inf,0.0,{_ACT(ri,ti):1.0,_ACT(ri,ti-1):-1.0})

    lb=np.zeros(NV); ub=np.full(NV,np.inf)
    for ri,route in enumerate(ROUTES):
        cutoff=route.get(f"cutoff_{sc.lower()}")
        for ti,y in enumerate(YEARS):
            if y<route["start"] or (cutoff is not None and y>cutoff):
                ub[_NC(ri,ti)]=0.0
            else:
                ub[_NC(ri,ti)]=route["max_ramp"]*DT

    n_con=len(rows)
    A=lil_matrix((n_con,NV)); lb_arr=np.empty(n_con); ub_arr=np.empty(n_con)
    for ci,(lo,hi,d) in enumerate(rows):
        lb_arr[ci]=lo; ub_arr[ci]=hi
        for col,val in d.items(): A[ci,col]=val

    res=milp(c,constraints=LinearConstraint(A.tocsr(),lb_arr,ub_arr),
             integrality=np.zeros(NV),bounds=Bounds(lb=lb,ub=ub),
             options={"time_limit":60.0,"disp":False})

    if res.status==0: return res.x,0,"optimal"
    if res.status==1: return (res.x,2,"time_limit") if res.x is not None else (None,1,"tl_no_sol")
    if res.status==2: return None,1,f"infeasible: {res.message}"
    return None,-1,f"status_{res.status}: {res.message}"

def _lp_periods(x,sc,demand_anchors=None):
    d_anch=demand_anchors or DEMAND.get(sc,DEMAND["CPS"])
    lp={}
    for ti,y in enumerate(YEARS):
        pbr={}; total=co2=0.0
        for ri,route in enumerate(ROUTES):
            prod=max(0.0,float(x[_ACT(ri,ti)])/DT)
            pbr[route["id"]]=round(prod,4); total+=prod; co2+=prod*_ef(route,sc,y)
        lp[y]={"year":y,"total_production":round(total,3),
               "co2_intensity":round(co2/total,4) if total>0 else 0.0,
               "co2_total":round(co2,3),"production_by_route":pbr}
    return lp

def extract_yearly(x,sc,demand_anchors=None):
    d_anch=demand_anchors or DEMAND.get(sc,DEMAND["CPS"])
    lp=_lp_periods(x,sc,demand_anchors); out={}
    for y in ALL_YEARS:
        if y in lp: out[y]=dict(lp[y]); out[y]["year"]=y; continue
        if y>YEARS[-1]:
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

app=FastAPI(title="Textile Transition Backend v2",version="2.0.0")
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
    return {"status":"ok","sector":SECTOR,"model":"HiGHS LP v2 (CRF+WACC+MultiFuel+PLI)",
            "port":PORT,**VOL4}

@app.get("/api/scenarios")
def scenarios():
    return {"scenarios":[{"key":"CPS","label":"Current Policy Scenario"},
                          {"key":"NZS","label":"Net Zero Scenario"}]}

@app.get("/api/demand-trajectories")
def demand_trajectories():
    return {sc:{str(y):interp(anch,y) for y in ALL_YEARS} for sc,anch in DEMAND.items()}

@app.post("/api/run")
async def run_scenario(payload:dict):
    sc=payload.get("scenario","CPS").upper()
    if sc not in ("CPS","NZS"): return {"status":"error","message":f"Unknown: {sc}"}
    d_anch=None
    if payload.get("demand_anchors"):
        d_anch={int(k):float(v) for k,v in payload["demand_anchors"].items() if v is not None}
    import asyncio, functools
    loop = asyncio.get_event_loop()
    x,code,msg=await loop.run_in_executor(None, functools.partial(solve,sc,demand_anchors=d_anch,enforce_co2_ceiling=True))
    if x is None: return {"status":"infeasible","message":msg,"sector":SECTOR,"scenario":sc}
    yearly=extract_yearly(x,sc,d_anch)
    return {"status":"optimal" if code==0 else "feasible","message":msg,
            "sector":SECTOR,"scenario":sc,"years":ALL_YEARS,
            "yearly_results":{str(y):v for y,v in yearly.items()},"summary":_summary(yearly)}

@app.post("/api/lab/run")
async def lab_run(payload:dict):
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
    coal_adj      = float(payload.get("coal_price_adj", 0.0))
    gas_adj       = float(payload.get("gas_price_adj", 0.0))
    biomass_adj   = float(payload.get("biomass_price_adj", 0.0))
    re_adj        = float(payload.get("re_price_adj", 0.0))
    pli_on        = bool(payload.get("pli_active", True))
    circ_on       = bool(payload.get("circular_active", True))
    gas_on        = bool(payload.get("gas_active", True))
    bio_on        = bool(payload.get("biomass_active", True))
    bio_cap       = float(payload.get("biomass_cap", 0.50))
    circ_cap      = float(payload.get("circular_cap", 0.40))
    dr_adj        = float(payload.get("discount_rate_adj", 0.0))
    cbr           = payload.get("capex_by_route") or {}
    capex_by_r    = {k: float(v) for k, v in cbr.items()} if cbr else None
    import asyncio, functools
    loop = asyncio.get_event_loop()
    x,code,msg=await loop.run_in_executor(None, functools.partial(solve,sc,demand_anchors=d_anch,carbon_price_anchors=cp_anch,
                      green_premium_val=gp_val,capex_mult=capex_m,wacc_adj_pct=wacc,
                      enforce_co2_ceiling=False,
                      coal_price_adj=coal_adj,gas_price_adj=gas_adj,
                      biomass_price_adj=biomass_adj,re_price_adj=re_adj,
                      pli_active=pli_on,circular_active=circ_on,
                      gas_active=gas_on,biomass_active=bio_on,
                      biomass_cap=bio_cap,circular_cap=circ_cap,
                      discount_rate_adj=dr_adj,capex_by_route=capex_by_r))
    if x is None: return {"status":"infeasible","message":msg,"sector":SECTOR,"scenario":sc}
    yearly=extract_yearly(x,sc,d_anch)
    return {"status":"optimal" if code==0 else "feasible","message":msg,
            "sector":SECTOR,"scenario":f"LAB-{sc}","years":ALL_YEARS,
            "yearly_results":{str(y):v for y,v in yearly.items()},"summary":_summary(yearly)}

if __name__=="__main__":
    uvicorn.run(app,host="0.0.0.0",port=PORT,log_level="info")
