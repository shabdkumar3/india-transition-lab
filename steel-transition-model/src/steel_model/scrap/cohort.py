"""
Historical production cohorts for the Step 9 scrap circularity module.

HistoricalProduction_tau is the crude steel entering use in historical
year tau (tau < 2024, per the frozen MODEL_FORMULATION §6 cohort window
1990-2023). These cohorts, together with post-2024 modelled production,
generate future end-of-life steel flows.

Data discipline (Step 9 §4):
- The historical period follows the frozen specification (1990-2023).
- Available years carry EXTERNAL provenance (MoS AR 2025-26 production
  series). Years without data are explicitly marked missing
  (EXTERNAL_PENDING) and contribute ZERO to EOL — nothing is fabricated
  and no growth rate is introduced silently.
- No arbitrary starting stock is added: the historical cohorts ARE the
  representation of historical in-use stock (no double counting).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from steel_model.scrap.validators import (
    check_non_negative,
    require_provenance,
    validate_no_cohort_overlap,
)


@dataclass
class HistoricalProductionCohort:
    """One historical production cohort (a single year's crude steel)."""

    year: int
    production_mt: Optional[float]  # None = explicitly missing (EXTERNAL_PENDING)
    provenance: str
    source: str = ""
    source_page: str = ""
    notes: str = ""

    def validate(self) -> None:
        if self.production_mt is not None:
            check_non_negative(self.production_mt, f"historical production {self.year}")


@dataclass
class HistoricalCohortSet:
    """
    Container for all historical production cohorts in the frozen window.

    Attributes
    ----------
    start_year : first year of the frozen historical window (1990)
    end_year   : last year of the frozen historical window (2023)
    cohorts    : {year: HistoricalProductionCohort}
    unit       : "Mt" (million tonnes)
    """

    start_year: int
    end_year: int
    cohorts: Dict[int, HistoricalProductionCohort] = field(default_factory=dict)
    unit: str = "Mt"

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, cfg: dict, model_start_year: int) -> "HistoricalCohortSet":
        """
        Build a HistoricalCohortSet from the `historical_cohorts` config block.

        The config declares the frozen window (start_year/end_year) and a
        `production_mt` mapping: {year: value} for AVAILABLE years. Years
        inside the window not present in the mapping are explicitly missing
        and stored as EXTERNAL_PENDING cohorts (production_mt=None).
        """
        start_year = int(cfg.get("start_year", 1990))
        end_year = int(cfg.get("end_year", 2023))
        if start_year > end_year:
            raise ValueError(
                f"historical_cohorts window inverted: {start_year} > {end_year}"
            )
        raw_production = cfg.get("production_mt", {})
        if not isinstance(raw_production, dict):
            raise ValueError(
                "historical_cohorts.production_mt must be a "
                "{year: value} mapping of AVAILABLE years."
            )
        # An empty mapping is VALID: it means no historical production is
        # available at all (every year in the window is explicitly marked
        # missing -> Step 9 §14 Test 4 regime). Nothing is fabricated.
        for y in raw_production:
            if int(y) < start_year or int(y) > end_year:
                raise ValueError(
                    f"Historical cohort year {y} is outside the frozen window "
                    f"[{start_year}, {end_year}]. The historical period must "
                    "follow the frozen specification (MODEL_FORMULATION §6) "
                    "and end before the model start year."
                )

        cohorts: Dict[int, HistoricalProductionCohort] = {}
        # Every year inside the frozen window is represented: available
        # years with their sourced value, missing years explicitly marked.
        for y in range(start_year, end_year + 1):
            if y in raw_production:
                raw = raw_production[y]
                if isinstance(raw, dict):
                    require_provenance(raw, f"historical_cohorts[{y}]")
                    value = raw.get("value")
                    cohorts[y] = HistoricalProductionCohort(
                        year=y,
                        production_mt=float(value) if value is not None else None,
                        provenance=str(raw.get("provenance")),
                        source=str(raw.get("source", "")),
                        source_page=str(raw.get("source_page", "")),
                        notes=str(raw.get("notes", "")),
                    )
                else:
                    # Bare numeric entry: provenance must come from a
                    # top-level block provenance record (never hard-coded).
                    cohorts[y] = HistoricalProductionCohort(
                        year=y,
                        production_mt=float(raw),
                        provenance=str(cfg.get("provenance", "")),
                        source=str(cfg.get("source", "")),
                        source_page=str(cfg.get("source_page", "")),
                        notes="Bare numeric cohort; block-level provenance applied.",
                    )
            else:
                cohorts[y] = HistoricalProductionCohort(
                    year=y,
                    production_mt=None,
                    provenance="EXTERNAL_PENDING",
                    notes="Historical production for this year is not available "
                          "in the approved project files; no value fabricated.",
                )

        cohort_set = cls(
            start_year=start_year,
            end_year=end_year,
            cohorts=cohorts,
            unit=str(cfg.get("unit", "Mt")),
        )
        cohort_set.validate(model_start_year)
        return cohort_set

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, model_start_year: int) -> None:
        for cohort in self.cohorts.values():
            cohort.validate()
        validate_no_cohort_overlap(self.cohorts.keys(), model_start_year)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def available_years(self) -> List[int]:
        return sorted(
            y for y, c in self.cohorts.items() if c.production_mt is not None
        )

    def missing_years(self) -> List[int]:
        """Years inside the frozen window with no sourced production."""
        return sorted(
            y for y, c in self.cohorts.items() if c.production_mt is None
        )

    def production_mt(self, year: int) -> Optional[float]:
        cohort = self.cohorts.get(year)
        return cohort.production_mt if cohort else None

    def production_series(self) -> Dict[int, float]:
        """{year: production} for AVAILABLE years only (missing -> absent)."""
        return {
            y: c.production_mt
            for y, c in self.cohorts.items()
            if c.production_mt is not None
        }

    @property
    def total_available_production_mt(self) -> float:
        return sum(self.production_series().values())

    def provenance_summary(self) -> Dict[str, str]:
        """{year: provenance} for available cohorts (for result retention)."""
        return {
            y: c.provenance
            for y, c in self.cohorts.items()
            if c.production_mt is not None
        }
