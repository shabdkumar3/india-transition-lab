"""
Technology Cost Crossover (Step 15 §8).

Detects years where EffectiveCost_A,t < EffectiveCost_B,t changes
to the opposite ordering.

Only compares routes when:
- same cost basis (annualised CAPEX + FOM+VOM + resource costs)
- same units (USD/t)
- compatible scope (both enabled in baseline)
- complete enough economics (not EXTERNAL_PENDING)

If incomplete: NOT_COMPARABLE
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from steel_model.diagnostics.cost_diagnostics import decompose_cost
from steel_model.optimization.model import BaselineInputs
from steel_model.optimization.results import BaselineMILPResult


@dataclass
class CostCrossover:
    """Detected cost crossover between two routes."""
    route_a: str
    route_b: str
    crossover_year: int
    cost_a_before: float
    cost_b_before: float
    cost_a_after: float
    cost_b_after: float
    direction: str  # "A_overtook_B" or "B_overtook_A"
    status: str  # "COMPARABLE" or "NOT_COMPARABLE"
    limitation: str = ""


def detect_crossovers(
    inputs: BaselineInputs,
    result: BaselineMILPResult,
) -> List[CostCrossover]:
    """
    Detect cost crossovers between all pairs of enabled routes.

    Returns list of CostCrossover objects.
    """
    cost_decomp = decompose_cost(inputs, result)
    crossovers = []

    enabled = inputs.routes
    years = sorted(inputs.years)

    for i, route_a in enumerate(enabled):
        for route_b in enabled[i + 1:]:
            # Check if both routes have complete economics
            comparable = True
            limitations = []

            for route in (route_a, route_b):
                c = cost_decomp.get((route, years[0]), {})
                if c.get("capex_status") == "UNAVAILABLE":
                    comparable = False
                    limitations.append(f"{route}: CAPEX EXTERNAL_PENDING")
                if c.get("fom_status") == "UNAVAILABLE":
                    comparable = False
                    limitations.append(f"{route}: FOM EXTERNAL_PENDING")
                if c.get("scrap_cost_status") == "UNAVAILABLE" and route == "Scrap-EAF":
                    comparable = False
                    limitations.append(f"{route}: SCRAP_INTENSITY EXTERNAL_PENDING")

            if not comparable:
                crossovers.append(CostCrossover(
                    route_a=route_a,
                    route_b=route_b,
                    crossover_year=-1,
                    cost_a_before=0.0,
                    cost_b_before=0.0,
                    cost_a_after=0.0,
                    cost_b_after=0.0,
                    direction="NOT_COMPARABLE",
                    status="NOT_COMPARABLE",
                    limitation="; ".join(limitations),
                ))
                continue

            # Track cost ordering over time
            prev_order = None  # "A_cheaper", "B_cheaper", "equal"
            crossover_year = None

            for t in years:
                cost_a = cost_decomp.get((route_a, t), {}).get("total")
                cost_b = cost_decomp.get((route_b, t), {}).get("total")

                if cost_a is None or cost_b is None:
                    continue

                if abs(cost_a - cost_b) < 1.0:  # Within $1/t
                    curr_order = "equal"
                elif cost_a < cost_b:
                    curr_order = "A_cheaper"
                else:
                    curr_order = "B_cheaper"

                if prev_order is not None and curr_order != prev_order and curr_order != "equal":
                    # Crossover detected
                    crossover_year = t
                    if curr_order == "A_cheaper" and prev_order == "B_cheaper":
                        direction = "A_overtook_B"
                    elif curr_order == "B_cheaper" and prev_order == "A_cheaper":
                        direction = "B_overtook_A"
                    else:
                        direction = "ORDER_CHANGED"

                    # Get costs just before and after
                    before_year = t - 1
                    while before_year >= years[0] and cost_decomp.get((route_a, before_year), {}).get("total") is None:
                        before_year -= 1

                    cost_a_before = cost_decomp.get((route_a, before_year), {}).get("total", 0.0)
                    cost_b_before = cost_decomp.get((route_b, before_year), {}).get("total", 0.0)
                    cost_a_after = cost_a
                    cost_b_after = cost_b

                    crossovers.append(CostCrossover(
                        route_a=route_a,
                        route_b=route_b,
                        crossover_year=crossover_year,
                        cost_a_before=cost_a_before,
                        cost_b_before=cost_b_before,
                        cost_a_after=cost_a_after,
                        cost_b_after=cost_b_after,
                        direction=direction,
                        status="COMPARABLE",
                    ))
                    break

                prev_order = curr_order

    return crossovers