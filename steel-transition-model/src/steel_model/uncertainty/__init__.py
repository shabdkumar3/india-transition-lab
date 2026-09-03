"""
Uncertainty and Sensitivity Module (Step 13).
"""

from __future__ import annotations

from steel_model.uncertainty.registry import (
    UncertaintyParameter,
    UncertaintyRegistry,
)
from steel_model.uncertainty.sensitivity import (
    ScenarioRunner,
    apply_overrides,
    extract_scenario_metrics,
    calculate_technology_presence_frequency,
    calculate_feasibility_rate,
    calculate_cost_robustness,
    export_results_to_csv_json,
)
from steel_model.uncertainty.pathway import (
    PathwayScenarioEngine,
    compute_robustness_metrics,
    classify_conclusion,
    answer_study_questions,
    verify_control_baselines,
    export_results,
    generate_pathway_plots,
    SCRAP_LEVELS,
    DRI_ALTERNATIVES,
    FLEET_SCENARIOS,
)

__all__ = [
    "UncertaintyParameter",
    "UncertaintyRegistry",
    "ScenarioRunner",
    "apply_overrides",
    "extract_scenario_metrics",
    "calculate_technology_presence_frequency",
    "calculate_feasibility_rate",
    "calculate_cost_robustness",
    "export_results_to_csv_json",
    "PathwayScenarioEngine",
    "compute_robustness_metrics",
    "classify_conclusion",
    "answer_study_questions",
    "verify_control_baselines",
    "export_results",
    "generate_pathway_plots",
    "SCRAP_LEVELS",
    "DRI_ALTERNATIVES",
    "FLEET_SCENARIOS",
]
