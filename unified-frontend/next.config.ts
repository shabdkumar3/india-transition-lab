import type { NextConfig } from "next";

// ── Backend routing ───────────────────────────────────────────────────────────
// Local dev (start_all.ps1): leave BACKEND_URL unset → 5 separate ports, unchanged.
// Production (Render/Railway): set BACKEND_URL to combined backend URL, e.g.
//   https://india-transition-lab.onrender.com
//
// The rewrite rules differ because:
//   Local:  /api/steel/* → http://localhost:8000/*           (strips /api/steel prefix)
//   Prod:   /api/steel/* → BACKEND_URL/steel/*               (keeps /steel for sub-app routing)

const BACKEND = process.env.BACKEND_URL?.replace(/\/$/, ""); // trim trailing slash

const nextConfig: NextConfig = {
  async rewrites() {
    if (BACKEND) {
      // ── Production: single combined backend ──────────────────────────────
      // Combined backend mounts steel at /steel, so /api/steel/api/lab
      // becomes BACKEND/steel/api/lab → steel sub-app receives /api/lab ✓
      return [
        { source: "/api/steel/:path*",      destination: `${BACKEND}/steel/:path*` },
        { source: "/api/cement/:path*",     destination: `${BACKEND}/cement/:path*` },
        { source: "/api/aluminium/:path*",  destination: `${BACKEND}/aluminium/:path*` },
        { source: "/api/textile/:path*",    destination: `${BACKEND}/textile/:path*` },
        { source: "/api/fertiliser/:path*", destination: `${BACKEND}/fertiliser/:path*` },
      ];
    }

    // ── Local development: 5 separate backends on dedicated ports ────────────
    // Proxy all sector API calls through Next.js (avoids CORS in browser)
    return [
      { source: "/api/steel/:path*",      destination: "http://localhost:8000/:path*" },
      { source: "/api/cement/:path*",     destination: "http://localhost:8001/:path*" },
      { source: "/api/aluminium/:path*",  destination: "http://localhost:8002/:path*" },
      { source: "/api/textile/:path*",    destination: "http://localhost:8003/:path*" },
      { source: "/api/fertiliser/:path*", destination: "http://localhost:8004/:path*" },
    ];
  },
};

export default nextConfig;
