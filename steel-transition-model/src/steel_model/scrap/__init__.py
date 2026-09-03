"""
Step 9 — Dynamic Scrap Circularity module.

Pure cohort stock-flow accounting: historical production cohorts
(1990-2023, EXTERNAL where sourced, EXTERNAL_PENDING where missing) plus
post-2024 modelled production cohorts generate future end-of-life scrap
through a configurable lifetime kernel (deterministic or Weibull), then a
distinct collection -> processing chain produces usable domestic scrap
that bounds Scrap-EAF consumption in the MILP (Mode B only).

Mode A (control baseline) keeps dynamic scrap DISABLED via explicit
configuration gating; nothing here modifies the frozen Step 8 baseline.
"""

from steel_model.scrap.cohort import HistoricalCohortSet, HistoricalProductionCohort
from steel_model.scrap.collection import CollectionProcessing
from steel_model.scrap.lifetime import LifetimeKernel
from steel_model.scrap.scrap_engine import ScrapAccounting, ScrapEngine

__all__ = [
    "HistoricalCohortSet",
    "HistoricalProductionCohort",
    "CollectionProcessing",
    "LifetimeKernel",
    "ScrapAccounting",
    "ScrapEngine",
]
