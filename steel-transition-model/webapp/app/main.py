"""
India Steel Transition Lab — FastAPI application.

Endpoints wrap the EXISTING research engine (`steel_model`) and the recorded
research outputs. No scientific logic is reimplemented here; no arbitrary
Python execution is exposed; config paths are whitelisted server-side.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import MODEL_VERSION
from .data_store import (
    FROZEN_BASELINE_OBJECTIVE,
    get_parameter,
    get_source,
    list_recorded_run_dirs,
    list_run_files,
    load_benchmark,
    load_diagnostics,
    load_parameters,
    load_run_config_snapshot,
    load_run_manifest,
    load_run_results,
    load_sources,
    load_uncertainty_metrics,
    load_uncertainty_scenarios,
    resolve_run_dir,
    uncertainty_dimension_definitions,
)
from .run_manager import _map_solver_status, manager
from .frozen_store import (
    load_frozen_registry,
    load_health_detail,
    load_hydrogen,
    load_route_completeness,
    load_route_economics,
    load_scrap,
)
from .schemas import (
    BenchmarkOut,
    CompletenessRow,
    CompareMetric,
    CompareOut,
    CompareRequest,
    CompareTechnology,
    DiagnosticsOut,
    FrozenRegistryOut,
    HealthDetailOut,
    HealthOut,
    HydrogenOut,
    ParameterOut,
    RouteEconomicsRow,
    RunCreate,
    RunFileOut,
    RunResultOut,
    RunStatusOut,
    ScenarioDetail,
    ScenarioSummary,
    ScrapOut,
    SourceOut,
    UncertaintyStudyOut,
)
from steel_model.uncertainty.pathway import classify_conclusion

from .scenarios import ScenarioValidationError, get_scenario, list_scenarios

from contextlib import asynccontextmanager
import asyncio as _asyncio


@asynccontextmanager
async def _lifespan(application: "FastAPI"):  # noqa: F821
    """Pre-warm canonical CPS + NZS + control runs in background threads.

    Triggered once at server startup.  By the time a real user hits /api/run
    the results are already cached, so they get an instant response instead
    of waiting 60-120 s for the solver.
    """
    import threading as _t

    def _warm(scenario: str) -> None:
        import logging as _lg
        _lg.getLogger("steel_lab.api").info("Pre-warming scenario: %s", scenario)
        try:
            _sync_run(scenario, {})
            _lg.getLogger("steel_lab.api").info("Pre-warm complete: %s", scenario)
        except Exception as exc:  # noqa: BLE001
            _lg.getLogger("steel_lab.api").warning("Pre-warm failed (%s): %s", scenario, exc)

    # Fire off all three in parallel daemon threads so startup doesn't block.
    for sc in ("cps", "nzs", "control"):
        _t.Thread(target=_warm, args=(sc,), daemon=True, name=f"prewarm-{sc}").start()

    yield  # server is live


app = FastAPI(
    title="India Steel Transition Lab API",
    version=MODEL_VERSION,
    description=(
        "Research-grade REST/JSON interface to the India Steel Transition Model. "
        "The API wraps the existing `steel_model` engine; it contains no scientific "
        "logic of its own."
    ),
    lifespan=_lifespan,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("steel_lab.api")

# CORS — dev frontend (Next.js). Same-origin proxying is the production path.
# NOTE: allow_credentials=True with allow_origins=["*"] is invalid per CORS spec.
# Frontend does not send credentials, so False is correct here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)




# ---------------------------------------------------------------------------
# Health / status
# ---------------------------------------------------------------------------
@app.get("/api/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(
        status="ok",
        model_version=MODEL_VERSION,
        baseline_objective=FROZEN_BASELINE_OBJECTIVE,
        data_store_ok=bool(list_recorded_run_dirs()),
        engine_importable=True,
    )

# Alias used by the unified-frontend health-check (GET /health → same response)
@app.get("/health")
def health_alias() -> Dict[str, Any]:
    return {
        "status": "ok",
        "sector": "steel",
        "model_version": MODEL_VERSION,
    }


@app.get("/api/status")
def status() -> Dict[str, Any]:
    """Model status for the landing page (no scientific claims added)."""
    runs = list_recorded_run_dirs()
    latest = None
    if runs:
        latest_dir = max(runs, key=lambda p: p.name)
        manifest = load_run_manifest(latest_dir)
        latest = {
            "run_id": latest_dir.name,
            "scenario": manifest.get("scenario") if manifest else None,
            "solver_status": manifest.get("solver_status") if manifest else None,
            "objective": manifest.get("objective") if manifest else None,
            "timestamp": manifest.get("timestamp") if manifest else None,
        }
    return {
        "model_version": MODEL_VERSION,
        "baseline_objective": FROZEN_BASELINE_OBJECTIVE,
        "data_completeness": {
            "existing_route_capacity": "UNRESOLVED",
            "m1": "DEFERRED",
            "scrap_intensity": "PROJECT_PROPOSAL",   # overridden: 1.08 t/t (IEA/IMC-2021)
            "coking_coal_intensity": "PROJECT_PROPOSAL",  # overridden: 0.89 t/t (IEA/WorldSteel)
            "route_transition_interpretability": False,
        },
        "latest_run": latest,
        "recorded_run_count": len(runs),
        "methodology_strip": [
            "Demand",
            "Technology",
            "Resources",
            "Optimization",
            "Uncertainty",
            "Benchmark",
            "Explainability",
        ],
    }


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
@app.get("/api/scenarios", response_model=List[ScenarioSummary])
def scenarios() -> List[ScenarioSummary]:
    return list_scenarios()


@app.get("/api/scenarios/{scenario_id}", response_model=ScenarioDetail)
def scenario_detail(scenario_id: str) -> ScenarioDetail:
    s = get_scenario(scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"Unknown scenario '{scenario_id}'.")
    return s


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------
def _job_to_status(job: Dict[str, Any]) -> RunStatusOut:
    # Canonical runs pre-registered in jobs.json carry recorded=True so that the
    # frontend's pickRunForScenario helper can match them by scenario_id.  Live
    # web runs never set this field and correctly default to recorded=False.
    return RunStatusOut(
        run_id=job["run_id"],
        scenario_id=job["scenario_id"],
        status=job["status"],
        created_at=job["created_at"],
        started_at=job.get("started_at"),
        finished_at=job.get("finished_at"),
        error=job.get("error"),
        objective=job.get("objective"),
        recorded=bool(job.get("recorded", False)),
    )


@app.get("/api/runs", response_model=List[RunStatusOut])
def list_runs() -> List[RunStatusOut]:
    """Recorded runs from the results store + live web runs.

    Jobs from jobs.json take precedence (they carry the correct scenario_id
    mapping).  Recorded-only runs (no jobs.json entry) are appended afterwards.
    Deduplication by run_id ensures each run appears exactly once.
    """
    seen: Dict[str, RunStatusOut] = {}

    # 1. Jobs layer first — carries canonical scenario_id (control/cps/nzs).
    for job in manager.list_jobs():
        entry = _job_to_status(job)
        seen[entry.run_id] = entry

    # 2. Recorded runs from results/ — only add if not already covered by jobs.
    for d in list_recorded_run_dirs():
        if d.name in seen:
            continue  # deduplicate: job entry already present
        manifest = load_run_manifest(d)
        if manifest is None:
            continue
        seen[d.name] = RunStatusOut(
            run_id=d.name,
            scenario_id=str(manifest.get("scenario", "")),
            status=_map_solver_status(str(manifest.get("solver_status", ""))),
            created_at=str(manifest.get("timestamp", "")),
            objective=manifest.get("objective"),
            recorded=True,
        )

    out = list(seen.values())
    out.sort(key=lambda r: r.created_at, reverse=True)
    return out


@app.post("/api/runs", response_model=RunStatusOut, status_code=202)
def create_run(body: RunCreate) -> RunStatusOut:
    """Validate + queue a run. Returns QUEUED; frontend polls GET /api/runs/{id}."""
    try:
        run_id = manager.create_job(body.scenario_id, body.overrides, body.uncertainty_params)
    except ScenarioValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    logger.info("POST /api/runs -> %s (scenario=%s)", run_id, body.scenario_id)
    return _job_to_status(manager.get_job(run_id))  # type: ignore[arg-type]


@app.get("/api/runs/{run_id}", response_model=RunStatusOut)
def run_status(run_id: str) -> RunStatusOut:
    job = manager.get_job(run_id)
    if job is not None:
        return _job_to_status(job)
    d = resolve_run_dir(run_id)
    if d is not None:
        manifest = load_run_manifest(d) or {}
        return RunStatusOut(
            run_id=run_id,
            scenario_id=str(manifest.get("scenario", "")),
            status=_map_solver_status(str(manifest.get("solver_status", ""))),
            created_at=str(manifest.get("timestamp", "")),
            objective=manifest.get("objective"),
            recorded=True,
        )
    raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")


def _require_run_dir(run_id: str) -> Path:
    d = resolve_run_dir(run_id)
    if d is not None:
        return d
    job = manager.get_job(run_id)
    if job is not None and job.get("results_dir"):
        d = Path(job["results_dir"])
        if d.exists():
            return d
    raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")


@app.get("/api/runs/{run_id}/results", response_model=RunResultOut)
def run_results(run_id: str) -> RunResultOut:
    d = _require_run_dir(run_id)
    data = load_run_results(d)
    if data is None:
        raise HTTPException(status_code=404, detail="Run has no results.json (may have failed).")
    return RunResultOut(**data)


@app.get("/api/runs/{run_id}/diagnostics", response_model=DiagnosticsOut)
def run_diagnostics(run_id: str) -> DiagnosticsOut:
    d = _require_run_dir(run_id)
    return load_diagnostics(run_dir=d)


@app.get("/api/runs/{run_id}/benchmark", response_model=BenchmarkOut)
def run_benchmark(run_id: str) -> BenchmarkOut:
    return load_benchmark()


@app.get("/api/runs/{run_id}/uncertainty", response_model=UncertaintyStudyOut)
def run_uncertainty(run_id: str) -> UncertaintyStudyOut:
    return _uncertainty_study()


@app.get("/api/runs/{run_id}/provenance")
def run_provenance(run_id: str) -> Dict[str, Any]:
    d = _require_run_dir(run_id)
    manifest = load_run_manifest(d) or {}
    snapshot = load_run_config_snapshot(d) or {}
    return {
        "run_id": run_id,
        "config_path": manifest.get("config_path"),
        "config_hash": manifest.get("config_hash"),
        "data_hash": manifest.get("data_hash"),
        "parameter_registry_version": manifest.get("parameter_registry_version"),
        "enabled_modules": manifest.get("enabled_modules", []),
        "mode": manifest.get("mode"),
        "scenario": manifest.get("scenario"),
        "solver": manifest.get("solver"),
        "snapshot_keys": sorted(snapshot.keys()),
    }


@app.get("/api/runs/{run_id}/files", response_model=List[RunFileOut])
def run_files(run_id: str) -> List[RunFileOut]:
    d = _require_run_dir(run_id)
    return [RunFileOut(**f) for f in list_run_files(d)]


@app.get("/api/runs/{run_id}/download/{file_path:path}")
def download_file(run_id: str, file_path: str) -> FileResponse:
    """Download a recorded artefact (manifest, results.json/csv, plots, diagnostics)."""
    d = _require_run_dir(run_id)
    base = d.resolve()
    target = (d / file_path).resolve()
    # Containment: the resolved path must live inside the run directory.
    # A string-prefix test is insufficient (sibling run ids are prefixes of
    # each other), so use a strict relative_to check.
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=404, detail="File not found.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(target, filename=os.path.basename(target))





# ---------------------------------------------------------------------------
# Benchmark / uncertainty (recorded studies)
# ---------------------------------------------------------------------------
def _uncertainty_study() -> UncertaintyStudyOut:
    metrics = load_uncertainty_metrics()
    if metrics is None:
        raise HTTPException(status_code=404, detail="No recorded uncertainty study found.")
    raw_metrics = metrics.get("metrics", {})
    # Derive the per-technology conclusion classification using the ENGINE's
    # own documented function (reuse, not new science). The recorded stats do
    # not carry the classification field; without this the robustness table
    # would misreport every technology as UNRESOLVED.
    stats = dict(raw_metrics.get("technology_stats", {}))
    for tech, stat in stats.items():
        stat = dict(stat)
        try:
            stat["classification"] = classify_conclusion(stat)
        except Exception:  # noqa: BLE001 — keep UNRESOLVED on malformed records
            stat["classification"] = "UNRESOLVED"
        stats[tech] = stat
    raw_metrics = dict(raw_metrics)
    raw_metrics["technology_stats"] = stats
    return UncertaintyStudyOut(
        metrics=raw_metrics,
        answers=metrics.get("answers", {}),
        scenarios=load_uncertainty_scenarios(),
        source="recorded",
    )


@app.get("/api/uncertainty", response_model=UncertaintyStudyOut)
def uncertainty_study() -> UncertaintyStudyOut:
    return _uncertainty_study()


@app.get("/api/uncertainty/dimensions")
def uncertainty_dimensions() -> Dict[str, Any]:
    return uncertainty_dimension_definitions()


@app.get("/api/benchmark", response_model=BenchmarkOut)
def benchmark() -> BenchmarkOut:
    return load_benchmark()


# ---------------------------------------------------------------------------
# Parameters / sources
# ---------------------------------------------------------------------------
@app.get("/api/parameters", response_model=List[ParameterOut])
def parameters() -> List[ParameterOut]:
    return load_parameters()


@app.get("/api/parameters/{parameter_id}", response_model=ParameterOut)
def parameter_detail(parameter_id: str) -> ParameterOut:
    p = get_parameter(parameter_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Parameter '{parameter_id}' not found.")
    return p


@app.get("/api/sources", response_model=List[SourceOut])
def sources() -> List[SourceOut]:
    return load_sources()


@app.get("/api/sources/{source_id}", response_model=SourceOut)
def source_detail(source_id: str) -> SourceOut:
    s = get_source(source_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found.")
    return s


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
@app.post("/api/compare", response_model=CompareOut)
def compare(body: CompareRequest) -> CompareOut:
    a_dir = _require_run_dir(body.run_id_a)
    b_dir = _require_run_dir(body.run_id_b)
    a = load_run_results(a_dir)
    b = load_run_results(b_dir)
    if a is None or b is None:
        raise HTTPException(status_code=404, detail="One of the runs has no results.")

    def _yearly(data: Dict[str, Any], key: str, year: int) -> Optional[float]:
        for yr in data.get("yearly_results", []):
            if yr.get("year") == year:
                v = yr.get(key)
                return v if v is not None else None
        return None

    def _share(data: Dict[str, Any], tech: str, year: int) -> Optional[float]:
        for yr in data.get("yearly_results", []):
            if yr.get("year") == year:
                return yr.get("technology_shares", {}).get(tech)
        return None

    techs = ["BF-BOF", "Coal-DRI-EAF", "Coal-DRI-IF", "NG-DRI-EAF", "H2-DRI-EAF", "Scrap-EAF"]

    metrics = [
        CompareMetric(metric="objective", a=a.get("objective"), b=b.get("objective"), unit="M USD"),
        CompareMetric(metric="H2 demand (2050)", a=_yearly(a, "H2", 2050), b=_yearly(b, "H2", 2050), unit="Mt"),
        CompareMetric(metric="Electricity (2050)", a=_yearly(a, "electricity", 2050), b=_yearly(b, "electricity", 2050), unit="TWh"),
        CompareMetric(metric="CO2 (2050)", a=_yearly(a, "CO2", 2050), b=_yearly(b, "CO2", 2050), unit="Mt"),
        CompareMetric(metric="Investment (2050)", a=_yearly(a, "investment", 2050), b=_yearly(b, "investment", 2050), unit="M USD"),
        CompareMetric(metric="Scrap use (2050)", a=_yearly(a, "scrap", 2050), b=_yearly(b, "scrap", 2050), unit="Mt"),
    ]

    tech_changes = []
    for t in techs:
        a50, b50 = _share(a, t, 2050), _share(b, t, 2050)
        a70, b70 = _share(a, t, 2070), _share(b, t, 2070)
        if a50 is None and b50 is None:
            continue
        direction = ""
        if a50 is not None and b50 is not None:
            direction = "grows in B" if b50 > a50 else ("shrinks in B" if b50 < a50 else "unchanged")
        tech_changes.append(
            CompareTechnology(
                technology=t,
                share_2050_a=a50,
                share_2050_b=b50,
                share_2070_a=a70,
                share_2070_b=b70,
                change_direction=direction,
            )
        )

    notes = [
        "Comparison is descriptive only; it does not attribute causality.",
        "Shares are model outputs (fraction of tested-scenario results, not probabilities).",
    ]

    return CompareOut(
        run_a=run_status(body.run_id_a),
        run_b=run_status(body.run_id_b),
        metrics=metrics,
        technology_changes=tech_changes,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Frozen registries (read-only; single source of truth is the CSV/YAML files)
# ---------------------------------------------------------------------------
@app.get("/api/routes", response_model=List[CompletenessRow])
def routes() -> List[CompletenessRow]:
    """Route-level economic completeness from the frozen Phase 25 matrix."""
    return load_route_completeness()


@app.get("/api/route-economics", response_model=List[RouteEconomicsRow])
def route_economics() -> List[RouteEconomicsRow]:
    """Route economics matrix rows (CAPEX/FOM/VOM/intensities) from the frozen registry."""
    return load_route_economics()


@app.get("/api/scrap", response_model=ScrapOut)
def scrap() -> ScrapOut:
    """Scrap availability series + evidence (historical official, policy scenario, candidate bounds)."""
    return load_scrap()


@app.get("/api/hydrogen", response_model=HydrogenOut)
def hydrogen() -> HydrogenOut:
    """Hydrogen-DRI economics evidence (global crosschecks, India pilot, policy status)."""
    return load_hydrogen()


@app.get("/api/health/detail", response_model=HealthDetailOut)
def health_detail() -> HealthDetailOut:
    """Model-health transparency payload (tests, baseline, hash, completeness)."""
    return load_health_detail()


@app.get("/api/frozen-registry", response_model=FrozenRegistryOut)
def frozen_registry() -> FrozenRegistryOut:
    """One-shot bundle of all frozen-registry data for the frontend."""
    return load_frozen_registry()


# ---------------------------------------------------------------------------
# Demand trajectories (Step 27: model-fitted vs NITI Vol.4)
# ---------------------------------------------------------------------------
@app.get("/api/demand-trajectories")
def demand_trajectories() -> Dict[str, Any]:
    """
    Returns two demand trajectories for India crude steel (2024–2070):

    1. ``niti``: NITI Aayog Vol.4 published anchors (144→624→821 Mt), piecewise-linear.
    2. ``model_fitted``: Logistic S-curve fitted to historical India production data
       (WorldSteel/JPC 1990–2025). Produces a more conservative ~669 Mt by 2070.

    Also returns the historical production series and population data for the frontend.
    """
    from steel_model.data.demand_forecast import trajectory_summary
    return trajectory_summary()


# ---------------------------------------------------------------------------
# Unified-frontend compatibility shims
# Expose /api/run and /api/lab/run in the same contract as the v2 sector
# backends so the Lab page works identically for Steel.
# ---------------------------------------------------------------------------

import threading as _threading
import json as _json
import hashlib as _hashlib
import time as _time

# ---------------------------------------------------------------------------
# Result cache — keyed by (scenario_id, sorted-overrides-hash).
# Canonical runs (no overrides) are permanent; Lab runs are LRU-capped at 32.
# ---------------------------------------------------------------------------
_cache_lock = _threading.Lock()
_results_cache: Dict[str, Any] = {}          # key → result dict
_cache_order: list = []                      # LRU tracking for Lab entries
_CACHE_MAX_LAB = 32

# In-flight deduplication: if a solve for key K is running, other callers
# wait on the same Event instead of spawning a second solve.
_inflight: Dict[str, _threading.Event] = {}


def _cache_key(scenario_id: str, overrides: dict) -> str:
    canonical = _json.dumps(overrides, sort_keys=True, separators=(",", ":"))
    h = _hashlib.md5(canonical.encode(), usedforsecurity=False).hexdigest()[:8]
    return f"{scenario_id}:{h}"


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    with _cache_lock:
        return _results_cache.get(key)


def _cache_put(key: str, result: Dict[str, Any], is_canonical: bool) -> None:
    with _cache_lock:
        if not is_canonical:
            # Evict oldest Lab entry if at cap
            lab_keys = [k for k in _cache_order if k not in _canonical_keys]
            while len(lab_keys) >= _CACHE_MAX_LAB:
                evict = lab_keys.pop(0)
                _results_cache.pop(evict, None)
            if key in _cache_order:
                _cache_order.remove(key)
            _cache_order.append(key)
        _results_cache[key] = result


# Canonical scenario keys (never evicted)
_canonical_keys: set = set()


def _sync_run(scenario_id: str, overrides: dict) -> Dict[str, Any]:
    """Create a job, block until complete, return transformed results.

    Optimisations applied:
    1. In-memory cache — canonical (no overrides) runs are permanent; Lab
       runs are LRU-capped at 32 entries. Cache hit returns in <1 ms.
    2. In-flight deduplication — if two callers request the same key while
       a solve is in progress, only one thread runs the solver; the second
       waits on a threading.Event and gets the cached result.
    3. No more "solver busy" rejections — concurrent requests for *different*
       scenarios are still serialized by the job manager, but via the event
       mechanism the second caller waits up to 240 s rather than being dropped.
    """
    import time

    is_canonical = not overrides and scenario_id in ("cps", "nzs", "control")
    key = _cache_key(scenario_id, overrides)
    if is_canonical:
        _canonical_keys.add(key)

    # ── Cache hit ──────────────────────────────────────────────────────────
    cached = _cache_get(key)
    if cached is not None:
        return cached

    # ── In-flight deduplication ────────────────────────────────────────────
    with _cache_lock:
        if key in _inflight:
            event = _inflight[key]
        else:
            event = _threading.Event()
            _inflight[key] = event
            event = None  # this thread is the runner

    if event is not None:
        # Another thread is solving — wait for it (up to 240 s)
        event.wait(timeout=240.0)
        return _cache_get(key) or {"status": "error", "message": "Solver timed out waiting for in-flight run."}

    # ── This thread runs the solver ────────────────────────────────────────
    try:
        try:
            run_id = manager.create_job(scenario_id, overrides, {})
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

        deadline = time.monotonic() + 240.0  # 4 min ceiling
        job = None
        while time.monotonic() < deadline:
            job = manager.get_job(run_id)
            if job is None:
                break
            st = job.get("status", "")
            if st in ("OPTIMAL", "FEASIBLE", "INFEASIBLE", "FAILED"):
                break
            time.sleep(0.4)

        # Resolve results dir from job record (absolute path, always set on success)
        d = None
        if job and job.get("results_dir"):
            from pathlib import Path as _P
            candidate = _P(job["results_dir"])
            if candidate.exists():
                d = candidate
        if d is None:
            d = resolve_run_dir(run_id)
        if d is None:
            return {"status": "error", "message": "Run did not complete in time or has no results."}

        data = load_run_results(d)
        if data is None:
            return {"status": "error", "message": "results.json missing."}

        # Transform to v2 contract: {str(year): {co2_intensity, co2_total, production_by_route}}
        yearly: Dict[str, Any] = {}
        for yr_obj in data.get("yearly_results", []):
            y = yr_obj.get("year")
            if y is None:
                continue
            prod: Dict[str, float] = yr_obj.get("production", {})
            co2: float = yr_obj.get("CO2", 0.0)
            total_prod = sum(prod.values()) if prod else 1.0
            # investment: results.json stores per-route dict or a scalar
            inv_raw = yr_obj.get("investment", {})
            if isinstance(inv_raw, dict):
                inv_br = {k: round(v, 1) for k, v in inv_raw.items()}
                total_inv = round(sum(inv_raw.values()), 1)
            else:
                inv_br = {"total": round(float(inv_raw), 1)}
                total_inv = round(float(inv_raw), 1)
            yearly[str(y)] = {
                "co2_intensity": round(co2 / total_prod, 4) if total_prod > 0 else 0.0,
                "co2_total": round(co2, 4),
                "production_by_route": {k: round(v, 4) for k, v in prod.items()},
                "total_production": round(total_prod, 4),      # canonical field
                "total_production_mt": round(total_prod, 4),   # alias
                "total_cost": round(float(yr_obj.get("total_cost", 0.0)), 1),
                "investment_by_route": inv_br,
                "total_investment": total_inv,
            }

        result = {
            "status": "optimal",
            "sector": "steel",
            "scenario": scenario_id.upper(),
            "yearly_results": yearly,
        }

        # ── Store in cache + wake waiters ──────────────────────────────────
        _cache_put(key, result, is_canonical)
        return result

    finally:
        # Always signal and remove the in-flight entry so waiters unblock
        with _cache_lock:
            ev = _inflight.pop(key, None)
        if ev is not None:
            ev.set()


@app.post("/api/run")
async def simple_run(payload: dict) -> Dict[str, Any]:
    """Unified-frontend compatibility: synchronous run returning v2-format results."""
    import asyncio, functools
    sc = payload.get("scenario", "CPS").lower()
    if sc not in ("cps", "nzs", "control"):
        sc = "cps"
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(_sync_run, sc, {}))


@app.post("/api/lab/run")
async def lab_run_shim(payload: dict) -> Dict[str, Any]:
    """Unified-frontend compatibility: lab run with parameter overrides."""
    raw_sc = payload.get("scenario", "CPS").upper()
    sc = raw_sc.lower() if raw_sc in ("CPS", "NZS", "CONTROL") else "cps"

    # Build overrides mapped to steel model's ALLOWED_OVERRIDE_KEYS and correct format.
    #
    # CRITICAL: apply_overrides() in run.py uses deep_merge for dict values, so a
    # top-level dict override is deep-merged into the base config's same key. To
    # REPLACE a nested sub-trajectory (e.g. carbon_price.trajectories.CPS), we must
    # use dot-notation override keys — those do direct assignment, not deep-merge.
    overrides: dict = {}

    # carbon_price trajectory: overrides carbon_price.trajectories.CPS directly so
    # the model's trajectories.get("CPS") path finds the user's values.
    cp = payload.get("carbon_price", {})
    if cp:
        traj = {str(int(k)): float(v) for k, v in cp.items() if v is not None}
        if traj:
            overrides["carbon_price.trajectories.CPS"] = traj
            overrides["carbon_price.enabled"] = True

    # green_steel_premium: {enabled, provenance, emission_threshold_tco2_per_t,
    #                        qualifying_routes, premium_usd_per_t: {year: usd}}
    gp = payload.get("green_premium")
    if gp is not None and float(gp) > 0:
        premium = float(gp)
        overrides["green_steel_premium"] = {
            "enabled": True,
            "provenance": "Lab scenario user override",
            "emission_threshold_tco2_per_t": 1.4,
            "qualifying_routes": ["H2-DRI-EAF", "Scrap-EAF"],
            "premium_usd_per_t": {2024: premium * 0.3, 2035: premium * 0.7, 2050: premium, 2070: premium},
        }

    # wacc_premium: {enabled, provenance, premium_by_route: {route: multiplier}}
    # NOTE: model reads 'premium_by_route', not 'by_route'.
    # WACC slider sends absolute WACC % (e.g. 12 for 12%).
    # Steel base WACC = 8% (discount_rate.value=0.08 in config).
    # We compute the CRF ratio (30yr representative lifetime) to get the correct
    # multiplier on annualised CAPEX. Applied only to clean/new tech routes which
    # carry higher financing risk. At user_wacc=8% (base): mult=1.0, no effect.
    _BASE_WACC = 0.08
    _REP_LIFETIME = 30
    def _crf(r: float, n: int = _REP_LIFETIME) -> float:
        if r == 0 or n == 0:
            return 1.0 / max(n, 1)
        return r * (1 + r) ** n / ((1 + r) ** n - 1)

    user_wacc_frac = float(payload.get("wacc", 0)) or float(payload.get("wacc_pct", 0)) / 100
    if abs(user_wacc_frac - _BASE_WACC) > 0.005:
        mult = _crf(user_wacc_frac) / _crf(_BASE_WACC)
        overrides["wacc_premium"] = {
            "enabled": True,
            "provenance": f"Lab WACC override: {user_wacc_frac*100:.1f}% vs base {_BASE_WACC*100:.0f}%",
            "premium_by_route": {
                "H2-DRI-EAF": mult,
                "NG-DRI-EAF": mult,
                "Coal-DRI-EAF": mult,  # new-build DRI routes carry financing risk
            },
        }

    # H2 price trajectory: overrides resource_price_trajectories.hydrogen.trajectories.CPS.anchor_years
    # (config uses "hydrogen" as the key, not "h2"; the model maps it to the H2 resource internally).
    h2_cost = payload.get("h2_cost", {})
    if h2_cost:
        h2_traj = {str(int(k)): float(v) for k, v in h2_cost.items() if v is not None}
        if h2_traj:
            # Dot-notation direct assignment replaces the CPS anchor_years entirely.
            overrides["resource_price_trajectories.hydrogen.trajectories.CPS.anchor_years"] = h2_traj

    # Grid emission intensity: overrides trajectories.CPS.grid_ei_tco2_per_mwh directly.
    # Payload sends grid_ei_2070 in kgCO2/kWh = tCO2/MWh (same numeric value, unit equiv).
    # We build a full trajectory: 2024 base + monotone decline to user's 2070 target.
    grid_ei_2070 = payload.get("grid_ei_2070")
    if grid_ei_2070 is not None:
        ei70 = float(grid_ei_2070)
        # Base 2024 grid EI from config: 0.716 tCO2/MWh (CEA 2022-23). Keep 2024 unchanged.
        overrides["grid_emission_intensity.trajectories.CPS.grid_ei_tco2_per_mwh"] = {
            "2024": 0.716,
            "2030": round(0.716 - (0.716 - ei70) * 0.2, 4),
            "2040": round(0.716 - (0.716 - ei70) * 0.5, 4),
            "2050": round(0.716 - (0.716 - ei70) * 0.8, 4),
            "2070": ei70,
        }
        overrides["grid_emission_intensity.enabled"] = True

    # economics: per-route CAPEX multipliers
    # Read base config to get base CAPEX values, then scale
    capex_by_route = payload.get("capex_by_route", {})
    if capex_by_route:
        import yaml as _yaml
        # Use absolute path — relative path fails when CWD != steel-transition-model/
        _steel_root = Path(__file__).resolve().parents[2]  # steel-transition-model/
        base_path = _steel_root / "configs" / "optimization" / "baseline.yaml"
        try:
            with open(base_path) as _f:
                _base_cfg = _yaml.safe_load(_f)
            _base_econ = _base_cfg.get("economics", {})
            _base_capex = _base_econ.get("capex_annualised_usd_per_t", {})
            for route_id, multiplier in capex_by_route.items():
                if multiplier is not None and float(multiplier) != 1.0 and route_id in _base_capex:
                    scaled = float(_base_capex[route_id]) * float(multiplier)
                    overrides[f"economics.capex_annualised_usd_per_t.{route_id}"] = scaled
        except Exception:
            pass  # silently skip if config not readable

    # Resource price overrides: frontend sends {scrap: 170, iron_ore: 40, ...}
    # as absolute values. Map to dot-notation value overrides.
    # NOTE: h2 is sent as a dict {year: price} — handled separately by H2 trajectory
    # logic below, so skip it here to avoid float(dict) TypeError.
    resource_prices = payload.get("resource_prices", {})
    for res_key, val in resource_prices.items():
        if val is not None and not isinstance(val, dict):
            try:
                overrides[f"resource_prices.{res_key}.value"] = float(val)
            except (TypeError, ValueError):
                pass  # skip malformed values

    # demand_anchors: frontend sends {year: Mt} dict from the selected demand trajectory.
    # We replace cfg["scenarios"] (a list) entirely so apply_overrides replaces rather
    # than deep-merges (lists are never deep-merged by the override system).
    # The schema validator (validate_config_dict) does not touch cfg["scenarios"] directly —
    # it reads specific top-level scalar keys — so this is safe.
    d_anch = payload.get("demand_anchors")
    if d_anch:
        try:
            anch_mt = {int(k): float(v) for k, v in d_anch.items()}
            # Replace scenarios list so model.py line ~370 finds the new anchors
            overrides["scenarios"] = [
                {"name": "CPS", "demand_anchors_mt": anch_mt},
                {"name": "NZS", "demand_anchors_mt": anch_mt},
            ]
        except Exception:
            pass  # malformed anchors — silently skip, model uses base config

    # Feature toggles (boolean overrides)
    for toggle_key in ("use_dynamic_scrap", "use_endogenous_learning", "use_deployment_dynamics"):
        if toggle_key in payload:
            overrides[toggle_key] = bool(payload[toggle_key])
    if "ccus" in payload:
        overrides["ccus"] = {"enabled": bool(payload["ccus"]),
                              "provenance": "Lab scenario user override"}

    import asyncio, functools
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(_sync_run, sc, overrides))
