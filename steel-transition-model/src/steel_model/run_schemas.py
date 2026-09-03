"""
Schemas for run execution, manifest files, and canonical result formats (Step 16).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RunConfig(BaseModel):
    """Configuration structure for a single reproducible experiment run."""

    base_config: str = Field(..., description="Path to base optimization config (e.g. configs/optimization/baseline.yaml)")
    overrides: Dict[str, Any] = Field(default_factory=dict, description="Fields to override in the loaded ModelConfig or ScenarioConfig")
    allow_external_pending: bool = Field(False, description="Flag to allow EXTERNAL_PENDING parameters when explicit overrides exist")
    diagnostic_overrides: Dict[str, Any] = Field(default_factory=dict, description="Explicit parameters to replace pending values")
    random_seed: Optional[int] = Field(None, description="Explicit seed for stochastic/uncertainty sampling")
    intensities_path: Optional[str] = Field(None, description="Optional path to custom steel_intensities.yaml")


class RunManifest(BaseModel):
    """Metadata manifest documenting experiment run settings, environments, and hashes."""

    run_id: str
    timestamp: str
    model_version: str
    code_version: str
    config_path: str
    config_hash: str
    data_hash: str
    parameter_registry_version: str
    scenario: str
    mode: str
    enabled_modules: List[str]
    solver: str
    solver_version: str
    solver_options: Dict[str, Any]
    objective: Optional[float] = None
    solver_status: str
    termination_reason: str
    random_seed: Optional[int] = None
    environment_metadata: Dict[str, str]
    git_available: bool = False
    git_commit_hash: Optional[str] = None
    git_branch: Optional[str] = None


class YearResultRecord(BaseModel):
    """Canonical results per year."""

    year: int
    production: Dict[str, float] = Field(default_factory=dict)
    capacity: Dict[str, float] = Field(default_factory=dict)
    new_capacity: Dict[str, float] = Field(default_factory=dict)
    retirement: Dict[str, float] = Field(default_factory=dict)
    technology_shares: Dict[str, float] = Field(default_factory=dict)

    # Resource consumption
    H2: float = 0.0
    electricity: float = 0.0
    coal: float = 0.0
    gas: float = 0.0
    ore: float = 0.0
    scrap: float = 0.0

    # Economics & CO2
    CO2: float = 0.0
    investment: float = 0.0
    total_cost: Optional[float] = None  # None if incomplete economics


class RunResultSchema(BaseModel):
    """Canonical run result container representing both JSON and CSV outputs."""

    scenario: str
    mode: str
    solver_status: str
    objective: Optional[float] = None
    data_completeness: str
    source_completeness: str
    optimization_eligibility: str
    technology_space_completeness: str
    M1_state: str
    existing_route_capacity_state: str
    economically_complete: Dict[str, bool] = Field(default_factory=dict)
    interpretation: List[str] = Field(default_factory=list)
    yearly_results: List[YearResultRecord] = Field(default_factory=list)
