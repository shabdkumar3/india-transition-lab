"""
Cost decomposition and gatekeeping (Step 15).
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from steel_model.optimization.model import BaselineInputs


def is_economics_complete(inputs: BaselineInputs, route: str) -> bool:
    """Return True if route has complete, source-backed economic inputs."""
    # Routes with unquantified full-plant economics are incomplete
    if route not in inputs.routes:
        return False

    capex = inputs.capex_annualised_usd_per_t.get(route)
    if capex is None:
        return False

    # Scrap-EAF has unresolved scrap charge intensity in baseline config
    if route == "Scrap-EAF":
        scrap_intensity = inputs.resource_intensity.get(("Scrap-EAF", "scrap"))
        if scrap_intensity is None or scrap_intensity == 0.0:
            # Marked as incomplete because scrap feed cost term is missing
            return False

    return True


def decompose_route_cost(
    inputs: BaselineInputs,
    route: str,
    year: int,
    production_mt: float,
    capacity_mt: float,
) -> Dict[str, Optional[float]]:
    """
    Decompose production cost into objective-compatible components.

    If inputs are incomplete (e.g., Scrap-EAF scrap price or H2-DRI-EAF capex),
    associated components must return None (UNAVAILABLE) to prevent zero-replacement.
    """
    # 1. Initialize default dictionary with None values
    out: Dict[str, Optional[float]] = {
        "capex_contribution": None,
        "fom_contribution": None,
        "vom_contribution": None,
        "fuel_cost": None,
        "resource_cost": None,
        "electricity_cost": None,
        "emission_cost": None,
        "effective_cost": None,
        "unit_effective_cost": None,
    }

    # 2. Check general technological availability
    if route not in inputs.routes:
        return out

    # 3. CAPEX & O&M
    capex_val = inputs.capex_annualised_usd_per_t.get(route)
    if capex_val is None:
        return out
    
    # Support time-varying or flat capex
    capex_ann = capex_val[year] if isinstance(capex_val, dict) else capex_val
    fom = inputs.opex_fixed_usd_per_t.get(route, 0.0)
    vom = inputs.vom_usd_per_t.get(route, 0.0)

    # In our MILP formulation, CAPEX is charged on installed capacity, while
    # FOM + VOM are charged per tonne of activity (production)
    out["capex_contribution"] = float(capex_ann * capacity_mt)
    out["fom_contribution"] = float(fom * production_mt)
    out["vom_contribution"] = float(vom * production_mt)

    # 4. Electricity Cost (RES: 'electricity_route')
    elec_price = inputs.resource_price_model_unit.get("electricity_route", 0.0)
    elec_int = inputs.resource_intensity.get((route, "electricity_route"))
    if elec_int is not None:
        out["electricity_cost"] = float(production_mt * elec_int * elec_price)
    else:
        out["electricity_cost"] = 0.0

    # 5. Fuel Cost (RES: 'natural_gas', 'coking_coal', 'non_coking_coal')
    gas_price = inputs.resource_price_model_unit.get("natural_gas", 0.0)
    coking_price = inputs.resource_price_model_unit.get("coking_coal", 0.0)
    non_coking_price = inputs.resource_price_model_unit.get("non_coking_coal", 0.0)

    gas_int = inputs.resource_intensity.get((route, "natural_gas"))
    coking_int = inputs.resource_intensity.get((route, "coking_coal"))
    non_coking_int = inputs.resource_intensity.get((route, "non_coking_coal"))

    gas_cost = (production_mt * gas_int * gas_price) if gas_int is not None else 0.0
    coking_cost = (production_mt * coking_int * coking_price) if coking_int is not None else 0.0
    non_coking_cost = (production_mt * non_coking_int * non_coking_price) if non_coking_int is not None else 0.0
    out["fuel_cost"] = float(gas_cost + coking_cost + non_coking_cost)

    # 6. Carbon / Emission Cost (always zero in baseline)
    out["emission_cost"] = 0.0

    # 7. Non-Energy Resource Cost (RES: 'iron_ore', 'scrap', 'hydrogen')
    ore_price = inputs.resource_price_model_unit.get("iron_ore", 0.0)
    h2_price = inputs.resource_price_model_unit.get("hydrogen", 0.0)
    scrap_price = inputs.resource_price_model_unit.get("scrap", 0.0)

    ore_int = inputs.resource_intensity.get((route, "iron_ore"))
    h2_int = inputs.resource_intensity.get((route, "hydrogen"))
    scrap_int = inputs.resource_intensity.get((route, "scrap"))

    ore_cost = (production_mt * ore_int * ore_price) if ore_int is not None else 0.0
    h2_cost = (production_mt * h2_int * h2_price) if h2_int is not None else 0.0

    # Special logic for scrap: if scrap intensity is None (unresolved), scrap_cost is None.
    # We must NOT report it as 0.0.
    if scrap_int is None:
        if route == "Scrap-EAF" or scrap_price > 0.0:
            out["resource_cost"] = None
        else:
            out["resource_cost"] = float(ore_cost + h2_cost)
    else:
        scrap_cost = production_mt * scrap_int * scrap_price
        out["resource_cost"] = float(ore_cost + h2_cost + scrap_cost)

    # 8. Compute Total Effective Cost and Unit Effective Cost
    # If any cost component is None, the sum is None (UNAVAILABLE)
    components = [
        out["capex_contribution"],
        out["fom_contribution"],
        out["vom_contribution"],
        out["fuel_cost"],
        out["resource_cost"],
        out["electricity_cost"],
        out["emission_cost"],
    ]

    if any(c is None for c in components):
        out["effective_cost"] = None
        out["unit_effective_cost"] = None
    else:
        total = sum(c for c in components if c is not None)
        out["effective_cost"] = float(total)
        out["unit_effective_cost"] = float(total / production_mt) if production_mt > 0.0 else float(
            capex_ann / inputs.availability.get(route, 0.90) + fom + vom +
            (elec_int * elec_price if elec_int else 0.0) +
            (gas_int * gas_price if gas_int else 0.0) +
            (coking_int * coking_price if coking_int else 0.0) +
            (non_coking_int * non_coking_price if non_coking_int else 0.0) +
            (ore_int * ore_price if ore_int else 0.0) +
            (h2_int * h2_price if h2_int else 0.0) +
            (scrap_int * scrap_price if scrap_int else 0.0)
        )

    return out
