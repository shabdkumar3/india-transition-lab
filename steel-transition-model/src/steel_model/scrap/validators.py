"""
Validation helpers for the Step 9 dynamic scrap circularity module.

Every scrap-related parameter MUST carry a provenance record (read from
configuration, never hard-coded inside optimization logic — the same rule
as the Step 8 final polish). Missing provenance fails loudly. Unit
consistency (Mt steel x t/t intensity = Mt scrap) is enforced at the
intensity level so no kg/t vs t/t mismatch can slip in silently.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

# Unit discipline: the scrap balance is expressed in Mt (million tonnes).
# Scrap intensities must be mass-per-mass (t scrap / t steel); a kg/t
# intensity would silently scale scrap use by 1000 and is rejected.
ACCEPTED_SCRAP_INTENSITY_UNITS = {"t/t steel", "t/t", "Mt/Mt"}


def require_provenance(record: Mapping[str, Any], label: str) -> None:
    """
    Fail loudly if a scrap parameter record lacks a provenance field.

    Provenance is the project's 6-tier taxonomy
    (V4 / TIMES / DERIVED / EXTERNAL / EXTERNAL_PENDING /
    PROJECT_PROPOSAL / UNKNOWN). A missing record is a configuration
    defect, never silently defaulted.
    """
    if not isinstance(record, dict):
        raise ValueError(
            f"Scrap parameter '{label}' must be a mapping with a "
            "'provenance' record; got {type(record).__name__}."
        )
    prov = record.get("provenance")
    if prov is None or str(prov).strip() == "":
        raise ValueError(
            f"Scrap parameter '{label}' is missing its provenance record: "
            "the configuration must carry 'provenance' (never hard-coded)."
        )


def check_scrap_intensity_unit(unit: str, label: str) -> None:
    """
    Reject scrap intensity units that would break the mass balance.

    RES_scrap,t = ACT_i,t x ScrapIntensity_i,t must yield Mt scrap.
    ACT is Mt steel and the intensity must therefore be mass/mass
    (t/t steel). A kg/t intensity would make scrap use 1000x too large.
    """
    u = str(unit).strip()
    if u not in ACCEPTED_SCRAP_INTENSITY_UNITS:
        raise ValueError(
            f"Scrap intensity '{label}' has unit '{u}' which is not "
            f"mass-per-mass. Accepted units: {sorted(ACCEPTED_SCRAP_INTENSITY_UNITS)}. "
            "The scrap balance requires Mt x (t/t) = Mt; kg/t is rejected."
        )


def check_fraction(value: float, label: str, lo: float = 0.0, hi: float = 1.0) -> float:
    """Validate a dimensionless fraction (e.g. collection rate, yield)."""
    v = float(value)
    if not (lo <= v <= hi):
        raise ValueError(f"Scrap parameter '{label}' = {v} outside [{lo}, {hi}].")
    return v


def check_non_negative(value: float, label: str) -> float:
    v = float(value)
    if v < 0.0:
        raise ValueError(f"Scrap parameter '{label}' cannot be negative, got {v}.")
    return v


def check_positive(value: float, label: str) -> float:
    v = float(value)
    if v <= 0.0:
        raise ValueError(f"Scrap parameter '{label}' must be > 0, got {v}.")
    return v


def validate_no_cohort_overlap(historical_years, model_start_year: int) -> None:
    """
    Double-counting guard: historical cohorts and model cohorts must be
    disjoint in time. Historical production covers tau < model_start_year
    (2024); model production covers tau >= model_start_year. Any overlap
    would represent the same tonne of steel twice.
    """
    for y in historical_years:
        if int(y) >= model_start_year:
            raise ValueError(
                f"Historical cohort year {y} overlaps the model horizon "
                f"(start_year={model_start_year}). A cohort can be historical "
                "OR modelled, never both (SCRAP_DOUBLE_COUNTING_AUDIT.md)."
            )


def optional_year_series(value: Any, label: str) -> Optional[Dict[int, float]]:
    """
    Normalise a scalar or per-year mapping into a {year: value} series.

    Scalar -> constant series is resolved later by the caller against the
    model years; per-year mappings are validated to be numeric.
    """
    if isinstance(value, dict):
        out: Dict[int, float] = {}
        for k, v in value.items():
            try:
                out[int(k)] = float(v)
            except (TypeError, ValueError):
                raise ValueError(
                    f"Scrap parameter '{label}' year '{k}' has non-numeric value {v!r}."
                )
        return out
    if value is None:
        return None
    try:
        float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"Scrap parameter '{label}' must be a number or a year mapping, got {value!r}."
        )
    return None  # scalar; caller resolves
