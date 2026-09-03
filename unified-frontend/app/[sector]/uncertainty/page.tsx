"use client";

import { useParams } from "next/navigation";
import { getSector } from "@/lib/sectors";
import { useState, useMemo, useEffect } from "react";
import { runScenario } from "@/lib/api";
import type { YearlyResult } from "@/lib/api";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from "recharts";
import { AlertTriangle, Info } from "lucide-react";

const T_   = { text:"#23261f", sub:"#474c44", muted:"#7a7e74", dim:"#a8ada5", border:"#e8e5de", card:"#ffffff", bg:"#f7f6f2" };
const CARD: React.CSSProperties = { background:T_.card, border:`1px solid ${T_.border}`, borderRadius:10, boxShadow:"0 1px 3px rgba(0,0,0,0.04)" };
const DIM = { color: T_.dim };
const TT = { background:"#ffffff", border:`1px solid ${T_.border}`, borderRadius:6, fontSize:12, color:T_.text };
const ACCENT: Record<string, string> = { steel: "#2563eb", cement: "#ea580c", aluminium: "#0284c7", textile: "#db2777", fertiliser: "#65a30d" };

const SENSITIVITY: Record<string, { label: string; low: string; high: string; note: string }[]> = {
  steel: [
    { label: "H\u2082 Cost", low: "$8/kg (no H\u2082-DRI)", high: "$0.50/kg (cheap green H\u2082)", note: "H\u2082 cost is the single largest swing factor for H2-DRI-EAF deployment" },
    { label: "Carbon Price", low: "$0/t (no pricing)", high: "$400/tCO\u2082", note: "Carbon price determines when coal routes become uneconomic" },
    { label: "Scrap Availability", low: "20 Mt/yr", high: "50 Mt/yr", note: "Scrap-EAF ceiling depends on national scrap supply" },
    { label: "Electricity Price", low: "$10/MWh (cheap RE)", high: "$80/MWh", note: "Affects all EAF routes" },
    { label: "Coal Price", low: "$50/t", high: "$200/t", note: "Coal-DRI routes are highly sensitive to coal cost" },
    { label: "CAPEX (H\u2082-DRI)", low: "\u221240% learning", high: "+40% no learning", note: "Technology learning rate uncertainty" },
  ],
  cement: [
    { label: "CCUS Cost", low: "$50/tCO\u2082", high: "$200/tCO\u2082", note: "CCUS viability depends on capture cost" },
    { label: "Carbon Price", low: "$0/t", high: "$300/tCO\u2082", note: "Drives LC3 and CCUS adoption" },
    { label: "Blending Limit", low: "50% clinker factor", high: "35% clinker factor", note: "SCM availability and IS standards" },
    { label: "Alternative Fuel", low: "10% thermal share", high: "60% thermal share", note: "Waste-derived fuel availability" },
  ],
  aluminium: [
    { label: "RE Electricity Price", low: "$15/MWh (cheap solar)", high: "$60/MWh", note: "RE-Electrolysis dominates when RE is cheap" },
    { label: "Carbon Price", low: "$0/t", high: "$400/tCO\u2082", note: "Coal-CPP becomes very expensive" },
    { label: "Grid Decarbonisation", low: "0.02 tCO\u2082/kWh (NZS)", high: "0.40 tCO\u2082/kWh (CPS)", note: "Grid-Electrolysis sensitivity" },
  ],
  textile: [
    { label: "Coal Price", low: "$30/t (cheap coal)", high: "$150/t", note: "Coal-Processing route sensitivity" },
    { label: "Biomass Availability", low: "10 Mt/yr", high: "50 Mt/yr", note: "Agri-residue availability" },
    { label: "Carbon Price", low: "$0/t", high: "$200/tCO\u2082", note: "Drives shift from coal to clean routes" },
  ],
  fertiliser: [
    { label: "Green H\u2082 Cost", low: "$0.50/kg", high: "$5/kg", note: "Green-H2-Urea competitiveness vs NG-SMR" },
    { label: "NG Price", low: "$4/MMBtu", high: "$15/MMBtu", note: "NG-SMR route sensitivity" },
    { label: "Carbon Price", low: "$0/t", high: "$300/tCO\u2082", note: "Coal-Gasification becomes very expensive" },
  ],
};

