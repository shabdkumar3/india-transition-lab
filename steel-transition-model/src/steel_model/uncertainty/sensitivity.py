"""
Sensitivity and Scenario Runner (Step 13).
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Tuple

import pandas as pd

from steel_model.optimization.model import BaselineInputs, BaselineMILP
from steel_model.uncertainty.registry import UncertaintyRegistry, UncertaintyParameter


def apply_overrides(inputs: BaselineInputs, overrides: Dict[str, float]) -> BaselineInputs:
    """Return a deep copy of inputs with parameter overrides applied."""
    new_inputs = copy.deepcopy(inputs)
    for param_id, value in overrides.items():
        if param_id == "discount_rate":
            new_inputs.discount_rate = value
        elif param_id == "price_iron_ore":
            new_inputs.resource_price_model_unit["iron_ore"] = value
        elif param_id == "price_scrap":
            new_inputs.resource_price_model_unit["scrap"] = value
        elif param_id == "price_natural_gas":
            # Divide by 1.055 to get USD/GJ
            new_inputs.resource_price_model_unit["natural_gas"] = value / 1.055
        elif param_id == "price_electricity":
            new_inputs.resource_price_model_unit["electricity_route"] = value
        elif param_id == "price_hydrogen":
            new_inputs.resource_price_model_unit["hydrogen"] = value
        elif param_id == "price_coking_coal":
            new_inputs.resource_price_model_unit["coking_coal"] = value
        elif param_id == "price_non_coking_coal":
            new_inputs.resource_price_model_unit["non_coking_coal"] = value
        elif param_id.startswith("capex_"):
            route = param_id.split("_")[1]
            if route in new_inputs.capex_annualised_usd_per_t:
                new_inputs.capex_annualised_usd_per_t[route] = value
    return new_inputs


def extract_scenario_metrics(inputs: BaselineInputs, res: Any) -> Dict[str, Any]:
    """Extract standard metrics from a solve result."""
    if res.status != 0:
        return {
            "solver_status": res.status,
            "status_label": res.status_label,
            "objective": None,
            "technology_mix": {},
            "capacity": {},
            "production": {},
            "H2": {},
            "electricity": {},
            "coal": {},
            "gas": {},
            "ore": {},
            "scrap": {},
            "CO2": {},
            "investment": {},
            "data_completeness": {
                "existing_route_capacity_available": False,
                "route_transition_interpretability": False,
                "technology_space_completeness": "INCOMPLETE",
                "scrap_intensity": {},
            },
        }

    years = list(inputs.years)
    tech_mix = {}
    capacity = {}
    production = {}
    for r in inputs.routes:
        tech_mix[r] = {t: res.production_share(r)[t] for t in years}
        capacity[r] = {t: res.cap_mt[r][t] for t in years}
        production[r] = {t: res.act_mt[r][t] for t in years}

    h2 = {t: res.res_use.get("hydrogen", {}).get(t, 0.0) for t in years}
    elec = {t: res.res_use.get("electricity_route", {}).get(t, 0.0) for t in years}
    coking = {t: res.res_use.get("coking_coal", {}).get(t, 0.0) for t in years}
    non_coking = {t: res.res_use.get("non_coking_coal", {}).get(t, 0.0) for t in years}
    coal = {t: coking[t] + non_coking[t] for t in years}
    gas = {t: res.res_use.get("natural_gas", {}).get(t, 0.0) for t in years}
    ore = {t: res.res_use.get("iron_ore", {}).get(t, 0.0) for t in years}
    scrap = {t: res.res_use.get("scrap", {}).get(t, 0.0) for t in years}
    co2 = {t: res.co2_total_mt.get(t, 0.0) for t in years}

    investment = {}
    for t in years:
        investment[t] = sum(
            res.ncap_mt[r][t] * inputs.capex_annualised_usd_per_t[r]
            for r in inputs.routes
        )

    return {
        "solver_status": res.status,
        "status_label": res.status_label,
        "objective": res.objective_value,
        "technology_mix": tech_mix,
        "capacity": capacity,
        "production": production,
        "H2": h2,
        "electricity": elec,
        "coal": coal,
        "gas": gas,
        "ore": ore,
        "scrap": scrap,
        "CO2": co2,
        "investment": investment,
        "data_completeness": {
            "existing_route_capacity_available": res.existing_route_capacity_available,
            "route_transition_interpretability": res.route_transition_interpretability,
            "technology_space_completeness": res.technology_space_completeness,
            "scrap_intensity": {
                r: res.scrap_intensity_status.get(r, {})
                for r in inputs.routes
            },
        },
    }


class ScenarioRunner:
    """Runner for structured scenario runs and OAT sensitivity analysis."""

    def __init__(self, inputs: BaselineInputs, registry: UncertaintyRegistry) -> None:
        self.inputs = inputs
        self.registry = registry

    def run_oat_sensitivity(self) -> List[Dict[str, Any]]:
        """Run low and high bounds for all eligible uncertainty parameters."""
        results = []
        eligible = self.registry.get_eligible_parameters()

        # Run Baseline (BASE)
        base_res = BaselineMILP(self.inputs).solve()
        base_metrics = extract_scenario_metrics(self.inputs, base_res)
        base_metrics.update({
            "parameter_id": "BASE",
            "variation": "base",
            "value": None,
        })
        results.append(base_metrics)

        for p in eligible:
            for var_type, val in [("low", p.lower_bound), ("high", p.upper_bound)]:
                if val is None:
                    continue
                overridden_inputs = apply_overrides(self.inputs, {p.parameter_id: val})
                res = BaselineMILP(overridden_inputs).solve()
                metrics = extract_scenario_metrics(overridden_inputs, res)
                metrics.update({
                    "parameter_id": p.parameter_id,
                    "variation": var_type,
                    "value": val,
                })
                results.append(metrics)

        return results

    def run_scenario_matrix(self) -> Dict[str, Dict[str, Any]]:
        """Run named scenario combinations."""
        scenarios = {
            "BASE": {},
            "HIGH_H2_COST": {"price_hydrogen": 3.5},
            "LOW_H2_COST": {"price_hydrogen": 1.2},
            "HIGH_ELECTRICITY_COST": {"price_electricity": 90.0},
            "LOW_ELECTRICITY_COST": {"price_electricity": 30.0},
            "HIGH_CAPEX": {
                "capex_BF-BOF": 94.0,
                "capex_NG-DRI-EAF": 136.0,
                "capex_Scrap-EAF": 58.0,
            },
            "LOW_CAPEX": {
                "capex_BF-BOF": 52.0,
                "capex_NG-DRI-EAF": 53.0,
                "capex_Scrap-EAF": 34.0,
            },
            "HIGH_SCRAP_COST": {"price_scrap": 300.0},
            "LOW_SCRAP_COST": {"price_scrap": 200.0},
        }

        results = {}
        for sc_id, overrides in scenarios.items():
            overridden_inputs = apply_overrides(self.inputs, overrides)
            res = BaselineMILP(overridden_inputs).solve()
            metrics = extract_scenario_metrics(overridden_inputs, res)
            metrics.update({
                "scenario_id": sc_id,
                "parameter_overrides": overrides,
                "provenance": "GLOBAL_SCENARIO_COMBINATION",
            })
            results[sc_id] = metrics

        return results


# ──────────────────────────────────────────────────────────────────────────────
# Robustness Metrics Calculations
# ──────────────────────────────────────────────────────────────────────────────

def calculate_technology_presence_frequency(
    scenario_results: Dict[str, Dict[str, Any]],
    technology_id: str,
    share_threshold: float = 0.05,
    year: int = 2050,
) -> float:
    """Calculate the fraction of scenarios where technology exceeds a share threshold."""
    feasible_runs = [r for r in scenario_results.values() if r["solver_status"] == 0]
    if not feasible_runs:
        return 0.0

    count = 0
    for r in feasible_runs:
        shares = r["technology_mix"].get(technology_id, {})
        if shares.get(year, 0.0) >= share_threshold:
            count += 1
    return count / len(feasible_runs)


def calculate_feasibility_rate(scenario_results: Dict[str, Dict[str, Any]]) -> float:
    """Calculate feasible_runs / total_runs."""
    total = len(scenario_results)
    if total == 0:
        return 0.0
    feasible = sum(1 for r in scenario_results.values() if r["solver_status"] == 0)
    return feasible / total


def calculate_cost_robustness(
    scenario_results: Dict[str, Dict[str, Any]],
    cost_threshold_pct: float = 0.15,
) -> float:
    """Calculate fraction of scenarios within cost_threshold_pct of BASE objective."""
    base = scenario_results.get("BASE")
    if not base or base["objective"] is None:
        return 0.0

    base_cost = base["objective"]
    feasible_runs = [r for r in scenario_results.values() if r["solver_status"] == 0]
    if not feasible_runs:
        return 0.0

    count = 0
    for r in feasible_runs:
        cost = r["objective"]
        if cost is not None:
            if abs(cost - base_cost) / base_cost <= cost_threshold_pct:
                count += 1
    return count / len(feasible_runs)


# ──────────────────────────────────────────────────────────────────────────────
# Exporters
# ──────────────────────────────────────────────────────────────────────────────

def export_results_to_csv_json(
    results: Any,
    output_dir: str,
    prefix: str,
) -> None:
    """Save metrics to CSV and JSON files in the output directory."""
    os.makedirs(output_dir, exist_ok=True)
    
    # JSON export (full nested structure)
    json_path = os.path.join(output_dir, f"{prefix}_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Flatten nested metrics for CSV export (annual totals at 2030, 2050, 2070)
    rows = []
    if isinstance(results, list):
        # List of dicts (OAT results)
        for r in results:
            obj = r["objective"]
            row = {
                "parameter_id": r["parameter_id"],
                "variation": r["variation"],
                "value": r["value"],
                "solver_status": r["solver_status"],
                "objective": obj,
            }
            if r["solver_status"] == 0:
                for y in [2030, 2050, 2070]:
                    row[f"CO2_{y}"] = r["CO2"].get(y)
                    row[f"H2_{y}"] = r["H2"].get(y)
                    row[f"electricity_{y}"] = r["electricity"].get(y)
                    for route in r["technology_mix"].keys():
                        row[f"share_{route}_{y}"] = r["technology_mix"][route].get(y)
            rows.append(row)
    else:
        # Dict of dicts (Scenario matrix results)
        for sc_id, r in results.items():
            obj = r["objective"]
            row = {
                "scenario_id": sc_id,
                "solver_status": r["solver_status"],
                "objective": obj,
            }
            if r["solver_status"] == 0:
                for y in [2030, 2050, 2070]:
                    row[f"CO2_{y}"] = r["CO2"].get(y)
                    row[f"H2_{y}"] = r["H2"].get(y)
                    row[f"electricity_{y}"] = r["electricity"].get(y)
                    for route in r["technology_mix"].keys():
                        row[f"share_{route}_{y}"] = r["technology_mix"][route].get(y)
            rows.append(row)

    df = pd.DataFrame(rows)
    csv_path = os.path.join(output_dir, f"{prefix}_results.csv")
    df.to_csv(csv_path, index=False)
