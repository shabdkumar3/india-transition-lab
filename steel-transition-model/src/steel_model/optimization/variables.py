"""
Decision variable index for the baseline MILP.

Flat contiguous vector layout (blocks in order):
  NCAP[i,t]  new capacity commissioned (Mt capacity/yr)
  CAP[i,t]   installed operating capacity (Mt capacity/yr)
  ACT[i,t]   annual production (Mt steel/yr)
  RET[i,t]   retirement of new capacity (Mt capacity/yr)
  RES[r,t]   resource consumption (physical units per registry)
  CO2[t]     total CO2 emissions (Mt CO2/yr)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class VariableIndex:
    """Maps (block, item, year) -> flat column index in the LP vector."""

    routes: List[str]
    resources: List[str]
    years: List[int]
    _loc: Dict[Tuple[str, str, int], int] = field(default_factory=dict)
    _n: int = 0

    def build(self) -> "VariableIndex":
        n = 0
        self._loc = {}
        # Route-scoped blocks: NCAP, CAP, ACT, RET
        for block in ("NCAP", "CAP", "ACT", "RET"):
            for i in self.routes:
                for t in self.years:
                    self._loc[(block, i, t)] = n
                    n += 1
        # Resource block
        for r in self.resources:
            for t in self.years:
                self._loc[("RES", r, t)] = n
                n += 1
        # Emissions block
        for t in self.years:
            self._loc[("CO2", "", t)] = n
            n += 1
        self._n = n
        return self

    def idx(self, block: str, item: str, year: int) -> int:
        return self._loc[(block, item, year)]

    def n_vars(self) -> int:
        return self._n


def build_bounds(
    index: VariableIndex,
    start_year: Dict[str, int],
    lifetime: int,
    deployment_dynamics_enabled: bool = False,
    construction_lead_time_years: Dict[str, int] = None,
    ncap_cutoff_years: Dict[str, int] = None,
) -> Tuple[list, list]:
    """
    Bounds for all variables (all lb=0; ub=+inf except start-year/lead-time zeros).

    Start-year/Lead-time rule: a technology cannot be commissioned before its allowed
    commissioning start year plus lead time -> NCAP[i,t] = 0 for t < start_year[i] + lead_time.
    RET[i,t] is implied zero when t - lifetime < start_year[i] + lead_time.

    Mode B cutoff rule: NCAP[i,t] = 0 for t > ncap_cutoff_years[i].
    This implements Vol.4 technology availability restrictions (e.g. "no new capacity
    addition after 2030"). Existing capacity is unaffected — it survives to natural
    retirement via the CAP evolution constraints in constraints.py.
    Source: MODE_B_APPROVAL_GATES.md — Gate A approved 2026-08-14.
    """
    lb = [0.0] * index.n_vars()
    ub = [float("inf")] * index.n_vars()
    for i in index.routes:
        sy = start_year.get(i, 2024)
        lead_time = 0
        if deployment_dynamics_enabled and construction_lead_time_years:
            lead_time = construction_lead_time_years.get(i, 0)

        # If deployment dynamics are enabled, commissioning is delayed by lead time
        # relative to the model start year, but can occur on or after the commercialization
        # start year (since construction can begin in t = T_comm - L_i, which is feasible
        # if T_comm - L_i >= T_model_start).
        # Therefore, earliest commissioning year = max(T_comm, T_model_start + L_i).
        earliest_year = max(sy, index.years[0] + lead_time)
        for t in index.years:
            if t < earliest_year:
                ub[index.idx("NCAP", i, t)] = 0.0
            if (t - lifetime) < earliest_year:
                ub[index.idx("RET", i, t)] = 0.0

        # Mode B upper-bound cutoff: NCAP[i,t] = 0 for all t > cutoff_year.
        # Gate A approved: "no new capacity after year X" = NCAP[i,t] = 0 for t > X.
        # Existing capacity is NOT affected by this bound.
        if ncap_cutoff_years and i in ncap_cutoff_years:
            cutoff = ncap_cutoff_years[i]
            for t in index.years:
                if t > cutoff:
                    ub[index.idx("NCAP", i, t)] = 0.0

    return lb, ub
