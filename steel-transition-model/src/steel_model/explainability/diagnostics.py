"""
Pathway diagnostics orchestrator (Step 15).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import pandas as pd

from steel_model.optimization.model import BaselineInputs, BaselineMILPResult
from steel_model.explainability.schemas import (
    TechnologyYearRecord,
    TechnologyShift,
    ConstraintDiagnostic,
    CostCrossover,
    PathwayEvent,
    BenchmarkDiagnostic,
    ScrapWaypointDiagnostic,
)
from steel_model.explainability.costs import is_economics_complete, decompose_route_cost
from steel_model.explainability.constraints import run_constraint_diagnostics
from steel_model.explainability.crossover import run_crossover_analysis
from steel_model.explainability.shifts import detect_technology_shifts


def generate_technology_diagnostics(
    inputs: BaselineInputs,
    res: BaselineMILPResult,
) -> List[TechnologyYearRecord]:
    """Generate structured diagnostic records for all technologies and years."""
    records: List[TechnologyYearRecord] = []
    years = sorted(list(inputs.years))

    for r in inputs.all_routes:
        # Determine status
        active = r in inputs.routes
        complete = is_economics_complete(inputs, r)

        if r == "Scrap-EAF":
            completeness = "INCOMPLETE"
            status = "DATA_LIMITED"
        elif r in ("BF-BOF", "NG-DRI-EAF"):
            completeness = "COMPLETE" if complete else "INCOMPLETE"
            # Route capacites and vintages are missing, making the physical constraints limited
            status = "DATA_LIMITED"
        elif r in ("H2-DRI-EAF", "Coal-DRI-EAF", "Coal-DRI-IF"):
            completeness = "INCOMPLETE"
            # Now actively modelled with Vol.4-derived existing capacity and
            # PROJECT_PROPOSAL economics — DATA_LIMITED (not NOT_BENCHMARK_READY).
            # Economics are not FROZEN but the route participates in the optimiser.
            status = "DATA_LIMITED"
        else:
            completeness = "INCOMPLETE"
            status = "NOT_BENCHMARK_READY"

        for t in years:
            prod = res.production_mt(r).get(t, 0.0) if active else 0.0
            share = res.production_share(r).get(t, 0.0) if active else 0.0
            cap = res.cap_mt.get(r, {}).get(t, 0.0) if active else 0.0
            ncap = res.ncap_mt.get(r, {}).get(t, 0.0) if active else 0.0
            ret = res.ret_mt.get(r, {}).get(t, 0.0) if active else 0.0

            # Decompose costs
            cost_decomp = decompose_route_cost(inputs, r, t, prod, cap)

            # Learning properties
            learning_enabled = inputs.endogenous_learning_enabled and r in inputs.learning_rates
            learning_effect = None
            learning_prov = None
            if learning_enabled and res.learning_history is not None:
                # Exponent or factor
                hist = res.learning_history.get(r, {})
                learning_effect = hist.get(t)
                learning_prov = inputs.learning_provenance_by_route.get(r)

            records.append(
                TechnologyYearRecord(
                    year=t,
                    technology=r,
                    production=float(prod) if active else None,
                    share=float(share) if active else None,
                    installed_capacity=float(cap) if active else None,
                    new_capacity=float(ncap) if active else None,
                    retirement=float(ret) if active else None,
                    capex_contribution=cost_decomp["capex_contribution"],
                    fom_contribution=cost_decomp["fom_contribution"],
                    vom_contribution=cost_decomp["vom_contribution"],
                    fuel_cost=cost_decomp["fuel_cost"],
                    resource_cost=cost_decomp["resource_cost"],
                    electricity_cost=cost_decomp["electricity_cost"],
                    emission_cost=cost_decomp["emission_cost"],
                    effective_cost=cost_decomp["effective_cost"],
                    unit_effective_cost=cost_decomp["unit_effective_cost"],
                    capacity_used=float(prod) if active else None,
                    capacity_available=float(inputs.availability.get(r, 0.90) * cap) if active else None,
                    deployment_used=float(ncap) if active else None,
                    deployment_available=inputs.ncap_limits_mt.get(r) if active else None,
                    scrap_used=float(prod * inputs.resource_intensity.get((r, "scrap"), 0.0)) if (active and inputs.resource_intensity.get((r, "scrap")) is not None) else None,
                    scrap_available=res.scrap_accounting.usable_scrap_mt.get(t) if (inputs.dynamic_scrap_enabled and res.scrap_accounting is not None and r == "Scrap-EAF") else None,
                    learning_enabled=learning_enabled,
                    learning_effect=learning_effect,
                    learning_provenance=learning_prov,
                    provenance=inputs.availability_provenance_by_route.get(r, "UNKNOWN"),
                    data_completeness=completeness,
                    interpretability_status=status,
                )
            )

    return records


def generate_pathway_events(
    shifts: List[TechnologyShift],
    constraints: List[ConstraintDiagnostic],
) -> List[PathwayEvent]:
    """Connect technology shifts to their active constraints and limiting data parameters."""
    events: List[PathwayEvent] = []
    
    # Map year+type -> binding status
    binding_map = {}
    for c in constraints:
        if c.binding_status == "BINDING":
            binding_map[(c.year, c.constraint_type)] = True

    for s in shifts:
        drivers = []
        active_c = []
        limits = []
        status = "DATA_LIMITED"

        # Determine drivers and limits based on technology shifts
        if s.technology == "Scrap-EAF":
            drivers.append("cost_competitiveness")
            limits.append("missing_scrap_intensity")
            if (s.year, "demand") in binding_map:
                active_c.append("demand")
            if (s.year, "scrap") in binding_map:
                active_c.append("scrap")
        elif s.technology in ("BF-BOF", "NG-DRI-EAF"):
            drivers.append("cost_competitiveness")
            limits.append("missing_route_capacity_and_vintages")
            if (s.year, f"capacity_{s.technology}") in binding_map:
                active_c.append("capacity")
        elif s.technology == "H2-DRI-EAF":
            limits.append("missing_h2_dri_economics")
            status = "NOT_BENCHMARK_READY"

        events.append(
            PathwayEvent(
                year=s.year,
                technology=s.technology,
                event_type=s.event_type,
                share_change=s.absolute_change,
                associated_drivers=drivers,
                active_constraints=active_c,
                limiting_data=limits,
                interpretation_status=status,
            )
        )

    return events


def generate_benchmark_diagnostics(
    inputs: BaselineInputs,
    benchmark_dir: str,
) -> List[BenchmarkDiagnostic]:
    """Link Vol.4 comparison differences to drivers and data limitations."""
    records: List[BenchmarkDiagnostic] = []
    
    # Load Step 14 outputs if available
    json_path = os.path.join(benchmark_dir, "v4_benchmark.json")
    if not os.path.exists(json_path):
        # Fallback to empty list if benchmark has not run
        return records

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data.get("rows", []):
        # Link material technology differences
        metric = item.get("metric", "")
        year = item.get("year", 2050)
        ours = item.get("ours")
        vol4 = item.get("vol4")
        diff = item.get("difference_absolute")
        status = item.get("comparison_status", "")
        
        drivers = []
        limits = []
        comp_status = "DATA_LIMITED"

        if "mix" in metric or "share" in metric:
            drivers.append("missing_scrap_intensity")
            limits.append("Scrap-EAF scrap intensity is null")
            comp_status = "DATA_LIMITED"
        elif "green_h2" in metric or "hydrogen" in metric:
            drivers.append("missing_h2_dri_economics")
            limits.append("H2-DRI-EAF economics are EXTERNAL_PENDING")
            comp_status = "NOT_BENCHMARK_READY"
        elif "CO2" in metric or "emissions" in metric:
            drivers.append("missing_scrap_intensity")
            limits.append("Scrap-EAF scrap intensity is null")
            comp_status = "DATA_LIMITED"

        records.append(
            BenchmarkDiagnostic(
                metric=metric,
                year=year,
                ours=ours,
                vol4=vol4,
                difference=diff,
                comparison_status=comp_status,
                data_completeness="INCOMPLETE" if limits else "COMPLETE",
                active_constraints=["demand"],
                associated_drivers=drivers,
            )
        )

    return records


# Match tolerance (share points) used to classify MATCH vs BELOW/ABOVE.
SCRAP_WAYPOINT_TOLERANCE = 0.01  # +/-1 pp of the Vol.4 waypoint share


def generate_scrap_waypoint_diagnostics(
    inputs: BaselineInputs,
    res: BaselineMILPResult,
) -> List[ScrapWaypointDiagnostic]:
    """
    Gate C — post-solve scrap share vs Vol.4 NZS waypoints (MATCH/BELOW/ABOVE).

    Approved 2026-08-14 (MODE_B_APPROVAL_GATES.md, Gate C, Interpretation A).
    These are DIAGNOSTIC TARGETS ONLY and are NEVER imposed as MILP floors.

    model_scrap_share = ACT[Scrap-EAF, t] / D[t]. When the route or demand is
    unavailable (data-limited), the record is UNRESOLVED rather than 0/100%.
    """
    records: List[ScrapWaypointDiagnostic] = []
    waypoints = list(inputs.scrap_waypoints or [])
    if not waypoints:
        return records

    for wp in waypoints:
        year = int(wp["year"])
        waypoint_share = float(wp.get("share"))
        demand_t = inputs.demand_mt.get(year, 0.0)
        scrap_act = res.act_mt.get("Scrap-EAF", {}).get(year, 0.0)

        if demand_t <= 0.0 or "Scrap-EAF" not in res.routes:
            records.append(
                ScrapWaypointDiagnostic(
                    year=year,
                    waypoint_share=waypoint_share,
                    model_scrap_share=None,
                    status="UNRESOLVED",
                    interpretation=(
                        "Scrap-EAF not represented or demand unavailable; "
                        "no diagnostic comparison computed."
                    ),
                )
            )
            continue

        model_share = scrap_act / demand_t
        diff = model_share - waypoint_share
        if abs(diff) <= SCRAP_WAYPOINT_TOLERANCE:
            status = "MATCH"
            interp = (
                "Model scrap share is within +/-1 pp of the Vol.4 NZS waypoint. "
                "This is a diagnostic alignment, NOT a policy-constrained match."
            )
        elif diff < 0.0:
            status = "BELOW"
            interp = (
                "Model scrap share is below the Vol.4 NZS waypoint by "
                f"{abs(diff):.3f} pp. The waypoint is a diagnostic target only; "
                "no scrap floor is imposed."
            )
        else:
            status = "ABOVE"
            interp = (
                "Model scrap share is above the Vol.4 NZS waypoint by "
                f"{diff:.3f} pp. The waypoint is a diagnostic target only; "
                "the model is not constrained to match it."
            )

        records.append(
            ScrapWaypointDiagnostic(
                year=year,
                waypoint_share=waypoint_share,
                model_scrap_share=round(model_share, 4),
                status=status,
                interpretation=interp,
            )
        )

    return records


# ──────────────────────────────────────────────────────────────────────────────
# Exporters
# ──────────────────────────────────────────────────────────────────────────────

def export_explainability_results(
    diagnostics: List[TechnologyYearRecord],
    shifts: List[TechnologyShift],
    constraints: List[ConstraintDiagnostic],
    crossovers: List[CostCrossover],
    events: List[PathwayEvent],
    benchmarks: List[BenchmarkDiagnostic],
    output_dir: str,
) -> None:
    """Save explainability output structures to JSON and CSV formats."""
    os.makedirs(output_dir, exist_ok=True)

    # 1. JSON Exports
    for name, data in [
        ("technology_diagnostics", [d.model_dump() for d in diagnostics]),
        ("technology_shifts", [s.model_dump() for s in shifts]),
        ("constraint_diagnostics", [c.model_dump() for c in constraints]),
        ("cost_crossovers", [cr.model_dump() for cr in crossovers]),
        ("pathway_events", [e.model_dump() for e in events]),
        ("benchmark_diagnostics", [b.model_dump() for b in benchmarks]),
    ]:
        with open(os.path.join(output_dir, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # 2. CSV Exports
    pd.DataFrame([d.model_dump() for d in diagnostics]).to_csv(
        os.path.join(output_dir, "technology_diagnostics.csv"), index=False
    )
    pd.DataFrame([s.model_dump() for s in shifts]).to_csv(
        os.path.join(output_dir, "technology_shifts.csv"), index=False
    )
    pd.DataFrame([c.model_dump() for c in constraints]).to_csv(
        os.path.join(output_dir, "constraint_diagnostics.csv"), index=False
    )
    pd.DataFrame([cr.model_dump() for cr in crossovers]).to_csv(
        os.path.join(output_dir, "cost_crossovers.csv"), index=False
    )
    pd.DataFrame([e.model_dump() for e in events]).to_csv(
        os.path.join(output_dir, "pathway_events.csv"), index=False
    )
    pd.DataFrame([b.model_dump() for b in benchmarks]).to_csv(
        os.path.join(output_dir, "benchmark_diagnostics.csv"), index=False
    )
