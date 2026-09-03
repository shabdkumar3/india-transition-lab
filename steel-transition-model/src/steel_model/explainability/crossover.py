"""
Cost crossover analysis between technologies (Step 15).
"""

from __future__ import annotations

from typing import List
from steel_model.optimization.model import BaselineInputs
from steel_model.explainability.schemas import CostCrossover
from steel_model.explainability.costs import is_economics_complete, decompose_route_cost


def run_crossover_analysis(
    inputs: BaselineInputs,
    tech_a: str,
    tech_b: str,
) -> List[CostCrossover]:
    """Calculate relative cost ordering and detect crossovers between tech_a and tech_b."""
    records: List[CostCrossover] = []
    years = sorted(list(inputs.years))

    prev_order: Optional[int] = None  # -1 if Cost_A < Cost_B, +1 if Cost_A > Cost_B, 0 if equal

    for t in years:
        a_complete = is_economics_complete(inputs, tech_a)
        b_complete = is_economics_complete(inputs, tech_b)

        if not (a_complete and b_complete):
            records.append(
                CostCrossover(
                    year=t,
                    technology_a=tech_a,
                    technology_b=tech_b,
                    cost_a=None,
                    cost_b=None,
                    comparison_status="NOT_COMPARABLE",
                    crossover_detected=False,
                )
            )
            prev_order = None
            continue

        # Decompose costs with 1.0 Mt activity to extract unit levelized cost
        cost_a_decomp = decompose_route_cost(inputs, tech_a, t, 1.0, 1.0 / inputs.availability.get(tech_a, 0.90))
        cost_b_decomp = decompose_route_cost(inputs, tech_b, t, 1.0, 1.0 / inputs.availability.get(tech_b, 0.90))

        cost_a = cost_a_decomp["unit_effective_cost"]
        cost_b = cost_b_decomp["unit_effective_cost"]

        if cost_a is None or cost_b is None:
            records.append(
                CostCrossover(
                    year=t,
                    technology_a=tech_a,
                    technology_b=tech_b,
                    cost_a=cost_a,
                    cost_b=cost_b,
                    comparison_status="NOT_COMPARABLE",
                    crossover_detected=False,
                )
            )
            prev_order = None
            continue

        # Compare and check crossover
        crossover_detected = False
        curr_order = -1 if cost_a < cost_b else (1 if cost_a > cost_b else 0)
        
        if prev_order is not None and prev_order != 0 and curr_order != 0:
            if prev_order != curr_order:
                crossover_detected = True

        records.append(
            CostCrossover(
                year=t,
                technology_a=tech_a,
                technology_b=tech_b,
                cost_a=cost_a,
                cost_b=cost_b,
                comparison_status="COMPARABLE",
                crossover_detected=crossover_detected,
            )
        )
        prev_order = curr_order

    return records
