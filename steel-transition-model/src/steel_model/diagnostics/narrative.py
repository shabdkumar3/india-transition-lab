"""
Pathway Narrative Generator (Step 15 §10).

Creates structured explanations with controlled vocabulary.

Output schema:
{
  "technology": "Scrap-EAF",
  "year": 2050,
  "change_type": "HIGH_SHARE",
  "share_change": 0.25,
  "associated_drivers": ["COST_COMPETITIVENESS"],
  "active_constraints": [],
  "limiting_data": ["SCRAP_INTENSITY_EXTERNAL_PENDING"],
  "interpretation_status": "DATA_LIMITED"
}
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Dict, Optional

from steel_model.diagnostics.pathway_record import PathwayRecord
from steel_model.diagnostics.shift_detection import TechnologyShift
from steel_model.diagnostics.driver_decomposition import DriverAttribution, classify_drivers
from steel_model.diagnostics.constraint_diagnostics import compute_constraint_pressures
from steel_model.diagnostics.cost_diagnostics import decompose_cost
from steel_model.optimization.model import BaselineInputs
from steel_model.optimization.results import BaselineMILPResult


@dataclass
class PathwayNarrative:
    """Structured pathway explanation."""
    technology: str
    year: int
    change_type: str
    share_change: float
    associated_drivers: List[str]
    active_constraints: List[str]
    limiting_data: List[str]
    interpretation_status: str  # "INTERPRETABLE", "DIAGNOSTIC", "DATA_LIMITED", "NOT_COMPARABLE"

    def to_dict(self) -> dict:
        return asdict(self)


def generate_narratives(
    inputs: BaselineInputs,
    result: BaselineMILPResult,
    shifts: List[TechnologyShift],
) -> List[PathwayNarrative]:
    """
    Generate pathway narratives for detected shifts.

    Integrates cost decomposition, constraint pressures, and driver attribution.
    """
    cost_decomp = decompose_cost(inputs, result)
    pressures = compute_constraint_pressures(inputs, result)
    pathway_records = []  # Could be built from pathway_record module

    narratives = []

    for shift in shifts:
        # Classify drivers
        drivers = classify_drivers(
            shift, inputs, result, cost_decomp, pressures, pathway_records
        )

        # Extract driver names
        driver_names = [d.driver for d in drivers]

        # Identify active constraints
        active_constraints = []
        pres = pressures.get((shift.technology, shift.year), {})
        if pres.get("capacity_binding"):
            active_constraints.append("CAPACITY")
        if pres.get("deployment_binding"):
            active_constraints.append("DEPLOYMENT")
        if pres.get("scrap_binding"):
            active_constraints.append("SCRAP")
        if pres.get("emission_pressure", 0) > 0.8:
            active_constraints.append("EMISSIONS")

        # Extract limiting data
        cdecomp = cost_decomp.get((shift.technology, shift.year), {})
        limiting_data = []
        if cdecomp.get("scrap_cost_status") == "UNAVAILABLE":
            limiting_data.append("SCRAP_INTENSITY_EXTERNAL_PENDING")
        if cdecomp.get("capex_status") == "UNAVAILABLE":
            limiting_data.append("CAPEX_EXTERNAL_PENDING")
        if cdecomp.get("fom_status") == "UNAVAILABLE":
            limiting_data.append("FOM_EXTERNAL_PENDING")
        if inputs.existing_capacity_per_route_mt.get(shift.technology, 0.0) == 0.0:
            limiting_data.append("EXISTING_ROUTE_CAPACITY_UNAVAILABLE")

        # Determine interpretation status
        if limiting_data:
            interpretation_status = "DATA_LIMITED"
        elif shift.technology not in inputs.routes:
            interpretation_status = "NOT_COMPARABLE"
        elif active_constraints:
            interpretation_status = "DIAGNOSTIC"
        else:
            interpretation_status = "INTERPRETABLE"

        # Share change magnitude
        share_change = 0.0
        # Would need previous year share - simplified here
        if shift.previous_value is not None and shift.current_value is not None:
            share_change = shift.current_value - shift.previous_value

        narrative = PathwayNarrative(
            technology=shift.technology,
            year=shift.year,
            change_type=shift.shift_type,
            share_change=share_change,
            associated_drivers=driver_names,
            active_constraints=active_constraints,
            limiting_data=limiting_data,
            interpretation_status=interpretation_status,
        )
        narratives.append(narrative)

    return narratives


def narratives_to_csv_rows(narratives: List[PathwayNarrative]) -> List[dict]:
    """Convert narratives to CSV-friendly rows."""
    rows = []
    for n in narratives:
        rows.append({
            "technology": n.technology,
            "year": n.year,
            "change_type": n.change_type,
            "share_change": n.share_change,
            "associated_drivers": ";".join(n.associated_drivers),
            "active_constraints": ";".join(n.active_constraints),
            "limiting_data": ";".join(n.limiting_data),
            "interpretation_status": n.interpretation_status,
        })
    return rows