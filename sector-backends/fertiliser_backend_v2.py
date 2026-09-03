"""
Fertiliser Transition Backend v2 — India Transition Lab  (port 8004)
=====================================================================
Dedicated LP for India's nitrogenous fertiliser (urea) sector.

Key sector physics:
  - Natural gas is the dominant feedstock and energy cost (25–28 MMBTU/t urea)
  - Green-H2-Urea replaces SMR with electrolytic H2 (H2 price falls with RE LCOE)
  - NG-SMR-CCUS captures 90% of CO2 from reforming; residual scope-1 remains
  - Coal-Gasification routes face earliest cutoffs (high EF + stranded asset risk)
  - EF for fertiliser is NET of CO2 sequestered in urea during synthesis
    (~0.73 tCO2/t urea absorbed → reduces apparent EF by ~0.51 tCO2/t)
  - Government subsidy reform: NZS assumes removal of urea price control
    post-2030, enabling real carbon pricing to flow through

Upgrades over v1 (shared milp_sector_backend.py):
  1. CRF-annualised CAPEX on CAP per period
  2. WACC per route (Green-H2-Urea 22% premium; CCUS 18%)
  3. Three fuel resources: natural gas, coal, green hydrogen
     Gas price trajectory branches significantly between CPS/NZS
     H2 price trajectory follows National Green Hydrogen Mission targets
  4. Explicit CO2[t] variable with carbon price
  5. PLI: National Green Hydrogen Mission subsidies (USD/kg H2 equivalent/t urea)
  6. Monotonic coal decline in NZS from 2025; gas decline from 2035
  7. Lead time: Green-H2-Urea 2 periods (electrolyser scale-up + plant integration)

Sources: IEA Ammonia Technology Roadmap 2021; CEEW India ammonia 2024;
         FAI Fertiliser Statistics 2023; NITI Vol.4 Sec 3.2.8;
         National Green Hydrogen Mission targets 2023.
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
SECTOR = "fertiliser"; PORT = 8004

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
# Production unit: Mt urea/yr
# EF: tCO2/t urea NET of urea CO2 sequestration (~0.51 tCO2/t)
#
# Natural gas intensity (MMBTU/t urea):
#   NG-SMR baseline: 26 MMBTU/t (global benchmark ~24-28)
#   NG-SMR-CCUS: 28 MMBTU/t (CCS parasitic load)
#
# Coal intensity (t coal / t urea):
#   Coal-Gasification: coal-to-ammonia via Koppers-Totzek = 1.35 t coal/t urea
#
# H2 intensity (kg H2 / t urea):
#   Green-H2-Urea: NH3 synthesis requires 177 kg H2 / t NH3; urea = 0.567 t NH3/t urea
#   → H2 per t urea = 177 × 0.567 = 100.3 kg H2/t urea ≈ 100 kg H2/t urea
#
# Bio-Ammonia uses biomass gasification; priced through biomass resource

ROUTES: List[Dict[str,Any]] = [
    {
        "id": "Coal-Gasification",
        "existing": 2.42,
        "lifetime": 25,
        "capex": 360.0,
        "fom": 32.0,
        "vom_residual": 10.0,       # non-feedstock O&M (catalyst, maintenance)
        "wacc_mult": 1.00,
        "lead_p": 0,
        "fossil_decline": True,
        "avail": 0.88,
        "start": 2024,
        "max_ramp": 0.5,
        "cutoff_cps": 2029,
        "cutoff_nzs": 2025,
        "ef_2024": 1.20, "ef_cps_2050": 1.00, "ef_cps_2070": 0.88,
                         "ef_nzs_2050": 0.88, "ef_nzs_2070": 0.75,
        "gas_mmbtu_per_t": 0.0,
        "coal_t_per_t": 1.35,
        "h2_kg_per_t": 0.0,
        "biomass_gj_per_t": 0.0,
    },
    {
        "id": "NG-SMR",
        "existing": 25.3,           # dominant route — all major plants
        "lifetime": 25,
        "capex": 270.0,
        "fom": 26.0,
        "vom_residual": 8.0,
        "wacc_mult": 1.00,
        "lead_p": 0,
        "fossil_decline": True,     # gas SMR is fossil; decline in NZS
        "avail": 0.88,
        "start": 2024,
        "max_ramp": 3.0,
        "cutoff_cps": None,
        "cutoff_nzs": 2040,
        "ef_2024": 0.55, "ef_cps_2050": 0.46, "ef_cps_2070": 0.40,
                         "ef_nzs_2050": 0.40, "ef_nzs_2070": 0.30,
        "gas_mmbtu_per_t": 26.0,    # MMBTU / t urea
        "coal_t_per_t": 0.0,
        "h2_kg_per_t": 0.0,
        "biomass_gj_per_t": 0.0,
    },
    {
        "id": "NG-SMR-CCUS",
        "existing": 5.02,
        "lifetime": 25,
        "capex": 320.0,
        "fom": 29.0,
        "vom_residual": 18.0,       # CO2 compression, pipeline, injection
        "wacc_mult": 1.18,          # CCUS project finance risk (India first-of-kind)
        "lead_p": 0,
        "fossil_decline": False,    # CCUS route can expand in both scenarios
        "avail": 0.85,
        "start": 2024,
        "max_ramp": 3.0,
        "cutoff_cps": None,
        "cutoff_nzs": None,
        "ef_2024": 0.35, "ef_cps_2050": 0.28, "ef_cps_2070": 0.22,
                         "ef_nzs_2050": 0.22, "ef_nzs_2070": 0.15,
        "gas_mmbtu_per_t": 28.0,    # higher due to CCS parasitic load
        "coal_t_per_t": 0.0,
        "h2_kg_per_t": 0.0,
        "biomass_gj_per_t": 0.0,
    },
    {
        "id": "Green-H2-Urea",
        "existing": 0.0,
        "lifetime": 20,
        "capex": 800.0,             # USD/t urea (green NH3 plant + electrolyser)
        "fom": 62.0,
        "vom_residual": 12.0,       # balance of plant, water treatment
        "wacc_mult": 1.22,          # pre-commercial technology; high project risk
        "lead_p": 1,                # 5yr: electrolyser order + commissioning
        "fossil_decline": False,
        "avail": 0.82,
        "start": 2030,
        "max_ramp": 4.0,
        "cutoff_cps": None,
        "cutoff_nzs": None,
        "ef_2024": -0.35, "ef_cps_2050": -0.35, "ef_cps_2070": -0.35,
                          "ef_nzs_2050": -0.35,  "ef_nzs_2070": -0.35,
        # Negative EF: net CO2 negative because 100% renewable H2 and urea sequesters CO2
        "gas_mmbtu_per_t": 0.0,
        "coal_t_per_t": 0.0,
        "h2_kg_per_t": 100.0,       # kg green H2 / t urea
        "biomass_gj_per_t": 0.0,
        "scrap_frac_cap": {2024:0.00, 2030:0.02, 2040:0.18, 2050:0.48, 2060:0.72, 2070:0.90},
    },
    {
        "id": "Bio-Ammonia",
        "existing": 2.29,
        "lifetime": 20,
        "capex": 650.0,
        "fom": 50.0,
        "vom_residual": 15.0,
        "wacc_mult": 1.12,
        "lead_p": 0,
        "fossil_decline": False,
        "avail": 0.80,
        "start": 2024,
        "max_ramp": 2.0,
        "cutoff_cps": None,
        "cutoff_nzs": None,
        "ef_2024": 0.20, "ef_cps_2050": 0.16, "ef_cps_2070": 0.12,
                         "ef_nzs_2050": 0.12, "ef_nzs_2070": 0.08,
        "gas_mmbtu_per_t": 0.0,
        "coal_t_per_t": 0.0,
        "h2_kg_per_t": 0.0,
        "biomass_gj_per_t": 28.0,   # GJ / t urea (gasification of biomass feedstock)
        "scrap_frac_cap": {2024:0.08, 2030:0.12, 2040:0.22, 2050:0.35, 2070:0.50},
    },
]

# ── RESOURCES ─────────────────────────────────────────────────────────────────
# K=0: natural gas (USD/MMBTU) — dominant cost for NG-SMR routes
# K=1: coal (USD/t) — Coal-Gasification only
# K=2: green hydrogen (USD/kg) — Green-H2-Urea only
# K=3: biomass (USD/GJ) — Bio-Ammonia
RESOURCES: List[Dict[str,Any]] = [
    {
        "id": "nat_gas",
        "name": "Natural gas (USD/MMBTU)",
        "price": {
            # India LNG/domestic blend: JKM-linked + domestic administered pricing
            # CPS: slow reform, import dependence remains → price rises
            # NZS: domestic production + green methane blending → price falls
            "CPS": {2024:8.5, 2030:9.5, 2040:10.5, 2050:11.5, 2060:12.0, 2070:12.5},
            "NZS": {2024:8.5, 2030:8.0, 2040:7.0,  2050:5.8,  2060:4.5,  2070:3.5},
        },
        "int_key": "gas_mmbtu_per_t",
    },
    {
        "id": "coal",
        "name": "Coal (USD/t)",
        "price": {
            "CPS": {2024:100, 2030:90, 2040:78, 2050:65, 2060:55, 2070:46},
            "NZS": {2024:100, 2030:80, 2040:56, 2050:36, 2060:26, 2070:16},
        },
        "int_key": "coal_t_per_t",
    },
    {
        "id": "green_h2",
        "name": "Green hydrogen (USD/kg)",
        "price": {
            # National Green Hydrogen Mission: target <1 USD/kg by 2030; falls with RE + scale
            # CPS: slow scale-up; stays high
            # NZS: meets mission targets; reaches 0.8 USD/kg by 2050
            "CPS": {2024:6.0, 2030:4.5, 2040:3.2, 2050:2.5, 2060:2.0, 2070:1.8},
            "NZS": {2024:6.0, 2030:2.8, 2040:1.6, 2050:0.9, 2060:0.7, 2070:0.6},
        },
        "int_key": "h2_kg_per_t",
    },
    {
        "id": "biomass",
        "name": "Biomass feedstock (USD/GJ)",
        "price": {
            "CPS": {2024:3.5, 2030:3.7, 2040:4.0, 2050:4.3, 2060:4.6, 2070:4.8},
            "NZS": {2024:3.5, 2030:3.6, 2040:3.8, 2050:4.0, 2060:4.1, 2070:4.2},
        },
        "int_key": "biomass_gj_per_t",
    },
]
K = len(RESOURCES)

# PLI: National Green Hydrogen Mission production incentives (USD/t urea equivalent)
# Budget: INR 19,744 Cr for electrolyser + incentive; translates to USD/kg H2 subsidy
# At 100 kg H2/t urea: 1 USD/kg H2 = 100 USD/t urea subsidy equivalent
PLI: Dict[str, Dict[int,float]] = {
    "Green-H2-Urea": {2024:0, 2030: 80, 2035:120, 2040:150, 2045:130, 2050:100, 2060:60, 2070:30},
    "Bio-Ammonia":   {2024:0, 2030: 10, 2035: 20,  2040: 30,  2050: 40, 2070:35},
    "NG-SMR-CCUS":   {2024:0, 2030:  5, 2035: 12,  2040: 20,  2050: 25, 2070:20},
}

GREEN_PREMIUM_ROUTES = {"Green-H2-Urea", "Bio-Ammonia"}
GREEN_PREMIUM: Dict[str, Dict[int,float]] = {
    "CPS": {2024:0, 2070:0},
    "NZS": {2024:15, 2030:55, 2040:130, 2050:220, 2070:310},
}

DEMAND: Dict[str, Dict[int,float]] = {
    "CPS": {2024:30.5, 2030:36.5, 2040:46.0, 2050:55.0, 2060:64.0, 2070:70.0},
    "NZS": {2024:30.5, 2030:36.0, 2040:44.0, 2050:53.0, 2060:61.0, 2070:67.0},
}
CARBON_PRICE: Dict[str, Dict[int,float]] = {
    "CPS": {2024:2, 2030:8, 2040:18, 2050:32, 2060:42, 2070:50},
    "NZS": {2024:10, 2030:50, 2040:135, 2050:235, 2060:285, 2070:330},
}

VOL4 = {"cps_2050":1.8,"cps_2070":1.2,"nzs_2050":0.7,"nzs_2070":0.05}
CO2_CEILING: Dict[str, Dict[int, float]] = {
    # tCO2/t urea; NG-SMR ef_2024=0.55→ef_cps_2070=0.40; CPS: gas lock-in, limited CCUS
    "CPS": {2054: 0.48, 2069: 0.42},
    "NZS": {2054: 0.15, 2069: 0.02},
}
CO2_FLOOR: Dict[str, Dict[int, float]] = {
    # CPS floor: urea price control + lack of green H2 infrastructure delays rapid switch
    "CPS": {2054: 0.36, 2069: 0.30},
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
          gas_price_adj=0.0, biomass_price_adj=0.0, coal_price_adj=0.0,
          pli_active=True, ccus_active=False,
          bio_ammonia_active=True, ng_smr_active=True,
          bio_cap=0.35, capex_by_route=None, discount_rate_adj=0.0):
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

    # Build H2 price trajectory with h2_cost_adj override (Lab slider)
    h2_price_traj={y: interp(RESOURCES[2]["price"].get(sc,RESOURCES[2]["price"]["CPS"]),y)+h2_cost_adj
                   for y in YEARS}

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
            ccus_pen=0.0 if ccus_active else (300.0 if "CCUS" in route["id"] else 0.0)
            bio_pen =0.0 if bio_ammonia_active else (300.0 if route["id"]=="Bio-Ammonia" else 0.0)
            ng_pen  =0.0 if ng_smr_active else (300.0 if route["id"]=="NG-SMR" else 0.0)
            c[_CAP(ri,ti)]+=d*(ann_cap*wacc_m+route["fom"])*DT
            c[_ACT(ri,ti)]+=d*(route["vom_residual"]-pl-gp+ccus_pen+bio_pen+ng_pen)*DT

    for ti,y in enumerate(YEARS):
        c[_CO2(ti)]+=df[y]*interp(cp_anch,y)

    # K=0:nat_gas, K=1:coal, K=2:green_h2, K=3:biomass
    _res_adj={0:gas_price_adj,1:coal_price_adj,3:biomass_price_adj}
    for ki,res in enumerate(RESOURCES):
        price_t=res["price"].get(sc,res["price"]["CPS"])
        adj=_res_adj.get(ki,0.0)
        for ti,y in enumerate(YEARS):
            # H2 resource: use adjusted trajectory
            if res["id"]=="green_h2":
                c[_RES(ki,ti)]+=df[y]*h2_price_traj[y]
            else:
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
                if route["id"]=="Bio-Ammonia": base=min(base,bio_cap)
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
        for ri,route in enumerate(ROUTES):
            if route["fossil_decline"]:
                # coal: decline from 2025; gas: from 2035
                start_y=2025 if route.get("coal_t_per_t",0)>0 else 2034
                start_ti=next((i for i,y in enumerate(YEARS) if y>=start_y),T-1)
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

app=FastAPI(title="Fertiliser Transition Backend v2",version="2.0.0")
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
    return {"status":"ok","sector":SECTOR,
            "model":"HiGHS LP v2 (CRF+WACC+GasH2Trajectory+NGHM-PLI)",
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
    x,code,msg=solve(sc,demand_anchors=d_anch,enforce_co2_ceiling=True)
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
    h2_adj=0.0
    if "h2_cost_adj" in payload:
        try: h2_adj=float(payload["h2_cost_adj"])
        except: pass
    elif "h2_cost" in payload:
        vals=[float(v) for v in payload["h2_cost"].values() if v is not None]
        h2_adj=(sum(vals)/len(vals)-interp(RESOURCES[2]["price"].get(sc,RESOURCES[2]["price"]["CPS"]),2040)
                if vals else 0.0)
    gas_adj       = float(payload.get("gas_price_adj", 0.0))
    biomass_adj   = float(payload.get("biomass_price_adj", 0.0))
    coal_adj      = float(payload.get("coal_price_adj", 0.0))
    pli_on        = bool(payload.get("pli_active", True))
    ccus_on       = bool(payload.get("ccus_active", False))
    bio_nh3_on    = bool(payload.get("bio_ammonia_active", True))
    ng_on         = bool(payload.get("ng_smr_active", True))
    bio_cap       = float(payload.get("bio_cap", 0.35))
    dr_adj        = float(payload.get("discount_rate_adj", 0.0))
    cbr           = payload.get("capex_by_route") or {}
    capex_by_r    = {k: float(v) for k, v in cbr.items()} if cbr else None
    x,code,msg=solve(sc,demand_anchors=d_anch,carbon_price_anchors=cp_anch,
                      green_premium_val=gp_val,capex_mult=capex_m,wacc_adj_pct=wacc,
                      h2_cost_adj=h2_adj,enforce_co2_ceiling=False,
                      gas_price_adj=gas_adj,biomass_price_adj=biomass_adj,
                      coal_price_adj=coal_adj,pli_active=pli_on,ccus_active=ccus_on,
                      bio_ammonia_active=bio_nh3_on,ng_smr_active=ng_on,
                      bio_cap=bio_cap,discount_rate_adj=dr_adj,
                      capex_by_route=capex_by_r)
    if x is None: return {"status":"infeasible","message":msg,"sector":SECTOR,"scenario":sc}
    yearly=extract_yearly(x,sc,d_anch)
    return {"status":"optimal" if code==0 else "feasible","message":msg,
            "sector":SECTOR,"scenario":f"LAB-{sc}","years":ALL_YEARS,
            "yearly_results":{str(y):v for y,v in yearly.items()},"summary":_summary(yearly)}

if __name__=="__main__":
    uvicorn.run(app,host="0.0.0.0",port=PORT,log_level="info")
