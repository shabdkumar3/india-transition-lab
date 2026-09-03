"""
India Steel Transition Lab — data store.

Reads the EXISTING research outputs (results/, data/uncertainty,
data/benchmark, data/explainability, data/external) and the frozen
configurations. No scientific logic lives here: it is a read-only loader
that maps recorded artefacts onto the API schemas.

Never shows a missing value as 0 unless zero is genuinely the source/model
value: ``value`` stays None when a parameter is EXTERNAL_PENDING / absent.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from steel_model.uncertainty.pathway import (
    DRI_ALTERNATIVES,
    FLEET_SCENARIOS,
    SCRAP_LEVELS,
)

from .schemas import (
    BenchmarkOut,
    DiagnosticsOut,
    ParameterOut,
    SourceOut,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "results"
DATA_DIR = REPO_ROOT / "data"
CONFIGS_DIR = REPO_ROOT / "configs"

# Status classification from provenance (no scientific interpretation added).
PROVENANCE_STATUS = {
    "V4": "FROZEN",
    "TIMES": "FROZEN",
    "EXTERNAL": "FROZEN",
    "DERIVED": "DERIVED",
    "PROJECT_PROPOSAL": "CONDITIONAL",
    "EXTERNAL_PENDING": "EXTERNAL_PENDING",
    "UNKNOWN": "UNKNOWN",
    "ML_ESTIMATED": "ML_ESTIMATED",
    "FROZEN_EXTERNAL": "FROZEN",
    "FROZEN_DERIVED": "DERIVED",
}


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _load_yaml(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Recorded runs
# ---------------------------------------------------------------------------
def list_recorded_run_dirs() -> List[Path]:
    """Return results/ sub-directories that contain a run_manifest.json."""
    if not RESULTS_DIR.exists():
        return []
    out = []
    for entry in sorted(RESULTS_DIR.iterdir()):
        if entry.is_dir() and (entry / "run_manifest.json").exists():
            out.append(entry)
    return out


def load_run_manifest(run_dir: Path) -> Optional[Dict[str, Any]]:
    return _load_json(run_dir / "run_manifest.json", None)


def load_run_results(run_dir: Path) -> Optional[Dict[str, Any]]:
    return _load_json(run_dir / "results.json", None)


def load_run_config_snapshot(run_dir: Path) -> Optional[Dict[str, Any]]:
    return _load_yaml(run_dir / "config_snapshot.yaml", None)


def resolve_run_dir(run_id: str) -> Optional[Path]:
    """Resolve a run_id to its results directory (recorded or web-run)."""
    candidate = RESULTS_DIR / run_id
    if candidate.is_dir() and (candidate / "run_manifest.json").exists():
        return candidate
    return None


def list_run_files(run_dir: Path) -> List[Dict[str, Any]]:
    files = []
    for f in sorted(run_dir.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(run_dir).as_posix()
        if rel.startswith("logs/"):
            kind = "log"
        elif rel == "run_manifest.json":
            kind = "manifest"
        elif rel == "results.json":
            kind = "results"
        elif rel == "results.csv":
            kind = "csv"
        elif rel == "config_snapshot.yaml":
            kind = "config"
        elif rel.startswith("diagnostics/"):
            kind = "diagnostics"
        elif rel.startswith("plots/"):
            kind = "plots"
        else:
            kind = "other"
        files.append(
            {"name": rel, "path": rel, "kind": kind, "size_bytes": f.stat().st_size}
        )
    return files


# ---------------------------------------------------------------------------
# Benchmark (Vol.4 comparison, Step 14 recorded output)
# ---------------------------------------------------------------------------
def load_benchmark() -> BenchmarkOut:
    data = _load_json(DATA_DIR / "benchmark" / "v4_benchmark.json", {})
    rows = data.get("rows", []) if isinstance(data, dict) else []
    thresholds = data.get("thresholds", {}) if isinstance(data, dict) else {}
    return BenchmarkOut(thresholds=thresholds, rows=rows)


# ---------------------------------------------------------------------------
# Uncertainty (Step 18 recorded study)
# ---------------------------------------------------------------------------
def load_uncertainty_metrics() -> Optional[Dict[str, Any]]:
    return _load_json(DATA_DIR / "uncertainty" / "robustness_metrics.json", None)


def load_uncertainty_scenarios() -> List[Dict[str, Any]]:
    data = _load_json(DATA_DIR / "uncertainty" / "pathway_scenarios.json", {})
    if isinstance(data, dict):
        return list(data.values())
    return []


# ---------------------------------------------------------------------------
# Explainability (recorded Step 15 diagnostics + per-run diagnostics)
# ---------------------------------------------------------------------------
def load_diagnostics(run_dir: Optional[Path] = None) -> DiagnosticsOut:
    """Per-run diagnostics if available, else the recorded Step 15 outputs."""
    if run_dir is not None and (run_dir / "diagnostics").exists():
        base = run_dir / "diagnostics"
        source = "per-run"
    else:
        base = DATA_DIR / "explainability"
        source = "recorded"

    return DiagnosticsOut(
        technology_diagnostics=_load_json(base / "technology_diagnostics.json", []),
        constraint_diagnostics=_load_json(base / "constraint_diagnostics.json", []),
        pathway_events=_load_json(base / "pathway_events.json", []),
        technology_shifts=_load_json(base / "technology_shifts.json", []),
        cost_crossovers=_load_json(base / "cost_crossovers.json", []),
        source=source,
    )


# ---------------------------------------------------------------------------
# Parameters / provenance
# ---------------------------------------------------------------------------
def _normalize_parameter(
    pid: str,
    name: str,
    value: Optional[float],
    unit: Optional[str],
    provenance: str,
    source: Optional[str],
    year: Optional[int],
    technology: Optional[str],
    impact: Optional[str],
    detail: Dict[str, Any],
) -> ParameterOut:
    status = PROVENANCE_STATUS.get(str(provenance).upper(), "UNKNOWN")
    if str(provenance).upper() == "EXTERNAL_PENDING":
        status = "EXTERNAL_PENDING"
    return ParameterOut(
        parameter_id=pid,
        name=name,
        value=value,
        value_min=detail.get("value_min"),
        value_max=detail.get("value_max"),
        unit=unit,
        provenance=str(provenance),
        source=source,
        source_id=detail.get("source_id"),
        year=year,
        technology=technology,
        status=status,
        impact=impact,
        detail=detail,
    )


def load_parameters() -> List[ParameterOut]:
    params: List[ParameterOut] = []

    # 1. External parameter freeze (Step 6) — frozen EXTERNAL values.
    freeze = _load_yaml(DATA_DIR / "external" / "external_parameter_freeze.yaml", {})
    for p in freeze.get("parameters", []):
        params.append(
            _normalize_parameter(
                pid=p.get("parameter_id", "unknown"),
                name=p.get("parameter", p.get("parameter_id", "")),
                value=p.get("value"),
                unit=p.get("unit"),
                provenance=p.get("provenance", "EXTERNAL_PENDING"),
                source=p.get("source_title") or p.get("source"),
                year=p.get("year"),
                technology=p.get("technology"),
                impact=p.get("scope"),
                detail=p,
            )
        )

    # 2. External parameters register (50 parameters with bounds).
    ext = _load_yaml(DATA_DIR / "external" / "parameters" / "external_parameters.yaml", {})
    for p in ext.get("parameters", []):
        params.append(
            _normalize_parameter(
                pid=p.get("parameter_id", "unknown"),
                name=p.get("parameter", p.get("parameter_id", "")),
                value=p.get("value_central"),
                unit=p.get("unit"),
                provenance=p.get("provenance", "EXTERNAL_PENDING"),
                source=p.get("source_id"),
                year=p.get("year"),
                technology=p.get("technology"),
                impact=p.get("definition"),
                detail=p,
            )
        )

    # 3. Conventional uncertainty registry.
    reg = _load_yaml(CONFIGS_DIR / "optimization" / "uncertainty_registry.yaml", {})
    for p in reg.get("parameters", []):
        params.append(
            _normalize_parameter(
                pid=p.get("parameter_id", "unknown"),
                name=p.get("parameter_id", ""),
                value=p.get("base_value"),
                unit=p.get("unit"),
                provenance=p.get("provenance", "UNKNOWN"),
                source=p.get("source"),
                year=None,
                technology=None,
                impact=p.get("uncertainty_basis"),
                detail=p,
            )
        )

    # 4. Pathway uncertainty registry (three unresolved dimensions).
    preg = _load_yaml(CONFIGS_DIR / "optimization" / "pathway_uncertainty_registry.yaml", {})
    for p in preg.get("parameters", []):
        detail = dict(p)
        detail["lower_bound"] = p.get("lower_bound")
        detail["upper_bound"] = p.get("upper_bound")
        params.append(
            _normalize_parameter(
                pid=p.get("parameter_id", "unknown"),
                name=p.get("parameter_id", ""),
                value=p.get("base_value"),  # None -> never displayed as 0
                unit=p.get("unit"),
                provenance=p.get("provenance", "EXTERNAL_PENDING"),
                source=p.get("source"),
                year=None,
                technology=None,
                impact=p.get("uncertainty_basis"),
                detail=detail,
            )
        )

    # Deduplicate by parameter_id, keeping the first (most authoritative).
    seen = {}
    for p in params:
        if p.parameter_id not in seen:
            seen[p.parameter_id] = p
    return list(seen.values())


_parameters_cache: Optional[List[ParameterOut]] = None


def _cached_parameters() -> List[ParameterOut]:
    global _parameters_cache
    if _parameters_cache is None:
        _parameters_cache = load_parameters()
    return _parameters_cache


def get_parameter(parameter_id: str) -> Optional[ParameterOut]:
    for p in _cached_parameters():
        if p.parameter_id == parameter_id:
            return p
    return None


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
def load_sources() -> List[SourceOut]:
    manifest = _load_yaml(DATA_DIR / "external" / "source_manifest.yaml", {})
    sources = manifest.get("sources", []) if isinstance(manifest, dict) else []
    out = []
    for s in sources:
        out.append(
            SourceOut(
                source_id=s.get("source_id", ""),
                title=s.get("title", ""),
                publisher=s.get("publisher", ""),
                year=s.get("year"),
                url=s.get("url"),
                source_level=s.get("source_level"),
                scope=s.get("scope"),
                parameters_extracted=s.get("parameters_extracted", []),
                notes=s.get("notes"),
                filename=s.get("filename"),
            )
        )
    return out


_sources_cache: Optional[List[SourceOut]] = None


def _cached_sources() -> List[SourceOut]:
    global _sources_cache
    if _sources_cache is None:
        _sources_cache = load_sources()
    return _sources_cache


def get_source(source_id: str) -> Optional[SourceOut]:
    for s in _cached_sources():
        if s.source_id == source_id:
            return s
    return None


# ---------------------------------------------------------------------------
# Uncertainty dimension definitions (recorded, source-backed)
# ---------------------------------------------------------------------------
def uncertainty_dimension_definitions() -> Dict[str, Any]:
    return {
        "scrap_levels": SCRAP_LEVELS,
        "dri_alternatives": DRI_ALTERNATIVES,
        "fleet_scenarios": FLEET_SCENARIOS,
    }


# ---------------------------------------------------------------------------
# Baseline invariance reference
# ---------------------------------------------------------------------------
# Updated 2026-08-18: all 6 routes enabled (Coal-DRI-EAF, Coal-DRI-IF, H2-DRI-EAF
# added with PROJECT_PROPOSAL economics from external_parameters.yaml cross-section).
# Existing capacity set from Vol.4 p.43 production data. Non-coking coal intensities
# for Coal-DRI routes derived from Vol.4 Fig 2.8 SEC (1.2 t/t). Static scrap cap
# recalibrated to 36-220 Mt/yr (vs old 30-185 Mt/yr) to cover all-route scrap use.
# Coal-DRI-IF cheapest route ($321/t vs BF-BOF $382/t) — correctly dominates baseline.
# Previous 3-route value: 1,935,207.13 M USD.
FROZEN_BASELINE_OBJECTIVE = 1726583.3837816007
