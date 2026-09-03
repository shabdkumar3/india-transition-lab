"""
Pathway explainability and diagnostics module (Step 15).
"""

from __future__ import annotations

from steel_model.explainability.schemas import (
    TechnologyYearRecord,
    TechnologyShift,
    ConstraintDiagnostic,
    CostCrossover,
    PathwayEvent,
    BenchmarkDiagnostic,
    ScrapWaypointDiagnostic,
)
from steel_model.explainability.costs import (
    is_economics_complete,
    decompose_route_cost,
)
from steel_model.explainability.constraints import (
    run_constraint_diagnostics,
)
from steel_model.explainability.crossover import (
    run_crossover_analysis,
)
from steel_model.explainability.shifts import (
    detect_technology_shifts,
)
from steel_model.explainability.diagnostics import (
    generate_technology_diagnostics,
    generate_pathway_events,
    generate_benchmark_diagnostics,
    generate_scrap_waypoint_diagnostics,
    export_explainability_results,
)
from steel_model.explainability.plots import (
    generate_explainability_plots,
)

__all__ = [
    "TechnologyYearRecord",
    "TechnologyShift",
    "ConstraintDiagnostic",
    "CostCrossover",
    "PathwayEvent",
    "BenchmarkDiagnostic",
    "ScrapWaypointDiagnostic",
    "is_economics_complete",
    "decompose_route_cost",
    "run_constraint_diagnostics",
    "run_crossover_analysis",
    "detect_technology_shifts",
    "generate_technology_diagnostics",
    "generate_pathway_events",
    "generate_benchmark_diagnostics",
    "generate_scrap_waypoint_diagnostics",
    "export_explainability_results",
    "generate_explainability_plots",
]
