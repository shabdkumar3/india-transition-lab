"""
India Steel Transition Lab — Pydantic API schemas.

Stable response contracts. Never return loosely structured dictionaries when
a stable schema is appropriate. These schemas mirror the existing
research-engine formats (run_schemas.py, data/uncertainty, data/benchmark,
data/explainability) without reimplementing any scientific logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Health / status
# ---------------------------------------------------------------------------
class HealthOut(BaseModel):
    status: str
    model_version: str
    baseline_objective: Optional[float] = None
    data_store_ok: bool
    engine_importable: bool


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
class ScenarioModule(BaseModel):
    """One toggleable module of the scenario builder."""

    id: str
    label: str
    state: str  # ACTIVE | DEFERRED | NOT_AVAILABLE
    reason: Optional[str] = None


class ScenarioSummary(BaseModel):
    id: str
    name: str
    mode: str  # MODE_A | MODE_B
    description: str
    runnable: bool
    modules: List[ScenarioModule] = Field(default_factory=list)
    policy_rules: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class UncertaintyDimensionOption(BaseModel):
    id: str
    label: str
    value: Optional[float] = None
    note: str


class ScenarioDetail(ScenarioSummary):
    base_config: str
    allowed_overrides: List[str] = Field(default_factory=list)
    gated_parameters: List[str] = Field(default_factory=list)
    uncertainty_dimensions: Dict[str, List[UncertaintyDimensionOption]] = Field(
        default_factory=dict
    )
    data_completeness: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Run submission
# ---------------------------------------------------------------------------
class RunCreate(BaseModel):
    scenario_id: str
    overrides: Dict[str, Any] = Field(default_factory=dict)
    uncertainty_params: Dict[str, str] = Field(
        default_factory=dict,
        description="Only for scenario_id='uncertainty_study': policy, scrap_level, dri_alternative, fleet_id.",
    )
    label: Optional[str] = None


class RunStatusOut(BaseModel):
    run_id: str
    scenario_id: str
    status: str  # QUEUED | RUNNING | OPTIMAL | FEASIBLE | INFEASIBLE | FAILED
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    objective: Optional[float] = None
    recorded: bool = False
    label: Optional[str] = None


# ---------------------------------------------------------------------------
# Manifests / results
# ---------------------------------------------------------------------------
class RunManifestOut(BaseModel):
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
    enabled_modules: List[str] = Field(default_factory=list)
    solver: str
    solver_version: str
    solver_options: Dict[str, Any] = Field(default_factory=dict)
    objective: Optional[float] = None
    solver_status: str
    termination_reason: str = ""
    random_seed: Optional[int] = None
    environment_metadata: Dict[str, str] = Field(default_factory=dict)


class YearResultOut(BaseModel):
    year: int
    production: Dict[str, float] = Field(default_factory=dict)
    capacity: Dict[str, float] = Field(default_factory=dict)
    new_capacity: Dict[str, float] = Field(default_factory=dict)
    retirement: Dict[str, float] = Field(default_factory=dict)
    technology_shares: Dict[str, float] = Field(default_factory=dict)
    H2: float = 0.0
    electricity: float = 0.0
    coal: float = 0.0
    gas: float = 0.0
    ore: float = 0.0
    scrap: float = 0.0
    CO2: float = 0.0
    investment: float = 0.0
    total_cost: Optional[float] = None


class RunResultOut(BaseModel):
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
    yearly_results: List[YearResultOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Diagnostics / explainability
# ---------------------------------------------------------------------------
class TechnologyDiagnosticOut(BaseModel):
    year: int
    technology: str
    # Nullable: recorded per-run diagnostics legitimately carry None for
    # technologies not present in a given year (never coerced to 0).
    production: Optional[float] = None
    share: Optional[float] = None
    installed_capacity: Optional[float] = None
    new_capacity: Optional[float] = None
    retirement: Optional[float] = None
    effective_cost: Optional[float] = None
    unit_effective_cost: Optional[float] = None
    provenance: Optional[str] = None
    data_completeness: Optional[str] = None
    interpretability_status: Optional[str] = None


class ConstraintDiagnosticOut(BaseModel):
    year: int
    constraint_type: str
    available: Optional[float] = None
    used: Optional[float] = None
    slack: Optional[float] = None
    pressure: Optional[float] = None
    binding_status: str = ""


class PathwayEventOut(BaseModel):
    year: int
    technology: str
    event_type: str
    share_change: Optional[float] = None
    associated_drivers: List[str] = Field(default_factory=list)
    active_constraints: List[str] = Field(default_factory=list)
    limiting_data: List[str] = Field(default_factory=list)
    interpretation_status: str = ""


class DiagnosticsOut(BaseModel):
    technology_diagnostics: List[TechnologyDiagnosticOut] = Field(default_factory=list)
    constraint_diagnostics: List[ConstraintDiagnosticOut] = Field(default_factory=list)
    pathway_events: List[PathwayEventOut] = Field(default_factory=list)
    technology_shifts: List[Dict[str, Any]] = Field(default_factory=list)
    cost_crossovers: List[Dict[str, Any]] = Field(default_factory=list)
    source: str = "recorded"  # recorded | per-run


# ---------------------------------------------------------------------------
# Uncertainty
# ---------------------------------------------------------------------------
class TechStatOut(BaseModel):
    presence_frequency: Optional[float] = None
    share_mean: Optional[float] = None
    share_min: Optional[float] = None
    share_max: Optional[float] = None
    fraction_of_tested_scenarios_above_threshold: Optional[float] = None
    classification: str = "UNRESOLVED"


class UncertaintyMetricsOut(BaseModel):
    year: int
    share_threshold: float
    dominance_threshold: float
    n_valid_scenarios: int
    n_feasible_scenarios: int
    feasibility_rate: float
    technology_stats: Dict[str, TechStatOut] = Field(default_factory=dict)
    objective_stats: Optional[Dict[str, float]] = None
    cost_stats: Optional[Dict[str, Any]] = None
    policy_families: Optional[Dict[str, Any]] = None


class UncertaintyAnswersOut(BaseModel):
    answers: Dict[str, str] = Field(default_factory=dict)


class UncertaintyStudyOut(BaseModel):
    metrics: UncertaintyMetricsOut
    # Recorded Step-18 answers contain structured values (dicts/lists), not
    # only strings; they are passed through unchanged (never re-interpreted).
    answers: Dict[str, Any] = Field(default_factory=dict)
    scenarios: List[Dict[str, Any]] = Field(default_factory=list)
    source: str = "recorded"


class UncertaintySummaryOut(BaseModel):
    study: UncertaintyStudyOut
    fleet_scenarios: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    scrap_levels: Dict[str, float] = Field(default_factory=dict)
    dri_alternatives: Dict[str, float] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Benchmark (Vol.4 comparison)
# ---------------------------------------------------------------------------
class BenchmarkRowOut(BaseModel):
    metric: str
    year: Optional[int] = None
    scenario: Optional[str] = None
    ours: Optional[float] = None
    vol4: Optional[float] = None
    difference_absolute: Optional[float] = None
    difference_percent: Optional[float] = None
    unit: Optional[str] = None
    definition: Optional[str] = None
    source: Optional[str] = None
    comparison_status: Optional[str] = None
    scientific_status: Optional[str] = None
    limitation: Optional[str] = None


class BenchmarkOut(BaseModel):
    thresholds: Dict[str, Any] = Field(default_factory=dict)
    rows: List[BenchmarkRowOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Parameters / provenance
# ---------------------------------------------------------------------------
class ParameterOut(BaseModel):
    parameter_id: str
    name: str
    value: Optional[float] = None
    value_min: Optional[float] = None
    value_max: Optional[float] = None
    unit: Optional[str] = None
    provenance: str
    source: Optional[str] = None
    source_id: Optional[str] = None
    year: Optional[int] = None
    technology: Optional[str] = None
    status: str  # FROZEN | PROMOTED | CONDITIONAL | EXTERNAL_PENDING | UNKNOWN | DERIVED
    impact: Optional[str] = None
    detail: Dict[str, Any] = Field(default_factory=dict)


class SourceOut(BaseModel):
    source_id: str
    title: str
    publisher: str
    year: Optional[int] = None
    url: Optional[str] = None
    source_level: Optional[str] = None
    scope: Optional[str] = None
    parameters_extracted: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    filename: Optional[str] = None


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
class CompareRequest(BaseModel):
    run_id_a: str
    run_id_b: str


class CompareMetric(BaseModel):
    metric: str
    a: Optional[float] = None
    b: Optional[float] = None
    unit: Optional[str] = None
    status: str = "COMPARABLE"


class CompareTechnology(BaseModel):
    technology: str
    share_2050_a: Optional[float] = None
    share_2050_b: Optional[float] = None
    share_2070_a: Optional[float] = None
    share_2070_b: Optional[float] = None
    change_direction: str = ""


class CompareOut(BaseModel):
    run_a: RunStatusOut
    run_b: RunStatusOut
    metrics: List[CompareMetric] = Field(default_factory=list)
    technology_changes: List[CompareTechnology] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Run files / downloads
# ---------------------------------------------------------------------------
class RunFileOut(BaseModel):
    name: str
    path: str
    kind: str  # manifest | results | csv | config | diagnostics | plots | log
    size_bytes: int


class RunDetailOut(BaseModel):
    status: RunStatusOut
    manifest: Optional[RunManifestOut] = None
    results: Optional[RunResultOut] = None
    files: List[RunFileOut] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Frozen Phase 25 registries (productization, read-only)
# ---------------------------------------------------------------------------
class CompletenessRow(BaseModel):
    """One route's economic-completeness assessment from the frozen matrix."""

    route: str
    capex: str
    fom: str
    vom: str
    ore: str
    coal: str
    gas: str
    h2: str
    scrap: str
    electricity: str
    other: str
    economically_complete: bool
    missing_components: str


