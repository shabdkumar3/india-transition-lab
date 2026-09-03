"""
Constraint diagnostics and slack calculations (Step 15).
"""

from __future__ import annotations

from typing import Any, Dict, List
from steel_model.optimization.model import BaselineInputs, BaselineMILPResult
from steel_model.explainability.schemas import ConstraintDiagnostic


def run_constraint_diagnostics(
    inputs: BaselineInputs,
    res: BaselineMILPResult,
) -> List[ConstraintDiagnostic]:
    """Calculate slack, pressure, and binding status for all model constraints."""
    records: List[ConstraintDiagnostic] = []
    years = list(inputs.years)
    tolerance = 1e-5

    for t in years:
        # 1. Demand Constraint
        avail_demand = inputs.demand_mt[t]
        used_demand = sum(res.act_mt.get(r, {}).get(t, 0.0) for r in inputs.routes)
        slack_demand = avail_demand - used_demand
        pressure_demand = (used_demand / avail_demand) if avail_demand > 0.0 else 0.0
        binding_demand = "BINDING" if abs(slack_demand) <= tolerance else "NON_BINDING"
        records.append(
            ConstraintDiagnostic(
                year=t,
                constraint_type="demand",
                available=float(avail_demand),
                used=float(used_demand),
                slack=float(slack_demand),
                pressure=float(pressure_demand),
                binding_status=binding_demand,
            )
        )

        # 2. Capacity Constraints (per route)
        for r in inputs.routes:
            avail_cap = inputs.availability.get(r, 0.90) * res.cap_mt.get(r, {}).get(t, 0.0)
            used_cap = res.act_mt.get(r, {}).get(t, 0.0)
            slack_cap = avail_cap - used_cap
            pressure_cap = (used_cap / avail_cap) if avail_cap > 0.0 else None
            binding_cap = "BINDING" if (avail_cap > 0.0 and abs(slack_cap) <= tolerance) else "NON_BINDING"
            records.append(
                ConstraintDiagnostic(
                    year=t,
                    constraint_type=f"capacity_{r}",
                    available=float(avail_cap) if avail_cap > 0.0 else 0.0,
                    used=float(used_cap),
                    slack=float(slack_cap) if avail_cap > 0.0 else 0.0,
                    pressure=float(pressure_cap) if pressure_cap is not None else None,
                    binding_status=binding_cap,
                )
            )

        # 3. Deployment Constraints (per route)
        for r in inputs.routes:
            if inputs.deployment_dynamics_enabled:
                limit = inputs.ncap_limits_mt.get(r)
                used_limit = res.ncap_mt.get(r, {}).get(t, 0.0)
                if limit is not None:
                    slack_limit = limit - used_limit
                    pressure_limit = (used_limit / limit) if limit > 0.0 else None
                    binding_limit = "BINDING" if abs(slack_limit) <= tolerance else "NON_BINDING"
                    records.append(
                        ConstraintDiagnostic(
                            year=t,
                            constraint_type=f"deployment_{r}",
                            available=float(limit),
                            used=float(used_limit),
                            slack=float(slack_limit),
                            pressure=float(pressure_limit) if pressure_limit is not None else None,
                            binding_status=binding_limit,
                        )
                    )
                else:
                    records.append(
                        ConstraintDiagnostic(
                            year=t,
                            constraint_type=f"deployment_{r}",
                            available=None,
                            used=float(used_limit),
                            slack=None,
                            pressure=None,
                            binding_status="UNCONSTRAINED",
                        )
                    )
            else:
                records.append(
                    ConstraintDiagnostic(
                        year=t,
                        constraint_type=f"deployment_{r}",
                        available=None,
                        used=0.0,
                        slack=None,
                        pressure=None,
                        binding_status="UNCONSTRAINED",
                    )
                )

        # 4. Scrap Constraints
        if inputs.dynamic_scrap_enabled and res.scrap_accounting is not None:
            avail_scrap = res.scrap_accounting.usable_scrap_mt.get(t)
            used_scrap = res.res_use.get("scrap", {}).get(t, 0.0)
            if avail_scrap is not None:
                slack_scrap = avail_scrap - used_scrap
                pressure_scrap = (used_scrap / avail_scrap) if avail_scrap > 0.0 else None
                binding_scrap = "BINDING" if abs(slack_scrap) <= tolerance else "NON_BINDING"
                records.append(
                    ConstraintDiagnostic(
                        year=t,
                        constraint_type="scrap",
                        available=float(avail_scrap),
                        used=float(used_scrap),
                        slack=float(slack_scrap),
                        pressure=float(pressure_scrap) if pressure_scrap is not None else None,
                        binding_status=binding_scrap,
                    )
                )
            else:
                records.append(
                    ConstraintDiagnostic(
                        year=t,
                        constraint_type="scrap",
                        available=None,
                        used=float(used_scrap),
                        slack=None,
                        pressure=None,
                        binding_status="UNCONSTRAINED",
                    )
                )
        else:
            records.append(
                ConstraintDiagnostic(
                    year=t,
                    constraint_type="scrap",
                    available=None,
                    used=res.res_use.get("scrap", {}).get(t, 0.0),
                    slack=None,
                    pressure=None,
                    binding_status="UNCONSTRAINED",
                )
            )

        # 5. Resource Constraints (unlimited imports/supply at fixed prices in baseline)
        for res_id in inputs.resources:
            used_res = res.res_use.get(res_id, {}).get(t, 0.0)
            records.append(
                ConstraintDiagnostic(
                    year=t,
                    constraint_type=f"resource_{res_id}",
                    available=None,
                    used=float(used_res),
                    slack=None,
                    pressure=None,
                    binding_status="UNCONSTRAINED",
                )
            )

        # 6. Emissions Constraint (no carbon budget/cap in baseline)
        used_co2 = res.co2_total_mt.get(t, 0.0)
        records.append(
            ConstraintDiagnostic(
                year=t,
                constraint_type="emissions",
                available=None,
                used=float(used_co2),
                slack=None,
                pressure=None,
                binding_status="UNCONSTRAINED",
            )
        )

    return records
