"""
Data module managing demand ingestion, validation, and S-curve diagnostic analysis.
"""

from .demand_types import DemandRecord, DemandDataset
from .demand_validator import DemandValidator
from .demand_loader import DemandLoader
from .scurve_diagnostic import SCurveDiagnostic
from .demand_forecast import (
    model_demand_series,
    india_policy_demand_series,
    international_demand_series,
    niti_demand_series,
    trajectory_summary,
    # legacy aliases kept for backward compat
    iea_steps_demand_series,
    cross_country_demand_series,
    MODEL_ANCHORS,
    INDIA_POLICY_OPT_ANCHORS,
    INTERNATIONAL_OPT_ANCHORS,
    # legacy aliases
    IEA_STEPS_OPT_ANCHORS,
    CROSS_COUNTRY_OPT_ANCHORS,
    NITI_ANCHORS,
    HISTORICAL_DATA,
)

__all__ = [
    "DemandRecord",
    "DemandDataset",
    "DemandValidator",
    "DemandLoader",
    "SCurveDiagnostic",
    "model_demand_series",
    "india_policy_demand_series",
    "international_demand_series",
    "niti_demand_series",
    "trajectory_summary",
    "iea_steps_demand_series",
    "cross_country_demand_series",
    "MODEL_ANCHORS",
    "INDIA_POLICY_OPT_ANCHORS",
    "INTERNATIONAL_OPT_ANCHORS",
    "IEA_STEPS_OPT_ANCHORS",
    "CROSS_COUNTRY_OPT_ANCHORS",
    "NITI_ANCHORS",
    "HISTORICAL_DATA",
]
