"""
Solver wrapper for the baseline MILP (Step 8).

Solver: HiGHS via scipy.optimize.milp.
All decision variables are continuous in this baseline (capacity and
production are real-valued Mt quantities); integrality is all-zero, so
HiGHS solves the underlying LP. The milp() interface is used because it
is the canonical scipy entry point for the HiGHS solver and keeps the
route open for future integer extensions without changing the API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp


@dataclass
class SolverResult:
    """Outcome of one MILP solve."""

    status: int
    message: str
    objective_value: Optional[float]
    x: Optional[np.ndarray]
    solver: str = "HiGHS (scipy.optimize.milp)"

    @property
    def success(self) -> bool:
        return self.status == 0

    @property
    def status_label(self) -> str:
        return {
            0: "optimal",
            1: "iteration/time-limit reached",
            2: "infeasible",
            3: "unbounded",
            4: "other error",
        }.get(self.status, f"unknown ({self.status})")


def solve_milp(
    c: np.ndarray,
    a: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    var_lb: np.ndarray,
    var_ub: np.ndarray,
    time_limit_seconds: Optional[float] = None,
) -> SolverResult:
    """
    Solve min c.x s.t. lb <= A x <= ub with box bounds var_lb <= x <= var_ub.

    All variables are continuous (integrality = 0). Returns a SolverResult.
    """
    if len(c.shape) != 1:
        raise ValueError(f"Objective vector c must be 1-D, got shape {c.shape}")
    n_vars = c.shape[0]
    if a.shape[1] != n_vars:
        raise ValueError(
            f"Constraint matrix columns ({a.shape[1]}) != n_vars ({n_vars})"
        )
    if len(var_lb) != n_vars or len(var_ub) != n_vars:
        raise ValueError("var_lb/var_ub must have length n_vars")

    integrality = np.zeros(n_vars, dtype=int)  # continuous LP in this baseline

    # HiGHS LP tuning — scipy 1.9+ compatible option names.
    # "presolve" takes True/False (not "on"/"off") since scipy 1.12.
    # Non-standard HiGHS keys removed to avoid OptimizeWarning → possible
    # solver error on strict scipy builds.
    options: dict = {
        "disp": False,
        "presolve": True,   # reduce problem before solve
        "time_limit": time_limit_seconds if time_limit_seconds is not None else 300.0,
    }
    # Optional HiGHS-native keys passed verbatim (scipy forwards unknown opts)
    # Removed: "solver", "simplex_strategy", "simplex_scale_strategy",
    #          "primal_feasibility_tolerance", "dual_feasibility_tolerance"
    # — these are unrecognized by scipy >= 1.12 and may cause errors on
    #   strict builds; HiGHS defaults are adequate for this problem size.

    res = milp(
        c=c,
        integrality=integrality,
        bounds=Bounds(var_lb, var_ub),
        constraints=LinearConstraint(a, lb, ub),
        options=options,
    )

    return SolverResult(
        status=int(res.status),
        message=str(res.message),
        objective_value=float(res.fun) if res.x is not None else None,
        x=np.array(res.x) if res.x is not None else None,
    )
