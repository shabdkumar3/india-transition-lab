"""
Cost Diagnostics (Step 15 §5).

Decomposes TotalEffectiveCost_i,t into components:
- CAPEX contribution (annualised CAPEX × discount factor)
- FOM contribution
- VOM contribution
- Fuel/resource contribution (via RES block)
- Electricity contribution
- Carbon/emission contribution (if applicable)

For Scrap-EAF: scrap_cost = UNAVAILABLE (EXTERNAL_PENDING).
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np

from steel_model.optimization.model import BaselineInputs
from steel_model.optimization.results import BaselineMILPResult


def _discount_factor(year: int, start_year: int, discount_rate: float) -> float:
    return (1.0 + discount_rate) ** (-(year - start_year))


def decompose_cost(
    inputs: BaselineInputs,
    result: BaselineMILPResult,
) -> Dict[Tuple[str, int], dict]:
    """
    Compute cost decomposition per route × year.

    Returns dict[(route, year)] = {
        "total": float,
        "capex": float,
        "fom": float,
        "vom": float,
        "fuel": float,          # coal + gas
        "resource": float,      # ore + scrap + other
        "electricity": float,
        "carbon": float,
        "capex_status": "COMPUTED"|"UNAVAILABLE",
        "fom_status": "COMPUTED"|"UNAVAILABLE",
        "vom_status": "COMPUTED"|"UNAVAILABLE",
        "scrap_cost_status": "COMPUTED"|"UNAVAILABLE",
    }
    """
    out = {}
    df = {t: _discount_factor(t, inputs.start_year, inputs.discount_rate) for t in inputs.years}

    # Resource grouping for cost attribution
    fuel_resources = {"coking_coal", "non_coking_coal", "natural_gas"}
    electricity_resources = {"electricity_route"}

    for route in inputs.routes:
        capex = inputs.capex_annualised_usd_per_t.get(route)
        fom = inputs.opex_fixed_usd_per_t.get(route, 0.0)
        vom = inputs.vom_usd_per_t.get(route, 0.0)

        capex_status = "COMPUTED" if capex is not None else "UNAVAILABLE"
        fom_status = "COMPUTED" if fom is not None else "UNAVAILABLE"
        vom_status = "COMPUTED" if vom is not None else "UNAVAILABLE"

        for t in inputs.years:
            d = df[t]
            act = result.act_mt.get(route, {}).get(t, 0.0)
            cap = result.cap_mt.get(route, {}).get(t, 0.0)

            # CAPEX contribution (annualised CAPEX on installed capacity)
            capex_contrib = d * capex if capex is not None else 0.0

            # FOM+VOM per tonne produced
            fom_contrib = d * fom if fom is not None else 0.0
            vom_contrib = d * vom if vom is not None else 0.0

            # Resource costs from RES block
            fuel_cost = 0.0
            resource_cost = 0.0
            electricity_cost = 0.0
            scrap_cost_status = "COMPUTED"

            for r in inputs.resources:
                price = inputs.resource_price_model_unit.get(r, 0.0)
                res_use = result.res_use.get(r, {}).get(t, 0.0)
                cost = d * price * res_use

                if r in fuel_resources:
                    fuel_cost += cost
                elif r in electricity_resources:
                    electricity_cost += cost
                elif r == "scrap":
                    # Scrap cost status depends on whether scrap intensity is available
                    scrap_intensity = inputs.resource_intensity.get((route, "scrap"))
                    if scrap_intensity is None or scrap_intensity == 0.0:
                        scrap_cost_status = "UNAVAILABLE"
                    resource_cost += cost
                else:
                    resource_cost += cost

            # Carbon cost (not in baseline objective, but available from emissions)
            carbon_cost = 0.0  # Baseline has no carbon price

            total = (
                capex_contrib
                + fom_contrib
                + vom_contrib
                + fuel_cost
                + resource_cost
                + electricity_cost
                + carbon_cost
            )

            out[(route, t)] = {
                "total": total if act > 0 else None,
                "capex": capex_contrib if act > 0 else None,
                "fom": fom_contrib if act > 0 else None,
                "vom": vom_contrib if act > 0 else None,
                "fuel": fuel_cost if act > 0 else None,
                "resource": resource_cost if act > 0 else None,
                "electricity": electricity_cost if act > 0 else None,
                "carbon": carbon_cost if act > 0 else None,
                "capex_status": capex_status,
                "fom_status": fom_status,
                "vom_status": vom_status,
                "scrap_cost_status": scrap_cost_status,
            }

    # Also populate for disabled routes (marking all as UNAVAILABLE)
    for route in inputs.all_routes:
        if route not in inputs.routes:
            for t in inputs.years:
                out[(route, t)] = {
                    "total": None,
                    "capex": None,
                    "fom": None,
                    "vom": None,
                    "fuel": None,
                    "resource": None,
                    "electricity": None,
                    "carbon": None,
                    "capex_status": "UNAVAILABLE",
                    "fom_status": "UNAVAILABLE",
                    "vom_status": "UNAVAILABLE",
                    "scrap_cost_status": "UNAVAILABLE",
                }

    return out