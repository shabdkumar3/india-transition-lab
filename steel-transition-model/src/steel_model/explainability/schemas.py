"""
Schemas for explainability and diagnostics (Step 15).
"""

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class TechnologyYearRecord(BaseModel):
    """Structured diagnostic record for a single technology in a single year."""

    year: int
    technology: str

    # Activity Metrics
    production: Optional[float] = None
    share: Optional[float] = None
    installed_capacity: Optional[float] = None
    new_capacity: Optional[float] = None
    retirement: Optional[float] = None

    # Economic Metrics (M USD)
    capex_contribution: Optional[float] = None
    fom_contribution: Optional[float] = None
    vom_contribution: Optional[float] = None
    fuel_cost: Optional[float] = None
    resource_cost: Optional[float] = None
    electricity_cost: Optional[float] = None
    emission_cost: Optional[float] = None
    effective_cost: Optional[float] = None  # absolute cost (M USD)
    unit_effective_cost: Optional[float] = None  # cost per tonne (USD/t)

    # Physical Metrics
    capacity_used: Optional[float] = None
    capacity_available: Optional[float] = None
    deployment_used: Optional[float] = None
    deployment_available: Optional[float] = None
    scrap_used: Optional[float] = None
    scrap_available: Optional[float] = None
    resource_used: Dict[str, float] = Field(default_factory=dict)
    resource_available: Dict[str, float] = Field(default_factory=dict)

    # Learning Metrics
    learning_enabled: bool = False
    learning_effect: Optional[float] = None
    learning_provenance: Optional[str] = None

    # Data Completeness & Interpretability
    provenance: str
    data_completeness: str
    interpretability_status: str


class TechnologyShift(BaseModel):
    """Detection of key technology events (shifts)."""

    year: int
    technology: str
    event_type: str  # APPEARS, DISAPPEARS, RISE, FALL, SPIKE_ADDITION, SPIKE_RETIREMENT
    before_value: Optional[float] = None
    after_value: Optional[float] = None
    absolute_change: Optional[float] = None
    threshold: float
    status: str


class ConstraintDiagnostic(BaseModel):
    """Diagnostic status of a mathematical constraint."""

    year: int
    constraint_type: str  # capacity, deployment, scrap, resources, emissions, demand
    available: Optional[float] = None
    used: Optional[float] = None
    slack: Optional[float] = None
    pressure: Optional[float] = None
    binding_status: str  # BINDING, NON_BINDING, UNCONSTRAINED


class CostCrossover(BaseModel):
    """Relative cost ordering and crossover detection."""

    year: int
    technology_a: str
    technology_b: str
    cost_a: Optional[float] = None
    cost_b: Optional[float] = None
    comparison_status: str  # COMPARABLE, NOT_COMPARABLE
    crossover_detected: bool


class PathwayEvent(BaseModel):
    """Interpretive event record connecting shifts, drivers, and constraints."""

    year: int
    technology: str
    event_type: str
    share_change: Optional[float] = None
    associated_drivers: List[str]
    active_constraints: List[str]
    limiting_data: List[str]
    interpretation_status: str


class BenchmarkDiagnostic(BaseModel):
    """Linkage of model vs Vol.4 differences to drivers and data limits."""

    metric: str
    year: Optional[int] = None
    ours: Optional[float] = None
    vol4: Optional[float] = None
    difference: Optional[float] = None
    comparison_status: str
    data_completeness: str
    active_constraints: List[str]
    associated_drivers: List[str]


class ScrapWaypointDiagnostic(BaseModel):
    """Gate C — post-solve comparison of model scrap share vs Vol.4 NZS waypoints.

    Approved 2026-08-14 (MODE_B_APPROVAL_GATES.md, Gate C, Interpretation A):
    these waypoints are DIAGNOSTIC TARGETS ONLY. They are NEVER imposed as
    MILP lower-bound constraints (no ACT[Scrap-EAF,t] >= ScrapFloor[t]*D[t]).
    """

    year: int
    waypoint_share: Optional[float] = None
    model_scrap_share: Optional[float] = None
    status: str = "UNRESOLVED"  # MATCH | BELOW | ABOVE | UNRESOLVED
    interpretation: str = ""
