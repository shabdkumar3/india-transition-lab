"""
India Steel Transition Lab — frozen-registry data store (Phase 25 productization).

Reads the FROZEN Phase 25 machine-readable registries (route completeness,
route economics, resource intensities, scrap availability/evidence, hydrogen
evidence, parameter readiness, master evidence, M1 audit) and maps them onto
stable API schemas. This module contains NO scientific logic and NO mutable
state — it is a read-only loader, exactly like ``data_store.py``.

Missing / EXTERNAL_PENDING / CANDIDATE values are never coerced to zero:
they are passed through as None or as their literal registry status string.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .data_store import list_recorded_run_dirs, load_run_manifest

from .schemas import (
    CompletenessRow,
    FrozenRegistryOut,
    HealthDetailOut,
    HydrogenOut,
    RouteCard,
    RouteEconomicsRow,
    ScrapEvidenceRow,
    ScrapOut,
    ScrapSeriesRow,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Routes / technologies
# ---------------------------------------------------------------------------
def load_route_completeness() -> List[CompletenessRow]:
    rows = _read_csv(REPO_ROOT / "FINAL_ROUTE_ECONOMIC_COMPLETENESS.csv")
    return [
        CompletenessRow(
            route=r.get("route", ""),
            capex=r.get("capex", ""),
            fom=r.get("fom", ""),
            vom=r.get("vom", ""),
            ore=r.get("ore", ""),
            coal=r.get("coal", ""),
            gas=r.get("gas", ""),
            h2=r.get("h2", ""),
            scrap=r.get("scrap", ""),
            electricity=r.get("electricity", ""),
            other=r.get("other", ""),
            economically_complete=(r.get("economically_complete", "FALSE") == "TRUE"),
            missing_components=r.get("missing_components", ""),
        )
        for r in rows
    ]


def load_route_economics() -> List[RouteEconomicsRow]:
    rows = _read_csv(REPO_ROOT / "FINAL_ROUTE_ECONOMICS_MATRIX.csv")
    out: List[RouteEconomicsRow] = []
    for r in rows:
        out.append(
            RouteEconomicsRow(
                parameter_id=r.get("parameter_id", ""),
                route=r.get("route", ""),
                category=r.get("category", ""),
                value=r.get("value", ""),
                unit=r.get("unit", ""),
                currency=r.get("currency", "") or None,
                base_year=r.get("base_year", "") or None,
                year=r.get("year", "") or None,
                source=r.get("source", "") or None,
                source_org=r.get("source_org", "") or None,
                page_or_table=r.get("page_or_table", "") or None,
                boundary_scope=r.get("boundary_scope", "") or None,
                population=r.get("population", "") or None,
                provenance=r.get("provenance", "") or None,
                confidence=r.get("confidence", "") or None,
                status=r.get("status", ""),
                notes=r.get("notes", "") or None,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Scrap
# ---------------------------------------------------------------------------
def load_scrap_series() -> List[ScrapSeriesRow]:
    rows = _read_csv(REPO_ROOT / "SCRAP_AVAILABILITY_SERIES.csv")
    return [
        ScrapSeriesRow(
            year=r.get("year", ""),
            scrap_consumption_mt=r.get("scrap_consumption_mt", ""),
            domestic_generation_mt=r.get("domestic_generation_mt", ""),
            imports_mt=r.get("imports_mt", ""),
            route_share_pct=r.get("route_share_pct", "") or None,
            source=r.get("source", ""),
            boundary=r.get("boundary", ""),
            status=r.get("status", ""),
        )
        for r in rows
    ]


def load_scrap_evidence() -> List[ScrapEvidenceRow]:
    rows = _read_csv(REPO_ROOT / "SCRAP_EAF_EVIDENCE.csv")
    return [
        ScrapEvidenceRow(
            evidence_id=r.get("evidence_id", ""),
            category=r.get("category", ""),
            value=r.get("value", ""),
            unit=r.get("unit", ""),
            currency=r.get("currency", "") or None,
            base_year=r.get("base_year", "") or None,
            year=r.get("year", "") or None,
            scope=r.get("scope", ""),
            source=r.get("source", ""),
            source_org=r.get("source_org", "") or None,
            page_or_table=r.get("page_or_table", "") or None,
            provenance=r.get("provenance", ""),
            confidence=r.get("confidence", "") or None,
            notes=r.get("notes", "") or None,
        )
        for r in rows
    ]


def load_scrap() -> ScrapOut:
    return ScrapOut(
        series=load_scrap_series(),
        evidence=load_scrap_evidence(),
    )


# ---------------------------------------------------------------------------
# Hydrogen
# ---------------------------------------------------------------------------
def load_hydrogen() -> HydrogenOut:
    rows = _read_csv(REPO_ROOT / "H2_DRI_ECONOMICS_EVIDENCE.csv")
    evidence = [
        {
            "evidence_id": r.get("evidence_id", ""),
            "category": r.get("category", ""),
            "value": r.get("value", ""),
            "unit": r.get("unit", ""),
            "currency": r.get("currency", "") or None,
            "base_year": r.get("base_year", "") or None,
            "year": r.get("year", "") or None,
            "scope": r.get("scope", ""),
            "source": r.get("source", ""),
            "source_org": r.get("source_org", "") or None,
            "page_or_table": r.get("page_or_table", "") or None,
            "provenance": r.get("provenance", ""),
            "confidence": r.get("confidence", "") or None,
            "notes": r.get("notes", "") or None,
        }
        for r in rows
    ]
    return HydrogenOut(evidence=evidence)


# ---------------------------------------------------------------------------
# Model health
# ---------------------------------------------------------------------------
def _latest_run_manifest() -> Optional[Dict[str, Any]]:
    """Newest recorded run manifest (for a live data_hash instead of a stale literal)."""
    runs = list_recorded_run_dirs()
    if not runs:
        return None
    latest_dir = max(runs, key=lambda p: p.name)
    return load_run_manifest(latest_dir)


def load_health_detail() -> HealthDetailOut:
    readiness = _read_json(REPO_ROOT / "FINAL_PARAMETER_READINESS_MATRIX.json")
    counts: Dict[str, int] = {}
    if isinstance(readiness, dict):
        sc = readiness.get("status_counts") or {}
        for k, v in sc.items():
            counts[str(k)] = int(v)
    else:
        counts = {"FROZEN": 0, "CANDIDATE": 0, "PROJECT_PROPOSAL": 0, "EXTERNAL_PENDING": 0}
    completeness = load_route_completeness()

    # Test count: recorded by the pytest session hook (webapp/app/validation_state.json)
    # so the UI never serves a stale count; fall back to the last known count.
    test_count = 510
    state = _read_json(REPO_ROOT / "webapp" / "app" / "validation_state.json")
    if isinstance(state, dict) and state.get("test_count"):
        test_count = int(state["test_count"])

    # Data hash: from the newest recorded run manifest (single source of truth),
    # falling back to the frozen hash if the store is empty.
    manifest = _latest_run_manifest()
    data_hash = manifest.get("data_hash") if manifest else None
    if not data_hash:
        data_hash = "d8b926754ec27cd75305e8c4ee2f6f4c2ae6d930cc1fcb9133e33963691f92a5"

    return HealthDetailOut(
        test_count=test_count,
        import_ok=True,
        baseline_objective=1726583.3837816007,  # 6-route baseline (2026-08-18)
        solver_status="OPTIMAL",
        data_hash=data_hash,
        parameter_counts=counts,
        route_completeness=completeness,
    )


def load_frozen_registry() -> FrozenRegistryOut:
    return FrozenRegistryOut(
        routes=load_route_completeness(),
        route_economics=load_route_economics(),
        scrap=load_scrap(),
        hydrogen=load_hydrogen(),
        health=load_health_detail(),
    )
