"""
Lifetime kernel for the Step 9 scrap circularity module.

omega(age) is the fraction of a steel cohort reaching end-of-life after
age `age` (age = t - tau). Supports:

- deterministic lifetime : omega(age) = 1 iff age == lifetime_years, else 0
- Weibull lifetime       : omega(age) = F(age) - F(age-1), where F is the
                           Weibull CDF with shape beta and scale eta.
                           omega(0) = F(0) - F(-1) = 0, so current-year
                           production never contributes to its own EOL.

Parameters are PROJECT_PROPOSAL per ASSUMPTION_DEBT_REGISTER.md (shape
2.5, scale 20 yr) and remain fully configurable with provenance, so no
arbitrary values are silently frozen (Step 9 §5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from steel_model.scrap.validators import check_positive, require_provenance


@dataclass
class LifetimeKernel:
    """
    omega(age): fraction of a cohort reaching EOL after `age` years.

    distribution: "deterministic" or "weibull".
    """

    distribution: str
    shape: Optional[float] = None          # Weibull beta
    scale: Optional[float] = None          # Weibull eta (years)
    lifetime_years: Optional[float] = None  # deterministic lifetime
    provenance: str = ""
    notes: str = ""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, cfg: dict) -> "LifetimeKernel":
        require_provenance(cfg, "lifetime")
        distribution = str(cfg.get("distribution", "weibull")).strip().lower()
        if distribution not in ("deterministic", "weibull"):
            raise ValueError(
                f"Unknown lifetime distribution '{distribution}'; "
                "expected 'deterministic' or 'weibull'."
            )
        if distribution == "weibull":
            shape = float(cfg.get("weibull_shape", cfg.get("shape")))
            scale = float(cfg.get("weibull_scale", cfg.get("scale")))
            check_positive(shape, "weibull_shape")
            check_positive(scale, "weibull_scale")
            return cls(
                distribution=distribution,
                shape=shape,
                scale=scale,
                provenance=str(cfg.get("provenance")),
                notes=str(cfg.get("notes", "")),
            )
        lifetime = float(cfg.get("deterministic_lifetime_years", cfg.get("lifetime_years")))
        check_positive(lifetime, "deterministic_lifetime_years")
        return cls(
            distribution=distribution,
            lifetime_years=lifetime,
            provenance=str(cfg.get("provenance")),
            notes=str(cfg.get("notes", "")),
        )

    # ------------------------------------------------------------------
    # Core kernel
    # ------------------------------------------------------------------

    def cdf(self, age):
        """Cumulative fraction EOL'd by age (Weibull only).

        Accepts a scalar or a numpy array (returns float or ndarray).
        """
        if self.distribution != "weibull":
            raise ValueError("cdf() is only defined for the weibull distribution.")
        age_arr = np.asarray(age, dtype=float)
        with np.errstate(over="ignore", invalid="ignore"):
            cdf = 1.0 - np.exp(-((age_arr / self.scale) ** self.shape))
        out = np.where(age_arr <= 0.0, 0.0, cdf)
        if np.ndim(age) == 0:
            return float(out)
        return out

    def weight(self, age: float) -> float:
        """
        omega(age): fraction of the cohort reaching EOL at exact age.

        Discrete annual kernel. omega(0) == 0 for both distributions, so
        a cohort never contributes to its own production year's EOL.
        """
        if age < 0:
            return 0.0
        if self.distribution == "deterministic":
            return 1.0 if age == self.lifetime_years else 0.0
        # Weibull: mass in bin [age-1, age]
        return self.cdf(age) - self.cdf(age - 1.0)

    def weights_for_ages(self, ages) -> np.ndarray:
        """Vectorised omega over an array of ages."""
        ages = np.asarray(ages, dtype=float)
        if self.distribution == "deterministic":
            return np.where(ages == self.lifetime_years, 1.0, 0.0)
        return self.cdf(ages) - self.cdf(ages - 1.0)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def total_mass(self, max_age: int = 400) -> float:
        """Sum of omega over ages 0..max_age (should be ~1.0)."""
        ages = np.arange(0, max_age + 1, dtype=float)
        return float(self.weights_for_ages(ages).sum())

    def eol_profile(self, horizon_years: int) -> Dict[int, float]:
        """{age: omega(age)} for age in 0..horizon_years (for tests/reporting)."""
        return {a: float(self.weight(a)) for a in range(horizon_years + 1)}
