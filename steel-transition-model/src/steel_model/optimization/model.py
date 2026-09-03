"""
Baseline multi-period MILP — model assembly (Step 8).

Loads the frozen control configuration (configs/optimization/baseline.yaml)
plus the Step-5 ResourceRegistry, assembles the LP (variables, bounds,
constraints, objective), solves it with HiGHS via scipy.optimize.milp and
returns a BaselineMILPResult.

Baseline identity (MODE A control run):
  "Baseline MILP — economics-available route subset"
  - Enabled routes: only those with FROZEN full-plant economics
    (BF-BOF, NG-DRI-EAF, Scrap-EAF).
  - Disabled routes: Coal-DRI-EAF, Coal-DRI-IF, H2-DRI-EAF
    (reason: EXTERNAL_PENDING_FULL_PLANT_ECONOMICS).
  - Existing per-route capacity: 0.0 (documented data limitation;
    aggregate 200.333 Mt is context only).
  - Discount rate 0.08 and availability 0.90 are PROJECT_PROPOSAL
    parameters, kept configurable and labelled as such.

Disabled routes produce zero ONLY because they are not economically
parameterized — never as an optimization conclusion.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import yaml

from steel_model.optimization.variables import VariableIndex, build_bounds
from steel_model.optimization.constraints import build_constraints
from steel_model.optimization.objective import build_objective
from steel_model.optimization.solver import solve_milp
from steel_model.optimization.results import (
    BaselineMILPResult,
    build_result,
)
from steel_model.resources.intensity_loader import IntensityLoader
from steel_model.resources.resource_registry import ResourceRegistry
from steel_model.scrap.scrap_engine import ScrapEngine
from steel_model.schema.provenance_policy import (
    ProvenanceGateError,
    resolve_intensity,
)

# Canonical six-route namespace (mirrors technology_ids.CANONICAL_TECHNOLOGY_IDS).
ALL_ROUTES = [
    "BF-BOF",
    "Coal-DRI-EAF",
    "Coal-DRI-IF",
    "NG-DRI-EAF",
    "H2-DRI-EAF",
    "Scrap-EAF",
]

# Resource IDs tracked in the RES block (kept separate per Step 8 §13):
# ore, scrap, coal (coking + non-coking), gas, H2, electricity.
DEFAULT_RESOURCES = [
    "iron_ore",
    "scrap",
    "coking_coal",
    "non_coking_coal",
    "natural_gas",
    "hydrogen",
    "electricity_route",
]

# Price-config key -> registry resource_id alias (only electricity differs).
_PRICE_KEY_TO_RESOURCE = {
    "iron_ore": "iron_ore",
    "scrap": "scrap",
    "coking_coal": "coking_coal",
    "non_coking_coal": "non_coking_coal",
    "natural_gas": "natural_gas",
    "hydrogen": "hydrogen",
    "electricity": "electricity_route",
}


@dataclass
class BaselineInputs:
    """All frozen/configurable inputs consumed by the baseline MILP."""

    routes: List[str]
    all_routes: List[str]
    years: List[int]
    start_year: int
    demand_mt: Dict[int, float]
    discount_rate: float
    discount_rate_provenance: str
    lifetime_years: int
    start_years: Dict[str, int]
    availability: Dict[str, float]
    availability_provenance: str
    availability_provenance_by_route: Dict[str, str]
    capex_annualised_usd_per_t: Dict[str, float]
    opex_fixed_usd_per_t: Dict[str, float]
    vom_usd_per_t: Dict[str, float]
    resources: List[str]
    resource_price_model_unit: Dict[str, float]
    resource_price_source_unit: Dict[str, str]
    resource_price_model_unit_name: Dict[str, str]
    resource_price_conversion_formula: Dict[str, str]
    resource_price_conversion_factor: Dict[str, float]
    resource_price_conversion_operation: Dict[str, str]
    resource_price_provenance: Dict[str, str]
    resource_intensity: Dict[Tuple[str, str], Optional[float]]
    process_emission: Dict[str, float]
    combustion_emission: Dict[str, float]
    existing_capacity_per_route_mt: Dict[str, float]
    existing_capacity_data_available: bool
    aggregate_capacity_context_mt: Optional[float]
    data_limitations: List[str] = field(default_factory=list)
    # Step 13 remediation: provenance-gated intensity status + gate record.
    intensity_status: Dict[Tuple[str, str], dict] = field(default_factory=dict)
    provenance_gating: dict = field(default_factory=dict)
    # Step 13 remediation: fleet/transition diagnostics.
    existing_route_capacity_available: bool = False
    route_transition_interpretability: bool = False
    technology_space_completeness: str = "INCOMPLETE"
    m1_enabled: bool = False
    endogenous_learning_enabled: bool = False
    dynamic_scrap_enabled: bool = False
    deployment_dynamics_enabled: bool = False
    deployment_penalties_enabled: bool = False
    construction_lead_time_years: Dict[str, int] = field(default_factory=dict)
    ncap_limits_mt: Dict[str, Optional[float]] = field(default_factory=dict)
    deployment_provenance: str = ""
    # Step 9: compiled scrap stock-flow engine (None when MODE A / disabled).
    scrap_engine: Optional[ScrapEngine] = None
    # Static scrap availability cap (Mode A only): upper bound on total scrap
    # consumed per year (Mt). None = uncapped. Values are piecewise-linearly
    # interpolated from anchor_years_mt in the config. Mode B uses the dynamic
    # scrap engine instead and does not apply this cap.
    static_scrap_cap_mt: Optional[Dict[int, float]] = None

    # Step 11: Endogenous Learning Parameters
    learning_rates: Dict[str, float] = field(default_factory=dict)
    learning_exponents: Dict[str, float] = field(default_factory=dict)
    initial_cumulative_capacity_mt: Dict[str, float] = field(default_factory=dict)
    learning_scopes: Dict[str, str] = field(default_factory=dict)
    learning_provenance_by_route: Dict[str, str] = field(default_factory=dict)
    learning_tolerance: float = 0.001
    learning_max_iterations: int = 20
    learning_provenance: str = ""

    # ── Step 20 realism enhancements ─────────────────────────────────────────
    # (A) Carbon price: cost on CO2[t] in the objective.
    #     carbon_price_usd_per_tco2 is interpolated from config anchor years.
    carbon_price_enabled: bool = False
    carbon_price_usd_per_tco2: Dict[int, float] = field(default_factory=dict)
    carbon_price_provenance: str = ""

    # (B) H₂ supply cap: upper bound on RES["hydrogen",t] per year.
    #     Represents infrastructure ramp-up limits on green H₂ availability.
    h2_supply_cap_enabled: bool = False
    h2_supply_cap_mt: Optional[Dict[int, float]] = None
    h2_supply_cap_provenance: str = ""

    # (C) Stranded-asset cost: penalty on RET[i,t] proportional to remaining CAPEX.
    #     stranded_cost_fraction * capex_i * RET[i,t] per retirement event.
    stranded_cost_enabled: bool = False
    stranded_cost_fraction: float = 0.0
    stranded_cost_provenance: str = ""

    # (D) Time-varying resource prices: resource_id -> {year: price}.
    #     When present, overrides the static price in the objective for that year.
    resource_price_trajectory: Dict[str, Dict[int, float]] = field(default_factory=dict)

    # ── Step 21 realism enhancements (batch 2) ───────────────────────────────
    # (A) Grid emission intensity: tCO₂/MWh electricity from grid.
    #     Adds elec_intensity[i] * grid_ei[t] to the CO2 constraint coefficient
    #     on ACT[i,t] — prevents electrolytic routes from appearing zero-carbon
    #     while India's grid is still coal-heavy.
    grid_emission_enabled: bool = False
    grid_ei_tco2_per_mwh: Dict[int, float] = field(default_factory=dict)
    grid_emission_provenance: str = ""

    # (B) Construction lead time: years before NCAP[i,t] appears in CAP.
    #     Constraint 3 becomes: CAP[i,t] = Existing + CumNCAP[i,t-L] - CumRET[i,t].
    #     Defaults to 0 (backward-compatible). Loaded from construction_lead_time
    #     block (standalone) or deployment_dynamics → TechnologyRegistry.
    construction_lead_time_active: bool = False

    # (C) WACC risk premium: multiplicative factor on annualised CAPEX.
    #     Represents higher financing cost for nascent / high-risk technologies.
    wacc_premium_enabled: bool = False
    wacc_premium_by_route: Dict[str, float] = field(default_factory=dict)
    wacc_premium_provenance: str = ""

    # (D) Policy incentives / PLI: negative USD/t cost on ACT[i,t].
    #     Route-specific subsidy schedule. Negative value = revenue/subsidy.
    policy_incentives_enabled: bool = False
    policy_incentives_usd_per_t: Dict[str, Dict[int, float]] = field(default_factory=dict)
    policy_incentives_provenance: str = ""

    # (E) Green-steel premium: revenue bonus for routes below emission threshold.
    #     Qualifying routes listed explicitly; premium interpolated per year.
    green_premium_enabled: bool = False
    green_premium_threshold_tco2_per_t: float = 0.5
    green_premium_qualifying_routes: List[str] = field(default_factory=list)
    green_premium_usd_per_t: Dict[int, float] = field(default_factory=dict)
    green_premium_provenance: str = ""

    # Step 22B: CCUS (Carbon Capture, Utilisation and Storage)
    # ccus_capture_fraction_by_route_year[route][year] = fraction of direct
    # emissions captured (0 = none; 0.85 = 85% captured).  Only non-zero
    # from ccus_available_from_year onwards for eligible routes.
    ccus_enabled: bool = False
    ccus_capture_fraction_by_route_year: Dict[str, Dict[int, float]] = field(default_factory=dict)
    ccus_provenance: str = ""

    # Step 24: SEC improvement trajectory (NITI Vol.4-sourced)
    # sec_improvement_factor_by_year[year] = cumulative fractional improvement
    # vs 2024 baseline. e.g. 0.23 in 2070 (CPS) = 23% lower fuel/energy intensity.
    # Applied to: combustion_emission (fuel burning) + all fuel resource_intensities
    #             (coal, natural_gas, electricity).
    # NOT applied to: process_emission (stoichiometric CO2), or material inputs
    #                 (iron_ore, scrap, hydrogen) which have separate drivers.
    # Source: NITI Vol.4 Table 3.1 — CPS: -12%/2050, -23%/2070; NZS: -24%/2050, -38%/2070
    sec_improvement_factor_by_year: Dict[int, float] = field(default_factory=dict)
    sec_improvement_provenance: str = ""

    # Step 17B: Mode B policy constraints (Vol.4-consistent scenario)
    # ncap_cutoff_years: route -> last year in which new capacity may be
    # commissioned. build_bounds() enforces ub[NCAP[i,t]] = 0 for t > cutoff.
    # Gate A approved 2026-08-14. Empty dict = Mode A (no cutoffs).
    ncap_cutoff_years: Dict[str, int] = field(default_factory=dict)
    mode_b_label: str = ""  # e.g. "MODE_B_CPS" / "MODE_B_NZS" / "" for Mode A
    # Step 17B: Gate F availability start years (route -> year) and Gate C
    # scrap waypoints (post-solve diagnostics only, NOT MILP constraints).
    route_availability_start_years: Dict[str, int] = field(default_factory=dict)
    scrap_waypoints: List[dict] = field(default_factory=list)
    explicit_non_rules: Dict[str, str] = field(default_factory=dict)
    mode_b_policy_record: dict = field(default_factory=dict)
    # Step 17B extension: Monotonic production decline constraint.
    # ACT[i, t+1] <= ACT[i, t] for all t >= from_year.
    # Prevents utilization cycling for legacy routes (BF-BOF) where restarting
    # idled plants has no physical basis in India's steel sector.
    monotonic_decline_from_years: Dict[str, int] = field(default_factory=dict)

    # Step 22: Technology ramp limits (TIMES-style bounded optimization).
    # NCAP[i,t] <= max_ncap_mt_per_year[i] for all t.
    # Prevents over-rapid scale-up of nascent technologies (H2-DRI, Scrap-EAF).
    # Per-route flat annual cap (Mt/yr); empty dict = no ramp limits applied.
    technology_ramp_limits_enabled: bool = False
    technology_ramp_limits_mt: Dict[str, float] = field(default_factory=dict)
    technology_ramp_limits_provenance: str = ""

    # Step 26: Minimum production floor for Vol.4-narrative-anchored routes.
    # ACT[i, t] >= floor_t for each (route, year) in this dict.
    # Implements "BF-BOF dominant through 2050 in CPS" (NITI Vol.4 Table 3.1).
    # Values are anchor years; intermediate years linearly interpolated in
    # constraints.py. Empty dict = no floor constraints applied.
    min_production_floor_mt: Dict[str, Dict[int, float]] = field(default_factory=dict)

    @property
    def baseline_label(self) -> str:
        return "Baseline MILP — economics-available route subset"


def derive_annual_demand(
    anchors_mt: Dict[int, float],
    start_year: int,
    end_year: int,
) -> Dict[int, float]:
    """
    Piecewise-linear interpolation of published demand anchors.

    The baseline uses Vol. 4 anchor points (2024/2050/2070) with linear
    interpolation between them (documented Step 3A convention). No
    S-curve, no yield factor, no scenario divergence in this baseline.
    """
    sorted_years = sorted(anchors_mt)
    if not sorted_years:
        raise ValueError("Demand anchors cannot be empty.")
    out: Dict[int, float] = {}
    for t in range(start_year, end_year + 1):
        if t in anchors_mt:
            out[t] = anchors_mt[t]
            continue
        # Clamp outside anchor range (flat extrapolation, documented).
        if t < sorted_years[0]:
            out[t] = anchors_mt[sorted_years[0]]
            continue
        if t > sorted_years[-1]:
            out[t] = anchors_mt[sorted_years[-1]]
            continue
        # Piecewise-linear between bracketing anchors.
        for lo, hi in zip(sorted_years, sorted_years[1:]):
            if lo <= t <= hi:
                span = hi - lo
                frac = (t - lo) / span if span > 0 else 0.0
                out[t] = anchors_mt[lo] + frac * (anchors_mt[hi] - anchors_mt[lo])
                break
    return out


def load_baseline_inputs(
    config_path: str,
    intensities_path: Optional[str] = None,
    scenario: str = "CPS",
) -> BaselineInputs:
    """
    Load baseline.yaml plus the Step-5 intensity registry into BaselineInputs.

    Raises ValueError on missing required keys. No scientific constants
    are hard-coded here: everything numeric comes from the config/registry.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Baseline config not found: '{config_path}'")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if intensities_path is None:
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        intensities_path = os.path.join(
            project_root, "configs", "resources", "steel_intensities.yaml"
        )
    dataset = IntensityLoader.load(intensities_path)
    registry = ResourceRegistry(dataset)

    # ------------------------------------------------------------------
    # Horizon & discounting
    # ------------------------------------------------------------------
    horizon = cfg.get("horizon", {})
    start_year = int(horizon.get("start_year", 2024))
    end_year = int(horizon.get("end_year", 2070))
    years = list(range(start_year, end_year + 1))

    # Discount-rate provenance is read from the config record — it is
    # NEVER hard-coded inside optimization logic (review item 2). A
    # missing provenance record fails loudly rather than silently
    # substituting a label.
    discount_cfg = cfg.get("discount_rate", {})
    if isinstance(discount_cfg, dict):
        if "provenance" not in discount_cfg:
            raise ValueError(
                "discount_rate is missing its provenance record: the config "
                "must carry 'discount_rate.provenance' (never hard-coded)."
            )
        discount_rate = float(discount_cfg.get("value", 0.08))
        discount_provenance = str(discount_cfg["provenance"])
    else:
        raise ValueError(
            "discount_rate must be a mapping {value, provenance}; scalar "
            "values are rejected so provenance is never hard-coded."
        )

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    enabled = list(cfg.get("enabled_routes", []))
    missing = [r for r in enabled if r not in ALL_ROUTES]
    if missing:
        raise ValueError(f"Unknown enabled routes in config: {missing}")

    # ------------------------------------------------------------------
    # Demand (scenario-invariant anchors in this baseline)
    # ------------------------------------------------------------------
    scenarios = cfg.get("scenarios", [])
    anchors: Dict[int, float] = {}
    for sc in scenarios:
        if sc.get("name") == scenario:
            anchors = {int(k): float(v) for k, v in sc.get("demand_anchors_mt", {}).items()}
            break
    if not anchors:
        raise ValueError(f"No demand anchors for scenario '{scenario}' in config.")
    demand = derive_annual_demand(anchors, start_year, end_year)

    # ------------------------------------------------------------------
    # Economics (frozen IEA 2020 annualised CAPEX; frozen Step-6 OPEX)
    # ------------------------------------------------------------------
    econ = cfg.get("economics", {})
    capex = {r: float(econ["capex_annualised_usd_per_t"][r]) for r in enabled}
    opex_fixed = {r: float(econ["opex_fixed_usd_per_t"][r]) for r in enabled}
    vom = {r: float(econ.get("vom_usd_per_t", {}).get(r, 0.0)) for r in enabled}

    # ------------------------------------------------------------------
    # Step 22B: CCUS — apply additional CAPEX/OPEX and build capture fraction
    # ------------------------------------------------------------------
    ccus_cfg = cfg.get("ccus", {})
    ccus_enabled = bool(ccus_cfg.get("enabled", False))
    ccus_capture_fraction_by_route_year: Dict[str, Dict[int, float]] = {}
    ccus_provenance = ccus_cfg.get("provenance", "PROJECT_PROPOSAL")
    if ccus_enabled:
        # Step 24: Route-specific capture rates supported via capture_rate_by_route dict.
        # BF-BOF gets 56% (NITI Vol.4: whole-plant CO2 reduction; only ~66% of BF-BOF
        # CO2 is in capturable concentrated streams, captured at ~85% efficiency → 56%).
        # DRI routes retain 0.85 (IEA CCUS for Steel 2023; concentrated CO2 streams).
        global_capture_rate = float(ccus_cfg.get("capture_rate", 0.85))
        capture_rate_by_route = ccus_cfg.get("capture_rate_by_route", {})
        available_from = int(ccus_cfg.get("available_from_year", 2030))
        eligible_routes = set(ccus_cfg.get("eligible_routes", []))
        add_capex_cfg = ccus_cfg.get("additional_capex_usd_per_t", {})
        add_opex_cfg = ccus_cfg.get("additional_opex_usd_per_t", {})
        for r in enabled:
            if r not in eligible_routes:
                continue
            # Add CCUS capital and operating cost to route economics
            capex[r] += float(add_capex_cfg.get(r, 0.0))
            opex_fixed[r] += float(add_opex_cfg.get(r, 0.0))
            # Route-specific capture fraction (falls back to global default)
            route_capture = float(capture_rate_by_route.get(r, global_capture_rate))
            # Build year-indexed capture fraction (0 before available_from)
            ccus_capture_fraction_by_route_year[r] = {
                t: (route_capture if t >= available_from else 0.0)
                for t in range(start_year, end_year + 1)
            }

    # ------------------------------------------------------------------
    # Step 24: SEC improvement trajectory — NITI Vol.4 Table 3.1
    # CPS: -12% by 2050, -23% by 2070 vs 2025 baseline
    # NZS: -24% by 2050, -38% by 2070 vs 2025 baseline
    # Linear interpolation between waypoints. Applied in constraints.py to
    # combustion emissions and fuel resource intensities only.
    # ------------------------------------------------------------------
    sec_imp_cfg = cfg.get("sec_improvement", {})
    sec_improvement_factor_by_year: Dict[int, float] = {}
    sec_improvement_provenance = "NOT_ENABLED"
    if sec_imp_cfg.get("enabled", False):
        scenario_name_for_sec = cfg.get("scenario_name", "")
        # Look up scenario-specific waypoints, fall back to global waypoints
        by_scenario = sec_imp_cfg.get("by_scenario", {})
        waypoints_raw = by_scenario.get(scenario_name_for_sec, sec_imp_cfg.get("waypoints", {}))
        if waypoints_raw:
            # Sort waypoints by year; anchor at (start_year, 0.0)
            sorted_wps = sorted((int(y), float(f)) for y, f in waypoints_raw.items())
            anchor_year = start_year
            anchored = [(anchor_year, 0.0)] + sorted_wps
            for t in years:
                if t <= anchor_year:
                    sec_improvement_factor_by_year[t] = 0.0
                elif t >= anchored[-1][0]:
                    sec_improvement_factor_by_year[t] = anchored[-1][1]
                else:
                    # Linear interpolation between bracketing waypoints
                    for k in range(len(anchored) - 1):
                        y0, f0 = anchored[k]
                        y1, f1 = anchored[k + 1]
                        if y0 <= t <= y1:
                            alpha = (t - y0) / (y1 - y0)
                            sec_improvement_factor_by_year[t] = f0 + alpha * (f1 - f0)
                            break
        sec_improvement_provenance = sec_imp_cfg.get("provenance", "V4")

    # ------------------------------------------------------------------
    # Lifetime / start years / availability (configurable)
    # ------------------------------------------------------------------
    lifetime = int(cfg.get("lifetime_years", 25))
    start_years = {r: int(cfg.get("start_years", {}).get(r, start_year)) for r in enabled}
    avail_cfg = cfg.get("availability", {})
    availability: Dict[str, float] = {}
    # Per-route provenance is read from the config records, never
    # hard-coded (review item 2); a missing record fails loudly.
    availability_provenance_by_route: Dict[str, str] = {}
    for r in enabled:
        entry = avail_cfg.get(r, {})
        if "provenance" not in entry:
            raise ValueError(
                f"availability['{r}'] is missing its provenance record: the "
                "config must carry 'availability[route].provenance'."
            )
        availability[r] = float(entry.get("value", 0.90))
        availability_provenance_by_route[r] = str(entry["provenance"])
    availability_provenance = "; ".join(
        sorted({p for p in availability_provenance_by_route.values()})
    )

    # ------------------------------------------------------------------
    # Existing capacity (aggregate context; per-route unavailable -> 0)
    # ------------------------------------------------------------------
    existing_per_route = {
        r: float(cfg.get("existing_capacity_per_route_mt", {}).get(r, 0.0))
        for r in enabled
    }
    aggregate_ctx = cfg.get("existing_capacity_mt_aggregate")
    existing_data_available = False  # tech-wise capacity is EXTERNAL_PENDING

    # ------------------------------------------------------------------
    # Resource prices (source_unit -> model_unit via explicit formula)
    # ------------------------------------------------------------------
    price_cfg = cfg.get("resource_prices", {})

    resources = list(DEFAULT_RESOURCES)
    price_model: Dict[str, float] = {}
    price_source_unit: Dict[str, str] = {}
    price_model_unit_name: Dict[str, str] = {}
    price_formula: Dict[str, str] = {}
    price_conversion_factor: Dict[str, float] = {}
    price_conversion_operation: Dict[str, str] = {}
    price_provenance: Dict[str, str] = {}
    for key, entry in price_cfg.items():
        res = _PRICE_KEY_TO_RESOURCE.get(key)
        if res is None:
            continue
        value = float(entry["value"])
        source_unit = str(entry.get("source_unit", ""))
        target_unit = str(entry.get("target_unit", source_unit))
        formula = str(entry.get("conversion_formula", "1:1"))

        # Conversion is FULLY configuration-driven: the configured
        # conversion_factor and conversion_operation are REQUIRED and
        # applied verbatim. No conversion is ever inferred from unit
        # strings, and a missing conversion spec fails loudly instead of
        # silently producing a wrong price (review item 1).
        if "conversion_factor" not in entry or "conversion_operation" not in entry:
            raise ValueError(
                f"Resource price '{key}' is missing explicit conversion "
                "metadata: both 'conversion_factor' and 'conversion_operation' "
                "must be present in the configuration."
            )
        if "provenance" not in entry:
            raise ValueError(
                f"Resource price '{key}' is missing its provenance record: "
                "the config must carry 'provenance' (never hard-coded)."
            )
        factor = float(entry["conversion_factor"])
        operation = str(entry["conversion_operation"])
        if operation == "multiply":
            converted = value * factor
        elif operation == "divide":
            converted = value / factor
        else:
            raise ValueError(
                f"Unknown conversion_operation '{operation}' for price '{key}'; "
                "expected 'multiply' or 'divide'."
            )
        price_model[res] = converted
        price_source_unit[res] = source_unit
        price_model_unit_name[res] = target_unit
        price_formula[res] = formula
        price_conversion_factor[res] = factor
        price_conversion_operation[res] = operation
        price_provenance[res] = str(entry["provenance"])

    # ------------------------------------------------------------------
    # Registry coefficients (intensities + emissions), scenario "ALL"
    # ------------------------------------------------------------------
    # PROVENANCE GATE (Step 13 remediation, Task 1): every registry value
    # that becomes an optimization coefficient is resolved through
    # resolve_intensity. EXTERNAL_PENDING/UNKNOWN values are NEVER silently
    # converted to zero: they require an explicit allowance
    # (provenance_gating.pending_intensity_allowances) or a value override
    # (provenance_gating.intensity_overrides), otherwise the load FAILS.
    # ------------------------------------------------------------------
    gate_cfg = cfg.get("provenance_gating", {})
    if not isinstance(gate_cfg, dict):
        raise ValueError("provenance_gating must be a mapping.")
    gate_policy = str(gate_cfg.get("policy", "strict"))
    if gate_policy != "strict":
        raise ValueError(
            f"provenance_gating.policy must be 'strict'; got '{gate_policy}'. "
            "Lenient policies are not implemented."
        )
    allow_proposal = bool(gate_cfg.get("allow_proposal_parameters", False))
    pending_allowances = set(
        str(x) for x in gate_cfg.get("pending_intensity_allowances", [])
    )
    intensity_overrides: Dict[str, dict] = {}
    for ov in gate_cfg.get("intensity_overrides", []):
        key = f"{ov['route']}/{ov['resource']}"
        if "value" not in ov or "provenance" not in ov:
            raise ValueError(
                f"intensity_overrides entry '{key}' must carry 'value' and "
                "'provenance' (never a silent override)."
            )
        intensity_overrides[key] = {
            "value": float(ov["value"]),
            "provenance": str(ov["provenance"]),
            "rationale": str(ov.get("rationale", "")),
        }

    intensity: Dict[Tuple[str, str], Optional[float]] = {}
    intensity_status: Dict[Tuple[str, str], dict] = {}
    gate_violations: List[str] = []
    for r in enabled:
        for res in resources:
            rec = registry.get_resource_intensity(r, res, start_year, "ALL")
            if rec is None:
                # Structurally absent (no registry claim): coefficient 0 is the
                # physical default. Surfaced in diagnostics, never fabricated.
                intensity[(r, res)] = None
                intensity_status[(r, res)] = {
                    "status": "absent",
                    "value": None,
                    "provenance": "UNKNOWN",
                    "override_provenance": None,
                    "rationale": "no registry record; structurally zero",
                }
                continue
            try:
                dec = resolve_intensity(
                    route=r,
                    resource=res,
                    value=rec.value,
                    provenance=rec.provenance.value,
                    allowances=pending_allowances,
                    overrides=intensity_overrides,
                    allow_proposal=allow_proposal,
                )
            except ProvenanceGateError as exc:
                gate_violations.append(str(exc))
                continue
            intensity[(r, res)] = dec.coefficient_value
            intensity_status[(r, res)] = {
                "status": dec.status,
                "value": dec.coefficient_value,
                "provenance": dec.provenance,
                "override_provenance": dec.override_provenance,
                "rationale": dec.rationale,
            }
    if gate_violations:
        raise ValueError(
            "Provenance gate FAILED (no silent EXTERNAL_PENDING/UNKNOWN "
            "conversion):\n  " + "\n  ".join(gate_violations)
        )

    proc_em: Dict[str, float] = {}
    comb_em: Dict[str, float] = {}
    emission_violations: List[str] = []
    for r in enabled:
        for etype, bucket in (("process", proc_em), ("combustion", comb_em)):
            rec = registry.get_emissions(r, etype, start_year, "ALL")
            if rec is None:
                bucket[r] = 0.0
                continue
            p = rec.provenance.value
            emkey = f"emissions/{r}/{etype}"
            if p in ("V4", "TIMES", "DERIVED", "EXTERNAL"):
                bucket[r] = rec.value if rec.value is not None else 0.0
                continue
            if p == "PROJECT_PROPOSAL" and allow_proposal:
                bucket[r] = rec.value if rec.value is not None else 0.0
                continue
            if p in ("EXTERNAL_PENDING", "UNKNOWN") and emkey in pending_allowances:
                bucket[r] = rec.value if rec.value is not None else 0.0
                continue
            emission_violations.append(
                f"[{emkey}] provenance '{p}' not optimization-eligible without an "
                "explicit allowance."
            )
    if emission_violations:
        raise ValueError(
            "Provenance gate (emissions) FAILED:\n  "
            + "\n  ".join(emission_violations)
        )

    # ------------------------------------------------------------------
    # Dynamic scrap (Step 9) — MODE B only; MODE A gate is explicit.
    # ------------------------------------------------------------------
    scrap_cfg = cfg.get("dynamic_scrap", {})
    dynamic_scrap_enabled = bool(scrap_cfg.get("enabled", False))
    scrap_engine: Optional[ScrapEngine] = None
    if dynamic_scrap_enabled:
        if not isinstance(scrap_cfg, dict):
            raise ValueError("dynamic_scrap must be a mapping with 'enabled'.")
        # Block-level provenance is mandatory (never hard-coded); the
        # engine validates every sub-parameter's provenance and fails
        # loudly on any missing record (Step 9 §16).
        scrap_engine = ScrapEngine.from_config(scrap_cfg, years, start_year)

    # ------------------------------------------------------------------
    # Deployment dynamics (Step 10) — MODE B only; MODE A gate is explicit.
    # ------------------------------------------------------------------
    deployment_cfg = cfg.get("deployment_dynamics", {})
    deployment_dynamics_enabled = bool(deployment_cfg.get("enabled", False))
    construction_lead_time_years = {r: 0 for r in enabled}
    ncap_limits_mt = {r: None for r in enabled}
    deployment_provenance = ""
    if deployment_dynamics_enabled:
        if not isinstance(deployment_cfg, dict):
            raise ValueError("deployment_dynamics must be a mapping with 'enabled'.")
        if "provenance" not in deployment_cfg:
            raise ValueError(
                "deployment_dynamics block is missing its provenance record: "
                "the config must carry 'provenance' (never hard-coded)."
            )
        deployment_provenance = str(deployment_cfg["provenance"])
        
        from steel_model.technologies.registry import TechnologyRegistry
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        tech_config_dir = os.path.join(project_root, "configs", "technologies")
        tech_registry = TechnologyRegistry(tech_config_dir)
        
        raw_limits = deployment_cfg.get("ncap_limits_mt", {})
        for r in enabled:
            card = tech_registry.get_technology_model(r)
            construction_lead_time_years[r] = card.construction_lead_time_years
            
            # Retrieve optional NCAP upper bound
            if r in raw_limits:
                val = raw_limits[r]
                ncap_limits_mt[r] = float(val) if val is not None else None

    # ------------------------------------------------------------------
    # Static scrap availability cap (Mode A only).
    # Piecewise-linear interpolation over anchor_years_mt -> one value per
    # horizon year. This is a PROJECT_PROPOSAL constraint that bounds the
    # total scrap consumed to India's physically plausible domestic generation
    # trajectory. Mode B uses the dynamic scrap engine instead.
    # ------------------------------------------------------------------
    static_scrap_cap_cfg = cfg.get("static_scrap_cap", {})
    static_scrap_cap_mt: Optional[Dict[int, float]] = None
    if static_scrap_cap_cfg.get("enabled", False):
        anchors_raw = static_scrap_cap_cfg.get("anchor_years_mt", {})
        if not anchors_raw:
            raise ValueError(
                "static_scrap_cap.enabled is true but anchor_years_mt is empty."
            )
        anchors: Dict[int, float] = {int(k): float(v) for k, v in anchors_raw.items()}
        # Piecewise-linear interpolation (same logic as demand anchors).
        sorted_anchor_years = sorted(anchors)
        cap_by_year: Dict[int, float] = {}
        for t in years:
            if t in anchors:
                cap_by_year[t] = anchors[t]
            elif t < sorted_anchor_years[0]:
                cap_by_year[t] = anchors[sorted_anchor_years[0]]
            elif t > sorted_anchor_years[-1]:
                cap_by_year[t] = anchors[sorted_anchor_years[-1]]
            else:
                for lo, hi in zip(sorted_anchor_years, sorted_anchor_years[1:]):
                    if lo <= t <= hi:
                        span = hi - lo
                        frac = (t - lo) / span if span > 0 else 0.0
                        cap_by_year[t] = anchors[lo] + frac * (anchors[hi] - anchors[lo])
                        break
        static_scrap_cap_mt = cap_by_year

    # ------------------------------------------------------------------
    # Endogenous learning (Step 11) — MODE B only; MODE A gate is explicit.
    # ------------------------------------------------------------------
    learning_cfg = cfg.get("endogenous_learning", {})
    endogenous_learning_enabled = bool(learning_cfg.get("enabled", False))
    learning_rates = {r: 0.0 for r in enabled}
    learning_exponents = {r: 0.0 for r in enabled}
    initial_cumulative_capacity_mt = {r: 1.0 for r in enabled}
    learning_scopes = {r: "full_plant" for r in enabled}
    learning_provenance_by_route = {r: "UNKNOWN" for r in enabled}
    learning_tolerance = float(learning_cfg.get("tolerance", 0.001))
    learning_max_iterations = int(learning_cfg.get("max_iterations", 20))
    learning_provenance = ""

    if endogenous_learning_enabled:
        if not isinstance(learning_cfg, dict):
            raise ValueError("endogenous_learning must be a mapping with 'enabled'.")
        if "provenance" not in learning_cfg:
            raise ValueError(
                "endogenous_learning block is missing its provenance record: "
                "the config must carry 'provenance' (never hard-coded)."
            )
        learning_provenance = str(learning_cfg["provenance"])
        
        routes_learning = learning_cfg.get("routes", {})
        for r in enabled:
            if r in routes_learning:
                entry = routes_learning[r]
                lr = float(entry.get("learning_rate", 0.0))
                init_cap = float(entry.get("initial_cumulative_capacity_mt", 1.0))
                if init_cap <= 0.0:
                    raise ValueError(f"initial_cumulative_capacity_mt for {r} must be > 0")
                scope = str(entry.get("learning_scope", "full_plant"))
                prov = str(entry.get("provenance", "UNKNOWN"))
                
                learning_rates[r] = lr
                import math
                b_i = -math.log2(1.0 - lr) if lr > 0.0 else 0.0
                learning_exponents[r] = b_i
                initial_cumulative_capacity_mt[r] = init_cap
                learning_scopes[r] = scope
                learning_provenance_by_route[r] = prov

    # ------------------------------------------------------------------
    # Mode B policy (Step 17B) — Vol.4-consistent scenario policy rules.
    # Gate approvals (MODE_B_APPROVAL_GATES.md, 2026-08-14):
    #   Gate A APPROVED   : "no new capacity after year X" = NCAP[i,t] = 0
    #                       for t > X (existing capacity survives to retirement).
    #   Gate B NOT APPROVED: do NOT apply the Coal-DRI-IF 2030 cutoff to
    #                       Coal-DRI-EAF (Vol.4 names only Coal-DRI-IF).
    #   Gate C APPROVED   : NZS scrap waypoints are POST-SOLVE DIAGNOSTICS
    #                       (MATCH/BELOW/ABOVE), never hard MILP floors.
    #   Gate F APPROVED   : only the directly source-supported availability
    #                       rules below are implemented.
    # Do NOT add carbon price, emissions cap, Coal-DRI-EAF cutoff, or a hard
    # scrap floor. Green-electricity numeric parameters remain EXTERNAL_PENDING.
    # ------------------------------------------------------------------
    policy_cfg = cfg.get("mode_b_policy", {})
    ncap_cutoff_years: Dict[str, int] = {}
    monotonic_decline_from_years: Dict[str, int] = {}
    min_production_floor_mt: Dict[str, Dict[int, float]] = {}
    route_availability_start_years: Dict[str, int] = {}
    scrap_waypoints: List[dict] = []
    mode_b_label = ""
    explicit_non_rules: Dict[str, str] = {}
    mode_b_policy_record: dict = {}
    if policy_cfg:
        if not isinstance(policy_cfg, dict):
            raise ValueError("mode_b_policy must be a mapping.")
        if not policy_cfg.get("enabled", False):
            mode_b_label = ""
            mode_b_policy_record = {"enabled": False, "reason": "policy block present but disabled"}
        else:
            if "provenance" not in policy_cfg:
                raise ValueError(
                    "mode_b_policy block is missing its provenance record: the "
                    "config must carry 'provenance' (never hard-coded)."
                )
            mode_b_label = str(policy_cfg.get("label", "MODE_B_POLICY"))

            scenario_policies = policy_cfg.get("scenario_policies", {})
            sp = scenario_policies.get(scenario, {})
            if not sp and scenario_policies:
                raise ValueError(
                    f"No mode_b_policy.scenario_policies entry for scenario '{scenario}'."
                )

            # Gate A / Gate F: new-capacity cutoff years (NCAP[i,t] = 0 for t > Y).
            raw_cutoffs = sp.get("ncap_cutoff_years", {})
            for r, y in raw_cutoffs.items():
                if r not in ALL_ROUTES:
                    raise ValueError(
                        f"Unknown route '{r}' in mode_b_policy ncap_cutoff_years."
                    )
                if r == "Coal-DRI-EAF":
                    raise ValueError(
                        "Gate B NOT APPROVED: mode_b_policy must NOT impose a "
                        "new-capacity cutoff on Coal-DRI-EAF (Vol.4 names only "
                        "Coal-DRI-IF for the 2030 rule)."
                    )
                ncap_cutoff_years[r] = int(y)

            # Step 17B extension: monotonic production decline years.
            # ACT[i, t+1] <= ACT[i, t] for t >= from_year — prevents utilization
            # cycling for legacy routes (BF-BOF) where restart after full idle
            # has no physical basis in India's integrated steel sector.
            raw_decline = sp.get("monotonic_decline_from_years", {})
            for r, y in raw_decline.items():
                if r not in ALL_ROUTES:
                    raise ValueError(
                        f"Unknown route '{r}' in mode_b_policy monotonic_decline_from_years."
                    )
                monotonic_decline_from_years[r] = int(y)

            # Step 26: Minimum production floor for Vol.4-narrative routes.
            # Reads anchor years from mode_b_policy.scenario_policies.<S>.min_production_floor_mt
            raw_floor = sp.get("min_production_floor_mt", {})
            for r, anchor_dict in raw_floor.items():
                if r not in ALL_ROUTES:
                    raise ValueError(
                        f"Unknown route '{r}' in mode_b_policy min_production_floor_mt."
                    )
                min_production_floor_mt[r] = {int(yr): float(v) for yr, v in anchor_dict.items()}

            # Gate F: technology availability start years (only bind when the
            # route is enabled; otherwise recorded as an inert policy window).
            raw_starts = sp.get("route_start_years", {})
            for r, y in raw_starts.items():
                route_availability_start_years[r] = int(y)
            for r in enabled:
                if r in route_availability_start_years:
                    start_years[r] = route_availability_start_years[r]

            explicit_non_rules = {
                str(k): str(v) for k, v in policy_cfg.get("explicit_non_rules", {}).items()
            }

            # Gate C: NZS scrap waypoints (diagnostic targets only).
            wp_map = policy_cfg.get("scrap_waypoints", {})
            for wp_scenario, wps in wp_map.items():
                if wp_scenario == scenario:
                    scrap_waypoints = list(wps)

            mode_b_policy_record = {
                "enabled": True,
                "label": mode_b_label,
                "scenario": scenario,
                "provenance": str(policy_cfg["provenance"]),
                "ncap_cutoff_years": dict(sorted(ncap_cutoff_years.items())),
                "route_availability_start_years": dict(sorted(route_availability_start_years.items())),
                "scrap_waypoints": list(scrap_waypoints),
                "explicit_non_rules": dict(explicit_non_rules),
                "approval_gates": ["A", "C", "F"],
            }

    # ------------------------------------------------------------------
    # Data limitations (explicit, never silent)
    # ------------------------------------------------------------------
    limitations: List[str] = []
    disabled = [r for r in ALL_ROUTES if r not in enabled]
    if disabled:
        limitations.append(
            "Routes without frozen full-plant economics (disabled in this "
            "baseline, reason EXTERNAL_PENDING_FULL_PLANT_ECONOMICS): "
            + ", ".join(disabled)
        )
    limitations.append(
        "Technology-wise existing capacity is unavailable (EXTERNAL_PENDING). "
        "Per-route existing capacity is set to 0.0 ONLY as a temporary model "
        "representation (BASELINE DATA LIMITATION). Aggregate 2024-25 capacity "
        "context is 200.333 Mt (MoS AR 2025-26) but is NOT a route-level split. "
        "No production/PLF derivation is used."
    )
    limitations.append(
        "Availability (0.90) and discount rate (0.08) are PROJECT_PROPOSAL "
        "parameters used only because this control run explicitly permits "
        "proposal-level parameters; they are not claimed as NITI/TIMES facts."
    )
    null_intensities = [
        f"{r}/{res}" for r in enabled for res in resources
        if intensity.get((r, res)) is None
    ]
    if null_intensities:
        limitations.append(
            "Resource intensities EXTERNAL_PENDING (entered as 0.0, so the "
            "associated cost term is absent): " + ", ".join(sorted(null_intensities))
        )
    pending_used = [
        f"{r}/{res}" for (r, res), st in intensity_status.items()
        if st["status"] == "pending_allowance"
    ]
    if pending_used:
        limitations.append(
            "EXTERNAL_PENDING/UNKNOWN intensities used under EXPLICIT config "
            "allowance (provenance-visible, NOT silent): "
            + ", ".join(sorted(pending_used))
        )
    override_used = [
        f"{r}/{res}" for (r, res), st in intensity_status.items()
        if st["status"] == "value_override"
    ]
    if override_used:
        limitations.append(
            "Intensity value OVERRIDES applied from "
            "provenance_gating.intensity_overrides (DIAGNOSTIC / sensitivity "
            "values, NOT frozen scientific facts): "
            + ", ".join(sorted(override_used))
        )
    absent_used = [
        f"{r}/{res}" for (r, res), st in intensity_status.items()
        if st["status"] == "absent"
    ]
    if absent_used:
        limitations.append(
            "Structurally absent intensities (no registry record; coefficient "
            "0.0, surfaced not fabricated): "
            + ", ".join(sorted(absent_used))
        )
    limitations.append(
        "VOM is 0.0 for every enabled route (VOM EXTERNAL_PENDING; explicit "
        "config choice — reported, not silent)."
    )
    if dynamic_scrap_enabled:
        limitations.append(
            "This is a STEP 9 MODE B run: dynamic scrap circularity is ENABLED. "
            "M1, endogenous learning, deployment dynamics, uncertainty and "
            "spatial modelling remain DISABLED. Scrap module parameters are "
            "PROJECT_PROPOSAL (lifetime kernel, collection rate, processing "
            "yield); imports are excluded (allowance 0)."
        )
    else:
        limitations.append(
            "This run is a CONTROL MODEL ('Baseline MILP — economics-available "
            "route subset'), not the final enriched model. M1, endogenous learning, "
            "dynamic scrap, deployment dynamics, uncertainty and spatial modelling "
            "are all DISABLED (Step 8 hard stop / Step 9 MODE A gate)."
        )

    # ------------------------------------------------------------------
    # Step 20 (A): Carbon price loading.
    # Provides a per-year cost on CO2[t] in the objective to reflect
    # India's evolving carbon pricing landscape (CCTS / PAT / green premium).
    # ------------------------------------------------------------------
    carbon_cfg = cfg.get("carbon_price", {})
    carbon_price_enabled = bool(carbon_cfg.get("enabled", False))
    carbon_price_usd_per_tco2: Dict[int, float] = {}
    carbon_price_provenance = ""
    if carbon_price_enabled:
        if "provenance" not in carbon_cfg:
            raise ValueError(
                "carbon_price block is missing 'provenance' (never hard-coded)."
            )
        carbon_price_provenance = str(carbon_cfg["provenance"])
        trajectories = carbon_cfg.get("trajectories", {})
        sc_traj = trajectories.get(scenario, {})
        if not sc_traj:
            # Fall back to a single non-scenario trajectory if defined
            sc_traj = {int(k): float(v) for k, v in carbon_cfg.get("anchor_years", {}).items()}
        else:
            sc_traj = {int(k): float(v) for k, v in sc_traj.items()}
        if not sc_traj:
            raise ValueError(
                f"carbon_price.enabled is true but no trajectory found for "
                f"scenario '{scenario}'. Add 'trajectories.{scenario}' or "
                "'anchor_years' to the carbon_price block."
            )
        # Interpolate to all model years
        sorted_cp_years = sorted(sc_traj.keys())
        for t in years:
            carbon_price_usd_per_tco2[t] = float(
                np.interp(t, sorted_cp_years, [sc_traj[k] for k in sorted_cp_years])
            )
        limitations.append(
            f"Step 20 CARBON PRICE ENABLED (provenance: {carbon_price_provenance}). "
            f"Scenario '{scenario}': {min(sc_traj.values()):.0f}–"
            f"{max(sc_traj.values()):.0f} USD/tCO₂. "
            "This adds a carbon cost on CO2[t] in the objective; it is a "
            "PROJECT_PROPOSAL parameter, not a frozen scientific fact."
        )

    # ------------------------------------------------------------------
    # Step 20 (B): H₂ supply cap loading.
    # Upper bound on RES["hydrogen",t] — represents infrastructure limits
    # on green H₂ availability (electrolysis + pipeline capacity ramp-up).
    # ------------------------------------------------------------------
    h2_cap_cfg = cfg.get("h2_supply_cap", {})
    h2_supply_cap_enabled = bool(h2_cap_cfg.get("enabled", False))
    h2_supply_cap_mt: Optional[Dict[int, float]] = None
    h2_supply_cap_provenance = ""
    if h2_supply_cap_enabled:
        if "provenance" not in h2_cap_cfg:
            raise ValueError(
                "h2_supply_cap block is missing 'provenance' (never hard-coded)."
            )
        h2_supply_cap_provenance = str(h2_cap_cfg["provenance"])
        # Scenario-specific trajectories: check trajectories.{scenario}.anchor_years_mt first.
        _h2_sc_traj = h2_cap_cfg.get("trajectories", {}).get(scenario, {})
        h2_anchors_raw = _h2_sc_traj.get("anchor_years_mt", {}) or h2_cap_cfg.get("anchor_years_mt", {})
        if not h2_anchors_raw:
            raise ValueError(
                f"h2_supply_cap.enabled is true but no anchor_years_mt found for "
                f"scenario '{scenario}' or as fallback."
            )
        h2_anchors: Dict[int, float] = {int(k): float(v) for k, v in h2_anchors_raw.items()}
        sorted_h2_years = sorted(h2_anchors.keys())
        # Unit conversion: cap is in Mt H₂/yr (physical); model RES units are
        # ACT_Mt × H2_intensity_kg_per_t. Since 1 Mt H₂ = 10^6 kg and the
        # intensity is in kg/t with ACT in Mt/yr:
        #   RES_model = ACT_Mt × intensity_kg_per_t
        #   H₂_physical_Mt = RES_model × 10^-3  (1 model unit = 1,000 t H₂)
        # Therefore: cap_model_units = cap_Mt_H2 × 10^3 = cap_Mt_H2 × 1000
        _H2_MT_TO_MODEL = 1000.0  # 1 Mt H₂ physical = 1000 model-RES units
        h2_supply_by_year: Dict[int, float] = {}
        for t in years:
            h2_supply_by_year[t] = float(
                np.interp(t, sorted_h2_years, [h2_anchors[k] for k in sorted_h2_years])
            ) * _H2_MT_TO_MODEL
        h2_supply_cap_mt = h2_supply_by_year
        limitations.append(
            f"Step 20 H₂ SUPPLY CAP ENABLED (provenance: {h2_supply_cap_provenance}). "
            "RES['hydrogen',t] bounded by exogenous H₂ supply ramp. "
            "This physically limits H2-DRI-EAF growth rate. PROJECT_PROPOSAL."
        )

    # ------------------------------------------------------------------
    # Step 20 (C): Stranded-asset cost loading.
    # Adds penalty stranded_cost_fraction * annCapex_i per Mt capacity
    # retired via RET[i,t]. Represents remaining asset value lost on
    # premature closure (balance-sheet stranded cost).
    # ------------------------------------------------------------------
    stranded_cfg = cfg.get("stranded_asset_cost", {})
    stranded_cost_enabled = bool(stranded_cfg.get("enabled", False))
    stranded_cost_fraction = 0.0
    stranded_cost_provenance = ""
    if stranded_cost_enabled:
        if "provenance" not in stranded_cfg:
            raise ValueError(
                "stranded_asset_cost block is missing 'provenance' (never hard-coded)."
            )
        stranded_cost_provenance = str(stranded_cfg["provenance"])
        stranded_cost_fraction = float(stranded_cfg.get("stranded_cost_fraction", 0.30))
        limitations.append(
            f"Step 20 STRANDED ASSET COST ENABLED (fraction={stranded_cost_fraction:.2f}, "
            f"provenance: {stranded_cost_provenance}). "
            "RET[i,t] incurs cost = fraction × annCapex_i in the objective. "
            "Discourages premature early retirement. PROJECT_PROPOSAL."
        )

    # ------------------------------------------------------------------
    # Step 20 (D): Time-varying resource price trajectories.
    # When a trajectory is provided for a resource, the per-year price
    # in the objective is taken from the trajectory (interpolated) rather
    # than the static price_model value. Represents declining H₂ / RE
    # electricity costs from electrolyser and solar learning curves.
    # ------------------------------------------------------------------
    resource_price_trajectory: Dict[str, Dict[int, float]] = {}
    traj_block = cfg.get("resource_price_trajectories", {})
    for res_key, traj_entry in traj_block.items():
        res_id = _PRICE_KEY_TO_RESOURCE.get(res_key, res_key)
        if not isinstance(traj_entry, dict):
            continue
        # Scenario-specific trajectories: check trajectories.{scenario}.anchor_years first,
        # then fall back to a single anchor_years for scenario-invariant resources (e.g. scrap).
        _sc_sub = traj_entry.get("trajectories", {}).get(scenario, {})
        anchors_raw = _sc_sub.get("anchor_years", {}) or traj_entry.get("anchor_years", {})
        if not anchors_raw:
            continue
        if "provenance" not in traj_entry:
            raise ValueError(
                f"resource_price_trajectories['{res_key}'] is missing 'provenance' "
                "(never hard-coded)."
            )
        raw_anchors: Dict[int, float] = {int(k): float(v) for k, v in anchors_raw.items()}
        sorted_traj_years = sorted(raw_anchors.keys())
        traj_by_year: Dict[int, float] = {}
        for t in years:
            traj_by_year[t] = float(
                np.interp(t, sorted_traj_years, [raw_anchors[k] for k in sorted_traj_years])
            )
        resource_price_trajectory[res_id] = traj_by_year
        limitations.append(
            f"Step 20 TIME-VARYING PRICE: '{res_key}' uses a year-indexed trajectory "
            f"(provenance: {traj_entry['provenance']}). "
            f"Range: {min(raw_anchors.values()):.2f}–{max(raw_anchors.values()):.2f} "
            f"{price_model_unit_name.get(res_id, '')}. "
            "Static price from resource_prices block is overridden for this resource."
        )

    # ------------------------------------------------------------------
    # Step 21 (A): Grid emission intensity loading.
    # Adds tCO₂/MWh factor to the CO2 constraint for electricity-using routes.
    # Represents India's grid carbon intensity declining as RE share grows.
    # ------------------------------------------------------------------
    grid_cfg = cfg.get("grid_emission_intensity", {})
    grid_emission_enabled = bool(grid_cfg.get("enabled", False))
    grid_ei_tco2_per_mwh: Dict[int, float] = {}
    grid_emission_provenance = ""
    if grid_emission_enabled:
        if "provenance" not in grid_cfg:
            raise ValueError(
                "grid_emission_intensity block is missing 'provenance' (never hard-coded)."
            )
        grid_emission_provenance = str(grid_cfg["provenance"])
        # Scenario-specific: check trajectories.{scenario}.grid_ei_tco2_per_mwh first.
        _grid_sc = grid_cfg.get("trajectories", {}).get(scenario, {})
        raw_ei = _grid_sc.get("grid_ei_tco2_per_mwh", {}) or grid_cfg.get("grid_ei_tco2_per_mwh", {})
        if not raw_ei:
            raise ValueError(
                f"grid_emission_intensity.enabled is true but no grid_ei_tco2_per_mwh "
                f"found for scenario '{scenario}' or as fallback."
            )
        ei_anchors: Dict[int, float] = {int(k): float(v) for k, v in raw_ei.items()}
        sorted_ei_years = sorted(ei_anchors.keys())
        for t in years:
            grid_ei_tco2_per_mwh[t] = float(
                np.interp(t, sorted_ei_years, [ei_anchors[k] for k in sorted_ei_years])
            )
        limitations.append(
            f"Step 21 GRID EMISSION INTENSITY ENABLED (provenance: {grid_emission_provenance}). "
            f"Grid EI: {ei_anchors.get(sorted_ei_years[0], 0):.3f}→"
            f"{ei_anchors.get(sorted_ei_years[-1], 0):.3f} tCO₂/MWh. "
            "Electricity-based indirect CO₂ added to constraint 6. PROJECT_PROPOSAL."
        )

    # ------------------------------------------------------------------
    # Step 21 (B): Standalone construction lead time loading.
    # When this block is enabled, overrides the deployment_dynamics-derived
    # construction_lead_time_years (or sets them when deployment_dynamics is off).
    # ------------------------------------------------------------------
    lead_time_cfg = cfg.get("construction_lead_time", {})
    construction_lead_time_active = False
    if lead_time_cfg.get("enabled", False):
        if "provenance" not in lead_time_cfg:
            raise ValueError(
                "construction_lead_time block is missing 'provenance' (never hard-coded)."
            )
        raw_lt = lead_time_cfg.get("lead_time_years", {})
        for r in enabled:
            if r in raw_lt:
                construction_lead_time_years[r] = int(raw_lt[r])
        construction_lead_time_active = True
        lt_summary = ", ".join(
            f"{r}:{construction_lead_time_years[r]}yr" for r in enabled
            if construction_lead_time_years.get(r, 0) > 0
        )
        limitations.append(
            f"Step 21 CONSTRUCTION LEAD TIME ACTIVE (provenance: {lead_time_cfg['provenance']}). "
            f"Lead times: {lt_summary}. "
            "NCAP[i,t] contributes to CAP from year t+lead_time. PROJECT_PROPOSAL."
        )

    # ------------------------------------------------------------------
    # Step 21 (C): WACC risk premium loading.
    # Multiplicative factor on annualised CAPEX per route. Represents the
    # higher cost of capital for nascent technologies in Indian markets.
    # ------------------------------------------------------------------
    wacc_cfg = cfg.get("wacc_premium", {})
    wacc_premium_enabled = bool(wacc_cfg.get("enabled", False))
    wacc_premium_by_route: Dict[str, float] = {r: 1.0 for r in enabled}
    wacc_premium_provenance = ""
    if wacc_premium_enabled:
        if "provenance" not in wacc_cfg:
            raise ValueError(
                "wacc_premium block is missing 'provenance' (never hard-coded)."
            )
        wacc_premium_provenance = str(wacc_cfg["provenance"])
        raw_wacc = wacc_cfg.get("premium_by_route", {})
        for r in enabled:
            if r in raw_wacc:
                wacc_premium_by_route[r] = float(raw_wacc[r])
        wacc_summary = ", ".join(
            f"{r}:{wacc_premium_by_route[r]:.2f}x" for r in enabled
            if abs(wacc_premium_by_route.get(r, 1.0) - 1.0) > 0.001
        )
        limitations.append(
            f"Step 21 WACC RISK PREMIUM ENABLED (provenance: {wacc_premium_provenance}). "
            f"Premium multipliers: {wacc_summary}. "
            "Effective CAPEX = annCapex × premium. PROJECT_PROPOSAL."
        )

    # ------------------------------------------------------------------
    # Step 21 (D): Policy incentives / PLI loading.
    # Route-specific subsidy schedule: negative USD/t on ACT[i,t].
    # Interpolated between anchor years; 0 outside defined range.
    # ------------------------------------------------------------------
    pli_cfg = cfg.get("policy_incentives", {})
    policy_incentives_enabled = bool(pli_cfg.get("enabled", False))
    policy_incentives_usd_per_t: Dict[str, Dict[int, float]] = {}
    policy_incentives_provenance = ""
    if policy_incentives_enabled:
        if "provenance" not in pli_cfg:
            raise ValueError(
                "policy_incentives block is missing 'provenance' (never hard-coded)."
            )
        policy_incentives_provenance = str(pli_cfg["provenance"])
        raw_incentives = pli_cfg.get("incentives_usd_per_t", {})
        for r in enabled:
            if r in raw_incentives:
                route_anchors = {int(k): float(v) for k, v in raw_incentives[r].items()}
                sorted_ri_years = sorted(route_anchors.keys())
                by_year: Dict[int, float] = {}
                for t in years:
                    if t < sorted_ri_years[0]:
                        by_year[t] = route_anchors[sorted_ri_years[0]]
                    elif t > sorted_ri_years[-1]:
                        by_year[t] = route_anchors[sorted_ri_years[-1]]
                    else:
                        by_year[t] = float(
                            np.interp(t, sorted_ri_years, [route_anchors[k] for k in sorted_ri_years])
                        )
                policy_incentives_usd_per_t[r] = by_year
        if policy_incentives_usd_per_t:
            pli_routes = list(policy_incentives_usd_per_t.keys())
            limitations.append(
                f"Step 21 POLICY INCENTIVES ENABLED (provenance: {policy_incentives_provenance}). "
                f"Routes with incentives: {pli_routes}. "
                "Negative USD/t cost on ACT[i,t] = effective subsidy. PROJECT_PROPOSAL."
            )

    # ------------------------------------------------------------------
    # Step 21 (E): Green-steel premium loading.
    # Revenue bonus (negative cost) for qualifying routes below emission
    # threshold. Premium interpolated over horizon years.
    # ------------------------------------------------------------------
    gp_cfg = cfg.get("green_steel_premium", {})
    green_premium_enabled = bool(gp_cfg.get("enabled", False))
    green_premium_threshold_tco2_per_t = 0.5
    green_premium_qualifying_routes: List[str] = []
    green_premium_usd_per_t: Dict[int, float] = {}
    green_premium_provenance = ""
    if green_premium_enabled:
        if "provenance" not in gp_cfg:
            raise ValueError(
                "green_steel_premium block is missing 'provenance' (never hard-coded)."
            )
        green_premium_provenance = str(gp_cfg["provenance"])
        green_premium_threshold_tco2_per_t = float(
            gp_cfg.get("emission_threshold_tco2_per_t", 0.5)
        )
        # Qualifying routes must be enabled to have effect
        raw_qualifying = gp_cfg.get("qualifying_routes", [])
        green_premium_qualifying_routes = [r for r in raw_qualifying if r in enabled]
        raw_premium = gp_cfg.get("premium_usd_per_t", {})
        if not raw_premium:
            raise ValueError(
                "green_steel_premium.enabled is true but premium_usd_per_t is empty."
            )
        gp_anchors: Dict[int, float] = {int(k): float(v) for k, v in raw_premium.items()}
        sorted_gp_years = sorted(gp_anchors.keys())
        for t in years:
            green_premium_usd_per_t[t] = float(
                np.interp(t, sorted_gp_years, [gp_anchors[k] for k in sorted_gp_years])
            )
        if green_premium_qualifying_routes:
            limitations.append(
                f"Step 21 GREEN-STEEL PREMIUM ENABLED (provenance: {green_premium_provenance}). "
                f"Threshold: {green_premium_threshold_tco2_per_t} tCO₂/t. "
                f"Qualifying routes: {green_premium_qualifying_routes}. "
                f"Premium: ${gp_anchors.get(sorted_gp_years[0], 0):.0f}→"
                f"${gp_anchors.get(sorted_gp_years[-1], 0):.0f}/t. PROJECT_PROPOSAL."
            )

    # ------------------------------------------------------------------
    # Mode B policy limitation notes (Step 17B) — never silent.
    # ------------------------------------------------------------------
    if mode_b_label and mode_b_policy_record.get("enabled", False):
        cutoff_note = ", ".join(
            f"{r} no-new-capacity after {y}" for r, y in sorted(ncap_cutoff_years.items())
        )
        limitations.append(
            "Step 17B MODE B POLICY ACTIVE: " + mode_b_label + ". "
            + (("NCAP cutoffs: " + cutoff_note + ". ") if cutoff_note else "No NCAP cutoffs active. ")
            + "Gate A applies (new capacity only; existing capacity unaffected). "
            + "Gate B NOT APPROVED (no Coal-DRI-EAF cutoff). "
            + "Gate C: scrap waypoints are post-solve diagnostics only. "
            + "Gate F availability start years recorded for disabled routes are "
            + "inert until those routes are economically enabled."
        )
        if explicit_non_rules:
            limitations.append(
                "Explicitly NOT imposed (Gate F): "
                + "; ".join(f"{k}: {v}" for k, v in sorted(explicit_non_rules.items()))
            )
        if scrap_waypoints:
            limitations.append(
                "NZS scrap waypoints recorded as POST-SOLVE DIAGNOSTIC targets "
                "(MATCH/BELOW/ABOVE); they are NOT MILP constraints: "
                + "; ".join(f"{wp['year']}={wp['share']}" for wp in scrap_waypoints)
            )

    # ------------------------------------------------------------------
    # Fleet / technology-space diagnostics (Step 13 remediation, Task 5/6).
    # The baseline has NO route-level existing capacity, so the "new
    # capacity" pathway cannot be interpreted as a replacement of the
    # actual 2024 Indian fleet.
    # ------------------------------------------------------------------
    existing_route_capacity_available = existing_data_available
    route_transition_interpretability = (
        existing_data_available
        and any(existing_per_route.get(r, 0.0) > 0.0 for r in enabled)
    )
    technology_space_completeness = "COMPLETE" if not disabled else "INCOMPLETE"
    if not route_transition_interpretability:
        limitations.append(
            "Route-level existing (starting) capacity is unavailable, so the new "
            "capacity pathway is NOT physically interpretable as a replacement "
            "of the actual 2024 Indian fleet (see "
            "existing_route_capacity_available / route_transition_interpretability)."
        )
    if disabled:
        limitations.append(
            "The technology space is INCOMPLETE for this run: enabled routes "
            "exclude " + ", ".join(disabled) + ". Mix results are conditional on "
            "the economics-available route subset."
        )

    # ------------------------------------------------------------------
    # Step 22: Technology ramp limits (TIMES-style bounded optimization).
    # NCAP[i,t] <= max_ncap_mt_per_year[i] for all t.
    # Per-scenario limits: NZS allows faster H2-DRI scale; CPS is conservative.
    # ------------------------------------------------------------------
    ramp_cfg = cfg.get("technology_ramp_limits", {})
    technology_ramp_limits_enabled = bool(ramp_cfg.get("enabled", False))
    technology_ramp_limits_mt: Dict[str, float] = {}
    technology_ramp_limits_provenance = ""
    if technology_ramp_limits_enabled:
        if "provenance" not in ramp_cfg:
            raise ValueError(
                "technology_ramp_limits block is missing 'provenance' (never hard-coded)."
            )
        technology_ramp_limits_provenance = str(ramp_cfg["provenance"])
        _ramp_sc = ramp_cfg.get("trajectories", {}).get(scenario, {})
        ramp_by_route = _ramp_sc.get("max_ncap_mt_per_year", {})
        if not ramp_by_route:
            # Fall back to top-level (scenario-invariant) if no per-scenario block
            ramp_by_route = ramp_cfg.get("max_ncap_mt_per_year", {})
        for route, limit_val in ramp_by_route.items():
            if route in enabled:
                technology_ramp_limits_mt[route] = float(limit_val)
        if technology_ramp_limits_mt:
            limitations.append(
                f"Step 22 TECHNOLOGY RAMP LIMITS ENABLED (provenance: "
                f"{technology_ramp_limits_provenance}). "
                f"Scenario '{scenario}': "
                + ", ".join(f"{r}: ≤{v:.1f} Mt/yr" for r, v in sorted(technology_ramp_limits_mt.items()))
                + ". NCAP[i,t] capped per year — prevents unrealistic overnight scale-up. "
                "PROJECT_PROPOSAL."
            )

    provenance_gating_record = {
        "policy": gate_policy,
        "allow_proposal_parameters": allow_proposal,
        "pending_intensity_allowances": sorted(pending_allowances),
        "intensity_overrides": {
            k: {
                "value": v["value"],
                "provenance": v["provenance"],
                "rationale": v["rationale"],
            }
            for k, v in sorted(intensity_overrides.items())
        },
    }

    return BaselineInputs(
        routes=enabled,
        all_routes=list(ALL_ROUTES),
        years=years,
        start_year=start_year,
        demand_mt=demand,
        discount_rate=discount_rate,
        discount_rate_provenance=discount_provenance,
        lifetime_years=lifetime,
        start_years=start_years,
        availability=availability,
        availability_provenance=availability_provenance,
        availability_provenance_by_route=availability_provenance_by_route,
        capex_annualised_usd_per_t=capex,
        opex_fixed_usd_per_t=opex_fixed,
        vom_usd_per_t=vom,
        resources=resources,
        resource_price_model_unit=price_model,
        resource_price_source_unit=price_source_unit,
        resource_price_model_unit_name=price_model_unit_name,
        resource_price_conversion_formula=price_formula,
        resource_price_conversion_factor=price_conversion_factor,
        resource_price_conversion_operation=price_conversion_operation,
        resource_price_provenance=price_provenance,
        resource_intensity=intensity,
        process_emission=proc_em,
        combustion_emission=comb_em,
        intensity_status=intensity_status,
        provenance_gating=provenance_gating_record,
        existing_route_capacity_available=existing_route_capacity_available,
        route_transition_interpretability=route_transition_interpretability,
        technology_space_completeness=technology_space_completeness,
        existing_capacity_per_route_mt=existing_per_route,
        existing_capacity_data_available=existing_data_available,
        aggregate_capacity_context_mt=aggregate_ctx,
        data_limitations=limitations,
        dynamic_scrap_enabled=dynamic_scrap_enabled,
        deployment_dynamics_enabled=deployment_dynamics_enabled,
        deployment_penalties_enabled=False,
        construction_lead_time_years=construction_lead_time_years,
        ncap_limits_mt=ncap_limits_mt,
        deployment_provenance=deployment_provenance,
        scrap_engine=scrap_engine,
        static_scrap_cap_mt=static_scrap_cap_mt,
        # Step 11: Endogenous learning
        endogenous_learning_enabled=endogenous_learning_enabled,
        learning_rates=learning_rates,
        learning_exponents=learning_exponents,
        initial_cumulative_capacity_mt=initial_cumulative_capacity_mt,
        learning_scopes=learning_scopes,
        learning_provenance_by_route=learning_provenance_by_route,
        learning_tolerance=learning_tolerance,
        learning_max_iterations=learning_max_iterations,
        learning_provenance=learning_provenance,
        # Step 17B: Mode B policy
        ncap_cutoff_years=ncap_cutoff_years,
        mode_b_label=mode_b_label,
        route_availability_start_years=route_availability_start_years,
        scrap_waypoints=scrap_waypoints,
        explicit_non_rules=explicit_non_rules,
        mode_b_policy_record=mode_b_policy_record,
        monotonic_decline_from_years=monotonic_decline_from_years,
        min_production_floor_mt=min_production_floor_mt,
        # Step 20: Realism enhancements
        carbon_price_enabled=carbon_price_enabled,
        carbon_price_usd_per_tco2=carbon_price_usd_per_tco2,
        carbon_price_provenance=carbon_price_provenance,
        h2_supply_cap_enabled=h2_supply_cap_enabled,
        h2_supply_cap_mt=h2_supply_cap_mt,
        h2_supply_cap_provenance=h2_supply_cap_provenance,
        stranded_cost_enabled=stranded_cost_enabled,
        stranded_cost_fraction=stranded_cost_fraction,
        stranded_cost_provenance=stranded_cost_provenance,
        resource_price_trajectory=resource_price_trajectory,
        # Step 21: Realism enhancements batch 2
        grid_emission_enabled=grid_emission_enabled,
        grid_ei_tco2_per_mwh=grid_ei_tco2_per_mwh,
        grid_emission_provenance=grid_emission_provenance,
        construction_lead_time_active=construction_lead_time_active,
        wacc_premium_enabled=wacc_premium_enabled,
        wacc_premium_by_route=wacc_premium_by_route,
        wacc_premium_provenance=wacc_premium_provenance,
        policy_incentives_enabled=policy_incentives_enabled,
        policy_incentives_usd_per_t=policy_incentives_usd_per_t,
        policy_incentives_provenance=policy_incentives_provenance,
        green_premium_enabled=green_premium_enabled,
        green_premium_threshold_tco2_per_t=green_premium_threshold_tco2_per_t,
        green_premium_qualifying_routes=green_premium_qualifying_routes,
        green_premium_usd_per_t=green_premium_usd_per_t,
        green_premium_provenance=green_premium_provenance,
        # Step 22B: CCUS
        ccus_enabled=ccus_enabled,
        ccus_capture_fraction_by_route_year=ccus_capture_fraction_by_route_year,
        ccus_provenance=ccus_provenance,
        # Step 24: SEC improvement trajectory
        sec_improvement_factor_by_year=sec_improvement_factor_by_year,
        sec_improvement_provenance=sec_improvement_provenance,
        # Step 22: Technology ramp limits
        technology_ramp_limits_enabled=technology_ramp_limits_enabled,
        technology_ramp_limits_mt=technology_ramp_limits_mt,
        technology_ramp_limits_provenance=technology_ramp_limits_provenance,
    )


