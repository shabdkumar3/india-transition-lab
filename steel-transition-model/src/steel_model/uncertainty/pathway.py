"""
UNCERTAINTY-BOUNDED PATHWAY STUDY — scenario engine (Step 18).

Determines how the three remaining unresolved empirical parameters affect
pathway conclusions under the Vol.4-consistent Mode B policy scenarios
(CPS / NZS):

    1. Scrap-EAF scrap intensity            (pure-scrap EAF charge, t/t steel)
    2. Coal-DRI-IF DRI charge ratio         (t DRI / t steel) + CEEW per-t-DRI
       coal / ore rates -> per-t-steel intensities
    3. Existing-fleet scenario              (per-route existing capacity, Mt)

SCIENTIFIC CONTRACT (RULE ZERO)
-------------------------------
- NOTHING here freezes an unresolved parameter. Scrap intensity and DRI
  charge ratio are exercised ONLY as source-supported SCENARIO bounds /
  discrete alternatives (no base promoted where the centre is not
  source-backed). Fleet scenarios are scenario constructions with explicit
  disclosure (source, derivation, coverage, remaining unknown).
- Coal-DRI-IF is enabled ONLY in DRI scenarios, using the documented CEEW
  EXTERNAL economics from data/external/external_parameter_freeze.yaml
  (capex 61.5, opex 26.0 USD/t) — a scenario exercise, NOT a freeze.
- Coal-DRI-EAF is never enabled: no defensible DRI charge value exists
  (DEFERRED / reported).
- H2-DRI-EAF remains EXTERNAL_PENDING (full-plant economics absent):
  H2 = 0 is a representation limit, never an economic rejection.
- The official Mode A baseline (1,726,583.38 M USD) is never modified;
  it is only re-verified. Mode B policy control runs (no uncertainty
  overrides) reproduce it exactly and anchor the comparison.
- No new MILP mathematics, no ML, no Vol.4 changes, no carbon price, no
  new policy constraints (only the approved Gate A / C / F rules already
  in configs/optimization/mode_b_policy.yaml are exercised).
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yaml

from steel_model.optimization.model import BaselineMILP, load_baseline_inputs
from steel_model.uncertainty.registry import UncertaintyRegistry
from steel_model.uncertainty.sensitivity import extract_scenario_metrics

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
CONFIG_DIR = os.path.join(PROJECT_ROOT, "configs", "optimization")
INTENSITIES_PATH = os.path.join(PROJECT_ROOT, "configs", "resources", "steel_intensities.yaml")

PATHWAY_REGISTRY_PATH = os.path.join(CONFIG_DIR, "pathway_uncertainty_registry.yaml")
BASE_POLICY_CONFIG = os.path.join(CONFIG_DIR, "mode_b_policy.yaml")
BASELINE_CONFIG = os.path.join(CONFIG_DIR, "baseline.yaml")

# Official Mode A baseline objective, M USD (6-route model, re-verified 2026-08-18).
# Updated from 506,663 (3-route) to 1,726,583 (6-route) after enabling
# Coal-DRI-EAF, Coal-DRI-IF, H2-DRI-EAF with cross-referenced economics.
# CLI verification: python -m steel_model.run --config configs/runs/mode_a_baseline.yaml
FROZEN_BASELINE_OBJECTIVE = 1726583.3837816007

ALL_ROUTES = [
    "BF-BOF",
    "Coal-DRI-EAF",
    "Coal-DRI-IF",
    "NG-DRI-EAF",
    "H2-DRI-EAF",
    "Scrap-EAF",
]

# ---------------------------------------------------------------------------
# Dimension definitions — source-supported scenario constructions
# ---------------------------------------------------------------------------

# 1. Scrap intensity: SCENARIO BOUNDS ONLY (no base). 1.08 is
#    diagnostic-only; 92.5% yield not source-backed; worldsteel 0.88/0.71
#    are the BLENDED recycled-EAF route (boundary mismatch).
SCRAP_LEVELS: Dict[str, float] = {
    "SCRAP_LOW": 1.0,
    "SCRAP_HIGH": 1.15,
}

# 2. DRI charge ratio — DISCRETE scenario alternatives (IBM IMYB 2022 vs
#    CEEW 2024 cluster survey; sources CONFLICT; neither 0.61 nor 0.80
#    promoted). Coal/ore per-t-DRI use the midpoint 1.5 of the CEEW
#    source-supported range 1.4-1.6 (disclosed construction value).
DRI_ALTERNATIVES: Dict[str, float] = {
    "DRI_IBM": 0.40,     # IBM IMYB 2022: IF metallic charge ~40% DRI
    "DRI_CEEW": 0.875,   # CEEW 2024: IF DRI + other ~87.5% (scrap ~12.5%)
}
DRI_PER_T_DRI_MID = 1.5  # midpoint of CEEW 1.4-1.6 per-t-DRI coal/ore range

# Coal-DRI-IF full-plant economics — documented CEEW EXTERNAL values
# (external_parameter_freeze.yaml: CAPEX_ANNUALISED_COAL_DRI_IF = 61.5,
#  OPEX_FIXED_COAL_DRI_IF = 26.0; tech card availability 0.85).
COAL_DRI_IF_ECONOMICS: Dict[str, float] = {
    "capex_annualised_usd_per_t": 61.5,
    "opex_fixed_usd_per_t": 26.0,
    "vom_usd_per_t": 0.0,
}
COAL_DRI_IF_AVAILABILITY = 0.85
COAL_DRI_IF_AVAILABILITY_PROVENANCE = "PROJECT_PROPOSAL"

# 3. Fleet scenarios — per-route existing capacity (Mt). Every scenario
#    carries a disclosure record (source / derivation / coverage /
#    remaining unknown). No fabrication.
FLEET_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "FLEET_CONSERVATIVE": {
        "existing_capacity_per_route_mt": {
            "BF-BOF": 57.9,
            "NG-DRI-EAF": 0.0,
            "Scrap-EAF": 36.61,
        },
        "disclosure": {
            "source": "india_steel_fleet_register.yaml (plant-level FROZEN_EXTERNAL); GSI/MoS Sept-2024",
            "derivation": (
                "BF-BOF 57.9 = documented plants only (SAIL 19.676 + RINL 7.3 + "
                "Tata 20.6 + JSPL 9.6 + NMDC 3.0; JSW excluded as PROJECT_PROPOSAL). "
                "NG-DRI-EAF 0.0 = no NG-DRI promoted. Scrap-EAF 36.61 = EAF aggregate "
                "residual (36.61 - 0.0 NG allocation); upper-bound interpretation "
                "(includes Coal-DRI-EAF share; feedstock split unresolved)."
            ),
            "coverage": "Documented plant evidence + GSI/MoS route aggregates (FY23-24).",
            "remaining_unknown": (
                "JSW and other non-documented plants; EAF feedstock split "
                "(Scrap-EAF vs Coal-DRI-EAF vs NG-DRI-EAF); hot-metal-to-crude boundary."
            ),
        },
    },
    "FLEET_CENTRAL": {
        "existing_capacity_per_route_mt": {
            "BF-BOF": 95.8,
            "NG-DRI-EAF": 9.0,
            "Scrap-EAF": 27.61,
        },
        "disclosure": {
            "source": "india_steel_fleet_register.yaml (GSI/MoS Sept-2024 route aggregates); AM/NS India disclosure",
            "derivation": (
                "BF-BOF 95.8 = GSI/MoS Sept-2024 BF hot-metal capacity (55 BF units, "
                "FY23-24) — hot-metal basis, NOT crude. NG-DRI-EAF 9.0 = AM/NS India "
                "Hazira (company disclosure, PROJECT_PROPOSAL). Scrap-EAF 27.61 = "
                "EAF aggregate residual (36.61 - 9.0 NG allocation)."
            ),
            "coverage": "GSI/MoS aggregate route capacities + AM/NS plant disclosure.",
            "remaining_unknown": (
                "Hot-metal-to-crude conversion; EAF feedstock split residual; "
                "JPC FY25 crude capacity split (gated)."
            ),
        },
    },
    "FLEET_ALTERNATIVE": {
        "existing_capacity_per_route_mt": {
            "BF-BOF": 112.7,
            "NG-DRI-EAF": 9.0,
            "Scrap-EAF": 27.61,
        },
        "disclosure": {
            "source": "india_steel_fleet_register.yaml (GSI/MoS Sept-2024); +15% BOF scrap interpretation",
            "derivation": (
                "BF-BOF 112.7 = 95.8 hot-metal grossed up by +15% BOF scrap-charge "
                "interpretation (hot-metal basis -> crude-steel equivalent). "
                "NG-DRI-EAF 9.0 and Scrap-EAF 27.61 as FLEET_CENTRAL."
            ),
            "coverage": "Aggregate route capacities with a documented BOF scrap interpretation.",
            "remaining_unknown": (
                "The +15% BOF scrap gross-up is a scenario interpretation, not a "
                "source fact; EAF feedstock split; JPC FY25 split (gated)."
            ),
        },
    },
}

POLICIES = ("CPS", "NZS")

# Robustness classification thresholds (documented, no probability language).
PRESENCE_SHARE_THRESHOLD = 0.05    # a technology is 'present' if 2050 share >= 5%
DOMINANCE_SHARE_THRESHOLD = 0.50   # 'dominant' if 2050 share >= 50%


# ---------------------------------------------------------------------------
# Scenario construction
# ---------------------------------------------------------------------------

class PathwayScenarioEngine:
    """Config-driven scenario matrix for the uncertainty-bounded pathway study."""

    def __init__(
        self,
        registry_path: str = PATHWAY_REGISTRY_PATH,
        base_policy_config: str = BASE_POLICY_CONFIG,
        intensities_path: str = INTENSITIES_PATH,
    ) -> None:
        self.registry_path = registry_path
        self.registry = UncertaintyRegistry(registry_path)
        self.base_policy_config = base_policy_config
        self.intensities_path = intensities_path
        with open(base_policy_config, "r", encoding="utf-8") as f:
            self.base_config_dict = yaml.safe_load(f)
        # The registry YAML is the source of truth for scenario bounds. If the
        # module constants drift outside the registered bounds, construction
        # fails loudly instead of silently diverging.
        issues = self.validate_registry_consistency()
        if issues:
            raise ValueError(
                "Pathway registry inconsistent with scenario constants:\n"
                + "\n".join(issues)
            )

    def validate_registry_consistency(self) -> List[str]:
        """
        Return a list of drift issues between the registry YAML (source of
        truth for bounds) and the module scenario constants.

        Empty list == consistent. Checks that the registered lower/upper
        bounds SPAN every scenario value the engine can construct.
        """
        issues: List[str] = []

        def _check(
            pid: str,
            lo: float,
            hi: float,
            label: str,
        ) -> None:
            p = self.registry.get_parameter(pid)
            if p is None:
                issues.append(f"registry missing parameter '{pid}'")
                return
            if p.lower_bound is None or p.upper_bound is None:
                issues.append(f"'{pid}' has no bounds in registry")
                return
            if p.lower_bound > lo or p.upper_bound < hi:
                issues.append(
                    f"'{pid}': registry [{p.lower_bound}, {p.upper_bound}] does not "
                    f"span {label} [{lo}, {hi}]"
                )

        _check(
            "scrap_intensity_Scrap-EAF",
            min(SCRAP_LEVELS.values()),
            max(SCRAP_LEVELS.values()),
            "SCRAP_LEVELS",
        )
        _check(
            "dri_charge_ratio_IF",
            min(DRI_ALTERNATIVES.values()),
            max(DRI_ALTERNATIVES.values()),
            "DRI_ALTERNATIVES",
        )
        _check(
            "dri_coal_intensity_per_t_dri",
            DRI_PER_T_DRI_MID,
            DRI_PER_T_DRI_MID,
            "DRI_PER_T_DRI_MID (coal)",
        )
        _check(
            "dri_ore_intensity_per_t_dri",
            DRI_PER_T_DRI_MID,
            DRI_PER_T_DRI_MID,
            "DRI_PER_T_DRI_MID (ore)",
        )
        for pid, route in [
            ("existing_capacity_BF-BOF_mt", "BF-BOF"),
            ("existing_capacity_NG-DRI-EAF_mt", "NG-DRI-EAF"),
            ("existing_capacity_Scrap-EAF_mt", "Scrap-EAF"),
        ]:
            vals = [
                FLEET_SCENARIOS[f]["existing_capacity_per_route_mt"][route]
                for f in FLEET_SCENARIOS
            ]
            _check(pid, min(vals), max(vals), f"FLEET {route}")
        return issues

    # -- config assembly ---------------------------------------------------

    def _base_routes(self) -> List[str]:
        return list(self.base_config_dict.get("enabled_routes", []))

    def build_config(
        self,
        policy: str,
        scrap_level: str,
        dri_alternative: Optional[str],
        fleet_id: str,
    ) -> Dict[str, Any]:
        """
        Build a merged scenario config dict from the Mode B policy base.

        ``dri_alternative`` None keeps Coal-DRI-IF disabled (baseline route
        subset). A DRI alternative enables Coal-DRI-IF with the documented
        CEEW EXTERNAL economics and charge-ratio-derived coal/ore
        intensities.
        """
        if policy not in POLICIES:
            raise ValueError(f"Unknown policy '{policy}'; expected one of {POLICIES}.")
        if scrap_level not in SCRAP_LEVELS:
            raise ValueError(
                f"Unknown scrap level '{scrap_level}'; expected one of {list(SCRAP_LEVELS)}."
            )
        if dri_alternative is not None and dri_alternative not in DRI_ALTERNATIVES:
            raise ValueError(
                f"Unknown DRI alternative '{dri_alternative}'; "
                f"expected one of {list(DRI_ALTERNATIVES)} or None."
            )
        if fleet_id not in FLEET_SCENARIOS:
            raise ValueError(
                f"Unknown fleet scenario '{fleet_id}'; expected one of {list(FLEET_SCENARIOS)}."
            )

        cfg = copy.deepcopy(self.base_config_dict)

        # --- dynamic scrap gate (DELIBERATE, documented) ----------------------
        # The pathway study isolates the THREE unresolved dimensions. The
        # Step 9 dynamic-scrap module has near-empty historical cohorts
        # (only 2021/2022 available), zero import allowance, and
        # PROJECT_PROPOSAL collection/yield parameters: with any positive
        # scrap intensity injected, its scrap-balance constraint is
        # infeasible (RES_scrap,t <= usable + imports ~ 0), which would
        # answer nothing about the dimensions under test. It is therefore
        # DISABLED here, exactly as in the established diagnostic config
        # (configs/optimization/diagnostic_scrap_intensity.yaml keeps
        # dynamic_scrap off "to keep the comparison clean"). The Mode B
        # policy rules (Gate A/C/F) still apply via the mode_b_policy block.
        cfg.setdefault("dynamic_scrap", {})["enabled"] = False

        # --- existing fleet -------------------------------------------------
        fleet_values = FLEET_SCENARIOS[fleet_id]["existing_capacity_per_route_mt"]
        per_route = {r: 0.0 for r in ALL_ROUTES}
        per_route.update(fleet_values)
        cfg["existing_capacity_per_route_mt"] = per_route
        # Aggregate stays as documented context only (never used as a split).
        # Source-backed: JPC FY2024-25 crude steel capacity 200.333 Mt
        # (data/external/source_manifest.yaml; frozen in baseline.yaml as
        # [EXTERNAL] context; fleet register total_crude_steel_capacity_mtpa).
        cfg["existing_capacity_mt_aggregate"] = 200.333

        # --- scrap intensity override ---------------------------------------
        scrap_val = SCRAP_LEVELS[scrap_level]
        overrides = list(cfg.get("provenance_gating", {}).get("intensity_overrides", []))
        overrides.append(
            {
                "route": "Scrap-EAF",
                "resource": "scrap",
                "value": scrap_val,
                "provenance": "EXTERNAL_PENDING",
                "rationale": (
                    f"UNCERTAINTY-BOUNDED PATHWAY SCENARIO '{scrap_level}' = {scrap_val} "
                    "t/t (source-supported scenario bound; NOT a frozen value. 1.08 is "
                    "diagnostic-only; 92.5% yield not source-backed; worldsteel 0.88/0.71 "
                    "are the BLENDED route, boundary mismatch)."
                ),
            }
        )

        # --- DRI charge alternative (enables Coal-DRI-IF) ---------------------
        if dri_alternative is not None:
            charge = DRI_ALTERNATIVES[dri_alternative]
            coal_int = charge * DRI_PER_T_DRI_MID   # t non-coking coal / t steel
            ore_int = charge * DRI_PER_T_DRI_MID    # t iron ore / t steel

            routes = list(cfg.get("enabled_routes", []))
            if "Coal-DRI-IF" not in routes:
                routes.append("Coal-DRI-IF")
            cfg["enabled_routes"] = routes

            econ = cfg.setdefault("economics", {})
            for k, v in COAL_DRI_IF_ECONOMICS.items():
                econ.setdefault(k, {})["Coal-DRI-IF"] = v
            cfg.setdefault("availability", {})["Coal-DRI-IF"] = {
                "value": COAL_DRI_IF_AVAILABILITY,
                "provenance": COAL_DRI_IF_AVAILABILITY_PROVENANCE,
            }
            cfg.setdefault("start_years", {})["Coal-DRI-IF"] = 2024

            overrides.append(
                {
                    "route": "Coal-DRI-IF",
                    "resource": "non_coking_coal",
                    "value": round(coal_int, 6),
                    "provenance": "EXTERNAL_PENDING",
                    "rationale": (
                        f"UNCERTAINTY-BOUNDED PATHWAY SCENARIO '{dri_alternative}' "
                        f"charge {charge} t DRI/t steel x CEEW coal {DRI_PER_T_DRI_MID} "
                        "t/t DRI (midpoint of source-supported 1.4-1.6). Scenario "
                        "construction, NOT frozen (IBM vs CEEW conflict unresolved)."
                    ),
                }
            )
            overrides.append(
                {
                    "route": "Coal-DRI-IF",
                    "resource": "iron_ore",
                    "value": round(ore_int, 6),
                    "provenance": "EXTERNAL_PENDING",
                    "rationale": (
                        f"UNCERTAINTY-BOUNDED PATHWAY SCENARIO '{dri_alternative}' "
                        f"charge {charge} t DRI/t steel x CEEW ore {DRI_PER_T_DRI_MID} "
                        "t/t DRI (midpoint of source-supported 1.4-1.6). Scenario "
                        "construction, NOT frozen."
                    ),
                }
            )

        cfg["provenance_gating"]["intensity_overrides"] = overrides
        return cfg

    # -- execution -----------------------------------------------------------

    def _solve_config(self, cfg: Dict[str, Any], policy: str) -> Tuple[Any, Any]:
        """Write config to a temp file, load inputs and solve deterministically."""
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".yaml")
        os.close(tmp_fd)
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f)
            inputs = load_baseline_inputs(
                tmp_path, self.intensities_path, scenario=policy
            )
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        res = BaselineMILP(inputs).solve()
        return inputs, res

    def run_scenario(
        self,
        policy: str,
        scrap_level: str,
        dri_alternative: Optional[str],
        fleet_id: str,
    ) -> Dict[str, Any]:
        """Run a single scenario and return its full record."""
        cfg = self.build_config(policy, scrap_level, dri_alternative, fleet_id)
        inputs, res = self._solve_config(cfg, policy)

        metrics = extract_scenario_metrics(inputs, res)

        scenario_id = f"{policy}_{scrap_level}_{dri_alternative or 'NO_DRI'}_{fleet_id}"

        # Parameter overrides record (provenance-visible, never silent).
        parameter_overrides = {
            "scrap_intensity_Scrap-EAF_t_per_t": SCRAP_LEVELS[scrap_level],
            "existing_capacity_per_route_mt": FLEET_SCENARIOS[fleet_id][
                "existing_capacity_per_route_mt"
            ],
        }
        if dri_alternative is not None:
            charge = DRI_ALTERNATIVES[dri_alternative]
            parameter_overrides["dri_charge_ratio_t_per_t"] = charge
            parameter_overrides["Coal-DRI-IF_non_coking_coal_t_per_t"] = round(
                charge * DRI_PER_T_DRI_MID, 6
            )
            parameter_overrides["Coal-DRI-IF_iron_ore_t_per_t"] = round(
                charge * DRI_PER_T_DRI_MID, 6
            )
            parameter_overrides["Coal-DRI-IF_capex_annualised_usd_per_t"] = COAL_DRI_IF_ECONOMICS[
                "capex_annualised_usd_per_t"
            ]
            parameter_overrides["Coal-DRI-IF_opex_fixed_usd_per_t"] = COAL_DRI_IF_ECONOMICS[
                "opex_fixed_usd_per_t"
            ]

        record = {
            "scenario_id": scenario_id,
            "scenario_name": f"{policy} / {scrap_level} / {dri_alternative or 'NO_DRI'} / {fleet_id}",
            "policy": policy,
            "scrap_level": scrap_level,
            "dri_alternative": dri_alternative,
            "fleet_id": fleet_id,
            "parameter_overrides": parameter_overrides,
            "data_completeness": metrics["data_completeness"],
            "solver_status": metrics["solver_status"],
            "status_label": metrics["status_label"],
            "objective": metrics["objective"],
            "technology_mix": metrics["technology_mix"],
            "H2": metrics["H2"],
            "electricity": metrics["electricity"],
            "scrap": metrics["scrap"],
            "coal": metrics["coal"],
            "gas": metrics["gas"],
            "ore": metrics["ore"],
            "CO2": metrics["CO2"],
            "investment": metrics["investment"],
            "fleet_disclosure": FLEET_SCENARIOS[fleet_id]["disclosure"],
        }
        return record

    def run_control(self, policy: str) -> Dict[str, Any]:
        """Run the Mode B policy control (no uncertainty overrides).

        Dynamic scrap is disabled for consistency with the scenario family
        (see build_config gate note). With null scrap intensity the scrap
        balance was vacuous anyway, so the control reproduces the official
        Mode A baseline objective 1,726,583.38 M USD exactly.
        """
        cfg = copy.deepcopy(self.base_config_dict)
        cfg.setdefault("dynamic_scrap", {})["enabled"] = False
        inputs, res = self._solve_config(cfg, policy)
        metrics = extract_scenario_metrics(inputs, res)
        record = {
            "scenario_id": f"CONTROL_{policy}",
            "scenario_name": f"{policy} / CONTROL (no uncertainty overrides)",
            "policy": policy,
            "scrap_level": None,
            "dri_alternative": None,
            "fleet_id": None,
            "parameter_overrides": {},
            "data_completeness": metrics["data_completeness"],
            "solver_status": metrics["solver_status"],
            "status_label": metrics["status_label"],
            "objective": metrics["objective"],
            "technology_mix": metrics["technology_mix"],
            "H2": metrics["H2"],
            "electricity": metrics["electricity"],
            "scrap": metrics["scrap"],
            "coal": metrics["coal"],
            "gas": metrics["gas"],
            "ore": metrics["ore"],
            "CO2": metrics["CO2"],
            "investment": metrics["investment"],
            "fleet_disclosure": {
                "source": "Mode B policy base config (baseline route subset).",
                "derivation": "No existing capacity (0.0 per route) — official baseline treatment.",
                "coverage": "Baseline control.",
                "remaining_unknown": "Route-level existing capacity (EXTERNAL_PENDING).",
            },
        }
        return record

    def run_matrix(
        self,
        policies: Tuple[str, ...] = POLICIES,
        include_controls: bool = True,
    ) -> Dict[str, Dict[str, Any]]:
        """Run the full scientifically-valid scenario matrix.

        Structure: for each policy (CPS, NZS) x scrap level (2) x DRI
        alternative (2) x fleet scenario (3) = 12 valid scenarios per
        policy. Controls (no uncertainty overrides) anchor the comparison.
        """
        results: Dict[str, Dict[str, Any]] = {}
        for policy in policies:
            if include_controls:
                results[f"CONTROL_{policy}"] = self.run_control(policy)
            for scrap_level in SCRAP_LEVELS:
                for dri_alt in DRI_ALTERNATIVES:
                    for fleet_id in FLEET_SCENARIOS:
                        record = self.run_scenario(
                            policy, scrap_level, dri_alt, fleet_id
                        )
                        results[record["scenario_id"]] = record
        return results


# ---------------------------------------------------------------------------
# Robustness metrics
# ---------------------------------------------------------------------------

def compute_robustness_metrics(
    results: Dict[str, Dict[str, Any]],
    year: int = 2050,
) -> Dict[str, Any]:
    """
    Compute robustness metrics over the VALID scenario set.

    Controls (CONTROL_*) are excluded: they carry no uncertainty overrides
    and would otherwise dilute presence statistics. Language: 'fraction of
    tested scenarios', never 'probability'.
    """
    valid = {
        sid: r for sid, r in results.items()
        if not sid.startswith("CONTROL_")
    }
    feasible = [r for r in valid.values() if r["solver_status"] == 0]
    n_feasible = len(feasible)
    n_total = len(valid)

    technology_stats: Dict[str, Dict[str, Any]] = {}
    for tech in ALL_ROUTES:
        shares = [
            r["technology_mix"].get(tech, {}).get(year, 0.0) for r in feasible
        ]
        if not shares:
            tech_stats = {
                "presence_frequency": None,
                "share_mean": None,
                "share_min": None,
                "share_max": None,
                "fraction_above_threshold": None,
                "n_feasible_scenarios": 0,
            }
        else:
            present = sum(1 for s in shares if s >= PRESENCE_SHARE_THRESHOLD)
            above_dom = sum(1 for s in shares if s >= DOMINANCE_SHARE_THRESHOLD)
            tech_stats = {
                "presence_frequency": present / len(shares),
                "share_mean": float(sum(shares) / len(shares)),
                "share_min": float(min(shares)),
                "share_max": float(max(shares)),
                "fraction_of_tested_scenarios_above_threshold": above_dom / len(shares),
                "n_feasible_scenarios": len(shares),
            }
        technology_stats[tech] = tech_stats

    # Cost / feasibility metrics over the valid set.
    objectives = [r["objective"] for r in feasible if r["objective"] is not None]
    cost_stats = {
        "objective_mean": float(sum(objectives) / len(objectives)) if objectives else None,
        "objective_min": float(min(objectives)) if objectives else None,
        "objective_max": float(max(objectives)) if objectives else None,
        "objective_relative_spread": (
            (max(objectives) - min(objectives)) / min(objectives) if objectives else None
        ),
    }

    # NOTE on fraction_of_tested_scenarios_above_threshold: the 'threshold'
    # is the DOMINANCE threshold (50% 2050 share, DOMINANCE_SHARE_THRESHOLD),
    # i.e. the fraction of tested feasible scenarios in which the technology
    # is selected as the (co-)dominant option. Presence (>=5%) is reported
    # separately as presence_frequency. This is documented so the generic
    # name is not confused with the 5% presence threshold.

    # Per-policy technology classification (ROBUST / CONDITIONALLY_ROBUST /
    # SENSITIVE / UNRESOLVED) and overall classification, so the required
    # conclusion classes are explicit deliverables.
    classifications: Dict[str, Dict[str, Any]] = {
        "overall": {
            tech: classify_conclusion(st) for tech, st in technology_stats.items()
        }
    }
    for policy in POLICIES:
        fam = [r for r in feasible if r["policy"] == policy]
        per_tech: Dict[str, Dict[str, Any]] = {}
        for tech in ALL_ROUTES:
            shares = [r["technology_mix"].get(tech, {}).get(year, 0.0) for r in fam]
            if not shares:
                st = {
                    "presence_frequency": None,
                    "share_mean": None,
                    "share_min": None,
                    "share_max": None,
                    "n_feasible_scenarios": 0,
                }
            else:
                present = sum(1 for s in shares if s >= PRESENCE_SHARE_THRESHOLD)
                st = {
                    "presence_frequency": present / len(shares),
                    "share_mean": float(sum(shares) / len(shares)),
                    "share_min": float(min(shares)),
                    "share_max": float(max(shares)),
                    "n_feasible_scenarios": len(shares),
                }
            per_tech[tech] = {"stats": st, "classification": classify_conclusion(st)}
        classifications[policy] = per_tech

    # Range metrics per policy family (feasible runs only).
    policy_families: Dict[str, Dict[str, Any]] = {}
    for policy in POLICIES:
        fam = [r for r in feasible if r["policy"] == policy]
        if not fam:
            continue
        policy_families[policy] = {
            "n_valid_scenarios": sum(1 for r in valid.values() if r["policy"] == policy),
            "n_feasible": len(fam),
            "feasibility_rate": len(fam) / sum(
                1 for r in valid.values() if r["policy"] == policy
            ),
            "objective_mean": float(
                sum(r["objective"] for r in fam if r["objective"] is not None) / len(fam)
            ),
        }

    return {
        "year": year,
        "share_threshold": PRESENCE_SHARE_THRESHOLD,
        "dominance_threshold": DOMINANCE_SHARE_THRESHOLD,
        "n_valid_scenarios": n_total,
        "n_feasible_scenarios": n_feasible,
        "feasibility_rate": n_feasible / n_total if n_total else 0.0,
        "technology_stats": technology_stats,
        "classifications": classifications,
        "cost_stats": cost_stats,
        "policy_families": policy_families,
    }


def classify_conclusion(tech_stats: Dict[str, Any]) -> str:
    """
    Classify a technology's pathway conclusion.

    ROBUST               : present (>=5% 2050 share) in >= 80% of tested
                           feasible scenarios AND never below 5% in any.
    CONDITIONALLY_ROBUST : present in 50-80% of tested feasible scenarios,
                           or always present but with share dipping below 5%.
    SENSITIVE            : present in < 50% of tested feasible scenarios
                           but non-zero in at least one.
    UNRESOLVED           : no feasible scenario shows any share (route
                           unrepresented or never selected under tested
                           coverage).
    """
    if tech_stats["n_feasible_scenarios"] == 0 or tech_stats["presence_frequency"] is None:
        return "UNRESOLVED"
    pf = tech_stats["presence_frequency"]
    if pf >= 0.8 and tech_stats["share_min"] >= PRESENCE_SHARE_THRESHOLD:
        return "ROBUST"
    if pf >= 0.8:
        # Present in >=80% of tested scenarios but share dips below the 5%
        # presence threshold in at least one -> CONDITIONALLY_ROBUST
        # (matches the docstring contract above).
        return "CONDITIONALLY_ROBUST"
    if 0.5 <= pf < 0.8:
        return "CONDITIONALLY_ROBUST"
    if pf > 0.0:
        return "SENSITIVE"
    return "UNRESOLVED"


def verify_control_baselines(
    results: Dict[str, Dict[str, Any]],
    rel_tol: float = 1e-9,
) -> Dict[str, float]:
    """
    Assert every CONTROL record reproduces the official Mode A baseline.

    Uses FROZEN_BASELINE_OBJECTIVE (defined in this module) so the constant
    is exercised at scenario level, not only in the runner. Returns the
    {scenario_id: objective} mapping for the caller to record.
    """
    checks: Dict[str, float] = {}
    for sid, r in results.items():
        if sid.startswith("CONTROL_"):
            obj = r["objective"]
            rel = abs(obj - FROZEN_BASELINE_OBJECTIVE) / FROZEN_BASELINE_OBJECTIVE
            if rel >= rel_tol:
                raise AssertionError(
                    f"{sid} drifted from official baseline: {obj} "
                    f"(rel {rel:.2e} >= {rel_tol:.0e})"
                )
            checks[sid] = obj
    if not checks:
        raise AssertionError("No CONTROL_* records found to verify.")
    return checks


def answer_study_questions(
    results: Dict[str, Dict[str, Any]],
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    """Answer questions A-F using only actual valid scenario coverage."""
    tech_stats = metrics["technology_stats"]

    def share_range(tech: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        st = tech_stats.get(tech, {})
        return st.get("share_mean"), st.get("share_min"), st.get("share_max")

    # A. Scrap-EAF dominance under defensible scrap-intensity bounds
    mean, lo, hi = share_range("Scrap-EAF")
    answers: Dict[str, Any] = {}
    if mean is not None and mean >= 0.5:
        answers["A_scrap_eaf_dominant"] = (
            f"Scrap-EAF mean 2050 share {mean:.3f} (min {lo:.3f}, max {hi:.3f}) "
            "across tested scenarios -> dominance survives defensible scrap bounds."
        )
    elif mean is not None:
        answers["A_scrap_eaf_dominant"] = (
            f"Scrap-EAF mean 2050 share {mean:.3f} (min {lo:.3f}, max {hi:.3f}) "
            "across tested scenarios -> dominance does NOT survive defensible "
            "scrap-intensity bounds."
        )
    else:
        answers["A_scrap_eaf_dominant"] = "UNRESOLVED — no feasible scenario coverage for Scrap-EAF."

    # B. Coal-DRI-IF role under honest DRI charge handling
    mean_b, lo_b, hi_b = share_range("Coal-DRI-IF")
    if mean_b is None:
        answers["B_coal_dri_if_dominant"] = "UNRESOLVED — no feasible scenario coverage."
    else:
        answers["B_coal_dri_if_dominant"] = (
            f"Coal-DRI-IF mean 2050 share {mean_b:.3f} (min {lo_b:.3f}, max {hi_b:.3f}) "
            "across tested scenarios (DRI charge alternatives + CEEW economics). "
            "Scenario result, NOT a frozen parameter conclusion."
        )

    # C. Fleet uncertainty materiality
    fleet_objectives: Dict[str, List[float]] = {}
    for r in results.values():
        if r["solver_status"] != 0 or r["fleet_id"] is None or r["objective"] is None:
            continue
        fleet_objectives.setdefault(r["fleet_id"], []).append(r["objective"])
    fleet_summary = {
        fid: {
            "n": len(vals),
            "objective_min": min(vals),
            "objective_max": max(vals),
            "objective_spread_pct": (
                (max(vals) - min(vals)) / min(vals) * 100.0 if vals else 0.0
            ),
        }
        for fid, vals in sorted(fleet_objectives.items())
    }
    spreads = [f["objective_spread_pct"] for f in fleet_summary.values()]
    max_spread = max(spreads) if spreads else 0.0
    answers["C_fleet_materiality"] = (
        f"Fleet scenarios objective spreads: { {k: round(v['objective_spread_pct'], 2) for k, v in fleet_summary.items()} } % "
        f"(max {max_spread:.1f}% within a fleet family). "
        + (
            "Fleet uncertainty materially moves system cost (>5% within-family spread)."
            if max_spread > 5.0
            else "Fleet uncertainty has minor cost impact within tested bounds (<=5%)."
        )
    )
    answers["C_fleet_detail"] = fleet_summary

    # D / E. Stable conclusions under CPS and NZS.
    # CONTROL_* records are excluded so the denominator is the same as in
    # compute_robustness_metrics (12 scenarios per policy, not 12 + control).
    for policy in POLICIES:
        fam = [
            r
            for r in results.values()
            if r["policy"] == policy
            and r["solver_status"] == 0
            and not r["scenario_id"].startswith("CONTROL_")
        ]
        stable = []
        for tech in ALL_ROUTES:
            shares = [r["technology_mix"].get(tech, {}).get(2050, 0.0) for r in fam]
            if not shares:
                continue
            pf = sum(1 for s in shares if s >= PRESENCE_SHARE_THRESHOLD) / len(shares)
            if pf >= 0.8:
                stable.append(
                    {
                        "technology": tech,
                        "presence_frequency": pf,
                        "share_mean": round(sum(shares) / len(shares), 4),
                    }
                )
        answers[f"{policy}_stable_technologies"] = stable

    # F. Conclusions dependent on unresolved evidence
    unresolved = []
    for tech in ("H2-DRI-EAF", "Coal-DRI-EAF"):
        st = tech_stats.get(tech, {})
        mean_f = st.get("share_mean")
        if mean_f is None or mean_f == 0.0:
            unresolved.append(tech)
    answers["F_unresolved_dependent"] = (
        unresolved
        + [
            "route-level fleet split (route_transition_interpretability stays FALSE)",
            "Coal-DRI-IF full-plant economics (CEEW EXTERNAL, scenario-exercised, not frozen)",
            "scrap availability (dynamic scrap parameters PROJECT_PROPOSAL)",
        ]
    )
    return answers


# ---------------------------------------------------------------------------
# Exporters
# ---------------------------------------------------------------------------

def flatten_record(record: Dict[str, Any], years=(2030, 2050, 2070)) -> Dict[str, Any]:
    """Flatten a scenario record to one CSV row at key years."""
    row: Dict[str, Any] = {
        "scenario_id": record["scenario_id"],
        "scenario_name": record["scenario_name"],
        "policy": record["policy"],
        "scrap_level": record.get("scrap_level"),
        "dri_alternative": record.get("dri_alternative"),
        "fleet_id": record.get("fleet_id"),
        "solver_status": record["solver_status"],
        "objective": record["objective"],
        "feasible": record["solver_status"] == 0,
    }
    for tech in ALL_ROUTES:
        for y in years:
            row[f"share_{tech}_{y}"] = (
                record["technology_mix"].get(tech, {}).get(y, 0.0) if record["solver_status"] == 0 else None
            )
    for key in ("H2", "electricity", "scrap", "coal", "gas", "ore", "CO2", "investment"):
        for y in years:
            row[f"{key}_{y}"] = (
                record[key].get(y, 0.0) if record["solver_status"] == 0 else None
            )
    return row


def export_results(
    results: Dict[str, Dict[str, Any]],
    metrics: Dict[str, Any],
    answers: Dict[str, Any],
    output_dir: str,
) -> None:
    """Write pathway_scenarios.csv / .json and the metrics + answers JSON."""
    os.makedirs(output_dir, exist_ok=True)
    rows = [flatten_record(r) for r in results.values()]
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(output_dir, "pathway_scenarios.csv"), index=False)

    with open(os.path.join(output_dir, "pathway_scenarios.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    with open(os.path.join(output_dir, "robustness_metrics.json"), "w", encoding="utf-8") as f:
        json.dump({"metrics": metrics, "answers": answers}, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------

def _plot_style() -> None:
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]


def generate_pathway_plots(
    results: Dict[str, Dict[str, Any]],
    output_dir: str,
) -> None:
    """Generate the five required range plots."""
    _plot_style()
    os.makedirs(output_dir, exist_ok=True)

    feasible = [r for r in results.values() if r["solver_status"] == 0]
    if not feasible:
        return

    # 1. technology_range.png — 2050 share range per technology (feasible runs)
    fig, ax = plt.subplots(figsize=(9, 5), dpi=200)
    techs = []
    means, lows, highs = [], [], []
    for tech in ALL_ROUTES:
        shares = [r["technology_mix"].get(tech, {}).get(2050, 0.0) for r in feasible]
        means.append(sum(shares) / len(shares))
        lows.append(min(shares))
        highs.append(max(shares))
        techs.append(tech)
    y = range(len(techs))
    ax.hlines(y, lows, highs, color="#457B9D", linewidth=6, alpha=0.85, label="range across tested scenarios")
    ax.scatter(means, y, color="#1D3557", s=40, zorder=5, label="mean 2050 share")
    ax.axvline(0.5, color="#E76F51", linestyle="--", linewidth=1.2, alpha=0.8, label="dominance threshold 50%")
    ax.set_yticks(list(y))
    ax.set_yticklabels(techs, fontsize=10, fontweight="bold", color="#1D3557")
    ax.set_xlim(-0.02, 1.02)
    ax.set_xlabel("2050 production share (fraction of tested feasible scenarios)", fontsize=10)
    ax.set_title("Technology Range Across Uncertainty-Bounded Pathway Scenarios (2050)", fontsize=12, fontweight="bold", color="#1D3557")
    ax.legend(loc="lower right", frameon=True, fontsize=9)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "technology_range.png"))
    plt.close()

    def _yearly_range(key: str, title: str, fname: str) -> None:
        fig, ax = plt.subplots(figsize=(9, 5), dpi=200)
        for y in (2030, 2050, 2070):
            vals = [r[key].get(y, 0.0) for r in feasible]
            ax.plot(
                [y, y], [min(vals), max(vals)], color="#2A9D8F", linewidth=5, alpha=0.75
            )
            ax.scatter([y], [sum(vals) / len(vals)], color="#1D3557", s=50, zorder=5)
        ax.set_title(title, fontsize=12, fontweight="bold", color="#1D3557")
        ax.set_xlabel("Year", fontsize=10)
        ax.set_ylabel("Value (range across tested scenarios)", fontsize=10)
        ax.set_xticks([2030, 2050, 2070])
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, fname))
        plt.close()

    # 2. h2_range.png
    _yearly_range("H2", "Hydrogen Use Range Across Uncertainty-Bounded Scenarios", "h2_range.png")
    # 3. co2_range.png
    _yearly_range("CO2", "CO2 Emissions Range Across Uncertainty-Bounded Scenarios", "co2_range.png")
    # 4. investment_range.png
    _yearly_range("investment", "Investment Range Across Uncertainty-Bounded Scenarios", "investment_range.png")
    # 5. cost_range.png — objective per scenario, coloured by policy
    fig, ax = plt.subplots(figsize=(10, 5), dpi=200)
    sids = [r["scenario_id"] for r in feasible]
    objs = [r["objective"] for r in feasible]
    colors = ["#2A9D8F" if r["policy"] == "CPS" else "#E76F51" for r in feasible]
    bars = ax.bar(sids, [o / 1000 for o in objs], color=colors, alpha=0.9, width=0.7)
    for bar, o in zip(bars, objs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5,
                f"{o / 1000:.0f}k", ha="center", va="bottom", fontsize=7, fontweight="bold", color="#1D3557")
    ax.set_title("Discounted System Cost Across Uncertainty-Bounded Scenarios (k M USD)", fontsize=12, fontweight="bold", color="#1D3557")
    ax.set_ylabel("Objective (k M USD)", fontsize=10)
    plt.xticks(rotation=90, fontsize=7)
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "cost_range.png"))
    plt.close()
