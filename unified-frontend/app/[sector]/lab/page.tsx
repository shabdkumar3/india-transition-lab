"use client";

import React from "react";
import { useParams } from "next/navigation";
import { getSector } from "@/lib/sectors";
import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { fmt1, fmt2 } from "@/lib/format";
import { Info, Download, Share2, ChevronDown, ChevronRight, FlaskConical, RotateCcw } from "lucide-react";
import { runLab, runScenario } from "@/lib/api";
import { exportYearlyCSV } from "@/lib/export";
import { copyLabLink } from "@/lib/url-state";
import type { LabParams } from "@/lib/url-state";
import type { YearlyResult } from "@/lib/api";
import {
  AreaChart, Area, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

type DemandKey = "niti" | "model_fitted" | "india_policy" | "international";

const RES_BASE: Record<string, Record<string, { label: string; unit: string; base: number; min: number; max: number; step: number }>> = {
  cement: {
    coal:  { label: "Coal",        unit: "$/t",    base: 90,  min: -50, max: 80,  step: 5   },
    elec:  { label: "Electricity", unit: "$/MWh",  base: 45,  min: -20, max: 40,  step: 2   },
  },
  aluminium: {
    coal_mwh:  { label: "Coal power",   unit: "$/MWh", base: 65,  min: -30, max: 50,  step: 2   },
    grid_elec: { label: "Grid elec",    unit: "$/MWh", base: 55,  min: -20, max: 40,  step: 2   },
    re_elec:   { label: "RE elec",      unit: "$/MWh", base: 35,  min: -15, max: 30,  step: 1   },
  },
  textile: {
    coal:    { label: "Coal",    unit: "$/t",     base: 90,  min: -50, max: 80,  step: 5   },
    gas:     { label: "Gas",     unit: "$/MMBtu", base: 8,   min: -5,  max: 10,  step: 0.5 },
    biomass: { label: "Biomass", unit: "$/GJ",    base: 6,   min: -3,  max: 10,  step: 0.5 },
    re_elec: { label: "RE elec", unit: "$/MWh",   base: 35,  min: -15, max: 30,  step: 1   },
  },
  fertiliser: {
    gas:     { label: "Nat. gas", unit: "$/MMBtu", base: 8,   min: -5,  max: 10,  step: 0.5 },
    coal:    { label: "Coal",     unit: "$/t",     base: 70,  min: -40, max: 60,  step: 5   },
    biomass: { label: "Biomass",  unit: "$/GJ",    base: 6,   min: -3,  max: 10,  step: 0.5 },
  },
  steel: {
    iron_ore:    { label: "Iron ore",        unit: "$/t",     base: 80,  min: -40, max: 60,  step: 5   },
    nat_gas:     { label: "Nat. gas",        unit: "$/MMBtu", base: 6,   min: -4,  max: 8,   step: 0.5 },
    coking_coal: { label: "Coking coal",     unit: "$/t",     base: 140, min: -60, max: 80,  step: 5   },
    non_coking:  { label: "Non-coking coal", unit: "$/t",     base: 70,  min: -40, max: 60,  step: 5   },
  },
};

type Toggle = { key: string; label: string; default: boolean; desc: string };
const SECTOR_TOGGLES: Record<string, Toggle[]> = {
  steel: [
    { key: "use_dynamic_scrap",       label: "Dynamic Scrap",       default: true,  desc: "Cohort-based EOL scrap stock-flow" },
    { key: "use_endogenous_learning", label: "Learning Curves",     default: true,  desc: "Technology cost learning as capacity scales" },
    { key: "ccus",                    label: "CCUS",                default: false, desc: "Carbon capture, utilisation & storage" },
    { key: "use_deployment_dynamics", label: "Deployment Dynamics", default: false, desc: "Ramp-rate constraints on new capacity" },
  ],
  cement: [
    { key: "pli_active",      label: "PLI Scheme",  default: true,  desc: "Production-linked incentives active" },
    { key: "lc3_active",      label: "LC3 Cement",  default: true,  desc: "Limestone calcined clay cement route" },
    { key: "alt_fuel_active", label: "Alt. Fuels",  default: true,  desc: "Alternative fuel substitution in kilns" },
    { key: "ccus_active",     label: "CCUS",        default: false, desc: "Post-combustion CO₂ capture on kilns" },
  ],
  aluminium: [
    { key: "pli_active",         label: "PLI Scheme",  default: true, desc: "Production-linked incentives active" },
    { key: "inert_anode_active", label: "Inert Anode", default: true, desc: "Carbon-free anode technology (no anode CO₂)" },
  ],
  textile: [
    { key: "pli_active",      label: "PLI / PM MITRA", default: true, desc: "PLI scheme & integrated textile parks" },
    { key: "gas_active",      label: "Gas Route",      default: true, desc: "Natural gas steam processing route" },
    { key: "biomass_active",  label: "Biomass Route",  default: true, desc: "Agri-residue / biomass steam route" },
    { key: "circular_active", label: "Circular",       default: true, desc: "High recycled-content fibre route" },
  ],
  fertiliser: [
    { key: "pli_active",         label: "NGHM PLI",       default: true,  desc: "National Green Hydrogen Mission incentives" },
    { key: "ccus_active",        label: "CCUS (Blue NH₃)", default: true,  desc: "Blue ammonia via NG-SMR + CCS" },
    { key: "bio_ammonia_active", label: "Bio-Ammonia",    default: true,  desc: "Biomass gasification ammonia route" },
    { key: "ng_smr_active",      label: "NG-SMR",         default: true,  desc: "Natural gas steam methane reforming" },
  ],
};

type RouteCapex = { routeId: string; label: string; default: number };
const ROUTE_CAPEX: Record<string, RouteCapex[]> = {
  steel:      [
    { routeId: "H2-DRI-EAF",  label: "H₂-DRI-EAF CAPEX", default: 1.0 },
    { routeId: "NG-DRI-EAF",  label: "NG-DRI-EAF CAPEX",  default: 1.0 },
    { routeId: "Scrap-EAF",   label: "Scrap-EAF CAPEX",   default: 1.0 },
  ],
  cement:     [
    { routeId: "CCUS-Blended",    label: "CCUS CAPEX",    default: 1.0 },
    { routeId: "Coal-LC3",        label: "LC3 CAPEX",     default: 1.0 },
    { routeId: "AltFuel-Blended", label: "AltFuel CAPEX", default: 1.0 },
  ],
  aluminium:  [
    { routeId: "RE-Primary",   label: "RE-Electrolysis CAPEX", default: 1.0 },
    { routeId: "Inert-Anode",  label: "Inert-Anode CAPEX",     default: 1.0 },
    { routeId: "Secondary-Al", label: "Secondary-Al CAPEX",    default: 1.0 },
  ],
  textile:    [
    { routeId: "RE-Electrified",  label: "RE-Processing CAPEX",  default: 1.0 },
    { routeId: "Circular-Fibre",  label: "Circular CAPEX",       default: 1.0 },
    { routeId: "Biomass-Cogen",   label: "Biomass CAPEX",        default: 1.0 },
    { routeId: "Green-H2-Steam",  label: "Green H₂ Steam CAPEX", default: 1.0 },
  ],
  fertiliser: [
    { routeId: "Green-H2",       label: "Green H₂-Urea CAPEX", default: 1.0 },
    { routeId: "Biomass-Reform", label: "Bio-Ammonia CAPEX",    default: 1.0 },
    { routeId: "NG-SMR-CCS",     label: "NG-SMR+CCUS CAPEX",   default: 1.0 },
  ],
};

type SupplyControl = { key: string; label: string; unit: string; min: number; max: number; step: number; default: number; desc: string };
const SUPPLY_CONTROLS: Record<string, SupplyControl[]> = {
  cement:     [{ key: "alt_fuel_cap",      label: "Alt-fuel supply cap",   unit: "% demand", min: 5,  max: 80, step: 5, default: 80, desc: "Max fraction of demand served by AltFuel-Blended route" }],
  aluminium:  [{ key: "secondary_cap_pct", label: "Secondary-Al cap",      unit: "% demand", min: 5,  max: 45, step: 5, default: 45, desc: "Max fraction of demand from scrap remelting" }],
  textile:    [
    { key: "biomass_cap",  label: "Biomass supply cap",   unit: "% demand", min: 5, max: 50, step: 5, default: 50, desc: "Max fraction served by Biomass-Processing" },
    { key: "circular_cap", label: "Circular textiles cap", unit: "% demand", min: 5, max: 40, step: 5, default: 40, desc: "Max fraction served by Circular-Textiles" },
  ],
  fertiliser: [{ key: "bio_cap", label: "Bio-Ammonia supply cap", unit: "% demand", min: 5, max: 50, step: 5, default: 35, desc: "Max fraction from biomass-based ammonia route" }],
  steel:      [],
};

// Reference carbon prices — calibrated to sector YAML configs (all sectors share same trajectory)
// CPS: PAT/NCEF extended  |  NZS: IPCC SR1.5 NDC-compatible  |  2024 USD
const SCENARIO_CARBON: Record<"CPS"|"NZS", {"2030":number;"2050":number;"2070":number}> = {
  CPS: { "2030": 15,  "2050": 65,  "2070": 110 },  // matches YAML CPS trajectory
  NZS: { "2030": 30,  "2050": 120, "2070": 185 },  // matches YAML NZS trajectory
};

interface LabState {
  scenario:    "CPS" | "NZS";
  demandModel: DemandKey;
  carbonPrice: { "2030": number; "2050": number; "2070": number };
  h2Cost:      { "2030": number; "2050": number; "2070": number };
  greenPremium: number;
  waccPct:      number;
  gridEI2070:   number;
  toggles:      Record<string, boolean>;
  resPrices:    Record<string, number>;
  capexByRoute: Record<string, number>;
  supply:       Record<string, number>;
}

function makeDefaults(sectorId: string): LabState {
  const toggles: Record<string, boolean> = {};
  for (const t of SECTOR_TOGGLES[sectorId] ?? []) toggles[t.key] = t.default;
  const resPrices: Record<string, number> = {};
  for (const k of Object.keys(RES_BASE[sectorId] ?? {})) resPrices[k] = 0;
  const capexByRoute: Record<string, number> = {};
  for (const r of ROUTE_CAPEX[sectorId] ?? []) capexByRoute[r.routeId] = r.default;
  const supply: Record<string, number> = {};
  for (const c of SUPPLY_CONTROLS[sectorId] ?? []) supply[c.key] = c.default / 100;
  return {
    scenario: "CPS",
    demandModel: "niti",
    carbonPrice: { "2030": 15, "2050": 65, "2070": 110 },  // CPS YAML defaults
    h2Cost:      { "2030": 4.0, "2050": 1.5, "2070": 1.0 },
    greenPremium: 0, waccPct: 10, gridEI2070: 0,  // 0 = use scenario trajectory (auto)
    toggles, resPrices, capexByRoute, supply,
  };
}

const DEMAND_OPTS: { key: DemandKey; label: string }[] = [
  { key: "niti",          label: "NITI Vol.4"             },
  { key: "model_fitted",  label: "Historical trend"       },
  { key: "india_policy",  label: "India Policy Consensus" },
  { key: "international", label: "International Baseline" },
];
const CHART_YEARS = [2024,2029,2034,2039,2044,2049,2054,2059,2064,2069];

const SECTOR_ACCENT: Record<string, string> = {
  steel: "#2563eb", cement: "#ea580c", aluminium: "#0284c7",
  textile: "#db2777", fertiliser: "#65a30d",
};

// Light theme tokens
const T = { text:"#23261f", sub:"#474c44", muted:"#7a7e74", dim:"#a8ada5", border:"#e8e5de", card:"#ffffff", bg:"#f7f6f2" };
const CARD_STYLE: React.CSSProperties = { background: T.card, border:`1px solid ${T.border}`, borderRadius:12, boxShadow:"0 1px 3px rgba(0,0,0,0.04)" };
const TT = { background:"#ffffff", border:`1px solid ${T.border}`, borderRadius:6, fontSize:12, color:T.text };

// ─── Toggle switch ────────────────────────────────────────────────────────────
function ToggleSwitch({ on, onChange, accent }: { on: boolean; onChange: (v: boolean) => void; accent: string }) {
  return (
    <button onClick={() => onChange(!on)} role="switch" aria-checked={on}
      style={{
        position:"relative", width:36, height:20, borderRadius:10, flexShrink:0,
        border:"none", cursor:"pointer", transition:"background 200ms",
        background: on ? accent : "#d1d5db",
      }}>
      <span style={{
        position:"absolute", top:2, width:16, height:16, borderRadius:"50%",
        background:"#ffffff", boxShadow:"0 1px 3px rgba(0,0,0,0.2)",
        transition:"left 200ms",
        left: on ? 18 : 2,
      }} />
    </button>
  );
}

// ─── Tag pill ─────────────────────────────────────────────────────────────────
function Tag({ label, active, onChange, accent, desc }: { label:string; active:boolean; onChange:(v:boolean)=>void; accent:string; desc?:string }) {
  return (
    <button title={desc} onClick={() => onChange(!active)}
      style={{
        padding:"4px 10px", borderRadius:20, fontSize:11, fontWeight:600, cursor:"pointer",
        border:"1px solid", transition:"all 120ms", lineHeight:1.3, whiteSpace:"nowrap",
        ...(active
          ? { background: accent+"18", color: accent, borderColor: accent+"55" }
          : { background:"transparent", color:T.muted, borderColor:T.border })
      }}>
      {active ? "✓ " : ""}{label}
    </button>
  );
}

// ─── Slider ───────────────────────────────────────────────────────────────────
function Slider({ label, value, onChange, min, max, step=1, unit="", accent="#2563eb", baseline, small=false }: {
  label:string; value:number; onChange:(v:number)=>void; min:number; max:number;
  step?:number; unit?:string; accent?:string; baseline?:number; small?:boolean;
}) {
  const pct = Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100));
  return (
    <div style={{ marginBottom: small ? 10 : 14 }}>
      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:4, alignItems:"center" }}>
        <span style={{ fontSize: small?10:11, color: T.muted }}>{label}</span>
        <div style={{ display:"flex", alignItems:"center", gap:6 }}>
          {baseline !== undefined && value !== 0 && (
            <span style={{ fontSize:9, color: value>0?"#dc2626":"#16a34a" }}>
              {value>0?"+":""}{value}{unit}
            </span>
          )}
          <span style={{ fontSize: small?10:12, fontWeight:700, color: T.text, fontVariantNumeric:"tabular-nums" }}>
            {baseline !== undefined ? `${baseline+value}${unit}` : `${value}${unit}`}
          </span>
        </div>
      </div>
      <div style={{ position:"relative", height:4, background:"rgba(0,0,0,0.08)", borderRadius:4, marginBottom:2 }}>
        <div style={{ position:"absolute", left:0, width:`${pct}%`, height:"100%", background:accent, borderRadius:4, opacity:0.75 }} />
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e=>onChange(Number(e.target.value))}
        style={{ width:"100%", accentColor:accent, cursor:"pointer", marginTop:-4, height:16, color:accent }} />
      <div style={{ display:"flex", justifyContent:"space-between" }}>
        <span style={{ fontSize:9, color:T.dim }}>{min}{unit}</span>
        <span style={{ fontSize:9, color:T.dim }}>{max}{unit}</span>
      </div>
    </div>
  );
}

