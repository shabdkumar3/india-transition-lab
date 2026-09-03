"""
Results assembly for the baseline MILP (Step 8).

Decodes the raw solver vector x back into named quantities and attaches
the diagnostic / interpretation metadata required by the Step 8 spec:

  - technology_enabled / reason_disabled for ALL six routes
  - existing-capacity data availability flags
  - resource use per resource (ore, scrap, coal, gas, H2, electricity)
  - emissions split: process / combustion / total (no double counting)
  - explicit interpretation rules for disabled routes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from steel_model.optimization.variables import VariableIndex
from steel_model.scrap.scrap_engine import ScrapAccounting

DISABLED_REASON = "EXTERNAL_PENDING_FULL_PLANT_ECONOMICS"


@dataclass
class BaselineMILPResult:
    """Full result object for one baseline MILP run."""

    # solver
    solver: str = "HiGHS (scipy.optimize.milp)"
    status: int = -1
    status_label: str = "not-run"
    message: str = ""
    objective_value: Optional[float] = None

    # structure
    routes: List[str] = field(default_factory=list)
    all_routes: List[str] = field(default_factory=list)
    years: List[int] = field(default_factory=list)
    resources: List[str] = field(default_factory=list)
    demand_mt: Dict[int, float] = field(default_factory=dict)

    # decision variables decoded from x
    ncap_mt: Dict[str, Dict[int, float]] = field(default_factory=dict)
    cap_mt: Dict[str, Dict[int, float]] = field(default_factory=dict)
    act_mt: Dict[str, Dict[int, float]] = field(default_factory=dict)
    ret_mt: Dict[str, Dict[int, float]] = field(default_factory=dict)
    res_use: Dict[str, Dict[int, float]] = field(default_factory=dict)
    co2_total_mt: Dict[int, float] = field(default_factory=dict)

    # derived indicators
    technology_status: Dict[str, dict] = field(default_factory=dict)
    existing_capacity_data_available: bool = False
    aggregate_capacity_context_mt: Optional[float] = None
    technology_capacity_data: str = "unavailable"
    data_limitations: List[str] = field(default_factory=list)
    interpretation: List[str] = field(default_factory=list)

    # Step 13 remediation: provenance + fleet/technology-space diagnostics.
    intensity_status: Dict[tuple, dict] = field(default_factory=dict)
    provenance_gating: dict = field(default_factory=dict)
    existing_route_capacity_available: bool = False
    route_transition_interpretability: bool = False
    technology_space_completeness: str = "INCOMPLETE"
    scrap_intensity_status: Dict[str, dict] = field(default_factory=dict)
    economically_complete: Dict[str, bool] = field(default_factory=dict)

    # provenance retained from the source records (review item 2):
    # every parameter carries its provenance through to the result so
    # downstream consumers never need to re-derive it.
    discount_rate_provenance: str = ""
    availability_provenance: str = ""
    availability_provenance_by_route: Dict[str, str] = field(default_factory=dict)
    resource_price_provenance: Dict[str, str] = field(default_factory=dict)

    # Step 9: dynamic scrap accounting (None when MODE A / disabled).
    scrap_accounting: Optional[ScrapAccounting] = None
    scrap_provenance: Dict[str, str] = field(default_factory=dict)

    # Step 11: endogenous learning (None when MODE A / disabled).
    learning_history: Optional[dict] = None
    learning_provenance: Dict[str, str] = field(default_factory=dict)

    # ---- helpers ------------------------------------------------------

    def production_mt(self, route: str) -> Dict[int, float]:
        """ACT for a route across years (0 for disabled routes)."""
        return self.act_mt.get(route, {t: 0.0 for t in self.years})

    def production_share(self, route: str) -> Dict[int, float]:
        """Route share of annual demand; NaN-safe 0 when demand is 0."""
        out = {}
        for t in self.years:
            d = self.demand_mt.get(t, 0.0)
            out[t] = (self.act_mt.get(route, {}).get(t, 0.0) / d) if d > 0 else 0.0
        return out

    def emissions(self) -> Dict[str, Dict[int, float]]:
        """
        Emissions split. The LP only carries CO2 total (process + combustion
        summed at registry intensity level). Per-component totals are
        reconstructed here from ACT x intensities — reported separately so
        process and combustion are never conflated or double counted.
        """
        proc = {t: 0.0 for t in self.years}
        comb = {t: 0.0 for t in self.years}
        for i in self.routes:
            for t in self.years:
                a = self.act_mt.get(i, {}).get(t, 0.0)
                proc[t] += a * self._route_process_intensity.get(i, 0.0)
                comb[t] += a * self._route_combustion_intensity.get(i, 0.0)
        return {
            "process": proc,
            "combustion": comb,
            "total": self.co2_total_mt,
        }

    def total_capacity_mt(self, year: int) -> float:
        return sum(self.cap_mt.get(i, {}).get(year, 0.0) for i in self.routes)

    def total_activity_mt(self, year: int) -> float:
        return sum(self.act_mt.get(i, {}).get(year, 0.0) for i in self.routes)

    # internal: emission intensities for the split reconstruction
    _route_process_intensity: Dict[str, float] = field(default_factory=dict)
    _route_combustion_intensity: Dict[str, float] = field(default_factory=dict)


def build_result(
    index: VariableIndex,
    inputs: "BaselineInputs",
    solver_result,
) -> BaselineMILPResult:
    """Decode a SolverResult into a fully populated BaselineMILPResult."""
    res = BaselineMILPResult()
    res.routes = list(inputs.routes)
    res.all_routes = list(inputs.all_routes)
    res.years = list(inputs.years)
    res.resources = list(inputs.resources)
    res.demand_mt = dict(inputs.demand_mt)
    res._route_process_intensity = dict(inputs.process_emission)
    res._route_combustion_intensity = dict(inputs.combustion_emission)

    # Retain provenance from inputs (which read it from config records).
    res.discount_rate_provenance = inputs.discount_rate_provenance
    res.availability_provenance = inputs.availability_provenance
    res.availability_provenance_by_route = dict(inputs.availability_provenance_by_route)
    res.resource_price_provenance = dict(inputs.resource_price_provenance)

    res.solver = solver_result.solver
    res.status = solver_result.status
    res.status_label = solver_result.status_label
    res.message = solver_result.message
    res.objective_value = solver_result.objective_value

    if solver_result.x is not None:
        x = solver_result.x
        for i in inputs.routes:
            res.ncap_mt[i] = {t: float(x[index.idx("NCAP", i, t)]) for t in inputs.years}
            res.cap_mt[i] = {t: float(x[index.idx("CAP", i, t)]) for t in inputs.years}
            res.act_mt[i] = {t: float(x[index.idx("ACT", i, t)]) for t in inputs.years}
            res.ret_mt[i] = {t: float(x[index.idx("RET", i, t)]) for t in inputs.years}
        for r in inputs.resources:
            res.res_use[r] = {t: float(x[index.idx("RES", r, t)]) for t in inputs.years}
        res.co2_total_mt = {t: float(x[index.idx("CO2", "", t)]) for t in inputs.years}

        # Step 9 (MODE B): post-solve scrap stock-flow accounting from the
        # ACT solution and the scrap resource use. Physical quantities stay
        # in Mt; provenance for every scrap parameter is retained.
        if inputs.scrap_engine is not None:
            act_by_route = {
                i: {t: float(x[index.idx("ACT", i, t)]) for t in inputs.years}
                for i in inputs.routes
            }
            scrap_use = {
                t: float(res.res_use.get("scrap", {}).get(t, 0.0))
                for t in inputs.years
            }
            accounting = inputs.scrap_engine.account(act_by_route, scrap_use, inputs.years)
            res.scrap_accounting = accounting
            res.scrap_provenance = dict(accounting.provenance)

    # ---- technology status (all six routes) ----
    for route in inputs.all_routes:
        enabled = route in inputs.routes
        res.technology_status[route] = {
            "technology_enabled": enabled,
            "reason_disabled": None if enabled else DISABLED_REASON,
        }

    # ---- existing capacity data availability ----
    res.existing_capacity_data_available = inputs.existing_capacity_data_available
    res.aggregate_capacity_context_mt = inputs.aggregate_capacity_context_mt
    res.technology_capacity_data = "unavailable" if not inputs.existing_capacity_data_available else "available"
    res.data_limitations = list(inputs.data_limitations)

    # ---- Step 13 remediation: provenance + fleet/technology diagnostics ----
    res.intensity_status = dict(inputs.intensity_status)
    res.provenance_gating = dict(inputs.provenance_gating)
    res.existing_route_capacity_available = inputs.existing_route_capacity_available
    res.route_transition_interpretability = inputs.route_transition_interpretability
    res.technology_space_completeness = inputs.technology_space_completeness

    # Economically-complete flag per route: the route is enabled AND its scrap
    # intensity resolves to a real coefficient (non-null). A null scrap
    # intensity (EXTERNAL_PENDING) means the scrap cost term is absent and the
    # route's production economics are incomplete.
    for route in inputs.all_routes:
        enabled = route in inputs.routes
        scrap_st = inputs.intensity_status.get((route, "scrap"))
        if not enabled:
            res.economically_complete[route] = False
            res.scrap_intensity_status[route] = {
                "status": "not_represented",
                "value": None,
                "provenance": None,
            }
            continue
        res.scrap_intensity_status[route] = (
            dict(scrap_st) if scrap_st is not None
            else {"status": "missing_record", "value": None, "provenance": None}
        )
        res.economically_complete[route] = (
            res.scrap_intensity_status[route].get("value") is not None
        )

    # ---- interpretation rules: only emit for truly absent routes ----
    res.interpretation = []
    all_routes = {"H2-DRI-EAF", "Coal-DRI-EAF", "Coal-DRI-IF", "BF-BOF", "NG-DRI-EAF", "Scrap-EAF"}
    absent_routes = all_routes - set(res.routes)

    if "H2-DRI-EAF" in absent_routes:
        res.interpretation.append(
            "H2_DRI_EAF = 0 is a DATA AVAILABILITY LIMITATION, NOT an optimization "
            "conclusion: H2-DRI-EAF full-plant economics remain EXTERNAL_PENDING and "
            "the route is not represented in this baseline optimization."
        )
    coal_absent = {"Coal-DRI-EAF", "Coal-DRI-IF"} & absent_routes
    if coal_absent:
        names = " and ".join(f"{r.replace('-', '_')} = 0" for r in sorted(coal_absent))
        res.interpretation.append(
            f"{names} are data-availability results (PROJECT_PROPOSAL / EXTERNAL_PENDING "
            f"economics), not cost conclusions: {', '.join(sorted(coal_absent))} "
            "are not represented in this optimization."
        )
    if "H2-DRI-EAF" in res.routes:
        h2_share_2050 = res.production_share("H2-DRI-EAF").get(2050, 0.0)
        if h2_share_2050 < 0.001:
            res.interpretation.append(
                "H2-DRI-EAF enters this optimization with PROJECT_PROPOSAL economics "
                "($64.2/t CAPEX, $27.4/t FOM). Its share of 0% reflects cost-competitiveness "
                "vs Coal-DRI-IF ($321/t), not a data absence. A carbon price or green-H2 "
                "subsidy would change this conclusion."
            )
    # Only flag route-transition uninterpretability if there are truly no existing capacities.
    if not res.route_transition_interpretability and absent_routes == all_routes:
        res.interpretation.append(
            "New capacity pathway is not physically interpretable as a "
            "replacement of the actual 2024 Indian fleet because route-specific "
            "existing capacity is unresolved."
        )
    for route in res.routes:
        if not res.economically_complete.get(route, False):
            res.interpretation.append(
                f"Route {route} enters optimization with its scrap intensity "
                "unresolved (EXTERNAL_PENDING, coefficient 0): its production cost "
                "is under-stated because the scrap cost term is absent. This is a "
                "data limitation, NOT a cost conclusion."
            )
    if res.scrap_accounting is not None:
        res.interpretation.append(
            "Step 9 MODE B: dynamic stock-flow scrap accounting is active. EOL "
            "scrap, collected scrap and usable scrap emerge from historical and "
            "modelled production cohorts (MODEL_FORMULATION §6). This is a model "
            "enrichment linking historical steel use to future scrap availability "
            "— it does NOT claim the Vol.4 Scrap-EAF pathway is wrong. Scrap "
            "parameters are PROJECT_PROPOSAL; imports are excluded (allowance 0)."
        )
    return res
