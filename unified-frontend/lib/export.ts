/**
 * CSV export utilities for Pathway and Lab results.
 */

import type { YearlyResult } from "./api";

function esc(v: string | number): string {
  const s = String(v);
  return s.includes(",") || s.includes('"') || s.includes("\n")
    ? `"${s.replace(/"/g, '""')}"` : s;
}

function download(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

/** Export yearly results as CSV */
export function exportYearlyCSV(
  yearly: Record<number, YearlyResult>,
  routeIds: string[],
  filename: string,
  meta: Record<string, string> = {},
) {
  const years = Object.keys(yearly).map(Number).sort((a, b) => a - b);
  const rows: string[] = [];

  // Meta header
  if (Object.keys(meta).length) {
    rows.push("# Metadata");
    for (const [k, v] of Object.entries(meta)) rows.push(`# ${k}: ${v}`);
    rows.push("");
  }

  // Column headers
  const headers = [
    "year", "total_production_mt", "co2_intensity_tco2_t",
    "co2_total_mt", "total_cost_musd",
    ...routeIds.map((id) => `route_${id.replace(/[^a-zA-Z0-9]/g, "_")}_mt`),
  ];
  rows.push(headers.map(esc).join(","));

  // Data rows
  for (const yr of years) {
    const d = yearly[yr];
    if (!d) continue;
    const routeVals = routeIds.map((id) =>
      esc((d.production_by_route?.[id] ?? 0).toFixed(3))
    );
    rows.push([
      esc(yr),
      esc(d.total_production.toFixed(3)),
      esc(d.co2_intensity.toFixed(4)),
      esc(d.co2_total.toFixed(3)),
      esc((d.total_cost ?? 0).toFixed(1)),
      ...routeVals,
    ].join(","));
  }

  download(filename, rows.join("\n"));
}

/** Export demand trajectory comparison as CSV */
export function exportDemandCSV(
  trajectories: { key: string; label: string; anchors: Record<string, number> }[],
  years: number[],
  sectorLabel: string,
) {
  function lerp(anchors: Record<string, number>, year: number): number {
    const ks = Object.keys(anchors).map(Number).sort((a, b) => a - b);
    if (year <= ks[0]) return anchors[ks[0]];
    if (year >= ks[ks.length - 1]) return anchors[ks[ks.length - 1]];
    for (let i = 0; i < ks.length - 1; i++) {
      const lo = ks[i], hi = ks[i + 1];
      if (lo <= year && year <= hi) {
        const f = (year - lo) / (hi - lo);
        return anchors[lo] + f * (anchors[hi] - anchors[lo]);
      }
    }
    return anchors[ks[ks.length - 1]];
  }

  const headers = ["year", ...trajectories.map((t) => esc(t.label))];
  const rows: string[] = [
    `# ${sectorLabel} Demand Trajectories (Mt)`,
    headers.join(","),
  ];
  for (const yr of years) {
    const vals = trajectories.map((t) => lerp(t.anchors, yr).toFixed(2));
    rows.push([esc(yr), ...vals].join(","));
  }
  download(`${sectorLabel.toLowerCase()}_demand_trajectories.csv`, rows.join("\n"));
}