class BaselineMILP:
    """
    Assemble and solve the baseline MILP for a given BaselineInputs.
    """

    def __init__(self, inputs: BaselineInputs):
        self.inputs = inputs
        self.index: Optional[VariableIndex] = None
        self.objective_meta: dict = {}

    def solve(self, time_limit_seconds: Optional[float] = None) -> BaselineMILPResult:
        if self.inputs.endogenous_learning_enabled:
            return self._solve_with_learning_loop(time_limit_seconds)
        else:
            return self._solve_once(self.inputs, time_limit_seconds)

    def _solve_once(self, inputs: BaselineInputs, time_limit_seconds: Optional[float] = None) -> BaselineMILPResult:
        index = VariableIndex(
            routes=inputs.routes,
            resources=inputs.resources,
            years=inputs.years,
        ).build()
        self.index = index

        var_lb, var_ub = build_bounds(
            index,
            inputs.start_years,
            inputs.lifetime_years,
            inputs.deployment_dynamics_enabled,
            inputs.construction_lead_time_years,
            inputs.ncap_cutoff_years,
        )

        a, lb, ub = build_constraints(index, inputs)
        c, meta = build_objective(index, inputs)
        self.objective_meta = meta

        result = solve_milp(
            c=c,
            a=a,
            lb=lb,
            ub=ub,
            var_lb=var_lb,
            var_ub=var_ub,
            time_limit_seconds=time_limit_seconds,
        )
        return build_result(index, inputs, result)

    def _solve_with_learning_loop(self, time_limit_seconds: Optional[float] = None) -> BaselineMILPResult:
        inputs = self.inputs
        
        # 1. Initialize CAPEX dictionary.
        current_capex = {}
        for r in inputs.routes:
            base_val = inputs.capex_annualised_usd_per_t[r]
            current_capex[r] = {t: base_val for t in inputs.years}

        tolerance = inputs.learning_tolerance
        max_iters = inputs.learning_max_iterations
        exponents = inputs.learning_exponents
        init_capacities = inputs.initial_cumulative_capacity_mt

        convergence_history = []
        iteration_count = 0
        capex_history = [dict(current_capex)]

        converged = False
        last_result = None

        for k in range(max_iters):
            iteration_count = k + 1
            
            # Make a local copy of inputs and assign CAPEX for iteration k
            import copy
            iter_inputs = copy.copy(inputs)
            iter_inputs.capex_annualised_usd_per_t = {
                r: dict(current_capex[r]) for r in inputs.routes
            }
            
            # Solve fixed-coefficient MILP
            last_result = self._solve_once(iter_inputs, time_limit_seconds)
            
            if last_result.status != 0:
                last_result.status = 3
                last_result.status_label = "not_converged"
                last_result.message = f"MILP solve failed at iteration {k}: {last_result.message}"
                break

            # Compute new CAPEX for iteration k+1
            new_capex = {}
            for r in inputs.routes:
                if r not in exponents or exponents[r] == 0.0:
                    new_capex[r] = dict(current_capex[r])
                    continue

                b_i = exponents[r]
                cumcap_0 = init_capacities.get(r, 1.0)
                if cumcap_0 <= 0.0:
                    cumcap_0 = 1.0
                
                route_new_capex = {}
                for t in inputs.years:
                    ncap_sum = 0.0
                    for s in inputs.years:
                        if s < t:
                            ncap_sum += last_result.ncap_mt[r].get(s, 0.0)
                    
                    cumcap_t_prev = cumcap_0 + ncap_sum
                    if cumcap_t_prev < cumcap_0:
                        cumcap_t_prev = cumcap_0
                        
                    base_capex = inputs.capex_annualised_usd_per_t[r]
                    val = base_capex * (cumcap_t_prev / cumcap_0) ** (-b_i)
                    route_new_capex[t] = val
                new_capex[r] = route_new_capex

            # Convergence test:
            max_rel_diff = 0.0
            epsilon = 1e-9
            for r in inputs.routes:
                for t in inputs.years:
                    old_val = current_capex[r][t]
                    new_val = new_capex[r][t]
                    abs_diff = abs(new_val - old_val)
                    rel_diff = abs_diff / max(abs(old_val), epsilon)
                    if rel_diff > max_rel_diff:
                        max_rel_diff = rel_diff

            convergence_history.append(max_rel_diff)
            
            # Update current_capex
            current_capex = new_capex
            capex_history.append(dict(current_capex))

            if max_rel_diff < tolerance:
                converged = True
                break

        if converged and last_result is not None:
            last_result.status_label = "optimal"
            last_result.message = f"Optimized solution converged after {iteration_count} iterations."
            last_result.learning_history = {
                "converged": True,
                "iteration_count": iteration_count,
                "convergence_history": convergence_history,
                "capex_history": capex_history,
            }
            last_result.learning_provenance = {
                r: inputs.learning_provenance_by_route.get(r, "UNKNOWN")
                for r in inputs.routes
            }
            return last_result
        else:
            if last_result is None:
                import scipy.optimize
                dummy_sol = scipy.optimize.OptimizeResult(
                    solver="HiGHS", status=-1, status_label="not-run", message="No iterations executed."
                )
                last_result = build_result(self.index, inputs, dummy_sol)
            
            last_result.status = 3
            last_result.status_label = "not_converged"
            last_result.message = f"Model did not converge within {max_iters} iterations. Last max_rel_diff = {max_rel_diff if 'max_rel_diff' in locals() else 'N/A'}"
            last_result.learning_history = {
                "converged": False,
                "iteration_count": iteration_count,
                "convergence_history": convergence_history,
                "capex_history": capex_history,
            }
            return last_result
