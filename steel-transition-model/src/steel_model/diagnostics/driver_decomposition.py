"""
Driver Decomposition (Step 15 §4).

For each major technology shift, classifies possible drivers:

A. Cost competitiveness
B. Existing asset retirement
C. Resource availability
D. Scrap availability
E. Deployment constraint
F. Emissions constraint
G. Learning
H. Demand growth
I. Data availability limitation

Uses controlled vocabulary and careful language:
- "associated driver"
- "consistent with"
- "supported by active constraint"

NOT causal claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from steel_model.diagnostics.pathway_record import PathwayRecord
from steel_model.diagnostics.shift_detection import TechnologyShift
from steel_model.diagnostics.cost_diagnostics import decompose_cost
from steel_model.diagnostics.constraint_diagnostics import compute_constraint_pressures
from steel_model.optimization.model import BaselineInputs
from steel_model.optimization.results import BaselineMILPResult


# Controlled driver vocabulary
DRIVER_VOCABULARY = (
    "COST_COMPETITIVENESS",
    "EXISTING_ASSET_RETIREMENT",
    "RESOURCE_AVAILABILITY",
    "SCRAP_AVAILABILITY",
    "DEPLOYMENT_CONSTRAINT",
    "EMISSIONS_CONSTRAINT",
    "LEARNING_EFFECT",
    "DEMAND_GROWTH",
    "DATA_AVAILABILITY_LIMITATION",
)

CONFIDENCE_LEVELS = ("HIGH", "MEDIUM", "LOW")


@dataclass
class DriverAttribution:
    """Driver attribution for a technology shift."""
    shift: TechnologyShift
    driver: str
    evidence: str
    confidence: str
    supporting_data: Dict[str, float]

    def __post_init__(self):
        if self.driver not in DRIVER_VOCABULARY:
            raise ValueError(f"Driver '{self.driver}' not in vocabulary")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"Confidence '{self.confidence}' not in {CONFIDENCE_LEVELS}")
        if not self.evidence or not self.evidence.strip():
            raise ValueError("Evidence must not be empty (no-causality rule)")


def classify_drivers(
    shift: TechnologyShift,
    inputs: BaselineInputs,
    result: BaselineMILPResult,
    cost_decomp: Dict,
    pressures: Dict,
    pathway_records: List[PathwayRecord],
) -> List[DriverAttribution]:
    """
    Classify possible drivers for a technology shift.

    Returns list of DriverAttribution with evidence and confidence.
    Never claims causality — uses "associated with", "consistent with", etc.
    """
    attributions = []
    tech = shift.technology
    year = shift.year

    # Get cost and constraint data for this tech/year
    cdecomp = cost_decomp.get((tech, year), {})
    pres = pressures.get((tech, year), {})

    # --- A. Cost Competitiveness ---
    if shift.shift_type in ("SHARE_INCREASE", "APPEARANCE", "NCAP_ACCELERATION"):
        # Check if this route's effective cost decreased relative to others
        other_costs = [
            cost_decomp.get((r, year), {}).get("total")
            for r in inputs.routes if r != tech and cost_decomp.get((r, year), {}).get("total") is not None
        ]
        this_cost = cdecomp.get("total")

        if this_cost is not None and other_costs:
            min_other = min(other_costs)
            if this_cost <= min_other * 1.05:  # within 5% of cheapest
                attributions.append(DriverAttribution(
                    shift=shift,
                    driver="COST_COMPETITIVENESS",
                    evidence=f"Effective cost {this_cost:.1f} USD/t is consistent with cheapest alternative ({min_other:.1f} USD/t); associated with cost competitiveness",
                    confidence="MEDIUM",
                    supporting_data={"this_cost": this_cost, "min_other_cost": min_other},
                ))

        # Check which cost component dominates
        if this_cost is not None and this_cost > 0:
            components = {
                "capex": cdecomp.get("capex", 0) or 0,
                "fom": cdecomp.get("fom", 0) or 0,
                "vom": cdecomp.get("vom", 0) or 0,
                "fuel": cdecomp.get("fuel", 0) or 0,
                "resource": cdecomp.get("resource", 0) or 0,
                "electricity": cdecomp.get("electricity", 0) or 0,
            }
            max_comp = max(components, key=components.get)
            if components[max_comp] > 0.3 * this_cost:
                attributions.append(DriverAttribution(
                    shift=shift,
                    driver="COST_COMPETITIVENESS",
                    evidence=f"Cost dominated by {max_comp.upper()} component ({components[max_comp]:.1f} USD/t, {100*components[max_comp]/this_cost:.0f}% of total); associated with cost structure",
                    confidence="MEDIUM",
                    supporting_data=components,
                ))

    # --- B. Existing Asset Retirement ---
    if shift.shift_type in ("SHARE_DECREASE", "DISAPPEARANCE", "RETIREMENT"):
        if shift.technology in ("BF-BOF", "NG-DRI-EAF"):  # routes with existing capacity potential
            attributions.append(DriverAttribution(
                shift=shift,
                driver="EXISTING_ASSET_RETIREMENT",
                evidence="Share decrease is consistent with retirement of existing capacity; route-specific existing capacity is UNAVAILABLE in baseline",
                confidence="LOW",
                supporting_data={"existing_capacity": inputs.existing_capacity_per_route_mt.get(tech, 0.0)},
            ))

    # --- C. Resource Availability ---
    if pres.get("resource_pressure") is not None and pres["resource_pressure"] > 0.8:
        attributions.append(DriverAttribution(
            shift=shift,
            driver="RESOURCE_AVAILABILITY",
            evidence=f"High resource pressure ({pres['resource_pressure']:.1%}) is associated with potential production constraints",
            confidence="MEDIUM",
            supporting_data={"resource_pressure": pres["resource_pressure"]},
        ))

    # --- D. Scrap Availability ---
    if tech == "Scrap-EAF" and pres.get("scrap_pressure") is not None:
        if shift.shift_type in ("SHARE_DECREASE", "DISAPPEARANCE"):
            if pres["scrap_pressure"] > 0.9:
                attributions.append(DriverAttribution(
                    shift=shift,
                    driver="SCRAP_AVAILABILITY",
                    evidence=f"Scrap constraint near binding (pressure {pres['scrap_pressure']:.1%}) is associated with Scrap-EAF limitation; usable scrap may limit Scrap-EAF",
                    confidence="HIGH",
                    supporting_data={
                        "scrap_pressure": pres["scrap_pressure"],
                        "scrap_available": pres.get("scrap_available"),
                        "scrap_used": pres.get("scrap_used"),
                    },
                ))

    # --- E. Deployment Constraint ---
    if pres.get("deployment_binding"):
        attributions.append(DriverAttribution(
            shift=shift,
            driver="DEPLOYMENT_CONSTRAINT",
            evidence=f"NCAP deployment limit binding for {tech} in {year} is consistent with deployment constraint",
            confidence="HIGH",
            supporting_data={
                "deployment_available": pres.get("deployment_available"),
                "deployment_used": pres.get("deployment_used"),
            },
        ))

    # --- F. Emissions Constraint ---
    if pres.get("emission_pressure") is not None and pres["emission_pressure"] > 0.8:
        attributions.append(DriverAttribution(
            shift=shift,
            driver="EMISSIONS_CONSTRAINT",
            evidence=f"High emission intensity pressure ({pres['emission_pressure']:.1%} of base 2.54 tCO2/t) is associated with emissions constraint",
            confidence="MEDIUM",
            supporting_data={"emission_pressure": pres["emission_pressure"]},
        ))

    # --- G. Learning Effect ---
    if pres.get("learning_effect") is not None and pres["learning_effect"] > 0.1:
        attributions.append(DriverAttribution(
            shift=shift,
            driver="LEARNING_EFFECT",
            evidence=f"Endogenous learning reducing CAPEX by {pres['learning_effect']:.1%} is consistent with learning effect",
            confidence="MEDIUM",
            supporting_data={"learning_effect": pres["learning_effect"]},
        ))

    # --- H. Demand Growth ---
    demand_prev = inputs.demand_mt.get(year - 1, 0)
    demand_curr = inputs.demand_mt.get(year, 0)
    if demand_prev > 0:
        demand_growth = (demand_curr - demand_prev) / demand_prev
        if demand_growth > 0.05:  # >5% growth
            attributions.append(DriverAttribution(
                shift=shift,
                driver="DEMAND_GROWTH",
                evidence=f"Demand growth {demand_growth:.1%} year-over-year is associated with capacity expansion needs",
                confidence="MEDIUM",
                supporting_data={"demand_growth": demand_growth, "demand_prev": demand_prev, "demand_curr": demand_curr},
            ))

    # --- I. Data Availability Limitation ---
    # Always check for data limitations
    data_limits = []
    if cdecomp.get("scrap_cost_status") == "UNAVAILABLE":
        data_limits.append("SCRAP_INTENSITY_EXTERNAL_PENDING")
    if cdecomp.get("capex_status") == "UNAVAILABLE":
        data_limits.append("CAPEX_EXTERNAL_PENDING")
    if cdecomp.get("fom_status") == "UNAVAILABLE":
        data_limits.append("FOM_EXTERNAL_PENDING")
    if inputs.existing_capacity_per_route_mt.get(tech, 0.0) == 0.0:
        data_limits.append("EXISTING_ROUTE_CAPACITY_UNAVAILABLE")

    if data_limits:
        attributions.append(DriverAttribution(
            shift=shift,
            driver="DATA_AVAILABILITY_LIMITATION",
            evidence=f"Interpretation limited by: {', '.join(data_limits)}; may limit analytical confidence",
            confidence="HIGH",
            supporting_data={"limitations": data_limits},
        ))

    return attributions