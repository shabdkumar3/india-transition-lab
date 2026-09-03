"""
Vol.4 Comparison Integration (Step 15 §11).

Uses Step 14 benchmark records to connect model differences to:
- model configuration
- source-supported inputs
- missing inputs
- active constraints
- definition differences
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from steel_model.benchmark.engine import BenchmarkEngine
from steel_model.benchmark.vol4_register import Vol4Register
from steel_model.optimization.model import BaselineInputs, BaselineMILPResult
from steel_model.diagnostics.pathway_record import PathwayRecords


@dataclass
class Vol4DifferenceLink:
    """Link between a Vol.4 difference and diagnostic evidence."""
    metric: str
    year: int
    scenario: str
    model_value: float
    vol4_value: float
    difference_pct: float
    comparison_status: str
    associated_drivers: List[str]
    limiting_data: List[str]
    active_constraints: List[str]
    interpretation: str


def integrate_vol4_differences(
    benchmark_rows: List[dict],
    pathway_records: PathwayRecords,
    inputs: BaselineInputs,
    result: BaselineMILPResult,
) -> List[Vol4DifferenceLink]:
    """
    Connect Vol.4 benchmark differences to diagnostic evidence.

    For each MATERIAL_DIFFERENCE or NOT_COMPARABLE row in the benchmark,
    identify associated drivers and limiting data from the diagnostics.
    """
    links = []

    for row in benchmark_rows:
        if row.get("comparison_status") not in ("MATERIAL_DIFFERENCE", "NOT_COMPARABLE", "UNRESOLVED"):
            continue

        metric = row["metric"]
        year = row["year"]
        scenario = row["scenario"]

        # Map metric to diagnostic drivers
        drivers = []
        limiting_data = []
        active_constraints = []

        if metric in ("technology_share", "scrap_share_production"):
            if "SCRAP_INTENSITY_EXTERNAL_PENDING" in str(row.get("limitation", "")):
                drivers.append("SCRAP_ACCOUNTING")
                limiting_data.append("SCRAP_INTENSITY_EXTERNAL_PENDING")
            if "existing_fleet" in str(row.get("limitation", "")).lower() or "existing capacity" in str(row.get("limitation", "")).lower():
                drivers.append("EXISTING_ASSET_RETIREMENT")
                limiting_data.append("EXISTING_ROUTE_CAPACITY_UNAVAILABLE")
            if "H2-DRI" in str(row.get("limitation", "")):
                drivers.append("TECHNOLOGY_ECONOMICS")
                limiting_data.append("H2_DRI_FULL_PLANT_ECONOMICS_EXTERNAL_PENDING")

        elif metric in ("co2_intensity", "co2_total"):
            if "CCUS" in str(row.get("limitation", "")):
                drivers.append("TECHNOLOGY_ECONOMICS")
                limiting_data.append("NO_CCUS_REPRESENTATION")
            if "cornered" in str(row.get("limitation", "")):
                drivers.append("SCRAP_ACCOUNTING")
                limiting_data.append("SCRAP_INTENSITY_EXTERNAL_PENDING")

        elif metric == "green_h2_steel":
            drivers.append("TECHNOLOGY_ECONOMICS")
            limiting_data.append("H2_DRI_FULL_PLANT_ECONOMICS_EXTERNAL_PENDING")
            limiting_data.append("M1_DEFERRED")

        elif metric in ("final_energy_steel", "electricity_steel", "coal_use_steel"):
            limiting_data.append("CAPTIVE_BOUNDARY_MISMATCH")
            if "coal" in metric:
                limiting_data.append("COAL_INTENSITIES_EXTERNAL_PENDING")

        elif metric in ("system_cost_discounted", "investment_industry_usd_trillion"):
            limiting_data.append("ANNUALISED_VS_OVERNIGHT_CAPEX_BASIS")
            limiting_data.append("INDUSTRY_VS_STEEL_BOUNDARY")
            if "investment" in metric:
                limiting_data.append("VOL4_INTERNAL_CONTRADICTION_CPS_3.4_VS_4.5")

        elif metric == "existing_fleet_route_capacity":
            limiting_data.append("ROUTE_CAPACITY_NOT_PUBLISHED_IN_VOL4")

        # Active constraints from pathway records
        # (simplified - would integrate with constraint diagnostics)
        for route in inputs.routes:
            if route == "Scrap-EAF" and "SCRAP" in str(row.get("limitation", "")).upper():
                active_constraints.append("SCRAP")

        interpretation = _build_interpretation(metric, drivers, limiting_data, row.get("comparison_status", ""))

        links.append(Vol4DifferenceLink(
            metric=metric,
            year=year,
            scenario=scenario,
            model_value=row.get("ours", 0.0) or 0.0,
            vol4_value=row.get("vol4", 0.0) or 0.0,
            difference_pct=row.get("difference_percent", 0.0) or 0.0,
            comparison_status=row.get("comparison_status", ""),
            associated_drivers=drivers,
            limiting_data=limiting_data,
            active_constraints=active_constraints,
            interpretation=interpretation,
        ))

    return links


def _build_interpretation(
    metric: str,
    drivers: List[str],
    limiting_data: List[str],
    status: str,
) -> str:
    """Build structured interpretation text."""
    parts = []

    if status == "MATERIAL_DIFFERENCE":
        parts.append(f"Material difference in {metric}.")
    elif status == "NOT_COMPARABLE":
        parts.append(f"{metric} not comparable to Vol.4 due to definition/boundary mismatch.")
    elif status == "UNRESOLVED":
        parts.append(f"{metric} unresolved — Vol.4 does not publish a numeric value.")

    if drivers:
        parts.append(f"Associated drivers: {', '.join(drivers)}.")
    if limiting_data:
        parts.append(f"Limiting data: {', '.join(limiting_data)}.")

    return " ".join(parts)


def links_to_csv_rows(links: List[Vol4DifferenceLink]) -> List[dict]:
    """Convert to CSV rows."""
    rows = []
    for l in links:
        rows.append({
            "metric": l.metric,
            "year": l.year,
            "scenario": l.scenario,
            "model_value": l.model_value,
            "vol4_value": l.vol4_value,
            "difference_pct": l.difference_pct,
            "comparison_status": l.comparison_status,
            "associated_drivers": ";".join(l.associated_drivers),
            "limiting_data": ";".join(l.limiting_data),
            "active_constraints": ";".join(l.active_constraints),
            "interpretation": l.interpretation,
        })
    return rows