// ─── PRow — parameter row (label + control) ───────────────────────────────────
function PRow({ label, sub, children }: { label:string; sub?:string; children:React.ReactNode }) {
  return (
    <div style={{ display:"flex", alignItems:"flex-start", gap:12, padding:"12px 0", borderBottom:`1px solid ${T.border}` }}>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontSize:12, fontWeight:600, color:T.text }}>{label}</div>
        {sub && <div style={{ fontSize:10, color:T.muted, marginTop:2, lineHeight:1.5 }}>{sub}</div>}
      </div>
      <div style={{ flexShrink:0, paddingTop:2 }}>{children}</div>
    </div>
  );
}

// ─── Collapsible section ──────────────────────────────────────────────────────
function Section({ title, children, defaultOpen=true }: { title:string; children:React.ReactNode; defaultOpen?:boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ marginBottom:0 }}>
      <button onClick={() => setOpen(o=>!o)}
        style={{ width:"100%", display:"flex", alignItems:"center", justifyContent:"space-between",
          padding:"10px 0 6px", background:"none", border:"none", cursor:"pointer",
          color:T.dim, fontSize:9, fontWeight:700, letterSpacing:"0.12em", textTransform:"uppercase" }}>
        {title}
        {open ? <ChevronDown size={11}/> : <ChevronRight size={11}/>}
      </button>
      {open && <div style={{ paddingBottom:4 }}>{children}</div>}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function LabPage() {
  const params   = useParams();
  const sectorId = Array.isArray(params.sector) ? params.sector[0] : (params.sector ?? "steel");
  const s        = getSector(sectorId);
  const accent   = SECTOR_ACCENT[sectorId] ?? "#2563eb";

  const [lab,      setLab]      = useState<LabState>(() => makeDefaults(sectorId));
  const [running,  setRunning]  = useState(false);
  const [run,      setRun]      = useState<Record<number,YearlyResult>|null>(null);
  const [baseline, setBaseline] = useState<Record<number,YearlyResult>|null>(null);
  const [runError, setRunError] = useState<string|null>(null);
  const sectorRef   = useRef(sectorId);
  const isRunningRef = useRef(false);

  useEffect(() => {
    if (sectorRef.current !== sectorId) {
      sectorRef.current = sectorId;
      setLab(makeDefaults(sectorId));
      setRun(null); setBaseline(null); setRunError(null);
    }
  }, [sectorId]);

  const setT_  = (k:string,v:boolean)=>setLab(p=>({...p,toggles:{...p.toggles,[k]:v}}));
  const setR   = (k:string,v:number)=>setLab(p=>({...p,resPrices:{...p.resPrices,[k]:v}}));
  const setCR  = (k:string,v:number)=>setLab(p=>({...p,capexByRoute:{...p.capexByRoute,[k]:v}}));
  const setSup = (k:string,v:number)=>setLab(p=>({...p,supply:{...p.supply,[k]:v}}));

  const buildPayload = useCallback((l: LabState) => {
    // Steel lab uses "LAB" scenario string (its own convention) + demand_anchors in Mt steel.
    // v3 backends (cement/aluminium/textile/fertiliser): use actual "CPS"/"NZS" + demand_model name
    // so backends can select the correct scaled YAML trajectory (avoids unit mismatch).
    const demandOverride: Record<string,unknown> = sectorId === "steel"
      ? { demand_anchors: s.demandTrajectories.find(t=>t.key===l.demandModel)?.anchors ?? s.demandTrajectories[0].anchors }
      : { demand_model: l.demandModel };
    const scenarioKey = sectorId === "steel" ? "LAB" : l.scenario;
    // Always include 2024 anchor so interpolation works from the start of the horizon
    const carbonPriceWithBase = { "2024": 5, ...l.carbonPrice };
    const p: Record<string,unknown> = {
      scenario: scenarioKey, carbon_price: carbonPriceWithBase,
      capex_multiplier:1.0, green_premium:l.greenPremium,
      wacc:l.waccPct/100,
      ...demandOverride, capex_by_route:l.capexByRoute, ...l.toggles,
    };
    // Only send grid_ei_2070 when user has explicitly set it (0 = auto, use scenario trajectory)
    if (l.gridEI2070 > 0) p.grid_ei_2070 = l.gridEI2070;
    for (const [k,v] of Object.entries(l.supply)) {
      const ctrl = SUPPLY_CONTROLS[sectorId]?.find(c=>c.key===k);
      if (ctrl) p[k] = ctrl.unit.includes("%") ? v : v;
    }
    const rp = l.resPrices;
    if (sectorId==="cement") {
      if (rp.coal!==undefined) p.coal_price_adj=rp.coal;
      if (rp.elec!==undefined) p.elec_price_adj=rp.elec;
    } else if (sectorId==="aluminium") {
      if (rp.coal_mwh!==undefined)  p.coal_price_adj =rp.coal_mwh;
      if (rp.grid_elec!==undefined) p.grid_price_adj =rp.grid_elec;
      if (rp.re_elec!==undefined)   p.re_price_adj   =rp.re_elec;
    } else if (sectorId==="textile") {
      if (rp.coal!==undefined)    p.coal_price_adj   =rp.coal;
      if (rp.gas!==undefined)     p.gas_price_adj    =rp.gas;
      if (rp.biomass!==undefined) p.biomass_price_adj=rp.biomass;
      if (rp.re_elec!==undefined) p.re_price_adj     =rp.re_elec;
    } else if (sectorId==="fertiliser") {
      if (rp.gas!==undefined)     p.gas_price_adj    =rp.gas;
      if (rp.coal!==undefined)    p.coal_price_adj   =rp.coal;
      if (rp.biomass!==undefined) p.biomass_price_adj=rp.biomass;
    } else if (sectorId==="steel") {
      p.h2_cost={...l.h2Cost};
      const resourcePrices: Record<string,unknown> = {
        h2: { "2030":l.h2Cost["2030"], "2050":l.h2Cost["2050"], "2070":l.h2Cost["2070"] },
      };
      if (rp.iron_ore!==undefined)    resourcePrices.iron_ore        =80 +rp.iron_ore;
      if (rp.nat_gas!==undefined)     resourcePrices.natural_gas     =6  +rp.nat_gas;
      if (rp.coking_coal!==undefined) resourcePrices.coking_coal     =140+rp.coking_coal;
      if (rp.non_coking!==undefined)  resourcePrices.non_coking_coal =70 +rp.non_coking;
      p.resource_prices=resourcePrices;
    }
    if (sectorId==="fertiliser") p.h2_cost={...l.h2Cost};
    return p;
  }, [s, sectorId]);

  const doRun = useCallback(async (l: LabState) => {
    if (isRunningRef.current) return;
    isRunningRef.current = true;
    setRunning(true); setRunError(null);
    try {
      const payload = buildPayload(l);
      const result = await runLab(s, payload);
      if (result.yearly_results) setRun(result.yearly_results as Record<number,YearlyResult>);
      else setRunError(result.message ?? "Solver returned no results.");
    } catch(e) { setRunError(e instanceof Error ? e.message : "Unknown error"); }
    setRunning(false);
    isRunningRef.current = false;
  }, [s, buildPayload]);

  const fetchBaseline = useCallback(async (dm: DemandKey) => {
    const overrides: Record<string,unknown> = sectorId === "steel"
      ? { demand_anchors: s.demandTrajectories.find(t=>t.key===dm)?.anchors ?? s.demandTrajectories[0].anchors }
      : { demand_model: dm };
    try {
      const result = await runScenario(s, "CPS", overrides);
      if (result.yearly_results) setBaseline(result.yearly_results as Record<number,YearlyResult>);
    } catch { /* optional */ }
  }, [s, sectorId]);

  useEffect(() => {
    const d = makeDefaults(sectorId);
    doRun(d);
    fetchBaseline(d.demandModel);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectorId]);

  // Re-fetch baseline when demand model changes so delta comparison stays correct.
  // Skip if triggered by sectorId change (that effect already fetches baseline).
  const prevSectorRef = useRef(sectorId);
  useEffect(() => {
    if (prevSectorRef.current !== sectorId) { prevSectorRef.current = sectorId; return; }
    fetchBaseline(lab.demandModel);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lab.demandModel]);

  const chartData = useMemo(() => {
    if (!run) return [];
    return CHART_YEARS.map(yr => {
      const d = run[yr];
      if (!d) return { year: yr };
      const row: Record<string,number> = { year: yr };
      for (const [route,val] of Object.entries(d.production_by_route ?? {})) row[route] = +(val as number).toFixed(3);
      row.co2_intensity = d.co2_intensity;
      row.co2_total     = d.co2_total;
      row.total_cost    = d.total_cost as number ?? 0;
      return row;
    });
  }, [run]);

  const kpis = useMemo(() => {
    if (!run) return null;
    const yrs = Object.keys(run).map(Number).sort((a,b)=>a-b);
    const first = run[yrs[0]]; const last = run[yrs[yrs.length-1]];
    if (!first||!last) return null;
    // Top route by production share in last year
    const routes2070 = last.production_by_route ?? {};
    const totalProd = last.total_production || 1;
    const topRoute = Object.entries(routes2070).sort(([,a],[,b])=>(b as number)-(a as number))[0];
    const topRouteLabel = topRoute ? topRoute[0] : "—";
    const topRoutePct  = topRoute ? Math.round(((topRoute[1] as number)/totalProd)*100) : 0;
    // Cumulative investment
    const cumInvest = Object.values(run).reduce((a,y)=>
      a + Object.values(y.investment_by_route??{}).reduce((s,v)=>s+(v as number),0), 0);
    return {
      finalIntensity: last.co2_intensity,
      reductionPct: ((first.co2_intensity - last.co2_intensity)/first.co2_intensity)*100,
      finalDemand:  last.total_production,
      cumulativeCo2: Object.values(run).reduce((a,y)=>a+(y.co2_total??0),0),
      totalCost2070: last.total_cost ?? 0,
      cumInvest,
      topRouteLabel, topRoutePct,
    };
  }, [run]);

  const delta = useMemo(() => {
    if (!run||!baseline) return null;
    const labYr = run[2069]||run[2070]; const bYr = baseline[2069]||baseline[2070];
    if (!labYr||!bYr) return null;
    const labCum = Object.values(run).reduce((a,y)=>a+(y.co2_total??0),0);
    const basCum = Object.values(baseline).reduce((a,y)=>a+(y.co2_total??0),0);
    return {
      intensityDelta: labYr.co2_intensity - bYr.co2_intensity,
      cumCo2Delta:    (labCum-basCum)/1000,
      co2TotalDelta:  labYr.co2_total - bYr.co2_total,
    };
  }, [run, baseline]);

  const resConf    = RES_BASE[sectorId] ?? {};
  const toggles    = SECTOR_TOGGLES[sectorId] ?? [];
  const routeCapex = ROUTE_CAPEX[sectorId] ?? [];
  const supplyCtrl = SUPPLY_CONTROLS[sectorId] ?? [];
  const showH2     = sectorId === "steel" || sectorId === "fertiliser";

  return (
    <div>
      {/* ── Header ── */}
      <div style={{ borderBottom:`1px solid ${T.border}`, paddingBottom:18, marginBottom:22 }}>
        <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:4 }}>
          <FlaskConical size={18} style={{ color:accent }} />
          <h1 style={{ fontSize:24, fontWeight:700, color:T.text, margin:0, letterSpacing:"-0.01em" }}>
            Scenario Builder
          </h1>
          {running && <span style={{ fontSize:11, color:accent, marginLeft:8 }} className="animate-pulse">solving…</span>}
        </div>
        <p style={{ fontSize:13, color:T.muted, margin:0 }}>
          Adjust parameters below — CPS/NZS reference values guide each input. Run the solver and see full results below.
        </p>
      </div>

      {/* ── Config card ── */}
      <div style={{ ...CARD_STYLE, marginBottom:22 }}>

        {/* Scenario + demand selector row */}
        <div style={{ padding:"16px 20px", borderBottom:`1px solid ${T.border}`, display:"flex", alignItems:"center", flexWrap:"wrap", gap:20 }}>
          {/* Scenario tabs */}
          <div>
            <div style={{ fontSize:10, fontWeight:600, letterSpacing:"0.1em", textTransform:"uppercase", color:T.dim, marginBottom:8 }}>
              Base Scenario
            </div>
            <div style={{ display:"inline-flex", borderRadius:8, border:`1px solid ${T.border}`, background:"#f7f6f2", padding:2 }}>
              {(["CPS","NZS"] as const).map(sc => (
                <button key={sc}
                  onClick={() => {
                    const cp = SCENARIO_CARBON[sc];
                    setLab(p => ({
                      ...p, scenario: sc, carbonPrice: cp,
                      // Reset grid EI to auto when switching scenarios so scenario trajectory applies
                      gridEI2070: p.gridEI2070 === 0 ? 0 : p.gridEI2070,
                    }));
                  }}
                  style={{
                    padding:"6px 18px", borderRadius:6, fontSize:12, fontWeight:600, cursor:"pointer", border:"none",
                    transition:"all 150ms",
                    background: lab.scenario === sc ? T.card : "transparent",
                    color: lab.scenario === sc ? T.text : T.muted,
                    boxShadow: lab.scenario === sc ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
                  }}>
                  {sc === "CPS" ? "Current Policy" : "Net Zero"}
                </button>
              ))}
            </div>
          </div>
          {/* Demand model pills */}
          <div>
            <div style={{ fontSize:10, fontWeight:600, letterSpacing:"0.1em", textTransform:"uppercase", color:T.dim, marginBottom:8 }}>
              Demand Model
            </div>
            <div style={{ display:"flex", flexWrap:"wrap", gap:5 }}>
              {DEMAND_OPTS.map(d => (
                <button key={d.key} onClick={()=>setLab(p=>({...p,demandModel:d.key}))}
                  style={{
                    padding:"5px 11px", borderRadius:6, fontSize:11, fontWeight:500,
                    cursor:"pointer", transition:"all 120ms", border:"1px solid",
                    ...(lab.demandModel===d.key
                      ? { background:accent+"14", color:accent, borderColor:accent+"50" }
                      : { background:"transparent", color:T.muted, borderColor:T.border })
                  }}>
                  {d.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Two-column parameter grid */}
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:0 }}>

          {/* ── Left column ── */}
          <div style={{ padding:"16px 24px", borderRight:`1px solid ${T.border}` }}>

            {/* Feature toggles */}
            {toggles.length > 0 && (
              <Section title="Feature Toggles">
                <div style={{ display:"flex", flexDirection:"column", gap:0 }}>
                  {toggles.map(t => (
                    <PRow key={t.key} label={t.label} sub={t.desc}>
                      <ToggleSwitch on={lab.toggles[t.key]??t.default} onChange={v=>setT_(t.key,v)} accent={accent}/>
                    </PRow>
                  ))}
                </div>
              </Section>
            )}

            {/* Carbon price */}
            <Section title="Carbon Price ($/tCO₂)">
              {(["2030","2050","2070"] as const).map(yr => (
                <Slider key={yr} label={yr}
                  value={lab.carbonPrice[yr]}
                  onChange={v=>setLab(p=>({...p,carbonPrice:{...p.carbonPrice,[yr]:v}}))}
                  min={0} max={yr==="2030"?100:yr==="2050"?400:600} unit=" $/t" accent={accent}/>
              ))}
            </Section>

            {/* H2 cost */}
            {showH2 && (
              <Section title="Green H₂ Cost ($/kg)">
                <Slider label="2030" value={lab.h2Cost["2030"]}
                  onChange={v=>setLab(p=>({...p,h2Cost:{...p.h2Cost,"2030":v}}))}
                  min={0.5} max={8} step={0.1} unit=" $/kg" accent={accent}/>
                <Slider label="2050" value={lab.h2Cost["2050"]}
                  onChange={v=>setLab(p=>({...p,h2Cost:{...p.h2Cost,"2050":v}}))}
                  min={0.5} max={4} step={0.1} unit=" $/kg" accent={accent}/>
                <Slider label="2070" value={lab.h2Cost["2070"]}
                  onChange={v=>setLab(p=>({...p,h2Cost:{...p.h2Cost,"2070":v}}))}
                  min={0.3} max={3} step={0.1} unit=" $/kg" accent={accent}/>
              </Section>
            )}

            {/* Resource prices */}
            {Object.keys(resConf).length > 0 && (
              <Section title="Resource Prices (±adjustment)">
                {Object.entries(resConf).map(([k,cfg]) => (
                  <Slider key={k} label={`${cfg.label} (${cfg.unit})`}
                    value={lab.resPrices[k]??0}
                    onChange={v=>setR(k,v)}
                    min={cfg.min} max={cfg.max} step={cfg.step}
                    unit={" "+cfg.unit.split("/")[0]} accent={accent}
                    baseline={cfg.base} small/>
                ))}
              </Section>
            )}
          </div>

          {/* ── Right column ── */}
          <div style={{ padding:"16px 24px" }}>

            {/* Route CAPEX */}
            {routeCapex.length > 0 && (
              <Section title="Route CAPEX Multipliers">
                {routeCapex.map(r => (
                  <Slider key={r.routeId} label={r.label}
                    value={lab.capexByRoute[r.routeId]??1}
                    onChange={v=>setCR(r.routeId,v)}
                    min={0.5} max={2.0} step={0.05} accent={accent} small/>
                ))}
              </Section>
            )}

            {/* Supply constraints */}
            {supplyCtrl.length > 0 && (
              <Section title="Supply Constraints">
                {supplyCtrl.map(c => (
                  <Slider key={c.key} label={`${c.label} (${c.unit})`}
                    value={Math.round((lab.supply[c.key]??c.default/100)*100)}
                    onChange={v=>setSup(c.key,v/100)}
                    min={c.min} max={c.max} step={c.step} unit="%" accent={accent} small/>
                ))}
              </Section>
            )}

            {/* Economics & Finance */}
            <Section title="Economics &amp; Finance">
              <Slider label="Green premium ($/t produced)"
                value={lab.greenPremium} onChange={v=>setLab(p=>({...p,greenPremium:v}))}
                min={0} max={120} unit=" $/t" accent={accent} small/>
              <Slider label="WACC (%)"
                value={lab.waccPct} onChange={v=>setLab(p=>({...p,waccPct:v}))}
                min={5} max={25} unit="%" accent={accent} small/>
              <Slider label={`Grid EI 2070 (kgCO₂/kWh)${lab.gridEI2070===0?" · Auto (scenario default)":""}`}
                value={lab.gridEI2070} onChange={v=>setLab(p=>({...p,gridEI2070:v}))}
                min={0} max={0.5} step={0.01} accent={accent} small/>
            </Section>

            {/* Vol.4 reference */}
            <div style={{ borderRadius:8, padding:"10px 14px", background:"#f7f6f2", border:`1px solid ${T.border}`, fontSize:11, color:T.muted, lineHeight:1.6, marginTop:8 }}>
              <span style={{ fontWeight:600, color:T.sub }}>Vol.4 targets</span>
              {" — "}CPS 2070: {s.vol4.co2_intensity.cps[2070]} · NZS 2070: {s.vol4.co2_intensity.nzs[2070]} tCO₂/{s.unit_short}
              <br />{s.vol4.citation}
            </div>

          </div>
        </div>

        {/* Action buttons row */}
        <div style={{ padding:"14px 20px", borderTop:`1px solid ${T.border}`, display:"flex", alignItems:"center", gap:10, flexWrap:"wrap" }}>
          <button onClick={()=>doRun(lab)} disabled={running}
            style={{
              padding:"9px 28px", borderRadius:8, fontSize:13, fontWeight:700,
              cursor:"pointer", border:"none",
              background: running ? "#e8e5de" : accent,
              color: running ? T.muted : "#ffffff",
              opacity:1, transition:"all 150ms",
              boxShadow: running ? "none" : `0 2px 8px ${accent}40`,
            }}>
            {running ? "Computing…" : "▶ Run Scenario"}
          </button>

          <button disabled={!run}
            onClick={()=>{ if(!run) return; exportYearlyCSV(run, s.routes.map(r=>r.id), `${sectorId}_lab.csv`,
              { sector:s.label, scenario:"LAB", generated:new Date().toISOString().slice(0,10) }); }}
            style={{
              display:"flex", alignItems:"center", gap:5,
              padding:"8px 16px", borderRadius:8, fontSize:12, cursor:"pointer",
              border:`1px solid ${T.border}`, background:T.card,
              color: !run ? T.dim : T.muted, opacity: !run ? 0.5 : 1,
              transition:"all 150ms",
            }}>
            <Download className="h-3.5 w-3.5"/> CSV
          </button>

          <button onClick={()=>{ const p:LabParams={cp30:lab.carbonPrice["2030"],cp50:lab.carbonPrice["2050"],
            cp70:lab.carbonPrice["2070"],h2_30:lab.h2Cost["2030"],h2_50:lab.h2Cost["2050"],h2_70:lab.h2Cost["2070"],
            capex:1,gp:lab.greenPremium,wacc:lab.waccPct,ei:lab.gridEI2070,dm:lab.demandModel,sc:"LAB"};copyLabLink(p);}}
            style={{
              display:"flex", alignItems:"center", gap:5,
              padding:"8px 16px", borderRadius:8, fontSize:12, cursor:"pointer",
              border:`1px solid ${T.border}`, background:T.card, color:T.muted,
              transition:"all 150ms",
            }}>
            <Share2 className="h-3.5 w-3.5"/> Share
          </button>

          <button onClick={()=>{ const d=makeDefaults(sectorId); setLab(d); doRun(d); }}
            style={{ display:"flex", alignItems:"center", gap:4,
              fontSize:11, color:T.dim, background:"none", border:"none",
              cursor:"pointer", padding:"8px 10px", marginLeft:"auto" }}>
            <RotateCcw size={12}/> Reset to defaults
          </button>
        </div>
      </div>

      {/* ── Results section ── */}

      {/* Error banner */}
      {runError && !running && (
        <div style={{ display:"flex", alignItems:"flex-start", gap:10, borderRadius:10, padding:"12px 16px", marginBottom:16,
          background:"#fffbeb", border:"1px solid #fde68a", color:"#b45309" }}>
          <Info className="h-4 w-4 mt-0.5 flex-shrink-0" style={{ opacity:0.7 }}/>
          <div style={{ flex:1 }}>
            <p style={{ fontWeight:600, fontSize:13, margin:0 }}>Backend not ready — solver warming up</p>
            <p style={{ fontSize:11, marginTop:3, color:"#92400e", margin:"3px 0 0" }}>
              Adjust any control or press Retry to re-run.
            </p>
          </div>
          <button onClick={()=>doRun(lab)}
            style={{ borderRadius:6, padding:"5px 12px", fontSize:11, fontWeight:600, cursor:"pointer",
              background:"rgba(180,83,9,0.12)", color:"#b45309", border:"1px solid rgba(180,83,9,0.3)" }}>
            Retry
          </button>
        </div>
      )}

      {/* KPI strip — two rows */}
      {kpis && (
        <div style={{ ...CARD_STYLE, overflow:"hidden", marginBottom:16 }}>
          {/* Row 1: emissions */}
          <div style={{ display:"flex", flexWrap:"wrap", borderBottom:`1px solid ${T.border}` }}>
            {[
              { label:`CO₂ intensity 2070`,      val:`${fmt2(kpis.finalIntensity)} tCO₂/${s.unit_short}`, color:"#dc2626" },
              { label:"Intensity reduction",      val:`−${fmt1(kpis.reductionPct)}%`,                      color:"#16a34a" },
              { label:"Cumulative CO₂ 2024–70",  val:`${fmt1(kpis.cumulativeCo2/1000)} GtCO₂`,            color:"#ea580c" },
            ].map((k,i) => (
              <div key={k.label} style={{ flex:"1 1 130px", padding:"14px 20px",
                borderRight: i<2 ? `1px solid ${T.border}` : "none" }}>
                <p style={{ fontSize:9, fontWeight:700, letterSpacing:"0.14em", textTransform:"uppercase",
                  color:T.dim, margin:"0 0 8px" }}>{k.label}</p>
                <p style={{ fontSize:20, fontWeight:800, color:k.color,
                  fontVariantNumeric:"tabular-nums", margin:0, lineHeight:1.15 }}>{k.val}</p>
              </div>
            ))}
          </div>
          {/* Row 2: production & economics */}
          <div style={{ display:"flex", flexWrap:"wrap" }}>
            {[
              { label:`Production 2070`,          val:`${fmt1(kpis.finalDemand)} ${s.unit_short}` },
              { label:"Dominant route 2070",      val:`${kpis.topRouteLabel} · ${kpis.topRoutePct}%` },
              { label:"Cumul. investment",         val: kpis.cumInvest > 1 ? `$${fmt1(kpis.cumInvest/1000)} B` : "—" },
            ].map((k,i) => (
              <div key={k.label} style={{ flex:"1 1 130px", padding:"14px 20px",
                borderRight: i<2 ? `1px solid ${T.border}` : "none" }}>
                <p style={{ fontSize:9, fontWeight:700, letterSpacing:"0.14em", textTransform:"uppercase",
                  color:T.dim, margin:"0 0 8px" }}>{k.label}</p>
                <p style={{ fontSize:16, fontWeight:800, color:T.text,
                  fontVariantNumeric:"tabular-nums", margin:0, lineHeight:1.15 }}>{k.val}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Delta vs CPS */}
      {delta && (
        <div style={{ ...CARD_STYLE, overflow:"hidden", marginBottom:16 }}>
          <div style={{ padding:"11px 20px 9px", borderBottom:`1px solid ${T.border}` }}>
            <p style={{ fontSize:10, fontWeight:700, letterSpacing:"0.14em", textTransform:"uppercase", color:T.dim, margin:0 }}>vs CPS Baseline</p>
          </div>
          <div style={{ display:"flex", flexWrap:"wrap" }}>
            {[
              { label:"CO₂ intensity 2070", value:delta.intensityDelta, unit:` tCO₂/${s.unit_short}`, dec:3 },
              { label:"Total CO₂ 2070",     value:delta.co2TotalDelta,  unit:" Mt/yr",               dec:1 },
              { label:"Cumulative CO₂",      value:delta.cumCo2Delta,    unit:" GtCO₂",               dec:2 },
            ].map(({label,value,unit,dec},i) => (
              <div key={label} style={{ flex:"1 1 130px", padding:"14px 20px", textAlign:"center",
                borderRight: i<2 ? `1px solid ${T.border}` : "none" }}>
                <p style={{ fontSize:9, fontWeight:700, letterSpacing:"0.12em", textTransform:"uppercase",
                  color:T.dim, margin:"0 0 8px" }}>{label}</p>
                <p style={{ fontSize:20, fontWeight:800, fontVariantNumeric:"tabular-nums", margin:"0 0 4px",
                  color:value<-0.001?"#16a34a":value>0.001?"#dc2626":T.muted }}>
                  {value>0?"+":""}{value.toFixed(dec)}{unit}
                </p>
                <p style={{ fontSize:9, color:T.dim, margin:0 }}>
                  {value<-0.001?"better than CPS":value>0.001?"worse than CPS":"≈ same as CPS"}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tech mix chart */}
      {chartData.length > 0 && (
        <div style={{ ...CARD_STYLE, padding:20, marginBottom:16 }}>
          <p style={{ fontSize:10, fontWeight:700, letterSpacing:"0.14em", textTransform:"uppercase", color:T.dim, margin:"0 0 2px" }}>Technology Mix</p>
          <p style={{ fontSize:13, fontWeight:600, color:T.sub, margin:"0 0 16px" }}>{s.unit_short}/yr · 2024–2069</p>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={chartData} margin={{ top:4, right:12, left:0, bottom:4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)"/>
              <XAxis dataKey="year" tick={{ fontSize:10, fill:T.dim }} stroke="rgba(0,0,0,0.1)"/>
              <YAxis tick={{ fontSize:10, fill:T.dim }} stroke="rgba(0,0,0,0.1)"/>
              <Tooltip contentStyle={TT}/>
              <Legend iconType="circle" wrapperStyle={{ fontSize:11, color:T.muted }}/>
              {s.routes.map(r => (
                <Area key={r.id} type="monotone" dataKey={r.id} stackId="1"
                  stroke={r.color} fill={r.color} fillOpacity={0.75} name={r.label}/>
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Triple charts: CO₂ intensity + Total CO₂ + System cost */}
      {chartData.length > 0 && (
        <div style={{ display:"flex", flexWrap:"wrap", gap:14, marginBottom:16 }}>
          {[
            { key:"co2_intensity", label:`CO₂ Intensity`,      sub:`tCO₂/${s.unit_short}`, color: accent },
            { key:"co2_total",     label:"Total CO₂",          sub:"Mt/yr",                 color:"#dc2626" },
            { key:"total_cost",    label:"System Cost",        sub:"Mn USD/yr",             color:"#7c3aed" },
          ].map(ch => (
            <div key={ch.key} style={{ ...CARD_STYLE, flex:"1 1 220px", padding:18, minWidth:0 }}>
              <p style={{ fontSize:12, fontWeight:600, color:T.sub, margin:"0 0 2px" }}>{ch.label}</p>
              <p style={{ fontSize:10, color:T.dim, margin:"0 0 14px" }}>{ch.sub}</p>
              <ResponsiveContainer width="100%" height={150}>
                <LineChart data={chartData} margin={{ top:4, right:12, left:0, bottom:4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)"/>
                  <XAxis dataKey="year" tick={{ fontSize:10, fill:T.dim }} stroke="rgba(0,0,0,0.1)"/>
                  <YAxis tick={{ fontSize:10, fill:T.dim }} stroke="rgba(0,0,0,0.1)" width={42}/>
                  <Tooltip contentStyle={TT}/>
                  <Line type="monotone" dataKey={ch.key} stroke={ch.color} strokeWidth={2} dot={false} name={ch.label}/>
                </LineChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      )}

      {/* Unmet-demand banner */}
      {run && (() => {
        const yearEntries = Object.entries(run).sort(([a],[b])=>parseInt(a)-parseInt(b));
        const maxUnmet = Math.max(...yearEntries.map(([,d])=>Number(d.unmet_demand_mt??0)));
        const unmet2070 = Number(run["2070"]?.unmet_demand_mt ?? 0);

        // 🟠 STRUCTURAL: demand still unmet in 2070 — user must act
        if (unmet2070 >= 1) {
          const isCement = sectorId === "cement";
          const lc3Off   = isCement && lab.toggles["lc3_active"] === false;
          const isNZS    = lab.scenario === "NZS";
          let explanation: React.ReactElement | string;
          if (isCement && lc3Off) {
            explanation = isNZS
              ? <>Without <strong>LC3</strong>, all blended routes share the <strong>fly-ash / slag (SCM) supply</strong>, which collapses in NZS as coal power shuts down. Enable <strong>LC3</strong> (uses clay) or switch to <strong>CPS</strong>.</>
              : <>Without <strong>LC3</strong>, blended cement is capped by SCM supply (≈286 Mt max vs 850 Mt demand by 2070). Enable <strong>LC3</strong> — the only route that can bridge this gap.</>;
          } else {
            explanation = <>The routes you&apos;ve enabled can&apos;t physically supply enough {s.unit_short} in 2070 — ramp rates, capacity caps, or supply constraints are binding. Check enabled routes and limits.</>;
          }
          return (
            <div style={{ background:"#fff3e0", border:"1.5px solid #f57c00", borderRadius:10, padding:"12px 18px", marginBottom:16, display:"flex", alignItems:"flex-start", gap:12 }}>
              <span style={{ fontSize:20, lineHeight:1 }}>⚠️</span>
              <div>
                <p style={{ margin:"0 0 4px", fontWeight:700, fontSize:13, color:"#e65100" }}>Demand cannot be met — constraint binding</p>
                <p style={{ margin:0, fontSize:12, color:"#bf360c" }}>
                  Up to <strong>{Math.round(maxUnmet)} {s.unit_short}</strong> goes unserved in 2070.{" "}{explanation}
                </p>
              </div>
            </div>
          );
        }

        // 🔵 RAMP-LAG: unmet early on but resolves before 2070 — info only, only if significant
        if (maxUnmet >= 2) {
          const lastBigEntry = [...yearEntries].reverse().find(([,d])=>Number(d.unmet_demand_mt??0)>=0.5);
          const lastBigYear  = lastBigEntry ? parseInt(lastBigEntry[0]) : null;
          const resolvedEntry = lastBigYear ? yearEntries.find(([y])=>parseInt(y)>lastBigYear) : null;
          const resolvedYear  = resolvedEntry ? resolvedEntry[0] : null;
          return (
            <div style={{ background:"#e3f2fd", border:"1.5px solid #1976d2", borderRadius:10, padding:"12px 18px", marginBottom:16, display:"flex", alignItems:"flex-start", gap:12 }}>
              <span style={{ fontSize:20, lineHeight:1 }}>ℹ️</span>
              <div>
                <p style={{ margin:"0 0 4px", fontWeight:700, fontSize:13, color:"#1565c0" }}>Early-period ramp-lag — resolves automatically</p>
                <p style={{ margin:0, fontSize:12, color:"#0d47a1" }}>
                  Up to <strong>{Math.round(maxUnmet)} {s.unit_short}</strong> unserved during early transition
                  {resolvedYear ? <> — fully met from <strong>{resolvedYear}</strong> onward</> : " — resolves as new capacity ramps up"}.
                  {" "}This is expected physics; no action needed.
                </p>
              </div>
            </div>
          );
        }

        return null;
      })()}

      {/* Year-by-year table */}
      {run && (
        <div style={{ ...CARD_STYLE, overflow:"hidden", marginBottom:16 }}>
          <div style={{ padding:"11px 20px 9px", borderBottom:`1px solid ${T.border}` }}>
            <p style={{ fontSize:10, fontWeight:700, letterSpacing:"0.14em", textTransform:"uppercase", color:T.dim, margin:0 }}>Year-by-Year Results</p>
          </div>
          <div style={{ overflowX:"auto" }}>
            <table style={{ width:"100%", fontSize:13, borderCollapse:"collapse" }}>
              <thead>
                <tr style={{ borderBottom:`1px solid ${T.border}`, background:"#f7f6f2" }}>
                  {[`Year`,`Production (${s.unit_short})`,`Unmet (${s.unit_short})`,`CO₂ intensity`,`Total CO₂ (Mt)`,`System cost (M$)`,`Investment (M$)`].map((h,i) => (
                    <th key={h} style={{ padding:"8px 16px", fontSize:10, fontWeight:600, textTransform:"uppercase",
                      letterSpacing:"0.1em", color: h.startsWith("Unmet") ? "#e53935" : T.dim, textAlign: i===0?"left":"right" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[2024,2029,2034,2039,2044,2049,2054,2059,2064,2069].map(yr => {
                  const d = run[yr];
                  if (!d) return null;
                  const annualInvest = Object.values(d.investment_by_route??{}).reduce((a,v)=>a+(v as number),0);
                  return (
                    <tr key={yr} style={{ borderBottom:`1px solid rgba(0,0,0,0.04)` }}>
                      <td style={{ padding:"8px 16px", fontWeight:600, color:T.sub }}>{yr}</td>
                      <td style={{ padding:"8px 16px", textAlign:"right", fontVariantNumeric:"tabular-nums", fontSize:12, color:T.muted }}>{fmt1(d.total_production)}</td>
                      <td style={{ padding:"8px 16px", textAlign:"right", fontVariantNumeric:"tabular-nums", fontSize:12, color:Number(d.unmet_demand_mt??0)>0.5?"#e53935":T.muted, fontWeight:Number(d.unmet_demand_mt??0)>0.5?600:400 }}>{Number(d.unmet_demand_mt??0)>0.5?fmt1(Number(d.unmet_demand_mt??0)):"—"}</td>
                      <td style={{ padding:"8px 16px", textAlign:"right", fontVariantNumeric:"tabular-nums", fontSize:12, color:T.muted }}>{fmt2(d.co2_intensity)}</td>
                      <td style={{ padding:"8px 16px", textAlign:"right", fontVariantNumeric:"tabular-nums", fontSize:12, color:T.muted }}>{fmt1(d.co2_total)}</td>
                      <td style={{ padding:"8px 16px", textAlign:"right", fontVariantNumeric:"tabular-nums", fontSize:12, color:T.muted }}>{d.total_cost ? fmt1(d.total_cost) : "—"}</td>
                      <td style={{ padding:"8px 16px", textAlign:"right", fontVariantNumeric:"tabular-nums", fontSize:12, color:T.muted }}>{annualInvest > 0 ? fmt1(annualInvest) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </div>
  );
}
