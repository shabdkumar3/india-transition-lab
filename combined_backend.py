"""
India Transition Lab — Combined Backend
Mounts all 5 sector backends under /steel, /cement, /aluminium, /textile, /fertiliser

For cloud deployment (Render, Railway, Fly.io, etc.):
    uvicorn combined_backend:app --host 0.0.0.0 --port $PORT

Local dev still uses start_all.ps1 (5 separate ports) — this file is only for production.
"""
from __future__ import annotations

import logging
import os
import sys
import importlib
import traceback
from pathlib import Path

# ── Ensure sector packages resolve ───────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent
STEEL_DIR  = ROOT / "steel-transition-model"
SECTOR_DIR = ROOT / "sector-backends"

for p in [str(STEEL_DIR), str(SECTOR_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

logger = logging.getLogger("itl.combined")

# ── Safe import helper ────────────────────────────────────────────────────────

def _import_app(module: str, attr: str = "app") -> tuple:
    """Return (app, error_str | None)."""
    try:
        mod = importlib.import_module(module)
        return getattr(mod, attr), None
    except Exception:
        err = traceback.format_exc()
        logger.error("Failed to import %s:\n%s", module, err)
        return None, err

# ── Import all sector apps ───────────────────────────────────────────────────

steel_app,      steel_err      = _import_app("webapp.app.main")
cement_app,     cement_err     = _import_app("cement_backend_v3")
aluminium_app,  aluminium_err  = _import_app("aluminium_backend_v3")
textile_app,    textile_err    = _import_app("textile_backend_v3")
fertiliser_app, fertiliser_err = _import_app("fertiliser_backend_v3")

# ── Combined FastAPI app ──────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager

@asynccontextmanager
async def _combined_lifespan(application):
    """Startup: log which sectors mounted OK.
    The individual sector apps handle their own pre-warm via their own lifespans
    (those are sub-applications and run their own lifespan when mounted).
    """
    pairs = [
        ("steel",      steel_app,      steel_err),
        ("cement",     cement_app,     cement_err),
        ("aluminium",  aluminium_app,  aluminium_err),
        ("textile",    textile_app,    textile_err),
        ("fertiliser", fertiliser_app, fertiliser_err),
    ]
    for name, a, e in pairs:
        if a:
            logger.info("  /%-12s mounted OK", name)
        else:
            logger.error("  /%-12s FAILED: %s", name, (e or "").splitlines()[-1])
    yield

app = FastAPI(
    title="India Transition Lab — Combined Backend",
    description="All 5 sector backends in one ASGI service (production deployment).",
    version="1.0.0",
    lifespan=_combined_lifespan,
)

# Single CORS gate — sector sub-apps each have their own but the parent's fires first
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Root health ───────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
def health():
    sectors_status = {
        "steel":      "ok" if steel_app      else "error",
        "cement":     "ok" if cement_app     else "error",
        "aluminium":  "ok" if aluminium_app  else "error",
        "textile":    "ok" if textile_app    else "error",
        "fertiliser": "ok" if fertiliser_app else "error",
    }
    errors = {k: v for k, v in {
        "steel": steel_err, "cement": cement_err,
        "aluminium": aluminium_err, "textile": textile_err,
        "fertiliser": fertiliser_err,
    }.items() if v}
    ok = all(v == "ok" for v in sectors_status.values())
    return {
        "status": "ok" if ok else "degraded",
        "sectors": sectors_status,
        **({"import_errors": {k: v.splitlines()[-1] for k, v in errors.items()}} if errors else {}),
    }

# ── Mount sector apps ─────────────────────────────────────────────────────────
# next.config.ts rewrites:
#   /api/steel/*  → BACKEND/steel/*
# This app receives /steel/api/lab, strips /steel, sub-app sees /api/lab — correct.

if steel_app:
    app.mount("/steel",      steel_app)
if cement_app:
    app.mount("/cement",     cement_app)
if aluminium_app:
    app.mount("/aluminium",  aluminium_app)
if textile_app:
    app.mount("/textile",    textile_app)
if fertiliser_app:
    app.mount("/fertiliser", fertiliser_app)

# (startup logging moved to _combined_lifespan above)

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("combined_backend:app", host="0.0.0.0", port=port, reload=False,
                log_level="info")
