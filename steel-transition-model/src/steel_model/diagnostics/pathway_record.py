"""
Technology Pathway Record (Step 15 §2).

Machine-readable record per technology × year with all available
model outputs and explicit status for missing/incomplete data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class PathwayRecord:
    """
    Single technology-year record.

    Fields that the current model cannot meaningfully calculate are set to
    None with an explicit status string indicating why.
    """
    technology: str
    year: int

    # Production & capacity
    production_mt: Optional[float] = None
    share: Optional[float] = None
    installed_capacity_mt: Optional[float] = None
    new_capacity_mt: Optional[float] = None
    retired_capacity_mt: Optional[float] = None

    # Cost components (where computable)
    effective_cost_usd_per_t: Optional[float] = None
    capex_contribution_usd_per_t: Optional[float] = None
    fom_contribution_usd_per_t: Optional[float] = None
    vom_contribution_usd_per_t: Optional[float] = None
    fuel_contribution_usd_per_t: Optional[float] = None
    resource_contribution_usd_per_t: Optional[float] = None
    electricity_contribution_usd_per_t: Optional[float] = None
    carbon_contribution_usd_per_t: Optional[float] = None

    # Constraints & pressures
    deployment_constraint_binding: Optional[bool] = None
    scrap_constraint_binding: Optional[bool] = None
    resource_pressure: Optional[float] = None
    emission_pressure: Optional[float] = None

    # Learning & data
    learning_effect: Optional[float] = None
    data_completeness: str = "COMPLETE"
    provenance: str = ""

    def to_dict(self) -> dict:
        """Convert to dict with stringified None for JSON/CSV export."""
        return {
            k: (v if v is not None else "UNAVAILABLE")
            for k, v in self.__dict__.items()
        }


@dataclass
class PathwayRecords:
    """Collection of pathway records with export helpers."""
    records: List[PathwayRecord] = field(default_factory=list)

    def add(self, record: PathwayRecord) -> None:
        self.records.append(record)

    def get(self, technology: str, year: int) -> Optional[PathwayRecord]:
        for r in self.records:
            if r.technology == technology and r.year == year:
                return r
        return None

    def by_technology(self, technology: str) -> List[PathwayRecord]:
        return [r for r in self.records if r.technology == technology]

    def by_year(self, year: int) -> List[PathwayRecord]:
        return [r for r in self.records if r.year == year]

    def to_csv_rows(self) -> List[dict]:
        """Export as flat rows for CSV writing."""
        return [r.to_dict() for r in self.records]


def build_pathway_records(inputs: "BaselineInputs", result: "BaselineMILPResult") -> PathwayRecords:
    """
    Build pathway records from model inputs and results.

    This function computes all available fields and explicitly marks
    UNAVAILABLE fields with their limitation reason in data_completeness.
    """
    from steel_model.diagnostics.cost_diagnostics import decompose_cost
    from steel_model.diagnostics.constraint_diagnostics import compute_constraint_pressures

    out = PathwayRecords()
    years = list(inputs.years)
    discount_rate = inputs.discount_rate
    start_year = inputs.start_year

    # Pre-compute cost decompositions per route × year
    cost_decomp = decompose_cost(inputs, result)

    # Pre-compute constraint pressures
    pressures = compute_constraint_pressures(inputs, result)

    for route in inputs.all_routes:
        enabled = route in inputs.routes

        for t in years:
            # Base production data
            prod = result.act_mt.get(route, {}).get(t, 0.0)
            cap = result.cap_mt.get(route, {}).get(t, 0.0)
            ncap = result.ncap_mt.get(route, {}).get(t, 0.0)
            ret = result.ret_mt.get(route, {}).get(t, 0.0)

            demand = inputs.demand_mt.get(t, 0.0)
            share = (prod / demand) if demand > 0 else 0.0

            # Cost decomposition
            cdecomp = cost_decomp.get((route, t), {})

            # Constraint pressures
            pres = pressures.get((route, t), {})

            # Data completeness assessment
            dc_parts = []
            if not enabled:
                dc_parts.append("ROUTE_DISABLED_EXTERNAL_PENDING")
            if cdecomp.get("scrap_cost_status") == "UNAVAILABLE":
                dc_parts.append("SCRAP_INTENSITY_EXTERNAL_PENDING")
            if cdecomp.get("capex_status") == "UNAVAILABLE":
                dc_parts.append("CAPEX_EXTERNAL_PENDING")
            if cdecomp.get("fom_status") == "UNAVAILABLE":
                dc_parts.append("FOM_EXTERNAL_PENDING")
            if inputs.existing_capacity_per_route_mt.get(route, 0.0) == 0.0:
                dc_parts.append("EXISTING_ROUTE_CAPACITY_UNAVAILABLE")

            data_completeness = ";".join(dc_parts) if dc_parts else "COMPLETE"

            rec = PathwayRecord(
                technology=route,
                year=t,
                production_mt=prod if enabled else None,
                share=share if enabled else None,
                installed_capacity_mt=cap if enabled else None,
                new_capacity_mt=ncap if enabled else None,
                retired_capacity_mt=ret if enabled else None,
                effective_cost_usd_per_t=cdecomp.get("total"),
                capex_contribution_usd_per_t=cdecomp.get("capex"),
                fom_contribution_usd_per_t=cdecomp.get("fom"),
                vom_contribution_usd_per_t=cdecomp.get("vom"),
                fuel_contribution_usd_per_t=cdecomp.get("fuel"),
                resource_contribution_usd_per_t=cdecomp.get("resource"),
                electricity_contribution_usd_per_t=cdecomp.get("electricity"),
                carbon_contribution_usd_per_t=cdecomp.get("carbon"),
                deployment_constraint_binding=pres.get("deployment_binding"),
                scrap_constraint_binding=pres.get("scrap_binding"),
                resource_pressure=pres.get("resource_pressure"),
                emission_pressure=pres.get("emission_pressure"),
                learning_effect=pres.get("learning_effect"),
                data_completeness=data_completeness,
                provenance="BaselineInputs+BaselineMILPResult",
            )
            out.add(rec)

    return out