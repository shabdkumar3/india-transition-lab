"""
Constraint Pressure Diagnostics (Step 15 §6).

For each major constraint, computes:
- available (capacity/limit)
- used (actual)
- slack = available - used
- binding_status (BINDING / SLACK / NOT_APPLICABLE)
- pressure = used / available (only where denominator > 0)

Constraints covered:
- capacity-activity (ACT <= avail * CAP)
- deployment limits (NCAP <= NCAPLimit)
- scrap balance (Step 9)
- resource availability (if limits exist)
- emissions (if limits exist)
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np

from steel_model.optimization.model import BaselineInputs
from steel_model.optimization.results import BaselineMILPResult


def compute_constraint_pressures(
    inputs: BaselineInputs,
    result: BaselineMILPResult,
) -> Dict[Tuple[str, int], dict]:
    """
    Compute constraint pressures per route × year.

    Returns dict[(route, year)] = {
        "capacity_available": float,
        "capacity_used": float,
        "capacity_slack": float,
        "capacity_pressure": float,
        "capacity_binding": bool,
        "deployment_available": Optional[float],
        "deployment_used": float,
        "deployment_slack": float,
        "deployment_pressure": Optional[float],
        "deployment_binding": bool,
        "scrap_available": Optional[float],
        "scrap_used": float,
        "scrap_slack": float,
        "scrap_pressure": Optional[float],
        "scrap_binding": bool,
        "resource_pressure": Optional[float],
        "emission_pressure": Optional[float],
        "learning_effect": Optional[float],
    }
    """
    out = {}

    for route in inputs.routes:
        for t in inputs.years:
            cap = result.cap_mt.get(route, {}).get(t, 0.0)
            act = result.act_mt.get(route, {}).get(t, 0.0)
            ncap = result.ncap_mt.get(route, {}).get(t, 0.0)
            avail = inputs.availability.get(route, 0.0)

            # --- Capacity-activity constraint ---
            cap_available = avail * cap
            cap_used = act
            cap_slack = cap_available - cap_used
            cap_pressure = (cap_used / cap_available) if cap_available > 0 else None
            cap_binding = cap_slack <= 1e-6 and cap_available > 0

            # --- Deployment limits ---
            dep_limit = inputs.ncap_limits_mt.get(route)
            dep_used = ncap
            dep_available = dep_limit
            dep_slack = (dep_available - dep_used) if dep_available is not None else None
            dep_pressure = (dep_used / dep_available) if dep_available is not None and dep_available > 0 else None
            dep_binding = dep_slack is not None and dep_slack <= 1e-6

            # --- Scrap balance (Step 9) ---
            scrap_available = None
            scrap_used = result.res_use.get("scrap", {}).get(t, 0.0)
            scrap_slack = None
            scrap_pressure = None
            scrap_binding = False

            if inputs.scrap_engine is not None:
                # Usable domestic scrap + imports from scrap accounting
                if result.scrap_accounting is not None:
                    # Usable scrap = domestic usable + imports
                    domestic_usable = sum(
                        result.scrap_accounting.usable_scrap_domestic.get(r, {}).get(t, 0.0)
                        for r in inputs.routes
                    )
                    imports = result.scrap_accounting.scrap_imports.get(t, 0.0)
                    scrap_available = domestic_usable + imports
                    scrap_slack = scrap_available - scrap_used
                    scrap_pressure = (scrap_used / scrap_available) if scrap_available > 0 else None
                    scrap_binding = scrap_slack <= 1e-6

            # --- Resource pressure (aggregate) ---
            # Simple aggregate: total resource cost / total resource value if limits existed
            # Since no explicit resource limits in baseline, compute as ratio of
            # resource use to some reference (demand × typical intensity)
            resource_pressure = None
            if act > 0:
                total_resource_cost = sum(
                    inputs.resource_price_model_unit.get(r, 0.0) * result.res_use.get(r, {}).get(t, 0.0)
                    for r in inputs.resources
                )
                # Reference: approximate cost if all demand met by this route
                demand = inputs.demand_mt.get(t, 0.0)
                if demand > 0:
                    resource_pressure = min(1.0, total_resource_cost / max(1.0, demand * 100.0))  # rough scale

            # --- Emission pressure ---
            emission_pressure = None
            if act > 0:
                co2 = result.co2_total_mt.get(t, 0.0)
                demand = inputs.demand_mt.get(t, 0.0)
                if demand > 0:
                    intensity = co2 / demand
                    # Compare to Vol.4 NZS 2050 intensity ~0.66 tCO2/t
                    emission_pressure = min(1.0, intensity / 2.54)  # relative to base 2.54

            # --- Learning effect ---
            learning_effect = None
            if inputs.endogenous_learning_enabled:
                # Learning effect = 1 - (current_capex / base_capex) if available
                base_capex = inputs.capex_annualised_usd_per_t.get(route)
                if isinstance(base_capex, dict):
                    current_capex = base_capex.get(t, base_capex)
                    # Would need cumulative capacity to compute
                    pass  # Placeholder

            out[(route, t)] = {
                "capacity_available": cap_available,
                "capacity_used": cap_used,
                "capacity_slack": cap_slack,
                "capacity_pressure": cap_pressure,
                "capacity_binding": cap_binding,
                "deployment_available": dep_available,
                "deployment_used": dep_used,
                "deployment_slack": dep_slack,
                "deployment_pressure": dep_pressure,
                "deployment_binding": dep_binding,
                "scrap_available": scrap_available,
                "scrap_used": scrap_used,
                "scrap_slack": scrap_slack,
                "scrap_pressure": scrap_pressure,
                "scrap_binding": scrap_binding,
                "resource_pressure": resource_pressure,
                "emission_pressure": emission_pressure,
                "learning_effect": learning_effect,
            }

    # Disabled routes
    for route in inputs.all_routes:
        if route not in inputs.routes:
            for t in inputs.years:
                out[(route, t)] = {
                    "capacity_available": None,
                    "capacity_used": None,
                    "capacity_slack": None,
                    "capacity_pressure": None,
                    "capacity_binding": None,
                    "deployment_available": None,
                    "deployment_used": None,
                    "deployment_slack": None,
                    "deployment_pressure": None,
                    "deployment_binding": None,
                    "scrap_available": None,
                    "scrap_used": None,
                    "scrap_slack": None,
                    "scrap_pressure": None,
                    "scrap_binding": None,
                    "resource_pressure": None,
                    "emission_pressure": None,
                    "learning_effect": None,
                }

    return out


def _safe_div(numerator: float, denominator: float) -> Optional[float]:
    """Safe division returning None if denominator <= 0."""
    if denominator <= 0:
        return None
    return numerator / denominator