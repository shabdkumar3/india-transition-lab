"""
ML Estimation Layer (Step 7A/7B) — specification only.

The MILP remains the DECISION ENGINE; ML is an ESTIMATION LAYER. Only the
approved module M1 (electrolyser learning-curve estimator, Option A) is
exposed here, and only as its interface specification. No training code.

Approved modules (ML_SYSTEM_SPEC.md, M1_INTERFACE_SPEC.md):
  M1 — electrolyser learning exponent b_elec (STATISTICAL_MODEL_PREFERRED)
"""

from steel_model.ml.m1_spec import (
    CAPEX_ELEC_0_USD_KWE,
    MIN_OBSERVATIONS_FOR_FIT,
    MIN_TIME_SPAN_YEARS,
    M1Output,
    M1Provenance,
    M1Segment,
    m1_trajectory,
)
from steel_model.ml.m1_estimator import fit_m1_estimator

__all__ = [
    "CAPEX_ELEC_0_USD_KWE",
    "MIN_OBSERVATIONS_FOR_FIT",
    "MIN_TIME_SPAN_YEARS",
    "M1Output",
    "M1Provenance",
    "M1Segment",
    "m1_trajectory",
    "fit_m1_estimator",
]
