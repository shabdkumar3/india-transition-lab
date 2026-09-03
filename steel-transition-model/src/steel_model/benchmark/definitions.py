"""
Definition harmonization and comparison classes (Step 14).

Every benchmark comparison must state: our quantity, Vol.4 quantity, unit,
definition, time, scenario, source, comparability (YES/NO) and reason. This
module centralises (a) the comparison classes with DOCUMENTED thresholds and
(b) the definition-harmonization helpers that detect unit / definition /
boundary mismatches (crude vs finished steel, production vs capacity,
annualised vs overnight CAPEX, captive-inclusive vs route-only energy, etc.).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Tuple


class ComparisonStatus(str, Enum):
    MATCH = "MATCH"
    CLOSE = "CLOSE"
    MATERIAL_DIFFERENCE = "MATERIAL_DIFFERENCE"
    UNRESOLVED = "UNRESOLVED"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class ScientificStatus(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


# Documented numerical thresholds (relative difference |ours-vol4|/|vol4|).
# Rationale: 1% is rounding / definition noise for well-defined anchors;
# 10% is the boundary above which a difference cannot be dismissed as noise
# for energy-system quantities at decadal scale. These are stated here so
# the classification is reproducible and reviewable, not arbitrary.
MATCH_TOLERANCE = 0.01
CLOSE_TOLERANCE = 0.10
THRESHOLD_RATIONALE = (
    "MATCH: |rel diff| <= 1% (anchor/rounding agreement). "
    "CLOSE: 1% < |rel diff| <= 10% (quantitative agreement within "
    "decadal-scale noise). MATERIAL_DIFFERENCE: |rel diff| > 10% "
    "(beyond noise; requires attribution). UNRESOLVED: one side missing "
    "or data-limited. NOT_COMPARABLE: unit/definition/boundary/scenario "
    "mismatch or a route/fleet feature not represented on one side. "
    "Thresholds are applied ONLY after harmonization confirms the two "
    "quantities share definition, unit, boundary and scenario."
)


def relative_difference(ours: Optional[float], vol4: Optional[float]) -> Optional[float]:
    """Relative difference (ours - vol4)/vol4; None when vol4 is 0/None."""
    if vol4 is None or ours is None or vol4 == 0.0:
        return None
    return (ours - vol4) / abs(vol4)


def classify_difference(ours: Optional[float], vol4: Optional[float]) -> ComparisonStatus:
    """
    Classify a HARMONIZED numeric difference. If either side is missing the
    result is UNRESOLVED; if vol4 == 0 the result is MATCH when ours == 0
    else MATERIAL_DIFFERENCE (a non-zero against a published zero).
    """
    if ours is None or vol4 is None:
        return ComparisonStatus.UNRESOLVED
    if vol4 == 0.0:
        return ComparisonStatus.MATCH if ours == 0.0 else ComparisonStatus.MATERIAL_DIFFERENCE
    rel = relative_difference(ours, vol4)
    assert rel is not None
    abs_rel = abs(rel)
    if abs_rel <= MATCH_TOLERANCE:
        return ComparisonStatus.MATCH
    if abs_rel <= CLOSE_TOLERANCE:
        return ComparisonStatus.CLOSE
    return ComparisonStatus.MATERIAL_DIFFERENCE


# ----------------------------------------------------------------------
# Definition-harmonization checks. Each returns (comparable: bool, reason).
# ----------------------------------------------------------------------

def check_crude_vs_finished(ours_definition: str, vol4_definition: str) -> Tuple[bool, str]:
    """Crude steel must never be compared to finished steel."""
    ours_words = set(ours_definition.lower().split())
    vol4_words = set(vol4_definition.lower().split())
    if ("crude" in ours_words and "finished" in vol4_words) or (
            "finished" in ours_words and "crude" in vol4_words):
        return False, "definition mismatch: crude vs finished steel"
    return True, "definitions agree on steel measure"


def check_production_vs_capacity(ours_kind: str, vol4_kind: str) -> Tuple[bool, str]:
    """Production (Mt/yr flow) must not be compared to capacity (Mt/yr stock)."""
    if ours_kind != vol4_kind:
        return False, f"kind mismatch: {ours_kind} vs {vol4_kind}"
    return True, "both quantities are the same kind"


def check_annualised_vs_overnight(capex_basis_ours: str, capex_basis_vol4: str) -> Tuple[bool, str]:
    """Annualised CAPEX (USD/t/yr) must not be compared to overnight CAPEX (USD/t)."""
    if capex_basis_ours != capex_basis_vol4:
        return False, f"CAPEX basis mismatch: {capex_basis_ours} vs {capex_basis_vol4}"
    return True, "CAPEX on the same annualisation basis"


def check_scenario(scenario_ours: str, scenario_vol4: str) -> Tuple[bool, str]:
    if scenario_ours != scenario_vol4:
        return False, f"scenario mismatch: {scenario_ours} vs {scenario_vol4}"
    return True, "scenarios agree"


def check_route_represented(route: str, enabled_routes) -> Tuple[bool, str]:
    if route not in enabled_routes:
        return False, f"{route} is not represented in the optimization (EXTERNAL_PENDING / not enabled)"
    return True, f"{route} is represented"


def check_ccs_representation(requires_ccs: bool, ccs_represented: bool) -> Tuple[bool, str]:
    if requires_ccs and not ccs_represented:
        return False, "Vol.4 quantity assumes CCUS, which the model does not represent"
    return True, "CCUS representation consistent"


def mtoe_from_mwh(twh: float) -> float:
    """Convert TWh to Mtoe (1 Mtoe = 11.63 TWh)."""
    return twh / 11.63


def pj_from_gj_per_t(sec_gj_t: float, production_mt: float) -> float:
    """Final energy in PJ from route SEC (GJ/t) x production (Mt)."""
    return sec_gj_t * production_mt  # GJ/t * Mt = GJ*1e6/1e6 = ... = PJ
