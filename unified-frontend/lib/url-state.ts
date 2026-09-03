/**
 * Encode / decode Lab scenario parameters in the URL hash.
 * Lets users share a specific Lab configuration via a link.
 *
 * Format: #lab=<base64url(JSON)>
 */

export interface LabParams {
  cp30: number; cp50: number; cp70: number;
  h2_30: number; h2_50: number; h2_70: number;
  capex: number; gp: number; wacc: number; ei: number;
  dm: string; sc: string;
}

function toB64(obj: unknown): string {
  try {
    return btoa(JSON.stringify(obj))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  } catch { return ""; }
}

function fromB64(s: string): unknown {
  try {
    const pad = s.length % 4 === 0 ? s : s + "=".repeat(4 - s.length % 4);
    return JSON.parse(atob(pad.replace(/-/g, "+").replace(/_/g, "/")));
  } catch { return null; }
}

export function encodeLabToHash(params: LabParams): string {
  return "#lab=" + toB64(params);
}

export function decodeLabFromHash(hash: string): Partial<LabParams> | null {
  const m = hash.match(/#lab=([A-Za-z0-9\-_]+)/);
  if (!m) return null;
  const obj = fromB64(m[1]);
  if (!obj || typeof obj !== "object") return null;
  return obj as Partial<LabParams>;
}

export function copyLabLink(params: LabParams): void {
  const url = window.location.origin + window.location.pathname + encodeLabToHash(params);
  navigator.clipboard?.writeText(url).catch(() => {
    // fallback: prompt
    window.prompt("Copy this Lab link:", url);
  });
}
