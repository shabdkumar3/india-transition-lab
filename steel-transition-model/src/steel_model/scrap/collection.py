"""
Collection and processing chain for the Step 9 scrap circularity module.

Distinct physical quantities (Step 9 §7), never collapsed into one
coefficient:

    EOLScrapGen_t  ->  CollectedScrap_t = EOL x CollectionRate_t
    CollectedScrap_t -> UsableScrap_t   = CollectedScrap_t x ProcessingYield_t

CollectionRate and ProcessingYield are separate, configurable, per-year
parameters carrying provenance (PROJECT_PROPOSAL defaults per
FINAL_ML_DECISION_MATRIX: collection/processing behaviour is DEFERRED
pending empirical Indian series).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from steel_model.scrap.validators import (
    check_fraction,
    optional_year_series,
    require_provenance,
)


@dataclass
class CollectionProcessing:
    """
    CollectionRate_t and ProcessingYield_t (both in [0, 1]).

    Per-year series or scalar constants; scalar is broadcast across years
    by the engine.
    """

    collection_rate: Dict[int, float]
    processing_yield: Dict[int, float]
    collection_provenance: str
    yield_provenance: str
    collection_notes: str = ""
    yield_notes: str = ""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, cfg: dict, years) -> "CollectionProcessing":
        """
        Build from the `collection` config block: {collection_rate,
        processing_yield, ...} with provenance records on each.
        """
        collection_cfg = cfg.get("collection_rate", {})
        yield_cfg = cfg.get("processing_yield", {})
        require_provenance(collection_cfg, "collection_rate")
        require_provenance(yield_cfg, "processing_yield")

        collection_series = optional_year_series(
            collection_cfg.get("value"), "collection_rate"
        )
        yield_series = optional_year_series(
            yield_cfg.get("value"), "processing_yield"
        )

        if collection_series is None:
            collection_series = {t: float(collection_cfg["value"]) for t in years}
        if yield_series is None:
            yield_series = {t: float(yield_cfg["value"]) for t in years}

        obj = cls(
            collection_rate=collection_series,
            processing_yield=yield_series,
            collection_provenance=str(collection_cfg.get("provenance")),
            yield_provenance=str(yield_cfg.get("provenance")),
            collection_notes=str(collection_cfg.get("notes", "")),
            yield_notes=str(yield_cfg.get("notes", "")),
        )
        obj.validate(years)
        return obj

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, years) -> None:
        for t in years:
            check_fraction(self.collection_rate.get(t, 0.0), f"collection_rate[{t}]")
            check_fraction(self.processing_yield.get(t, 0.0), f"processing_yield[{t}]")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def rate(self, year: int) -> float:
        return self.collection_rate.get(year, 0.0)

    def yield_value(self, year: int) -> float:
        return self.processing_yield.get(year, 0.0)

    def usable_factor(self, year: int) -> float:
        """Combined conversion EOL -> usable scrap for year t."""
        return self.rate(year) * self.yield_value(year)

    def provenance_summary(self) -> Dict[str, str]:
        return {
            "collection_rate": self.collection_provenance,
            "processing_yield": self.yield_provenance,
        }