export default function UncertaintyPage() {
  const params = useParams();
  const sectorId = (typeof params.sector === "string" ? params.sector : "steel");
  const s = getSector(sectorId);
  const accent = ACCENT[sectorId] ?? "#60a5fa";
  const dims = SENSITIVITY[sectorId] ?? SENSITIVITY.steel;
  const [activeDim, setActiveDim] = useState(0);
  const [cpsResult, setCpsResult] = useState<Record<number, YearlyResult> | null>(null);
  const [nzsResult, setNzsResult] = useState<Record<number, YearlyResult> | null>(null);

  useEffect(() => {
    Promise.all([runScenario(s, "CPS"), runScenario(s, "NZS")]).then(([c, n]) => {
      if (c.yearly_results) setCpsResult(c.yearly_results as Record<number, YearlyResult>);
      if (n.yearly_results) setNzsResult(n.yearly_results as Record<number, YearlyResult>);
    });
  }, [s]);

  const chartData = useMemo(() => {
    if (!cpsResult) return [];
    return [2024, 2030, 2035, 2040, 2050, 2060, 2070].map(yr => ({
      year: yr,
      cps: cpsResult[yr]?.co2_intensity ?? null,
      nzs: nzsResult?.[yr]?.co2_intensity ?? null,
    }));
  }, [cpsResult, nzsResult]);

  return (
    <div>
      <div className="space-y-4">
        {/* Header */}
        <div style={{ borderBottom:`1px solid ${T_.border}`, paddingBottom:18, marginBottom:6 }}>
          <h1 style={{ fontSize:24, fontWeight:700, color:T_.text, margin:"0 0 4px", letterSpacing:"-0.01em" }}>Uncertainty</h1>
          <p style={{ fontSize:13, color:T_.muted, margin:0 }}>Sensitivity analysis — what matters most for {s.label}</p>
        </div>
        <div style={{ ...CARD, padding: "16px 20px" }}>
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="h-4 w-4" style={{ color: "#d97706" }} />
            <p className="text-[10px] font-semibold tracking-widest uppercase" style={DIM}>Uncertainty &amp; Sensitivity</p>
          </div>
          <p className="text-sm" style={{ color:T_.muted }}>
            What happens if key assumptions change? Select a sensitivity dimension to understand which factors matter most for {s.label}.
          </p>
        </div>

        <div style={CARD} className="overflow-hidden">
          <div className="px-5 py-3" style={{ borderBottom:`1px solid ${T_.border}` }}>
            <p className="text-[10px] font-semibold tracking-widest uppercase" style={DIM}>Sensitivity Dimensions</p>
          </div>
          <div className="p-4" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {dims.map((d, i) => (
              <button key={i} onClick={() => setActiveDim(i)}
                style={{
                  padding: "10px 14px", borderRadius: 8, fontSize: 12, cursor: "pointer",
                  transition: "all 150ms", textAlign: "left", flex: "1 1 200px", maxWidth: 300,
                  ...(activeDim === i
                    ? { background: accent + "14", color: accent, border: "1px solid " + accent + "55" }
                    : { background: "transparent", color: T_.muted, border: `1px solid ${T_.border}` })
                }}>
                <p className="font-semibold">{d.label}</p>
                <p className="text-[10px] mt-1 opacity-70">{d.low} \u2192 {d.high}</p>
              </button>
            ))}
          </div>
        </div>

        <div style={CARD} className="p-5">
          <p className="text-sm font-semibold mb-1" style={{ color:T_.sub }}>{dims[activeDim].label}</p>
          <p className="text-xs mb-4" style={DIM}>{dims[activeDim].note}</p>
          <div style={{ display: "flex", gap: 16 }}>
            <div className="flex-1 p-3 rounded-lg" style={{ background:T_.bg, border:`1px solid ${T_.border}` }}>
              <p className="text-[9px] font-bold uppercase tracking-wider" style={DIM}>Low case</p>
              <p className="text-sm font-semibold mt-1" style={{ color:T_.text }}>{dims[activeDim].low}</p>
            </div>
            <div className="flex-1 p-3 rounded-lg" style={{ background:T_.bg, border:`1px solid ${T_.border}` }}>
              <p className="text-[9px] font-bold uppercase tracking-wider" style={DIM}>High case</p>
              <p className="text-sm font-semibold mt-1" style={{ color:T_.text }}>{dims[activeDim].high}</p>
            </div>
          </div>
        </div>

        {chartData.length > 0 && (
          <div className="p-5" style={CARD}>
            <p className="text-[10px] font-semibold tracking-widest uppercase mb-1" style={DIM}>CO\u2082 Intensity Envelope</p>
            <p className="text-sm font-semibold mb-4" style={{ color:T_.sub }}>CPS vs NZS &middot; {s.unit_short}</p>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={chartData} margin={{ top:4, right:12, left:0, bottom:4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
                <XAxis dataKey="year" tick={{ fontSize:11, fill:T_.dim }} stroke="rgba(0,0,0,0.1)" />
                <YAxis tick={{ fontSize:11, fill:T_.dim }} stroke="rgba(0,0,0,0.1)" />
                <Tooltip contentStyle={TT} />
                <Legend iconType="circle" wrapperStyle={{ fontSize:11 }} />
                <Area type="monotone" dataKey="nzs" stroke="#16a34a" fill="#16a34a" fillOpacity={0.08} strokeWidth={2} name="NZS" />
                <Area type="monotone" dataKey="cps" stroke="#ea580c" fill="#ea580c" fillOpacity={0.08} strokeWidth={2} name="CPS" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="flex items-start gap-2 text-xs rounded-lg px-4 py-3" style={{ ...CARD, color:T_.muted }}>
          <Info className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" style={{ color:T_.dim }} />
          <span>Sensitivity analysis shows how outputs change under different assumptions. Results are LP-optimised minimum-cost pathways \u2014 not probabilistic forecasts.</span>
        </div>
      </div>
    </div>
  );
}

