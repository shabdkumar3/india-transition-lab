"""
Step 15 — Pathway Explainability & Diagnostics.

Public surface for the diagnostic layer explaining "WHY did the optimizer
choose this pathway?"

This is an INTERPRETATION LAYER over actual model results — not a new
optimizer, not an ML decision system, not a causal inference model.
"""

from steel_model.diagnostics.pathway_record import (
    PathwayRecord,
    PathwayRecords,
    build_pathway_records,
)
from steel_model.diagnostics.shift_detection import (
    ShiftThresholds,
    TechnologyShift,
    detect_shifts,
)
from steel_model.diagnostics.driver_decomposition import (
    DRIVER_VOCABULARY,
    CONFIDENCE_LEVELS,
    DriverAttribution,
    classify_drivers,
)
from steel_model.diagnostics.cost_diagnostics import decompose_cost
from steel_model.diagnostics.constraint_diagnostics import compute_constraint_pressures
from steel_model.diagnostics.crossover import CostCrossover, detect_crossovers
from steel_model.diagnostics.narrative import PathwayNarrative, generate_narratives, narratives_to_csv_rows
from steel_model.diagnostics.vol4_integration import Vol4DifferenceLink, integrate_vol4_differences, links_to_csv_rows
from steel_model.diagnostics.ablation_interpretation import AblationStatus, interpret_ablation, ablation_statuses_to_csv_rows
from steel_model.diagnostics import plots

__all__ = [
    "PathwayRecord",
    "PathwayRecords",
    "build_pathway_records",
    "ShiftThresholds",
    "TechnologyShift",
    "detect_shifts",
    "DRIVER_VOCABULARY",
    "CONFIDENCE_LEVELS",
    "DriverAttribution",
    "classify_drivers",
    "decompose_cost",
    "compute_constraint_pressures",
    "CostCrossover",
    "detect_crossovers",
    "PathwayNarrative",
    "generate_narratives",
    "narratives_to_csv_rows",
    "Vol4DifferenceLink",
    "integrate_vol4_differences",
    "links_to_csv_rows",
    "AblationStatus",
    "interpret_ablation",
    "ablation_statuses_to_csv_rows",
    "plots",
]