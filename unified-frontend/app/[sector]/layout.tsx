"use client";

import { useParams, usePathname } from "next/navigation";
import Link from "next/link";
import { getSector, SECTOR_LIST } from "@/lib/sectors";
import {
  TrendingUp, FlaskConical, BarChart3, LayoutDashboard,
  BookOpen, Factory, Building2, Zap, Scissors, Leaf, GitCompare,
  AlertTriangle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface NavItem { href: string; label: string; icon: LucideIcon; absolute?: boolean; }

const PAGE_NAV: { label: string; items: NavItem[] }[] = [
  {
    label: "Results",
    items: [
      { href: "",              label: "Overview",     icon: LayoutDashboard },
      { href: "/demand",       label: "Demand",       icon: BarChart3 },
      { href: "/pathway",      label: "Pathway",      icon: TrendingUp },
      { href: "/technologies", label: "Technologies", icon: Zap },
    ],
  },
  {
    label: "Lab",
    items: [
      { href: "/lab",          label: "Scenario Builder", icon: FlaskConical },
    ],
  },
  {
    label: "Analysis",
    items: [
      { href: "/uncertainty",  label: "Uncertainty",  icon: AlertTriangle },
      { href: "/evidence",     label: "Evidence & Trust", icon: BookOpen },
    ],
  },
  {
    label: "About",
    items: [
      { href: "/methodology", label: "Methodology", icon: BookOpen, absolute: true },
    ],
  },
];

const SECTOR_META: Record<string, { color: string; Icon: React.ElementType }> = {
  steel:      { color: "#2563eb", Icon: Factory },
  cement:     { color: "#ea580c", Icon: Building2 },
  aluminium:  { color: "#0284c7", Icon: Zap },
  textile:    { color: "#db2777", Icon: Scissors },
  fertiliser: { color: "#65a30d", Icon: Leaf },
};

const SECTOR_NAV: { id: string; label: string }[] = [
  { id: "steel",      label: "Steel"      },
  { id: "cement",     label: "Cement"     },
  { id: "aluminium",  label: "Aluminium"  },
  { id: "textile",    label: "Textile"    },
  { id: "fertiliser", label: "Fertiliser" },
];

export default function SectorLayout({ children }: { children: React.ReactNode }) {
  const params   = useParams();
  const pathname = usePathname();
  const sectorId = typeof params.sector === "string" ? params.sector : "steel";
  const sector   = getSector(sectorId);
  const meta     = SECTOR_META[sectorId] ?? { color: "#2563eb", Icon: Factory };
  const accent   = meta.color;

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden", background: "#f7f6f2" }}>

      {/* ══════════ SIDEBAR ══════════ */}
      <aside style={{
        width: 224,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "#ffffff",
        borderRight: "1px solid #e8e5de",
        overflow: "hidden",
      }}>

        {/* Logo */}
        <Link href="/" style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "16px 16px 12px",
          textDecoration: "none",
          flexShrink: 0,
        }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8, flexShrink: 0,
            background: "linear-gradient(135deg, #1e3a5f, #2563eb)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <span style={{ color: "#ffffff", fontWeight: 900, fontSize: 10, letterSpacing: "-0.02em" }}>IN</span>
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#23261f", lineHeight: 1.2 }}>India Transition</div>
            <div style={{ fontSize: 10, color: "#a8ada5", lineHeight: 1.2 }}>Lab · NITI 2026</div>
          </div>
        </Link>

        {/* Scrollable nav area */}
        <div style={{ flex: 1, overflowY: "auto", padding: "4px 8px 8px" }}>

          {/* Sector switcher */}
          <div style={{ marginBottom: 4 }}>
            <div style={{
              padding: "6px 8px 4px",
              fontSize: 10, fontWeight: 600,
              letterSpacing: "0.1em", textTransform: "uppercase",
              color: "#a8ada5",
            }}>
              Sector
            </div>
            {SECTOR_NAV.map(s => {
              const sm = SECTOR_META[s.id] ?? { color: "#2563eb", Icon: Factory };
              const SIcon = sm.Icon;
              const isActive = s.id === sectorId;
              return (
                <Link key={s.id}
                  href={`/${s.id}`}
                  style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "6px 8px",
                    borderRadius: 8,
                    fontSize: 12.5, fontWeight: isActive ? 600 : 500,
                    textDecoration: "none",
                    transition: "all 100ms",
                    marginBottom: 1,
                    color: isActive ? sm.color : "#7a7e74",
                    background: isActive ? sm.color + "12" : "transparent",
                    boxShadow: isActive ? `inset 2px 0 0 ${sm.color}` : "none",
                  }}
                  onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = "rgba(0,0,0,0.04)"; }}
                  onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                >
                  <SIcon style={{ width: 14, height: 14, flexShrink: 0, color: isActive ? sm.color : "#a8ada5" }} />
                  {s.label}
                </Link>
              );
            })}
          </div>

          {/* Divider */}
          <div style={{ height: 1, background: "#e8e5de", margin: "8px 0" }} />

          {/* Page nav groups */}
          {PAGE_NAV.map(group => (
            <div key={group.label} style={{ marginBottom: 4 }}>
              <div style={{
                padding: "6px 8px 4px",
                fontSize: 10, fontWeight: 600,
                letterSpacing: "0.1em", textTransform: "uppercase",
                color: "#a8ada5",
              }}>
                {group.label}
              </div>
              {group.items.map(item => {
                const full     = item.absolute ? item.href : `/${sectorId}${item.href}`;
                const isActive = item.href === "" ? pathname === `/${sectorId}` : pathname.startsWith(full);
                const Icon     = item.icon;
                return (
                  <Link key={item.href} href={full}
                    aria-current={isActive ? "page" : undefined}
                    style={{
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "6px 8px",
                      borderRadius: 8,
                      fontSize: 12.5, fontWeight: isActive ? 600 : 500,
                      textDecoration: "none",
                      transition: "all 100ms",
                      marginBottom: 1,
                      color: isActive ? accent : "#7a7e74",
                      background: isActive ? accent + "12" : "transparent",
                      boxShadow: isActive ? `inset 2px 0 0 ${accent}` : "none",
                    }}
                    onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = "rgba(0,0,0,0.04)"; }}
                    onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                  >
                    <Icon style={{ width: 14, height: 14, flexShrink: 0, color: isActive ? accent : "#a8ada5" }} />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ))}

          {/* Cross-sector link */}
          <div style={{ height: 1, background: "#e8e5de", margin: "8px 0" }} />
          <Link href="/compare"
            style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "6px 8px", borderRadius: 8,
              fontSize: 12.5, fontWeight: 500,
              textDecoration: "none",
              color: "#7a7e74",
              transition: "all 100ms",
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "rgba(0,0,0,0.04)"; (e.currentTarget as HTMLElement).style.color = "#23261f"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "transparent"; (e.currentTarget as HTMLElement).style.color = "#7a7e74"; }}
          >
            <GitCompare style={{ width: 14, height: 14, flexShrink: 0, color: "#a8ada5" }} />
            Compare sectors
          </Link>
        </div>

        {/* Footer chip */}
        <div style={{ borderTop: "1px solid #e8e5de", padding: "10px 12px", flexShrink: 0 }}>
          <div style={{ fontSize: 10, color: "#a8ada5", background: "#f7f6f2", borderRadius: 8, padding: "8px 10px", lineHeight: 1.5 }}>
            <span style={{ fontWeight: 600, color: "#7a7e74" }}>{sector.label}</span>
            <br />{sector.routes.length} routes · HiGHS MILP
          </div>
        </div>
      </aside>

      {/* ══════════ MAIN CONTENT ══════════ */}
      <main style={{ flex: 1, overflowY: "auto", background: "#f7f6f2" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 24px 40px" }}>
          {children}
        </div>
      </main>
    </div>
  );
}
