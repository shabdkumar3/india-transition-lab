"""
India Steel Transition Lab — scenario registry + validation gates.

The web app must NOT silently alter scientific meaning. Scenario definitions
are whitelisted; overrides are validated against known config fields; M1 is
gated (DEFERRED — no real data); EXTERNAL_PENDING routes cannot be enabled
without the approved diagnostic gate. No arbitrary config paths, no
arbitrary Python, no silent parameter promotion.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import ScenarioDetail, ScenarioModule, ScenarioSummary

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNS_DIR = REPO_ROOT / "configs" / "runs"
OPT_DIR = REPO_ROOT / "configs" / "optimization"

# Routes whose full-plant economics remain EXTERNAL_PENDING (cannot be
# enabled in scientifically interpretable runs without the approved gate).
PENDING_ROUTES = ["Coal-DRI-EAF", "Coal-DRI-IF", "H2-DRI-EAF"]

# M1 (electrolyser learning) is DEFERRED — no real electrolyser dataset.
M1_GATE_REASON = (
    "M1: DEFERRED — no real electrolyser historical dataset is available. "
    "Activation is blocked to prevent synthetic-M1 leakage."
)

# Override keys the web API may accept for custom runs. Everything else is
# rejected (mirrors run.py's UNKNOWN-parameter gate).
ALLOWED_OVERRIDE_KEYS = {
    "mode",
    "scenario_name",
    "discount_rate",
    "use_dynamic_scrap",
    "use_deployment_dynamics",
    "use_endogenous_learning",
    "use_exogenous_electrolyser_cost_curve",
    "use_m1_electrolyser_learning",
    "enabled_routes",
    # Step 20/21 feature toggles (enabled: true/false inside the dict)
    "carbon_price",
    "h2_supply_cap",
    "stranded_asset_cost",
    "wacc_premium",
    "policy_incentives",
    "green_steel_premium",
    "grid_emission_intensity",
    "technology_ramp_limits",
    "resource_price_trajectories",
    "ccus",           # Step 22B: CCUS toggle
    "resource_prices",   # Step 23: resource price sensitivity (H2, coal, NG, iron ore)
    "economics",         # Step 23: CAPEX/OPEX sensitivity (H2-DRI CAPEX)
    "sec_improvement",   # Step 24: SEC improvement trajectory (NITI Vol.4-sourced)
    "demand_anchors_mt", # Step 27: custom demand trajectory (model-fitted vs NITI Vol.4)
    "scenarios",        # Step 27 override path: list of {name, demand_anchors_mt} replaces cfg["scenarios"]
}

# Uncertainty-study dimension keys.
UNCERTAINTY_DIMENSIONS = {
    "policy": ["CPS", "NZS"],
    "scrap_level": ["SCRAP_LOW", "SCRAP_HIGH"],
    "dri_alternative": ["DRI_IBM", "DRI_CEEW", "NONE"],
    "fleet_id": ["FLEET_CONSERVATIVE", "FLEET_CENTRAL", "FLEET_ALTERNATIVE"],
}


def _module(id_: str, label: str, state: str, reason: Optional[str] = None) -> ScenarioModule:
    return ScenarioModule(id=id_, label=label, state=state, reason=reason)


def _scenario_summaries() -> List[ScenarioSummary]:
    return [
        ScenarioSummary(
            id="cps",
            name="Current Policy Scenario (CPS)",
            mode="Vol.4",
            description=(
                "Vol.4-consistent Current Policy Scenario: "
                "Coal-DRI-IF no new capacity after 2030; BF-BOF new capacity allowed through mid-century (Vol.4 CPS); "
                "H2-DRI available from 2035. "
                "Full realism suite active: modelled carbon price trajectory, "
                "learning-by-doing, H₂ supply ramp, stranded-asset cost, "
                "grid emission intensity, construction lead times, WACC premium, "
                "PLI incentives, green-steel demand premium, rising scrap cost. "
                "Note: carbon price is a modelled incentive trajectory for scenario "
                "analysis — India has no enacted carbon pricing as of 2026."
            ),
            runnable=True,
            modules=[
                _module("scrap", "Dynamic scrap", "ON"),
                _module("learning", "Endogenous learning", "ON"),
                _module("carbon_price", "Carbon price $2→$130/tCO₂", "ON"),
                _module("h2_cap", "H₂ supply ramp", "ON"),
                _module("stranded", "Stranded-asset cost", "ON"),
                _module("grid_ei", "Grid emission intensity", "ON"),
                _module("lead_time", "Construction lead times", "ON"),
                _module("wacc", "WACC risk premium", "ON"),
                _module("pli", "PLI policy incentives", "ON"),
                _module("green_premium", "Green-steel premium", "ON"),
                _module("ramp_limits", "Technology ramp limits", "ON"),
                _module("m1", "M1 electrolyser learning", "DEFERRED", M1_GATE_REASON),
            ],
            policy_rules=[
                "Coal-DRI-IF: no new capacity after 2030; deployment ramp 8 Mt/yr (current policy project pipeline pace)",
                "Coal-DRI-EAF: deployment ramp 5 Mt/yr (niche route in India — Essar/JSW Hazira + announced expansions; 14 Mt existing near-ceiling; very limited new build)",
                "BF-BOF: new capacity allowed per Vol.4 CPS — dominance through 2050, gradual replacement thereafter; monotonic production decline from 2055",
                "H2-DRI-EAF enters market from 2035; deployment ramp 8 Mt/yr (nascent supply chain)",
                "NG-DRI-EAF deployment ramp: 12 Mt/yr (established shaft-furnace technology)",
                "Carbon price: $2/tCO₂ (2024) rising to $130/tCO₂ (2070) — modelled incentive trajectory for scenario analysis; India has no enacted carbon price as of 2026",
                "Green hydrogen supply cap (CPS): 0.20 Mt (2030) → 14 Mt (2070) — Vol.4 CPS steel-specific (13.3 Mt 2070)",
                "Learning-by-doing: H2-DRI-EAF costs fall 10% per doubling of capacity; Scrap-EAF 5%",
                "Stranded-asset penalty: 30% of annualised CAPEX per Mt retired before end-of-life",
                "H₂ price (CPS): $1.65/kg (2030) → $1.10/kg (2040) → $0.70/kg (2070) — moderate NGHM learning",
                "Electricity price (CPS): $40/MWh (2030) → $32/MWh (2040) → $17/MWh (2070)",
                "Grid emission intensity (CPS): 0.716 tCO₂/MWh (2024) → 0.565 (2030) → 0.055 (2070)",
                "Construction lead times: BF-BOF/H2-DRI 3 years; NG-DRI/Coal-DRI 2 years; Scrap-EAF 1 year",
                "WACC premium: H2-DRI-EAF costs 1.25× standard CAPEX (higher financing risk for early technology)",
                "PLI incentive: H2-DRI-EAF receives −$20/t subsidy (2030), tapering to zero by 2050",
                "Green-steel demand premium: $8/t (2030) rising to $65/t (2070) for H2-DRI-EAF and Scrap-EAF",
                "Scrap price: $250/t (2024) rising to $400/t (2070) as global scrap demand increases",
            ],
            tags=["vol4", "cps", "step20", "step21"],
        ),
        ScenarioSummary(
            id="nzs",
            name="Net Zero Scenario (NZS)",
            mode="Vol.4",
            description=(
                "Vol.4-consistent Net Zero Scenario: "
                "H2-DRI from 2030; NG-DRI cutoff 2040; BF-BOF no new investment after 2030. "
                "Full realism suite active: stronger modelled carbon price ($5→$200/tCO₂), "
                "all Step 21 enhancements active. "
                "Note: carbon price is a modelled trajectory for scenario analysis — "
                "India has no enacted carbon pricing as of 2026."
            ),
            runnable=True,
            modules=[
                _module("scrap", "Dynamic scrap", "ON"),
                _module("learning", "Endogenous learning", "ON"),
                _module("carbon_price", "Carbon price $5→$200/tCO₂", "ON"),
                _module("h2_cap", "H₂ supply ramp", "ON"),
                _module("stranded", "Stranded-asset cost", "ON"),
                _module("grid_ei", "Grid emission intensity", "ON"),
                _module("lead_time", "Construction lead times", "ON"),
                _module("wacc", "WACC risk premium", "ON"),
                _module("pli", "PLI policy incentives", "ON"),
                _module("green_premium", "Green-steel premium", "ON"),
                _module("ramp_limits", "Technology ramp limits", "ON"),
                _module("m1", "M1 electrolyser learning", "DEFERRED", M1_GATE_REASON),
            ],
            policy_rules=[
                "Coal-DRI-IF: no new capacity after 2030; deployment ramp 7 Mt/yr (coal discouraged under NZS carbon price)",
                "Coal-DRI-EAF: deployment ramp 5 Mt/yr (niche route; coal discouraged under NZS carbon price; 14 Mt existing near-ceiling)",
                "H2-DRI-EAF enters market from 2030 (5 years earlier than CPS); deployment ramp 20 Mt/yr (NGHM fully backed + global spill-in)",
                "NG-DRI-EAF: no new capacity after 2040; deployment ramp 10 Mt/yr",
                "BF-BOF: no new capacity after 2060 (Vol.4 NZS Table 3.1; 3-yr lead time → last commissioning 2060); monotonic production decline from 2040 (end of dominance)",
                "Carbon price: $5/tCO₂ (2024) rising to $200/tCO₂ (2070) — modelled incentive trajectory for scenario analysis (India has no enacted carbon price as of 2026)",
                "Green hydrogen supply cap (NZS): 0.55 Mt (2030) → 30 Mt (2070) — NGHM fully funded + imports",
                "Learning-by-doing: H2-DRI-EAF 10% cost reduction per doubling; Scrap-EAF 5%",
                "Stranded-asset penalty: 30% of annualised CAPEX per Mt retired early",
                "H₂ price (NZS): $1.30/kg (2030) → $0.60/kg (2040) → $0.30/kg (2070) — accelerated electrolyser learning",
                "Electricity price (NZS): $34/MWh (2030) → $22/MWh (2040) → $10/MWh (2070)",
                "Grid emission intensity (NZS): 0.716 tCO₂/MWh (2024) → 0.480 (2030) → 0.020 (2070) — near-zero grid",
                "Construction lead times, WACC premium, PLI incentives, green-steel premium — all active",
            ],
            tags=["vol4", "nzs", "step20", "step21"],
        ),
        ScenarioSummary(
            id="control",
            name="Control (Diagnostic only)",
            mode="MODE_A",
            description=(
                "Unconstrained least-cost diagnostic reference — no policy, no Vol.4 constraints. "
                "Use only to compare route costs without any realism enhancements. "
                "Not a valid decarbonization pathway."
            ),
            runnable=True,
            modules=[
                _module("scrap", "Dynamic scrap", "OFF"),
                _module("learning", "Endogenous learning", "OFF"),
                _module("carbon_price", "Carbon price", "OFF"),
                _module("grid_ei", "Grid emission intensity", "OFF"),
                _module("lead_time", "Construction lead times", "OFF"),
                _module("m1", "M1 electrolyser learning", "DEFERRED", M1_GATE_REASON),
            ],
            policy_rules=["No policy restrictions — unconstrained cost minimization only."],
            tags=["diagnostic"],
        ),
        ScenarioSummary(
            id="uncertainty_study",
            name="Uncertainty Study",
            mode="MODE_B",
            description=(
                "Uncertainty-bounded pathway study over three unresolved empirical "
                "dimensions: Scrap-EAF scrap intensity (scenario bounds), DRI charge "
                "ratio (IBM vs CEEW source interpretations), and existing fleet "
                "scenario. Runs one representative member of the recorded study."
            ),
            runnable=True,
            modules=[
                _module("scrap", "Scrap intensity (bounds)", "SCENARIO_BOUNDS"),
                _module("dri", "DRI charge ratio", "ALTERNATIVE_INTERPRETATIONS"),
                _module("fleet", "Existing fleet scenario", "SCENARIO"),
                _module("m1", "M1 electrolyser learning", "DEFERRED", M1_GATE_REASON),
            ],
            policy_rules=[
                "Scrap intensity: SCRAP_LOW 1.00 / SCRAP_HIGH 1.15 t/t (no frozen base)",
                "DRI charge: DRI_IBM 0.40 vs DRI_CEEW 0.875 (alternative interpretations)",
                "Fleet: FLEET_CONSERVATIVE / CENTRAL / ALTERNATIVE (coverage disclosed)",
                "Route-level fleet split remains UNRESOLVED — interpretability flagged",
            ],
            tags=["vol4", "uncertainty", "scenario-bounds"],
        ),
        ScenarioSummary(
            id="custom",
            name="Custom Scenario",
            mode="MODE_B",
            description=(
                "User-defined scenario from validated overrides on the Mode B policy "
                "base. EXTERNAL_PENDING routes and M1 activation are blocked."
            ),
            runnable=True,
            modules=[
                _module("scrap", "Dynamic scrap", "OFF"),
                _module("deployment", "Deployment dynamics", "OFF"),
                _module("learning", "Endogenous learning", "OFF"),
                _module("m1", "M1 electrolyser learning", "DEFERRED", M1_GATE_REASON),
                _module("uncertainty", "Uncertainty overrides", "OFF"),
            ],
            policy_rules=["Only whitelisted overrides; pending routes blocked."],
            tags=["custom", "vol4"],
        ),
    ]


def list_scenarios() -> List[ScenarioSummary]:
    return _scenario_summaries()


def get_scenario(scenario_id: str) -> Optional[ScenarioDetail]:
    for s in _scenario_summaries():
        if s.id == scenario_id:
            return _to_detail(s)
    return None


def _to_detail(s: ScenarioSummary) -> ScenarioDetail:
    base_config = {
        "control": "configs/optimization/baseline.yaml",
        "cps": "configs/optimization/mode_b_policy.yaml",
        "nzs": "configs/optimization/mode_b_policy.yaml",
        "uncertainty_study": "configs/optimization/mode_b_policy.yaml",
        "custom": "configs/optimization/mode_b_policy.yaml",
    }[s.id]
    dims = {}
    if s.id == "uncertainty_study":
        dims = {
            "policy": [
                {"id": "CPS", "label": "CPS", "value": None, "note": "Current Policies"},
                {"id": "NZS", "label": "NZS", "value": None, "note": "Net Zero"},
            ],
            "scrap_level": [
                {"id": "SCRAP_LOW", "label": "SCRAP_LOW", "value": 1.00, "note": "t/t — physical lower bound"},
                {"id": "SCRAP_HIGH", "label": "SCRAP_HIGH", "value": 1.15, "note": "t/t — source-supported upper bound"},
            ],
            "dri_alternative": [
                {"id": "DRI_IBM", "label": "DRI_IBM", "value": 0.40, "note": "IBM IMYB 2022 charge ratio"},
                {"id": "DRI_CEEW", "label": "DRI_CEEW", "value": 0.875, "note": "CEEW 2024 cluster survey"},
                {"id": "NONE", "label": "None", "value": None, "note": "Keep Coal-DRI-IF disabled"},
            ],
            "fleet_id": [
                {"id": "FLEET_CONSERVATIVE", "label": "Conservative", "value": None, "note": "Documented plants only"},
                {"id": "FLEET_CENTRAL", "label": "Central", "value": None, "note": "GSI/MoS aggregates"},
                {"id": "FLEET_ALTERNATIVE", "label": "Alternative", "value": None, "note": "+15% BOF scrap interpretation"},
            ],
        }
    return ScenarioDetail(
        **s.model_dump(),
        base_config=base_config,
        allowed_overrides=sorted(ALLOWED_OVERRIDE_KEYS),
        gated_parameters=PENDING_ROUTES if s.id == "custom" else [],
        uncertainty_dimensions=dims,
        data_completeness={
            "existing_route_capacity": "UNRESOLVED",
            "route_transition_interpretability": False,
            "m1": "DEFERRED",
            "scrap_intensity": "EXTERNAL_PENDING" if s.id == "uncertainty_study" else "SCENARIO_BOUNDS",
        },
    )


# ---------------------------------------------------------------------------
# Validation gates
# ---------------------------------------------------------------------------
class ScenarioValidationError(ValueError):
    """Raised when a run request violates a scientific/security gate."""


def validate_run_request(
    scenario_id: str, overrides: Dict[str, Any], uncertainty_params: Dict[str, str]
) -> None:
    """Validate a run request against every gate. Raises on violation."""
    if get_scenario(scenario_id) is None:
        raise ScenarioValidationError(f"Unknown scenario '{scenario_id}'.")

    # --- Gate: unknown override keys -------------------------------------
    for key in overrides:
        base_key = key.split(".")[0]
        if base_key not in ALLOWED_OVERRIDE_KEYS:
            raise ScenarioValidationError(
                f"UNKNOWN override '{key}' cannot enter optimization."
            )

    # --- Gate: M1 activation ----------------------------------------------
    m1 = overrides.get("use_m1_electrolyser_learning", False)
    if m1 is True:
        raise ScenarioValidationError(M1_GATE_REASON)

    # --- Gate: EXTERNAL_PENDING routes ------------------------------------
    enabled = overrides.get("enabled_routes")
    if isinstance(enabled, list):
        blocked = [r for r in enabled if r in PENDING_ROUTES]
        if blocked:
            raise ScenarioValidationError(
                f"Route(s) {blocked} contain EXTERNAL_PENDING parameters and cannot "
                "be enabled without the approved diagnostic gate."
            )

    # --- Gate: uncertainty-study dimensions --------------------------------
    if scenario_id == "uncertainty_study":
        for key, value in uncertainty_params.items():
            if key not in UNCERTAINTY_DIMENSIONS:
                raise ScenarioValidationError(f"Unknown uncertainty dimension '{key}'.")
            if value not in UNCERTAINTY_DIMENSIONS[key]:
                raise ScenarioValidationError(
                    f"Unknown value '{value}' for '{key}'; "
                    f"expected one of {UNCERTAINTY_DIMENSIONS[key]}."
                )
