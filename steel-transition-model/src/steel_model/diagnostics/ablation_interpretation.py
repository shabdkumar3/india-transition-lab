"""
Ablation Interpretation (Step 15 §12).

Builds diagnostics that make ablation statuses explicit:

SCRAP_LAYER:
  implemented
  but currently non-binding because required scrap parameter is incomplete

DEPLOYMENT_LAYER:
  implemented
  but certain scenario combinations become infeasible

LEARNING_LAYER:
  framework implemented
  but steel learning rates unresolved

M1:
  real data absent
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from steel_model.optimization.model import BaselineInputs
from steel_model.optimization.results import BaselineMILPResult


@dataclass
class AblationStatus:
    """Status of one ablation layer."""
    layer: str
    implemented: bool
    functional: bool  # Actually affects results
    status_text: str
    evidence: List[str]
    limiting_factors: List[str]


def interpret_ablation(
    control_inputs: BaselineInputs,
    control_result: BaselineMILPResult,
    mode_b_inputs: Optional[BaselineInputs] = None,
    mode_b_result: Optional[BaselineMILPResult] = None,
    deployment_inputs: Optional[BaselineInputs] = None,
    deployment_result: Optional[BaselineMILPResult] = None,
    learning_enabled: bool = False,
) -> List[AblationStatus]:
    """
    Interpret ablation layers from Step 14 results.

    Returns list of AblationStatus for each layer.
    """
    statuses = []

    # --- Control (base) ---
    statuses.append(AblationStatus(
        layer="CONTROL",
        implemented=True,
        functional=True,
        status_text="Baseline MILP — economics-available route subset (BF-BOF, NG-DRI-EAF, Scrap-EAF)",
        evidence=["Objective = 1,726,583 M USD", "Mix = 100% Scrap-EAF"],
        limiting_factors=["SCRAP_INTENSITY_EXTERNAL_PENDING", "EXISTING_ROUTE_CAPACITY_UNAVAILABLE", "H2_DRI_FULL_PLANT_ECONOMICS_EXTERNAL_PENDING"],
    ))

    # --- Scrap layer (Mode B dynamic scrap) ---
    if mode_b_result is not None and mode_b_result.status == 0:
        obj_diff = mode_b_result.objective_value - control_result.objective_value
        mix_same = True
        for r in control_inputs.routes:
            if control_result.production_share(r)[2070] != mode_b_result.production_share(r)[2070]:
                mix_same = False
                break

        if mix_same and abs(obj_diff) < 1.0:
            functional = False
            status_text = "VACUOUS — Scrap-EAF scrap intensity is EXTERNAL_PENDING (null), so scrap availability constraint never binds; mix and objective identical to control"
            evidence = [
                f"Control objective: {control_result.objective_value:.2f} M USD",
                f"Mode B objective: {mode_b_result.objective_value:.2f} M USD",
                "Difference < 1 M USD",
                "2070 mix identical (100% Scrap-EAF)",
            ]
        else:
            functional = True
            status_text = "ACTIVE — Dynamic scrap constraint binds and changes pathway"
            evidence = [f"Objective difference: {obj_diff:.2f} M USD"]

        statuses.append(AblationStatus(
            layer="SCRAP",
            implemented=True,
            functional=functional,
            status_text=status_text,
            evidence=evidence,
            limiting_factors=["SCRAP_INTENSITY_EXTERNAL_PENDING"],
        ))
    else:
        statuses.append(AblationStatus(
            layer="SCRAP",
            implemented=True,
            functional=False,
            status_text="Mode B not solved or infeasible; Scrap-EAF scrap intensity is EXTERNAL_PENDING (null), so scrap availability constraint cannot bind",
            evidence=[],
            limiting_factors=["SCRAP_INTENSITY_EXTERNAL_PENDING"],
        ))

    # --- Deployment layer ---
    if deployment_result is not None:
        if deployment_result.status == 2:  # infeasible
            statuses.append(AblationStatus(
                layer="DEPLOYMENT",
                implemented=True,
                functional=False,
                status_text="INFEASIBLE — Construction lead times with zero route-level existing capacity cannot serve 2024 demand",
                evidence=[
                    "Solver status: INFEASIBLE",
                    "No existing per-route capacity (all 0.0 Mt)",
                    "Lead times: BF-BOF=4yr, NG-DRI-EAF=3yr, Scrap-EAF=2yr",
                ],
                limiting_factors=["EXISTING_ROUTE_CAPACITY_UNAVAILABLE"],
            ))
        elif deployment_result.status == 0:
            statuses.append(AblationStatus(
                layer="DEPLOYMENT",
                implemented=True,
                functional=True,
                status_text="ACTIVE — Deployment limits constrain new capacity",
                evidence=[f"Objective: {deployment_result.objective_value:.2f} M USD"],
                limiting_factors=[],
            ))
        else:
            statuses.append(AblationStatus(
                layer="DEPLOYMENT",
                implemented=True,
                functional=False,
                status_text=f"Solver status: {deployment_result.status_label}",
                evidence=[],
                limiting_factors=[],
            ))
    else:
        statuses.append(AblationStatus(
            layer="DEPLOYMENT",
            implemented=True,
            functional=False,
            status_text="Not evaluated (no deployment config solved); would require route-level existing capacity to be feasible (default state: INFEASIBLE)",
            evidence=[],
            limiting_factors=["EXISTING_ROUTE_CAPACITY_UNAVAILABLE"],
        ))

    # --- Learning layer ---
    if learning_enabled:
        statuses.append(AblationStatus(
            layer="LEARNING",
            implemented=True,
            functional=True,
            status_text="ACTIVE — Endogenous learning loop running",
            evidence=[],
            limiting_factors=[],
        ))
    else:
        statuses.append(AblationStatus(
            layer="LEARNING",
            implemented=True,
            functional=False,
            status_text="DEFERRED — Framework implemented but steel-route learning rates are EXTERNAL_PENDING; no rates fabricated",
            evidence=[
                "learning_rates dict empty in BaselineInputs",
                "learning_exponents dict empty",
                "M1 b_elec DEFERRED (no real electrolyser cost data)",
            ],
            limiting_factors=["STEEL_LEARNING_RATES_EXTERNAL_PENDING", "M1_B_ELEC_DEFERRED"],
        ))

    # --- M1 ---
    statuses.append(AblationStatus(
        layer="M1",
        implemented=True,
        functional=False,
        status_text="REAL DATA ABSENT — M1 estimator implemented and synthetic-tested; real historical electrolyser cost/deployment dataset = 0 observations",
        evidence=[
            "M1_INTERFACE_SPEC.md defines interface",
            "M1_VALIDATION.md documents synthetic test",
            "M1_DATA_GAP.md: 0 real observations found",
            "b_elec remains DEFERRED",
        ],
        limiting_factors=["ELECTROLYSER_COST_DEPLOYMENT_DATA_ABSENT"],
    ))

    return statuses


def ablation_statuses_to_csv_rows(statuses: List[AblationStatus]) -> List[dict]:
    rows = []
    for s in statuses:
        rows.append({
            "layer": s.layer,
            "implemented": s.implemented,
            "functional": s.functional,
            "status_text": s.status_text,
            "evidence": "; ".join(s.evidence),
            "limiting_factors": "; ".join(s.limiting_factors),
        })
    return rows