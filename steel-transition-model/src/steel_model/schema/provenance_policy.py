"""
Provenance gating policy (Step 13 remediation — Task 1).

Explicit eligibility policy for provenance classes entering optimization
coefficients:

    Optimization-eligible : V4, TIMES, DERIVED, EXTERNAL
    Conditional           : PROJECT_PROPOSAL   (requires explicit enablement)
    NOT optimization-eligible: EXTERNAL_PENDING, UNKNOWN
                            (require an explicit allowance / value override,
                             otherwise the loader FAILS LOUDLY — never a
                             silent conversion to zero)

The gate is the single place where a registry intensity (value + provenance)
is resolved into a coefficient that may enter the MILP. It is provenance-
visible: every decision records the effective provenance and, for overrides,
the override provenance and rationale.

Never silently convert EXTERNAL_PENDING/UNKNOWN to zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Set

# Provenance classes that may enter optimization coefficients directly.
OPTIMIZATION_ELIGIBLE: frozenset = frozenset({"V4", "TIMES", "DERIVED", "EXTERNAL"})

# Provenance classes that are allowed only when explicitly enabled.
CONDITIONAL: frozenset = frozenset({"PROJECT_PROPOSAL"})

# Provenance classes that must NEVER enter optimization silently.
NOT_OPTIMIZATION_ELIGIBLE: frozenset = frozenset({"EXTERNAL_PENDING", "UNKNOWN"})

_ALL_CLASSES = OPTIMIZATION_ELIGIBLE | CONDITIONAL | NOT_OPTIMIZATION_ELIGIBLE


def classify_provenance(provenance: str) -> str:
    """Return the policy bucket for a provenance label."""
    if provenance in OPTIMIZATION_ELIGIBLE:
        return "optimization-eligible"
    if provenance in CONDITIONAL:
        return "conditional"
    if provenance in NOT_OPTIMIZATION_ELIGIBLE:
        return "not-optimization-eligible"
    raise ValueError(
        f"Unknown provenance label '{provenance}'. Valid labels: "
        f"{sorted(_ALL_CLASSES)}"
    )


class ProvenanceGateError(ValueError):
    """Raised when a parameter is not eligible for optimization without an override."""


@dataclass(frozen=True)
class IntensityGateDecision:
    """Resolved intensity decision for one (route, resource) coefficient."""

    coefficient_value: Optional[float]  # value that may enter the MILP (None -> 0)
    status: str  # "eligible" | "proposal_allowed" | "pending_allowance" | "value_override"
    provenance: str  # effective provenance label to report
    override_provenance: Optional[str] = None  # set when a value_override was used
    rationale: Optional[str] = None


def resolve_intensity(
    route: str,
    resource: str,
    value: Optional[float],
    provenance: str,
    allowances: Set[str],
    overrides: Dict[str, Dict],
    allow_proposal: bool,
) -> IntensityGateDecision:
    """
    Resolve one intensity into an optimization coefficient under the gate.

    ``allowances`` is a set of "route/resource" keys explicitly permitted to
    be used as-is even when their provenance is EXTERNAL_PENDING/UNKNOWN
    (their stored value, including None -> 0, is used).

    ``overrides`` maps "route/resource" -> {"value", "provenance", "rationale"}
    and replaces the registry value entirely (bypassing the gate).

    Raises ``ProvenanceGateError`` when the parameter is not eligible and no
    explicit allowance/override is present.
    """
    key = f"{route}/{resource}"

    # 1. Explicit value override (diagnostic / sensitivity mode).
    if key in overrides:
        ov = overrides[key]
        return IntensityGateDecision(
            coefficient_value=ov["value"],
            status="value_override",
            provenance=ov["provenance"],
            override_provenance=ov["provenance"],
            rationale=ov.get("rationale"),
        )

    # 2. Optimization-eligible.
    if provenance in OPTIMIZATION_ELIGIBLE:
        if value is None:
            raise ProvenanceGateError(
                f"[{key}] provenance '{provenance}' is optimization-eligible but the "
                "stored value is None. A null value with an eligible provenance is a "
                "registry defect and must be fixed, not silently zeroed."
            )
        return IntensityGateDecision(
            coefficient_value=value, status="eligible", provenance=provenance
        )

    # 3. Conditional (PROJECT_PROPOSAL) — requires explicit enablement.
    if provenance in CONDITIONAL:
        if not allow_proposal:
            raise ProvenanceGateError(
                f"[{key}] provenance '{provenance}' requires explicit enablement: set "
                "provenance_gating.allow_proposal_parameters: true to permit "
                "PROJECT_PROPOSAL values in this optimization."
            )
        return IntensityGateDecision(
            coefficient_value=value, status="proposal_allowed", provenance=provenance
        )

    # 4. Not optimization-eligible (EXTERNAL_PENDING / UNKNOWN).
    if provenance in NOT_OPTIMIZATION_ELIGIBLE:
        if key in allowances:
            return IntensityGateDecision(
                coefficient_value=value,
                status="pending_allowance",
                provenance=provenance,
            )
        raise ProvenanceGateError(
            f"[{key}] provenance '{provenance}' is NOT optimization-eligible without an "
            f"explicit override. Add '{key}' to provenance_gating.pending_intensity_allowances "
            "to use the stored value as-is, supply an intensity value_override, or exclude "
            "the route/resource. EXTERNAL_PENDING/UNKNOWN values are never silently "
            "converted to zero."
        )

    raise ProvenanceGateError(
        f"[{key}] unknown provenance label '{provenance}'."
    )