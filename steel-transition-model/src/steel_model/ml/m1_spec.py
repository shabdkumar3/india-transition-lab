"""
M1 output specification — electrolyser learning-curve estimator (Step 7B).

APPROVED_AS_ELECTROLYSER_LEARNING (Option A): M1 learns ONLY the electrolyser
component learning exponent b_elec. This module defines the exact output
schema consumed by the outer sequential learning loop in Mode B.

AUDIT ONLY: no training / fitting code lives here. Implementation is deferred
to Step 11. The schema is the interface contract (M1_INTERFACE_SPEC.md).
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator

MIN_OBSERVATIONS_FOR_FIT = 15
MIN_TIME_SPAN_YEARS = 10
CAPEX_ELEC_0_USD_KWE = 452.0  # frozen IEA 2020 central, 2019 USD


class M1Provenance(str, Enum):
    """Mandatory provenance for M1 outputs.

    Global statistical estimate applied to an India scenario. This label is
    mandatory until India-specific electrolyser learning evidence exists;
    it must NEVER be silently relabelled "Indian learning rate".
    """

    GLOBAL_STATISTICAL_ESTIMATE_APPLIED_TO_INDIA_SCENARIO = (
        "GLOBAL_STATISTICAL_ESTIMATE_APPLIED_TO_INDIA_SCENARIO"
    )


class M1Segment(str, Enum):
    ALKALINE = "alkaline"
    PEM = "pem"
    POOLED_WITH_INDICATOR = "pooled_with_indicator"


class M1Output(BaseModel):
    """Exact output contract of the M1 module.

    The schema-level guarantee: extra="forbid" means technology-mix,
    production, capacity, share, ACT, NCAP or emissions fields are REJECTED
    outright. M1 can only ever return the electrolyser learning parameter set.
    """

    model_config = {"extra": "forbid"}

    # learned quantity
    b_elec: float = Field(..., gt=0.0, description="Learning exponent, dimensionless")
    LR_elec: float = Field(..., gt=0.0, lt=1.0, description="Learning rate = 1 - 2^(-b_elec)")
    uncertainty_interval: Tuple[float, float] = Field(
        ...,
        description="(b_min, b_max) prediction interval; must contain b_elec",
    )
    # provenance — fixed enum, mandatory
    provenance: M1Provenance = Field(
        default=M1Provenance.GLOBAL_STATISTICAL_ESTIMATE_APPLIED_TO_INDIA_SCENARIO
    )
    # data / fit metadata
    source_ids: List[str] = Field(..., min_length=1)
    n_observations: int = Field(..., ge=MIN_OBSERVATIONS_FOR_FIT)
    time_span: str = Field(..., description="e.g. '2000-2024'")
    segment: M1Segment = Field(...)
    model_form: str = Field(default="OLS log-log (Wright's law)")
    currency_basis: str = Field(default="2019 USD")
    # validation summary (populated at fit time, Step 11)
    validation_metrics: Dict[str, float] = Field(default_factory=dict)
    # mode gating — M1 disabled in Mode A
    mode: str = Field(default="MODE_B")

    @model_validator(mode="after")
    def _check_lr_consistency(self) -> "M1Output":
        expected_lr = 1.0 - 2.0 ** (-self.b_elec)
        if abs(expected_lr - self.LR_elec) > 1e-9:
            raise ValueError(
                f"LR_elec must equal 1 - 2^(-b_elec) = {expected_lr:.6f}; got {self.LR_elec}"
            )
        lo, hi = self.uncertainty_interval
        if not (lo <= self.b_elec <= hi):
            raise ValueError(f"b_elec must lie within uncertainty_interval; got b={self.b_elec}, interval=({lo}, {hi})")
        if not (0.0 < lo < hi):
            raise ValueError(f"uncertainty_interval must be strictly ordered in (0, inf); got ({lo}, {hi})")
        return self

    @field_validator("mode")
    @classmethod
    def _mode_must_be_b(cls, v: str) -> str:
        if v != "MODE_B":
            raise ValueError("M1 is disabled in Mode A; mode must be MODE_B")
        return v

    @field_validator("source_ids")
    @classmethod
    def _source_ids_non_empty(cls, v: List[str]) -> List[str]:
        cleaned = [s for s in v if s and s.strip()]
        if not cleaned:
            raise ValueError("source_ids must contain at least one non-empty identifier")
        return cleaned


def m1_trajectory(cumcap_t: float, cumcap_0: float, b_elec: float, capex_0: float = CAPEX_ELEC_0_USD_KWE) -> float:
    """Wright's-law electrolyser CAPEX trajectory (Mode B, t >= 2025).

    CAPEX_elec,t = CAPEX_elec,0 * (CumCap_t / CumCap_0)^(-b_elec)
    """
    if cumcap_0 <= 0:
        raise ValueError("cumcap_0 must be > 0")
    if cumcap_t <= 0:
        raise ValueError("cumcap_t must be > 0")
    if b_elec <= 0:
        raise ValueError("b_elec must be > 0 (schema enforces gt=0.0 on M1Output)")
    return capex_0 * (cumcap_t / cumcap_0) ** (-b_elec)