class RouteEconomicsRow(BaseModel):
    parameter_id: str
    route: str
    category: str
    value: str
    unit: str
    currency: Optional[str] = None
    base_year: Optional[str] = None
    year: Optional[str] = None
    source: Optional[str] = None
    source_org: Optional[str] = None
    page_or_table: Optional[str] = None
    boundary_scope: Optional[str] = None
    population: Optional[str] = None
    provenance: Optional[str] = None
    confidence: Optional[str] = None
    status: str
    notes: Optional[str] = None


class RouteCard(BaseModel):
    route: str
    completeness: CompletenessRow
    economics: List[RouteEconomicsRow] = Field(default_factory=list)


class ScrapSeriesRow(BaseModel):
    year: str
    scrap_consumption_mt: str
    domestic_generation_mt: str
    imports_mt: str
    route_share_pct: Optional[str] = None
    source: str
    boundary: str
    status: str


class ScrapEvidenceRow(BaseModel):
    evidence_id: str
    category: str
    value: str
    unit: str
    currency: Optional[str] = None
    base_year: Optional[str] = None
    year: Optional[str] = None
    scope: str
    source: str
    source_org: Optional[str] = None
    page_or_table: Optional[str] = None
    provenance: str
    confidence: Optional[str] = None
    notes: Optional[str] = None


class ScrapOut(BaseModel):
    series: List[ScrapSeriesRow] = Field(default_factory=list)
    evidence: List[ScrapEvidenceRow] = Field(default_factory=list)


class HydrogenOut(BaseModel):
    evidence: List[Dict[str, Any]] = Field(default_factory=list)


class HealthDetailOut(BaseModel):
    test_count: int
    import_ok: bool
    baseline_objective: Optional[float] = None
    solver_status: str
    data_hash: str
    parameter_counts: Dict[str, int] = Field(default_factory=dict)
    route_completeness: List[CompletenessRow] = Field(default_factory=list)


class FrozenRegistryOut(BaseModel):
    routes: List[CompletenessRow] = Field(default_factory=list)
    route_economics: List[RouteEconomicsRow] = Field(default_factory=list)
    scrap: ScrapOut = Field(default_factory=ScrapOut)
    hydrogen: HydrogenOut = Field(default_factory=HydrogenOut)
    health: HealthDetailOut = Field(default_factory=HealthDetailOut)
