"""
Model configuration schema governing scenario settings, Mode A/B execution modes, and optimization parameters.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from steel_model.technology_ids import CANONICAL_TECHNOLOGY_IDS


class ModelMode(str, Enum):
    """Execution mode definition."""
    MODE_A = "MODE_A"  # Benchmark consistency / constrained diagnostic mode
    MODE_B = "MODE_B"  # Enriched physical feasibility model


class ScenarioConfig(BaseModel):
    """Configuration settings for a specific scenario run (CPS or NZS)."""
    scenario_name: str = Field(..., description="Scenario identifier (e.g. CPS or NZS)")
    discount_rate: float = Field(0.08, ge=0.0, le=0.25, description="Social discount rate (default 8%)")
    start_year: int = Field(2024, description="Start year of optimization horizon")
    end_year: int = Field(2070, description="End year of optimization horizon")
    use_endogenous_learning: bool = Field(False, description="Enable outer sequential endogenous learning loop")
    use_dynamic_scrap: bool = Field(False, description="Enable dynamic scrap cohort stock-flow modeling")
    use_m1_electrolyser_learning: bool = Field(
        False,
        description="Enable M1 electrolyser-component learning exponent (b_elec) in Mode B. "
        "M1 is DISABLED in Mode A and is mutually exclusive with "
        "use_exogenous_electrolyser_cost_curve (no double counting).",
    )
    use_exogenous_electrolyser_cost_curve: bool = Field(
        False,
        description="Use an exogenous IEA/CEEW electrolyser CAPEX trajectory (BASE structure). "
        "Mutually exclusive with use_m1_electrolyser_learning (no double counting of learning).",
    )
    use_deployment_dynamics: bool = Field(
        False,
        description="Enable technology deployment dynamics constraints (lead times, start years, deployment ceiling) in Mode B."
    )
    benchmark_slack_penalty: float = Field(1000.0, ge=0.0, description="Objective penalty per unit share deviation in Mode A")


class ModelConfig(BaseModel):
    """Master application configuration container."""
    mode: ModelMode = Field(ModelMode.MODE_A, description="Target execution mode")
    scenario: ScenarioConfig = Field(..., description="Active scenario configuration")
    technology_routes: List[str] = Field(
        default_factory=lambda: list(CANONICAL_TECHNOLOGY_IDS),
        description="Supported steel route IDs"
    )
    data_dir: str = Field("data", description="Root path to data directory")

    @model_validator(mode="after")
    def validate_mode_boundaries(self) -> "ModelConfig":
        """Keep Mode A free of Mode B-only dynamic assumptions."""
        if self.mode == ModelMode.MODE_A:
            if self.scenario.use_endogenous_learning:
                raise ValueError("Mode A cannot enable endogenous learning.")
            if self.scenario.use_dynamic_scrap:
                raise ValueError("Mode A cannot enable dynamic scrap.")
            if self.scenario.use_deployment_dynamics:
                raise ValueError("Mode A cannot enable deployment dynamics.")
            if self.scenario.use_m1_electrolyser_learning:
                raise ValueError("Mode A cannot enable M1 electrolyser learning.")
            if self.scenario.use_exogenous_electrolyser_cost_curve:
                raise ValueError(
                    "Mode A cannot enable an exogenous electrolyser cost curve: "
                    "Mode A reproduces the frozen Step 6 cross-section "
                    "(electrolyser CAPEX 452 USD/kWe, 2019 USD, no time trajectory)."
                )
        return self

    @model_validator(mode="after")
    def validate_m1_exogenous_exclusivity(self) -> "ModelConfig":
        """M1 and exogenous electrolyser cost curves are mutually exclusive.

        Both structures model the SAME quantity (electrolyser CAPEX trajectory);
        enabling both double-counts learning (Step 7B audit, M1_INTERFACE_SPEC.md).
        """
        if self.scenario.use_m1_electrolyser_learning and self.scenario.use_exogenous_electrolyser_cost_curve:
            raise ValueError(
                "M1 electrolyser learning and the exogenous electrolyser cost curve are "
                "mutually exclusive — enabling both double-counts electrolyser learning."
            )
        return self

    @model_validator(mode="after")
    def validate_m1_requires_learning_loop(self) -> "ModelConfig":
        """M1 feeds the outer sequential learning loop; enabling it without the
        loop is an incoherent state (b_elec would be produced but unconsumed).
        """
        if self.scenario.use_m1_electrolyser_learning and not self.scenario.use_endogenous_learning:
            raise ValueError(
                "M1 electrolyser learning requires use_endogenous_learning=True: "
                "b_elec is consumed only by the outer sequential learning loop "
                "(MODEL_FORMULATION Section 7, M1_INTERFACE_SPEC.md)."
            )
        return self
