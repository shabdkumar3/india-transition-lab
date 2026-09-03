"""
Objective builder for the baseline multi-period MILP (Step 8).

Baseline discounted system cost, minimised:

    min sum_t df(t) * [ sum_i ( annCapex_i * CAP[i,t]
                                + (FOM_i + VOM_i) * ACT[i,t] )
                        + sum_r price_r * RES[r,t] ]

where df(t) = (1 + discount_rate)^-(t - start_year).

Cost basis (frozen Step-6 / IEA 2020 cross-section, registry §6):
- annCapex_i  : IEA ANNUALISED CAPEX (USD/t capacity-year). Used AS-IS.
                 It is NOT re-annualised (no CRF, no division by lifetime).
- FOM+VOM     : combined fixed+variable O&M per tonne produced
                 (frozen Step-6 definition). VOM is 0 in the baseline
                 (EXTERNAL_PENDING) so there is no double counting.
- price_r     : resource price converted to cost-per-model-unit
                 (source_unit -> model_unit via explicit formula).
- Energy cost is charged ONLY through RES[r,t] (= ACT * intensity);
                 it is NOT double counted inside FOM/VOM.

EXCLUDED from this baseline objective (Mode-A control run):
  M1 electrolyser learning, endogenous learning, dynamic scrap,
  deployment/ramp penalties, benchmark-matching penalties, carbon price,
  unsupported technology costs.
"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

from steel_model.optimization.variables import VariableIndex


def discount_factors(years, start_year: int, discount_rate: float) -> Dict[int, float]:
    """df(t) = (1 + r)^-(t - start_year), t in years."""
    out = {}
    for t in years:
        out[t] = (1.0 + discount_rate) ** (-(t - start_year))
    return out


def build_objective(
    index: VariableIndex,
    inputs: "BaselineInputs",
) -> Tuple[np.ndarray, dict]:
    """
    Build the objective coefficient vector c (length n_vars) and a metadata
    dict describing the cost basis and provenance of each coefficient group.
    """
    c = np.zeros(index.n_vars())
    df = discount_factors(inputs.years, inputs.start_year, inputs.discount_rate)

    meta = {
        "discount_rate": inputs.discount_rate,
        "discount_rate_provenance": inputs.discount_rate_provenance,
        "cost_basis": "IEA annualised CAPEX (frozen, NOT re-annualised) "
                      "+ combined FOM/VOM (frozen) + resource cost via RES",
        "excluded": [
            "M1 electrolyser learning",
            "benchmark-matching penalties",
            "unsupported technology costs",
        ],
        "step20_enhancements": [
            "carbon_price: configurable (see carbon_price block)",
            "stranded_cost: configurable (see stranded_asset_cost block)",
            "time_varying_prices: configurable (see resource_price_trajectories block)",
            "endogenous_learning: configurable (see endogenous_learning block)",
            "h2_supply_cap: configurable (see h2_supply_cap block)",
        ],
        "coefficient_groups": [],
    }

    # --- CAP[i,t]: annualised CAPEX on installed capacity each year ---
    # Step 21C: WACC risk premium multiplies effective CAPEX per route
    for i in inputs.routes:
        capex = inputs.capex_annualised_usd_per_t[i]
        wacc_mult = inputs.wacc_premium_by_route.get(i, 1.0) if inputs.wacc_premium_enabled else 1.0
        meta["coefficient_groups"].append(
            {
                "block": "CAP",
                "route": i,
                "usd_per_t_capacity_yr": capex if not isinstance(capex, dict) else "time-varying",
                "wacc_premium_multiplier": wacc_mult,
                "provenance": "EXTERNAL (IEA Roadmap 2020 p.30 Fig 1.10, annualised)",
                "notes": "Annualised CAPEX charged per year of installed capacity; "
                         "wacc_premium applied for financing-cost realism (Step 21C).",
            }
        )
        for t in inputs.years:
            val = capex[t] if isinstance(capex, dict) else capex
            c[index.idx("CAP", i, t)] += df[t] * val * wacc_mult

    # --- ACT[i,t]: FOM+VOM per tonne produced ---
    for i in inputs.routes:
        fom = inputs.opex_fixed_usd_per_t[i]
        vom = inputs.vom_usd_per_t[i]
        meta["coefficient_groups"].append(
            {
                "block": "ACT",
                "route": i,
                "fom_usd_per_t": fom,
                "vom_usd_per_t": vom,
                "provenance": "FROZEN Step-6 OPEX definitions (FOM+VOM combined); "
                              "VOM EXTERNAL_PENDING -> 0",
                "notes": "No double count: energy cost is charged via RES block only.",
            }
        )
        for t in inputs.years:
            c[index.idx("ACT", i, t)] += df[t] * (fom + vom)

    # --- RES[r,t]: resource cost at converted price ---
    for r in inputs.resources:
        price = inputs.resource_price_model_unit[r]
        meta["coefficient_groups"].append(
            {
                "block": "RES",
                "resource": r,
                "usd_per_model_unit": price,
                "source_unit": inputs.resource_price_source_unit[r],
                "model_unit": inputs.resource_price_model_unit_name[r],
                "conversion_formula": inputs.resource_price_conversion_formula[r],
                "conversion_factor": inputs.resource_price_conversion_factor.get(r, 1.0),
                "conversion_operation": inputs.resource_price_conversion_operation.get(r, "multiply"),
                "provenance": inputs.resource_price_provenance[r],
            }
        )
        for t in inputs.years:
            c[index.idx("RES", r, t)] += df[t] * price

    # --- RES[r,t]: time-varying price override (Step 20D) ---
    # When a resource_price_trajectory is provided for a resource, the
    # per-year price replaces the static price set above. This allows
    # declining H₂ / RE electricity costs to flow into the objective.
    for r in inputs.resources:
        traj = inputs.resource_price_trajectory.get(r)
        if traj:
            static_price = inputs.resource_price_model_unit[r]
            for t in inputs.years:
                traj_price = traj.get(t, static_price)
                # Subtract the previously added static coefficient and add trajectory one
                c[index.idx("RES", r, t)] += df[t] * (traj_price - static_price)

    # --- RET[i,t]: stranded-asset cost (Step 20C) ---
    # When stranded_cost is enabled, retiring capacity before its natural
    # end-of-life incurs a penalty equal to stranded_cost_fraction × annCapex_i.
    # This represents the balance-sheet value lost on premature closure.
    if inputs.stranded_cost_enabled and inputs.stranded_cost_fraction > 0.0:
        frac = inputs.stranded_cost_fraction
        meta["stranded_cost"] = {
            "fraction": frac,
            "provenance": inputs.stranded_cost_provenance,
            "note": "Penalty on RET[i,t] = fraction × annCapex_i; discourages early retirement.",
        }
        for i in inputs.routes:
            capex = inputs.capex_annualised_usd_per_t[i]
            for t in inputs.years:
                capex_val = capex[t] if isinstance(capex, dict) else capex
                c[index.idx("RET", i, t)] += df[t] * frac * capex_val

    # --- CO2[t]: carbon price (Step 20A) ---
    # Adds df(t) × carbon_price[t] to the CO2[t] coefficient so that
    # higher-emission routes bear a per-tonne carbon cost. This signals
    # the direction of decarbonisation without imposing a hard CI cap.
    if inputs.carbon_price_enabled and inputs.carbon_price_usd_per_tco2:
        meta["carbon_price"] = {
            "enabled": True,
            "provenance": inputs.carbon_price_provenance,
            "trajectory": dict(sorted(inputs.carbon_price_usd_per_tco2.items())),
            "note": "USD/tCO₂ cost on CO2[t]; increases over time to incentivise decarbonisation.",
        }
        for t in inputs.years:
            cp = inputs.carbon_price_usd_per_tco2.get(t, 0.0)
            if cp > 0.0:
                c[index.idx("CO2", "", t)] += df[t] * cp

    # --- ACT[i,t]: policy incentives / PLI subsidies (Step 21D) ---
    # Negative USD/t cost on production — represents India's PLI / Green Steel
    # Mission financial support for strategic decarbonisation routes.
    # Negative contribution to objective cost = subsidy reducing effective LCOP.
    if inputs.policy_incentives_enabled and inputs.policy_incentives_usd_per_t:
        meta["policy_incentives"] = {
            "enabled": True,
            "provenance": inputs.policy_incentives_provenance,
            "routes": list(inputs.policy_incentives_usd_per_t.keys()),
            "note": "Negative USD/t on ACT[i,t]; represents PLI-equivalent subsidy schedule.",
        }
        for i in inputs.routes:
            incentive_by_year = inputs.policy_incentives_usd_per_t.get(i, {})
            if incentive_by_year:
                for t in inputs.years:
                    incentive = incentive_by_year.get(t, 0.0)
                    if incentive != 0.0:
                        c[index.idx("ACT", i, t)] += df[t] * incentive

    # --- ACT[i,t]: green-steel market premium (Step 21E) ---
    # Revenue bonus (negative cost) for qualifying low-emission routes.
    # Represents willingness-to-pay premium from green-steel buyers
    # (EU CBAM, automotive OEMs, ESG supply chains).
    if inputs.green_premium_enabled and inputs.green_premium_qualifying_routes:
        meta["green_steel_premium"] = {
            "enabled": True,
            "provenance": inputs.green_premium_provenance,
            "threshold_tco2_per_t": inputs.green_premium_threshold_tco2_per_t,
            "qualifying_routes": inputs.green_premium_qualifying_routes,
            "note": "Negative USD/t on ACT for qualifying routes = revenue bonus from green buyers.",
        }
        for i in inputs.green_premium_qualifying_routes:
            if i in inputs.routes:
                for t in inputs.years:
                    premium = inputs.green_premium_usd_per_t.get(t, 0.0)
                    if premium > 0.0:
                        # Premium is revenue (negative cost in minimization)
                        c[index.idx("ACT", i, t)] -= df[t] * premium

    return c, meta
