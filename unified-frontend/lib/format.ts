/** Shared number / label formatters */

export function fmt1(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return "—";
  return n.toFixed(1);
}

export function fmt2(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return "—";
  return n.toFixed(2);
}

export function fmtInt(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return "—";
  return Math.round(n).toLocaleString("en-IN");
}

export function fmtPct(n: number | null | undefined, decimals = 1): string {
  if (n == null || isNaN(n)) return "—";
  return `${n.toFixed(decimals)}%`;
}

export function fmtDelta(n: number, decimals = 1): string {
  if (n > 0) return `+${n.toFixed(decimals)}%`;
  if (n < 0) return `${n.toFixed(decimals)}%`;
  return "0.0%";
}

/** Compact: 1 234.5 → "1.2k", 1234567 → "1.2M" */
export function fmtCompact(n: number): string {
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
  return n.toFixed(1);
}

/** Employment given in thousands of jobs → "2.5M" above 1000K, else "450K" */
export function fmtJobsK(jobsK: number | null | undefined): string {
  if (jobsK == null || isNaN(jobsK)) return "—";
  if (jobsK >= 1000) return `${(jobsK / 1000).toFixed(1)}M`;
  return `${Math.round(jobsK).toLocaleString("en-IN")}K`;
}
