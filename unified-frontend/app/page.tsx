"use client";

import Link from "next/link";
import { SECTOR_LIST } from "@/lib/sectors";
import type { SectorConfig } from "@/lib/sectors";
import {
  Layers, ArrowRight, TrendingDown,
  Factory, Building2, Zap, Scissors, Leaf, GitCompare, BookOpen,
} from "lucide-react";
import { fmtJobsK } from "@/lib/format";

const SECTOR_ICONS: Record<string, React.ElementType> = {
  steel: Factory, cement: Building2, aluminium: Zap,
  textile: Scissors, fertiliser: Leaf,
};

/** Return the base-year demand, trying 2024 first then 2025 then earliest key. */
function baseYearDemand(demand: Record<number, number>): number {
  return demand[2024] ?? demand[2025] ?? (Object.values(demand)[0] ?? 0);
}

/** Derive home-page sector data from Vol.4 source data — no hardcoded scientific outputs. */
function deriveSectorData(s: SectorConfig) {
  const co2_cps_2070 = s.vol4.co2_total.cps[2070] ?? 0;
  const co2_nzs_2070 = s.vol4.co2_total.nzs[2070] ?? 0;
  const d2024 = baseYearDemand(s.vol4.demand);
  const avgInt = s.routes.reduce((sum, r) => sum + r.co2_intensity, 0) / Math.max(s.routes.length, 1);
  const co2_2024 = Math.round(d2024 * avgInt);
  const intensity = s.routes[0] ? `${s.routes[0].co2_intensity} tCO₂/t` : "—";
  const routes = s.routes.length;
  const pct = co2_cps_2070 > 0 ? Math.round((1 - co2_nzs_2070 / co2_cps_2070) * 100) : 0;
  return { co2_2024, co2_cps: co2_cps_2070, co2_nzs: co2_nzs_2070, intensity, routes, inv: 0, jobs_k: 0, pct };
}

const SD: Record<string, ReturnType<typeof deriveSectorData>> = {};
for (const s of SECTOR_LIST) { SD[s.id] = deriveSectorData(s); }

// Light-mode sector accents
const ACCENT: Record<string, string> = {
  steel: "#2563eb", cement: "#ea580c", aluminium: "#0284c7",
  textile: "#db2777", fertiliser: "#65a30d",
};

// Subtle tinted card backgrounds
const CARD_BG: Record<string, string> = {
  steel:      "#f5f8ff",
  cement:     "#fff7f3",
  aluminium:  "#f0f8ff",
  textile:    "#fff0f6",
  fertiliser: "#f4fbec",
};

const totalCO2 = Object.values(SD).reduce((a, b) => a + b.co2_2024, 0);
const totalNZS = Object.values(SD).reduce((a, b) => a + b.co2_nzs, 0);
const totalNZSpct = Math.round((1 - totalNZS / totalCO2) * 100);
const totalInv = Object.values(SD).reduce((a, b) => a + b.inv, 0);
const barMax = Math.max(...Object.values(SD).map(x => Math.max(x.co2_2024, x.co2_cps)));

// ── Shared tokens ──────────────────────────────────────────────────────────
const T = {
  text:    "#23261f",
  sub:     "#474c44",
  muted:   "#7a7e74",
  dim:     "#a8ada5",
  border:  "#e8e5de",
  surface: "rgba(0,0,0,0.025)",
  card:    "#ffffff",
};

