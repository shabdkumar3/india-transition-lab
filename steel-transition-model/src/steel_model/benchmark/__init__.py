"""
Step 14 — Vol.4 benchmark reconstruction & consistency assessment.

Public surface: Vol4Register, BenchmarkEngine, comparison classes,
scientific statuses, difference attribution, and the ablation analysis.

Hard rules (Step 14 §19, §21): no silent reconciliation of differences; no
new data to force agreement; Vol.4 never modified; H2-DRI economics never
fabricated; route-level existing capacity never fabricated; M1 values never
synthesised.
"""

from steel_model.benchmark.definitions import (
    CLOSE_TOLERANCE,
    ComparisonStatus,
    MATCH_TOLERANCE,
    ScientificStatus,
    THRESHOLD_RATIONALE,
    classify_difference,
    relative_difference,
)
from steel_model.benchmark.vol4_register import Vol4Register
from steel_model.benchmark.engine import BenchmarkEngine, TABLE_COLUMNS
from steel_model.benchmark.attribution import (
    DRIVER_VOCABULARY,
    Attribution,
    attribution_table,
    MATERIAL_DIFFERENCE_ATTRIBUTIONS,
)

__all__ = [
    "CLOSE_TOLERANCE",
    "ComparisonStatus",
    "MATCH_TOLERANCE",
    "ScientificStatus",
    "THRESHOLD_RATIONALE",
    "classify_difference",
    "relative_difference",
    "Vol4Register",
    "BenchmarkEngine",
    "TABLE_COLUMNS",
    "DRIVER_VOCABULARY",
    "Attribution",
    "attribution_table",
    "MATERIAL_DIFFERENCE_ATTRIBUTIONS",
]