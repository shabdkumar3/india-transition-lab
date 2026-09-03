"""
Baseline multi-period MILP — control/reference optimization engine (Step 8).

The MILP is the DECISION ENGINE for the source-driven least-cost steel
pathway under frozen inputs. M1 (electrolyser learning), dynamic scrap,
endogenous learning and deployment ML are all DISABLED here (Mode A
baseline / control configuration).
"""

from steel_model.optimization.model import (
    BaselineInputs,
    BaselineMILP,
    BaselineMILPResult,
    derive_annual_demand,
    load_baseline_inputs,
)

__all__ = [
    "BaselineInputs",
    "BaselineMILP",
    "BaselineMILPResult",
    "derive_annual_demand",
    "load_baseline_inputs",
]