export default function Home() {
  return (
    <div className="min-h-screen" style={{ background: "#f7f6f2" }}>

      {/* ── TOP NAV ── */}
      <header style={{
        background: "rgba(255,255,255,0.97)",
        borderBottom: `1px solid ${T.border}`,
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        position: "sticky", top: 0, zIndex: 50,
      }}>
        <div style={{ maxWidth: 1400, margin: "0 auto", padding: "0 24px" }}>
          <div style={{ display: "flex", alignItems: "center", height: 48, gap: 16 }}>

            {/* Brand */}
            <Link href="/" style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0, textDecoration: "none" }}>
              <div style={{
                width: 28, height: 28, borderRadius: 6, flexShrink: 0,
                background: "linear-gradient(135deg, #1d4f8a, #2563eb)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <span style={{ color: "#fff", fontWeight: 900, fontSize: 10 }}>IN</span>
              </div>
              <div style={{ lineHeight: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: T.text, letterSpacing: "-0.01em" }}>
                  India Transition Lab
                </div>
                <div style={{ fontSize: 9, fontWeight: 600, color: T.dim, letterSpacing: "0.12em", textTransform: "uppercase", marginTop: 2 }}>
                  NITI Vol.4 · 2026
                </div>
              </div>
            </Link>

            <div style={{ width: 1, height: 20, background: T.border, flexShrink: 0 }} />

            {/* Sector links */}
            <div style={{ display: "flex", alignItems: "center", gap: 2, flex: 1, overflowX: "auto" }}>
              {SECTOR_LIST.map(s => {
                const SIcon = SECTOR_ICONS[s.id] ?? Factory;
                const ac = ACCENT[s.id];
                return (
                  <Link key={s.id} href={`/${s.id}`} style={{
                    display: "flex", alignItems: "center", gap: 6,
                    padding: "5px 10px", borderRadius: 6,
                    fontSize: 12, fontWeight: 500,
                    color: T.muted, textDecoration: "none",
                    transition: "color 150ms, background 150ms",
                    whiteSpace: "nowrap", flexShrink: 0,
                  }}
                  onMouseEnter={e => { const el = e.currentTarget as HTMLElement; el.style.color = ac; el.style.background = ac + "12"; }}
                  onMouseLeave={e => { const el = e.currentTarget as HTMLElement; el.style.color = T.muted; el.style.background = "transparent"; }}>
                    <SIcon style={{ width: 13, height: 13 }} />
                    {s.label}
                  </Link>
                );
              })}
            </div>

            {/* Utility */}
            <div style={{ display: "flex", alignItems: "center", gap: 2, flexShrink: 0 }}>
              {[
                { href: "/compare", icon: GitCompare, label: "Compare" },
                { href: "/methodology", icon: BookOpen, label: "Docs" },
              ].map(({ href, icon: Icon, label }) => (
                <Link key={href} href={href} style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "5px 10px", borderRadius: 6,
                  fontSize: 12, fontWeight: 500, color: T.dim,
                  textDecoration: "none", transition: "color 150ms",
                }}
                onMouseEnter={e => (e.currentTarget as HTMLElement).style.color = T.muted}
                onMouseLeave={e => (e.currentTarget as HTMLElement).style.color = T.dim}>
                  <Icon style={{ width: 13, height: 13 }} /> {label}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </header>

      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "48px 24px 56px" }}>

        {/* ── HERO ── */}
        <div style={{ marginBottom: 48 }}>
          <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.18em", textTransform: "uppercase", color: T.dim, marginBottom: 20 }}>
            LP-optimised industrial decarbonisation · 5 sectors · 2024–2070
          </p>

          {/* Headline */}
          <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginBottom: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 88, fontWeight: 900, lineHeight: 1, color: "#23261f", letterSpacing: "-0.03em" }}>
              {Math.round(totalCO2)}
            </span>
            <span style={{ fontSize: 22, fontWeight: 300, color: T.muted, whiteSpace: "nowrap" }}>Mt CO₂ / yr</span>
          </div>
          <p style={{ fontSize: 18, fontWeight: 600, color: T.sub, marginBottom: 12 }}>
            India&apos;s industrial emissions today (2024)
          </p>
          <p style={{ fontSize: 13, color: T.muted, lineHeight: 1.7, maxWidth: 560, marginBottom: 32 }}>
            Capacity-expansion LP model (HiGHS 1.7.1) calibrated to NITI Aayog Sectoral Insights: Industry (Vol. 4), Scenarios Towards Viksit Bharat and Net Zero, February 2026.
            Steel · Cement · Aluminium · Textile · Fertiliser — 26 routes, CPS and NZS scenarios.
          </p>

          {/* KPI trio */}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {[
              { label: "NZS Reduction",  value: `−${totalNZSpct}%`, sub: "CO₂ by 2070",          color: "#16a34a", bg: "#f0fdf4", border: "rgba(22,163,74,0.25)"  },
              { label: "NZS CO₂ 2070",  value: `${Math.round(totalNZS)}`, unit: "Mt/yr", sub: "across all sectors", color: T.text, bg: T.card, border: T.border },
              { label: "NZS Investment", value: `$${totalInv}B`,    sub: "additional 2024–50",    color: "#b45309", bg: "#fffbeb", border: "rgba(180,83,9,0.22)"  },
            ].map(k => (
              <div key={k.label} style={{ background: k.bg, border: `1px solid ${k.border}`, borderRadius: 12, padding: "18px 22px", minWidth: 150, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: T.dim, margin: "0 0 12px" }}>
                  {k.label}
                </p>
                <p style={{ fontSize: 34, fontWeight: 900, lineHeight: 1, color: k.color, margin: 0 }}>
                  {k.value}
                </p>
                {"unit" in k && <p style={{ fontSize: 12, fontWeight: 500, color: T.muted, margin: "4px 0 0" }}>{(k as {unit: string}).unit}</p>}
                <p style={{ fontSize: 11, color: T.dim, margin: "12px 0 0" }}>{k.sub}</p>
              </div>
            ))}
          </div>
        </div>

        {/* ── SECTOR CARDS ── */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 14, marginBottom: 36 }}>
          {SECTOR_LIST.map(s => {
            const d = SD[s.id];
            const ac = ACCENT[s.id];
            const SIcon = SECTOR_ICONS[s.id] ?? Factory;
            const cardBg = CARD_BG[s.id] ?? "#ffffff";
            return (
              <Link key={s.id} href={`/${s.id}`} style={{
                display: "block", borderRadius: 14, overflow: "hidden",
                background: cardBg,
                border: `1px solid ${T.border}`,
                textDecoration: "none",
                boxShadow: "0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.04)",
                transition: "border-color 200ms, transform 200ms, box-shadow 200ms",
              }}
              onMouseEnter={e => {
                const el = e.currentTarget as HTMLElement;
                el.style.borderColor = ac + "55";
                el.style.transform = "translateY(-2px)";
                el.style.boxShadow = `0 4px 20px ${ac}18, 0 1px 4px rgba(0,0,0,0.06)`;
              }}
              onMouseLeave={e => {
                const el = e.currentTarget as HTMLElement;
                el.style.borderColor = T.border;
                el.style.transform = "";
                el.style.boxShadow = "0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.04)";
              }}>
                {/* Accent top bar */}
                <div style={{ height: 3, background: `linear-gradient(90deg, ${ac}60, ${ac})` }} />
                <div style={{ padding: "18px 20px 20px" }}>

                  {/* Header */}
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 16 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div style={{ width: 34, height: 34, borderRadius: 9, background: ac + "15", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, border: `1px solid ${ac}25` }}>
                        <SIcon style={{ width: 17, height: 17, color: ac }} />
                      </div>
                      <div>
                        <p style={{ fontSize: 15, fontWeight: 800, color: T.text, lineHeight: 1, margin: 0 }}>{s.label}</p>
                        <p style={{ fontSize: 10, color: T.dim, margin: "4px 0 0" }}>{d.routes} routes · {fmtJobsK(d.jobs_k)} jobs</p>
                      </div>
                    </div>
                    <ArrowRight style={{ width: 15, height: 15, color: ac + "80", flexShrink: 0, marginTop: 2 }} />
                  </div>

                  {/* NZS big stat */}
                  <div style={{ marginBottom: 14 }}>
                    <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.13em", textTransform: "uppercase", color: T.dim, margin: "0 0 6px" }}>
                      NZS CO₂ reduction
                    </p>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                      <span style={{ fontSize: 34, fontWeight: 900, color: ac, lineHeight: 1 }}>
                        −{d.pct}%
                      </span>
                      <span style={{ fontSize: 12, color: T.muted }}>by 2070</span>
                    </div>
                  </div>

                  {/* 3-stat mini grid */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6, marginBottom: 14 }}>
                    {[
                      { label: "2024",    val: d.co2_2024, color: T.sub },
                      { label: "CPS '70", val: d.co2_cps,  color: "#dc2626" },
                      { label: "NZS '70", val: d.co2_nzs,  color: "#16a34a" },
                    ].map(k => (
                      <div key={k.label} style={{ background: "rgba(0,0,0,0.03)", borderRadius: 7, padding: "8px 8px", textAlign: "center", border: "1px solid rgba(0,0,0,0.04)" }}>
                        <p style={{ fontSize: 9, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em", color: T.dim, margin: "0 0 5px" }}>{k.label}</p>
                        <p style={{ fontSize: 15, fontWeight: 800, color: k.color, margin: 0 }}>
                          {k.val < 10 ? k.val.toFixed(1) : Math.round(k.val)}
                        </p>
                        <p style={{ fontSize: 9, color: T.dim, margin: "2px 0 0" }}>Mt/yr</p>
                      </div>
                    ))}
                  </div>

                  {/* Progress bar */}
                  <div style={{ height: 4, borderRadius: 2, background: "rgba(0,0,0,0.07)" }}>
                    <div style={{ height: "100%", borderRadius: 2, width: `${d.pct}%`, background: `linear-gradient(90deg, ${ac}50, ${ac})` }} />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
                    <span style={{ fontSize: 10, color: T.dim }}>Today: {d.intensity}</span>
                    <span style={{ fontSize: 10, color: T.dim }}>Invest: ${d.inv}B</span>
                  </div>
                </div>
              </Link>
            );
          })}

          {/* Cross-sector card */}
          <Link href="/compare" style={{
            display: "block", borderRadius: 14, overflow: "hidden",
            background: T.card,
            border: `1px dashed ${T.border}`,
            textDecoration: "none",
            boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
            transition: "background 150ms, border-color 150ms",
          }}
          onMouseEnter={e => { const el = e.currentTarget as HTMLElement; el.style.background = "#f7f6f2"; el.style.borderColor = "#c8c4bc"; }}
          onMouseLeave={e => { const el = e.currentTarget as HTMLElement; el.style.background = T.card; el.style.borderColor = T.border; }}>
            <div style={{ height: 3, background: "linear-gradient(90deg, #2563eb, #ea580c, #0284c7, #db2777, #65a30d)" }} />
            <div style={{ padding: "18px 20px 20px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 220, gap: 14, textAlign: "center" }}>
              <div style={{ width: 44, height: 44, borderRadius: 12, background: "rgba(0,0,0,0.04)", border: `1px solid ${T.border}`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Layers style={{ width: 22, height: 22, color: T.muted }} />
              </div>
              <div>
                <p style={{ fontSize: 15, fontWeight: 800, color: T.text, margin: 0 }}>Cross-Sector</p>
                <p style={{ fontSize: 12, color: T.muted, marginTop: 6, lineHeight: 1.6 }}>
                  Compare all 5 sectors<br />on one chart
                </p>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600, color: T.muted }}>
                View comparison <ArrowRight style={{ width: 14, height: 14 }} />
              </div>
            </div>
          </Link>
        </div>

        {/* ── EMISSIONS COMPARISON TABLE ── */}
        <div style={{ borderRadius: 14, overflow: "hidden", background: T.card, border: `1px solid ${T.border}`, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
          <div style={{ padding: "16px 24px", borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
            <div>
              <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.16em", textTransform: "uppercase", color: T.dim, margin: 0 }}>
                Sectoral CO₂ — Mt / yr
              </p>
              <p style={{ fontSize: 12, color: T.muted, margin: "4px 0 0" }}>
                2024 baseline vs CPS and NZS projections (2070)
              </p>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              {[
                { color: "#a8ada5", label: "2024" },
                { color: "#dc2626", label: "CPS 2070" },
                { color: "#16a34a", label: "NZS 2070" },
              ].map(l => (
                <span key={l.label} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: T.muted }}>
                  <span style={{ width: 14, height: 8, borderRadius: 2, display: "inline-block", background: l.color }} />
                  {l.label}
                </span>
              ))}
            </div>
          </div>

          {SECTOR_LIST.map((s, i) => {
            const d = SD[s.id];
            const ac = ACCENT[s.id];
            const SIcon = SECTOR_ICONS[s.id] ?? Factory;
            return (
              <Link key={s.id} href={`/${s.id}`} style={{
                display: "flex", alignItems: "center", gap: 20,
                padding: "14px 24px",
                borderBottom: i < SECTOR_LIST.length - 1 ? `1px solid rgba(0,0,0,0.04)` : "none",
                textDecoration: "none",
                transition: "background 150ms",
              }}
              onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "rgba(0,0,0,0.02)"}
              onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = "transparent"}>
                <div style={{ width: 120, flexShrink: 0, display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ width: 28, height: 28, borderRadius: 7, background: ac + "15", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <SIcon style={{ width: 14, height: 14, color: ac }} />
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 700, color: T.sub }}>{s.label}</span>
                </div>
                <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 5 }}>
                  {[
                    { val: d.co2_2024, color: "#a8ada5" },
                    { val: d.co2_cps,  color: "#f87171" },
                    { val: d.co2_nzs,  color: "#4ade80" },
                  ].map((row, j) => (
                    <div key={j} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div style={{ flex: 1, height: 6, borderRadius: 3, overflow: "hidden", background: "rgba(0,0,0,0.05)" }}>
                        <div style={{ height: "100%", borderRadius: 3, width: `${(row.val / barMax) * 100}%`, background: row.color }} />
                      </div>
                      <span style={{ width: 36, fontSize: 11, fontWeight: 700, color: T.muted, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {row.val < 10 ? row.val.toFixed(1) : Math.round(row.val)}
                      </span>
                    </div>
                  ))}
                </div>
                <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 6 }}>
                  <TrendingDown style={{ width: 14, height: 14, color: "#16a34a" }} />
                  <span style={{ fontSize: 14, fontWeight: 800, color: "#16a34a" }}>
                    −{d.pct}%
                  </span>
                </div>
              </Link>
            );
          })}

          <div style={{ padding: "10px 24px", borderTop: `1px solid rgba(0,0,0,0.04)` }}>
            <p style={{ fontSize: 10, color: T.dim, margin: 0 }}>
              Source: NITI Aayog Sectoral Insights: Industry (Vol. 4), February 2026 · LP model HiGHS 1.7.1
            </p>
          </div>
        </div>

        {/* Footer */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 28, paddingTop: 20, borderTop: `1px solid rgba(0,0,0,0.06)`, flexWrap: "wrap", gap: 8 }}>
          <span style={{ fontSize: 11, color: T.dim }}>NITI Aayog Sectoral Insights: Industry (Vol. 4) · Scenarios Towards Viksit Bharat and Net Zero · February 2026</span>
          <span style={{ fontSize: 11, color: T.dim }}>HiGHS 1.7.1 · scipy.optimize.milp · Next.js 16</span>
        </div>
      </div>
    </div>
  );
}
