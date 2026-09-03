"""
Constraint builder for the baseline multi-period MILP (Step 8).

All constraints are expressed as flat dense rows over the variable vector
laid out by ``VariableIndex``. Every scientific quantity comes from the
``BaselineInputs`` object (loaded from config/registry); no hard-coded
values live in this module.

Constraint families
-------------------
1. Demand balance       sum_i ACT[i,t] = Demand_t                       (equality)
2. Capacity-activity    ACT[i,t] - avail_i * CAP[i,t] <= 0              (inequality)
3. Capacity evolution   CAP[i,t] = SurvivingExisting[i,t]
                                 + CumNCAP[i,t] - CumRET[i,t]           (equality)
4. Retirement vintage   CumRET[i,t] <= CumNCAP[i, t - lifetime]         (inequality)
5. Resource accounting  RES[r,t] = sum_i ACT[i,t] * Intensity[i,r,t]    (equality)
6. Emissions            CO2[t] = sum_i ACT[i,t] * (Proc[i] + Comb[i])   (equality)
7. Scrap balance (Step 9, MODE B only):
     RES_scrap,t - sum_{tau<t} sum_i CR_t*PY_t*omega(t-tau)*ACT[i,tau]
         <= CR_t*PY_t*HistEOL_t + ScrapImports_t                        (inequality)
     Present only when dynamic_scrap is enabled (inputs.scrap_engine).
     Linear in ACT; feedback through equations (Step 9 §10).

Notes
-----
- Route activity is structurally blocked before a route's start year by
  the variable bounds (NCAP ub = 0 for t < start_year, built in
  ``variables.build_bounds``); no extra constraint row is required.
- Resource intensity coefficients that are EXTERNAL_PENDING (None in the
  registry) enter as 0.0. This is a DATA AVAILABILITY LIMITATION, not an
  optimization conclusion (documented in BASELINE_DATA_LIMITATIONS.md).
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np

from steel_model.optimization.variables import VariableIndex


def _idx(index: VariableIndex, block: str, item: str, year: int) -> int:
    return index.idx(block, item, year)


def build_constraints(
    index: VariableIndex,
    inputs: "BaselineInputs",
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Build the full constraint matrix.

    Returns (A, lb, ub) such that every row satisfies lb <= A_row @ x <= ub.
    A has shape (n_rows, n_vars); lb/ub have length n_rows.
    """
    n_vars = index.n_vars()
    rows: List[Tuple[float, float, dict]] = []  # (lb, ub, {col: coeff})

    routes = inputs.routes
    years = inputs.years
    resources = inputs.resources

    # ------------------------------------------------------------------
    # 1. Demand balance: sum_i ACT[i,t] = Demand_t
    # ------------------------------------------------------------------
    for t in years:
        row: dict = {}
        for i in routes:
            row[_idx(index, "ACT", i, t)] = 1.0
        rows.append((inputs.demand_mt[t], inputs.demand_mt[t], row))

    # ------------------------------------------------------------------
    # 2. Capacity-activity: ACT[i,t] - AvailabilityFactor[i] * CAP[i,t] <= 0
    # ------------------------------------------------------------------
    # AvailabilityFactor is the PHYSICAL OPERATING LIMIT of the plant: it
    # bounds how much steel can be produced from installed capacity. The
    # 80% PLF is ONLY an INVESTMENT-SIZING CONVENTION (cost-scaling
    # parameter used when converting production to capacity for cost
    # accounting) — these two concepts must NEVER be conflated. The
    # baseline uses the configured availability value as the physical
    # bound only; the 0.80 PLF is not applied anywhere in the physics.
    for i in routes:
        for t in years:
            row = {
                _idx(index, "ACT", i, t): 1.0,
                _idx(index, "CAP", i, t): -inputs.availability[i],
            }
            rows.append((-np.inf, 0.0, row))

    # ------------------------------------------------------------------
    # 3. Capacity evolution with construction lead time (Step 21B):
    #    CAP[i,t] = Existing + CumNCAP[i, t-L] - CumRET[i,t]
    #
    # Investment decision at year s only contributes to CAP from year s+L
    # (construction lag). When construction_lead_time_active is False or
    # lead_time_years[i] == 0, this collapses to the original formulation.
    # RET is allowed from any modelled year (not delayed by lead time).
    # ------------------------------------------------------------------
    for i in routes:
        existing = inputs.existing_capacity_per_route_mt.get(i, 0.0)
        lead = inputs.construction_lead_time_years.get(i, 0) if inputs.construction_lead_time_active else 0
        for t in years:
            row: dict = {_idx(index, "CAP", i, t): 1.0}
            for s in years:
                if s <= t - lead:
                    # NCAP at s contributes to capacity only after lead_time years
                    row[_idx(index, "NCAP", i, s)] = row.get(_idx(index, "NCAP", i, s), 0.0) - 1.0
                if s <= t:
                    row[_idx(index, "RET", i, s)] = row.get(_idx(index, "RET", i, s), 0.0) + 1.0
            # SurvivingExisting is treated as a constant per-route value
            # (technology-wise vintages unavailable -> documented limitation).
            rows.append((existing, existing, row))

    # ------------------------------------------------------------------
    # 4. Retirement vintage: CumRET[i,t] <= CumNCAP[i, t - lifetime]
    #    (can only retire capacity commissioned >= lifetime years ago)
    # ------------------------------------------------------------------
    lifetime = inputs.lifetime_years
    for i in routes:
        for t in years:
            row: dict = {}
            for s in years:
                if s <= t:
                    row[_idx(index, "RET", i, s)] = row.get(_idx(index, "RET", i, s), 0.0) + 1.0
                if s <= t - lifetime:
                    row[_idx(index, "NCAP", i, s)] = row.get(_idx(index, "NCAP", i, s), 0.0) - 1.0
            rows.append((-np.inf, 0.0, row))

    # ------------------------------------------------------------------
    # 5. Resource accounting: RES[r,t] = sum_i ACT[i,t] * Intensity[i,r,t]
    # Step 24: SEC improvement applies to fuel resources (coal, gas, electricity).
    # Material resources (iron_ore, scrap, hydrogen) are excluded — these have
    # separate stoichiometric / supply drivers not linked to energy efficiency.
    # ------------------------------------------------------------------
    _FUEL_RESOURCES = frozenset({
        "coal", "non_coking_coal", "coking_coal", "natural_gas",
        "electricity_route", "electricity",
    })
    for r in resources:
        for t in years:
            row: dict = {_idx(index, "RES", r, t): 1.0}
            sec_factor = (
                inputs.sec_improvement_factor_by_year.get(t, 0.0)
                if inputs.sec_improvement_factor_by_year and r in _FUEL_RESOURCES
                else 0.0
            )
            sec_mult = 1.0 - sec_factor
            for i in routes:
                coeff = (inputs.resource_intensity.get((i, r), 0.0) or 0.0) * sec_mult
                if coeff != 0.0:
                    row[_idx(index, "ACT", i, t)] = row.get(_idx(index, "ACT", i, t), 0.0) - coeff
            rows.append((0.0, 0.0, row))

    # ------------------------------------------------------------------
    # 6. Emissions: CO2[t] = sum_i ACT[i,t] * (Proc[i] + Comb[i] + GridElec[i,t])
    #
    # Step 21A: When grid_emission_enabled, each route's electricity
    # consumption (ACT * elec_intensity) adds indirect grid CO₂:
    #   GridElec[i,t] = resource_intensity[i, "electricity_route"] * grid_ei[t]
    # This prevents H₂-DRI-EAF / Scrap-EAF from appearing zero-carbon
    # while India's electricity grid remains coal-heavy.
    # ------------------------------------------------------------------
    for t in years:
        row: dict = {_idx(index, "CO2", "", t): 1.0}
        grid_ei = inputs.grid_ei_tco2_per_mwh.get(t, 0.0) if inputs.grid_emission_enabled else 0.0
        # Step 24: SEC improvement reduces fuel-derived combustion CO2 (not stoichiometric process CO2)
        sec_factor = (
            inputs.sec_improvement_factor_by_year.get(t, 0.0)
            if inputs.sec_improvement_factor_by_year
            else 0.0
        )
        for i in routes:
            # Process emissions: stoichiometric (limestone, ore reduction) — NOT improved by SEC
            # Combustion emissions: from fuel burning — improved by SEC (less fuel = less CO2)
            comb_em_scaled = inputs.combustion_emission[i] * (1.0 - sec_factor)
            base_direct = inputs.process_emission[i] + comb_em_scaled
            # Step 22B: CCUS capture — reduce direct emission by capture fraction
            ccus_fraction = 0.0
            if getattr(inputs, "ccus_enabled", False):
                ccus_fraction = (
                    inputs.ccus_capture_fraction_by_route_year.get(i, {}).get(t, 0.0)
                )
            direct_coeff = base_direct * (1.0 - ccus_fraction)
            # Indirect grid-electricity emission (Step 21A) — also SEC-scaled
            elec_intensity = (inputs.resource_intensity.get((i, "electricity_route"), 0.0) or 0.0) * (1.0 - sec_factor)
            grid_coeff = elec_intensity * grid_ei
            total_coeff = direct_coeff + grid_coeff
            if total_coeff != 0.0:
                row[_idx(index, "ACT", i, t)] = row.get(_idx(index, "ACT", i, t), 0.0) - total_coeff
        rows.append((0.0, 0.0, row))

    # ------------------------------------------------------------------
    # 7. Scrap balance (Step 9, MODE B only):
    #    RES_scrap,t - sum_{tau<t} sum_i CR_t*PY_t*omega(t-tau)*ACT[i,tau]
    #        <= CR_t*PY_t*HistEOL_t + ScrapImports_t
    # ------------------------------------------------------------------
    # This is the linearised "ScrapUse_t <= UsableDomesticScrap_t +
    # Imports_t" constraint. The feedback (more production today -> more
    # EOL scrap -> more usable scrap -> greater future Scrap-EAF
    # potential) enters purely through the coefficients on PAST ACT
    # variables — never by forcing future route shares (Step 9 §10).
    # Current-year production is excluded from its own EOL by the
    # tau < t sum (and omega(0) = 0 by the lifetime kernel anyway).
    if inputs.scrap_engine is not None:
        templates = inputs.scrap_engine.scrap_balance_rows(years, routes)
        for tmpl in templates:
            row = {
                _idx(index, block, item, y): v
                for (block, item, y), v in tmpl["coeffs"].items()
            }
            rows.append((tmpl["lb"], tmpl["ub"], row))

    # ------------------------------------------------------------------
    # 8. Deployment limits (Step 10, MODE B only):
    #    NCAP[i,t] <= NCAPLimit_i
    # ------------------------------------------------------------------
    if inputs.deployment_dynamics_enabled:
        for i in routes:
            limit = inputs.ncap_limits_mt.get(i)
            if limit is not None:
                for t in years:
                    row = {_idx(index, "NCAP", i, t): 1.0}
                    rows.append((-np.inf, limit, row))

    # ------------------------------------------------------------------
    # 9. Static scrap availability cap (Mode A only):
    #    RES[scrap, t] <= StaticScrapCap_t
    #
    # In Mode A the dynamic scrap engine is OFF so nothing physically
    # bounds scrap consumption. Without a cap the optimizer freely picks
    # 100% Scrap-EAF because its capital and operating costs are cheapest
    # once the scrap-intensity coefficient is activated. This constraint
    # enforces India's physically plausible domestic scrap supply
    # trajectory (PROJECT_PROPOSAL anchor_years_mt, piecewise-linear).
    # Mode B uses the stock-flow scrap balance (constraint 7) instead
    # and must never also apply this cap.
    # ------------------------------------------------------------------
    if inputs.static_scrap_cap_mt is not None and inputs.scrap_engine is None:
        if "scrap" in resources:
            for t in years:
                cap = inputs.static_scrap_cap_mt.get(t)
                if cap is not None:
                    row = {_idx(index, "RES", "scrap", t): 1.0}
                    rows.append((-np.inf, cap, row))

    # ------------------------------------------------------------------
    # 10. H₂ supply cap (Step 20B, MODE B only):
    #     RES["hydrogen", t] <= H2SupplyCap_t
    #
    # Represents the physical limit on domestically available green H₂
    # from electrolysis capacity ramp-up (MW installed × capacity factor
    # → kt H₂/yr → Mt H₂/yr). Without this, the optimizer can commission
    # unlimited H2-DRI-EAF immediately after the route start year.
    # The cap follows an exogenous infrastructure build-out trajectory.
    # ------------------------------------------------------------------
    if inputs.h2_supply_cap_enabled and inputs.h2_supply_cap_mt is not None:
        if "hydrogen" in resources:
            for t in years:
                cap_h2 = inputs.h2_supply_cap_mt.get(t)
                if cap_h2 is not None:
                    row = {_idx(index, "RES", "hydrogen", t): 1.0}
                    rows.append((-np.inf, cap_h2, row))

    # ------------------------------------------------------------------
    # 11. Monotonic production decline for legacy routes (Step 17B extension):
    #     ACT[i, t+1] - ACT[i, t] <= 0  for t >= monotonic_decline_from[i]
    #
    # Physical rationale: integrated steel plants (BF-BOF) face substantial
    # restart costs once idled — blast furnace relining, crew demobilisation,
    # restart fuel load. Once production falls in a period it should not
    # reverse. This eliminates "utilization cycling" (model idles BF-BOF in
    # 2032, then re-uses it in 2035) which has no physical basis in India's
    # context where no BF-BOF plant has been restarted after full idle.
    #
    # Distinct from the NCAP cutoff (which prevents NEW capacity investment).
    # This constraint governs PRODUCTION from EXISTING capacity.
    # Applied only from the specified year onward (allows ramp-up phase
    # before the route peaks and begins its structural decline).
    # ------------------------------------------------------------------
    monotonic_decline = getattr(inputs, "monotonic_decline_from_years", {})
    if monotonic_decline:
        sorted_years = sorted(years)
        for i, from_year in monotonic_decline.items():
            if i not in routes:
                continue
            for idx_t, t in enumerate(sorted_years[:-1]):
                t_next = sorted_years[idx_t + 1]
                if t < from_year:
                    continue
                # ACT[i, t+1] - ACT[i, t] <= 0
                row = {
                    _idx(index, "ACT", i, t_next): 1.0,
                    _idx(index, "ACT", i, t): -1.0,
                }
                rows.append((-np.inf, 0.0, row))

    # ------------------------------------------------------------------
    # 12. Technology ramp limits (Step 22 — TIMES-style bounded optimization):
    #     NCAP[i,t] <= RampLimit_i  for all t in model years
    #
    # Prevents the MILP from commissioning more new capacity than what the
    # supply chain can physically deliver per year (electrolyser factories,
    # specialised EPC contractors, H2 pipeline co-builds). This is the core
    # TIMES mechanism that produces realistic transition pathways vs pure
    # cost-optimal overnight transitions. Applied independently of the
    # deployment_dynamics flag; these are physical bounds, not behavioural ones.
    # ------------------------------------------------------------------
    if getattr(inputs, "technology_ramp_limits_enabled", False):
        ramp_limits = getattr(inputs, "technology_ramp_limits_mt", {})
        for i, limit in ramp_limits.items():
            if i not in routes:
                continue
            for t in years:
                row = {_idx(index, "NCAP", i, t): 1.0}
                rows.append((-np.inf, limit, row))

    # ------------------------------------------------------------------
    # 13. Minimum production floor for BF-BOF / anchored routes (Step 26):
    #     ACT[i, t] >= floor_t  for each year with a specified floor.
    #
    # Physical rationale (Vol.4 CPS): BF-BOF is explicitly stated to be
    # dominant through 2050 in the CPS pathway. With stranded-asset costs
    # and economics alone, the model may prematurely retire BF-BOF when
    # Lab parameters shift costs slightly. A minimum production floor
    # encodes the Vol.4 narrative directly as a lower bound on utilisation.
    #
    # Anchor years are interpolated linearly between specified waypoints.
    # Years before the first anchor and after the last anchor are clamped
    # to the nearest specified value (flat extrapolation).
    # ------------------------------------------------------------------
    min_floor_by_route = getattr(inputs, "min_production_floor_mt", {})
    if min_floor_by_route:
        for i, anchor_years_dict in min_floor_by_route.items():
            if i not in routes or not anchor_years_dict:
                continue
            sorted_anchors = sorted((int(ay), float(av)) for ay, av in anchor_years_dict.items())
            anchor_yrs = [a[0] for a in sorted_anchors]
            anchor_vals = [a[1] for a in sorted_anchors]
            for t in years:
                # Linear interpolation between anchors; clamp at edges
                if t <= anchor_yrs[0]:
                    floor_val = anchor_vals[0]
                elif t >= anchor_yrs[-1]:
                    floor_val = anchor_vals[-1]
                else:
                    # find bracketing segment
                    for seg in range(len(anchor_yrs) - 1):
                        if anchor_yrs[seg] <= t <= anchor_yrs[seg + 1]:
                            frac = (t - anchor_yrs[seg]) / (anchor_yrs[seg + 1] - anchor_yrs[seg])
                            floor_val = anchor_vals[seg] + frac * (anchor_vals[seg + 1] - anchor_vals[seg])
                            break
                    else:
                        continue
                if floor_val <= 0.0:
                    continue
                # ACT[i, t] >= floor_val  →  lb=floor_val, ub=+inf
                row = {_idx(index, "ACT", i, t): 1.0}
                rows.append((floor_val, np.inf, row))

    # ------------------------------------------------------------------
    # Materialize
    # ------------------------------------------------------------------
    n_rows = len(rows)
    A = np.zeros((n_rows, n_vars))
    lb = np.zeros(n_rows)
    ub = np.zeros(n_rows)
    for k, (row_lb, row_ub, coeffs) in enumerate(rows):
        lb[k] = row_lb
        ub[k] = row_ub
        for col, val in coeffs.items():
            A[k, col] = val

    return A, lb, ub
