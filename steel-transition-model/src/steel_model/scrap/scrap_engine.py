"""
Scrap engine for the Step 9 dynamic scrap circularity module.

Implements the frozen stock-flow formulation (MODEL_FORMULATION §6):

    EOLScrapGen_t = Σ_{τ<2024} HistProd_τ · ω(t-τ)
                  + Σ_{τ=2024}^{t-1} TotalModelProduction_τ · ω(t-τ)

    CollectedScrap_t  = EOLScrapGen_t × CollectionRate_t
    UsableScrap_t     = CollectedScrap_t × ProcessingYield_t
    RES_scrap,t ≤ UsableScrap_t + ScrapImports_t     (MILP constraint row)

The model-cohort term is LINEAR in past ACT variables, so the scrap
balance enters the MILP as ordinary linear constraint rows
(feedback through equations, never by forcing future shares — Step 9 §10).

The convolution is implemented with precomputed numpy weight matrices
(cohort-lagged EOL vectors), not nested Python loops (Step 9 §13).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from steel_model.scrap.cohort import HistoricalCohortSet
from steel_model.scrap.collection import CollectionProcessing
from steel_model.scrap.lifetime import LifetimeKernel
from steel_model.scrap.validators import require_provenance


@dataclass
class ScrapAccounting:
    """Post-solve scrap balance reporting (Step 9 §20-§21)."""

    years: List[int] = field(default_factory=list)
    eol_generation_mt: Dict[int, float] = field(default_factory=dict)
    eol_historical_mt: Dict[int, float] = field(default_factory=dict)
    eol_model_mt: Dict[int, float] = field(default_factory=dict)
    collected_scrap_mt: Dict[int, float] = field(default_factory=dict)
    usable_scrap_mt: Dict[int, float] = field(default_factory=dict)
    scrap_use_mt: Dict[int, float] = field(default_factory=dict)
    scrap_imports_mt: Dict[int, float] = field(default_factory=dict)
    scrap_constraint_slack_mt: Dict[int, float] = field(default_factory=dict)
    in_use_stock_mt: Dict[int, float] = field(default_factory=dict)
    collection_loss_mt: Dict[int, float] = field(default_factory=dict)
    processing_loss_mt: Dict[int, float] = field(default_factory=dict)
    provenance: Dict[str, str] = field(default_factory=dict)
    data_gaps: List[str] = field(default_factory=list)
    imports_included: bool = False

    def scrap_balance_holds(self, tol: float = 1e-6) -> bool:
        """Usable + imports - use = slack >= -tol in every year."""
        return all(
            self.scrap_constraint_slack_mt.get(t, 0.0) >= -tol for t in self.years
        )


class ScrapEngine:
    """
    Deterministic stock-flow scrap model for one horizon.

    Holds the historical cohort set, lifetime kernel, collection /
    processing chain and (optional) import allowance, and provides both
    the MILP constraint coefficients and the post-solve accounting.
    """

    def __init__(
        self,
        cohorts: HistoricalCohortSet,
        kernel: LifetimeKernel,
        collection: CollectionProcessing,
        model_years: List[int],
        start_year: int,
        scrap_imports_mt: Optional[Dict[int, float]] = None,
        imports_provenance: str = "",
        historical_scrap_supplement_mt: Optional[Dict[int, float]] = None,
        supplement_provenance: str = "",
    ) -> None:
        self.cohorts = cohorts
        self.kernel = kernel
        self.collection = collection
        self.model_years = list(model_years)
        self.start_year = start_year
        self.scrap_imports_mt = scrap_imports_mt or {t: 0.0 for t in model_years}
        self.imports_provenance = imports_provenance
        # Supplement: usable scrap from pre-model historical production years
        # whose cohort data is EXTERNAL_PENDING (typically 1990-2020 in this
        # project). Added to constraint_rhs alongside imports and modelled EOL.
        # Must be piecewise-linearly interpolated from anchor_years_mt in the
        # config before being passed here — each year in model_years is keyed.
        self.historical_scrap_supplement_mt = (
            historical_scrap_supplement_mt or {t: 0.0 for t in model_years}
        )
        self.supplement_provenance = supplement_provenance
        self._validate()

    # ------------------------------------------------------------------
    # Construction from config
    # ------------------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        cfg: dict,
        model_years: List[int],
        start_year: int,
    ) -> "ScrapEngine":
        require_provenance(cfg, "dynamic_scrap")
        cohorts = HistoricalCohortSet.from_config(
            cfg.get("historical_cohorts", {}), model_start_year=start_year
        )
        kernel = LifetimeKernel.from_config(cfg.get("lifetime", {}))
        collection = CollectionProcessing.from_config(
            cfg.get("collection", {}), model_years
        )

        # Scrap import allowance. The config MUST explicitly declare the
        # allowance and its provenance (never hard-coded inside code): a
        # missing scrap_imports block fails loudly, and an explicit zero
        # value means imports are excluded from this version (documented,
        # never assumed).
        if "scrap_imports" not in cfg or not cfg["scrap_imports"]:
            raise ValueError(
                "dynamic_scrap.scrap_imports is missing: the config must "
                "explicitly declare the import allowance and its provenance "
                "(zero = imports excluded from this version)."
            )
        imports_cfg = cfg["scrap_imports"]
        require_provenance(imports_cfg, "scrap_imports")
        imports_provenance = str(imports_cfg.get("provenance"))
        imports: Dict[int, float] = {t: 0.0 for t in model_years}
        raw = imports_cfg.get("value")
        if isinstance(raw, dict):
            for k, v in raw.items():
                imports[int(k)] = float(v)
        elif raw is not None:
            imports = {t: float(raw) for t in model_years}

        # Historical scrap supplement (optional): usable scrap from
        # 1990-2020 production cohorts that are EXTERNAL_PENDING in the
        # cohort model. Provided as anchor_years_mt with piecewise-linear
        # interpolation; zero = supplement disabled (no data gap compensation).
        supplement_cfg = cfg.get("historical_scrap_supplement", {})
        supplement_provenance = ""
        supplement: Dict[int, float] = {t: 0.0 for t in model_years}
        if supplement_cfg:
            require_provenance(supplement_cfg, "historical_scrap_supplement")
            supplement_provenance = str(supplement_cfg["provenance"])
            anchors_raw = supplement_cfg.get("anchor_years_mt", {})
            anchors = {int(k): float(v) for k, v in anchors_raw.items()}
            if anchors:
                sorted_yrs = sorted(anchors)
                for t in model_years:
                    if t in anchors:
                        supplement[t] = anchors[t]
                    elif t < sorted_yrs[0]:
                        supplement[t] = anchors[sorted_yrs[0]]
                    elif t > sorted_yrs[-1]:
                        supplement[t] = anchors[sorted_yrs[-1]]
                    else:
                        for lo, hi in zip(sorted_yrs, sorted_yrs[1:]):
                            if lo <= t <= hi:
                                span = hi - lo
                                frac = (t - lo) / span if span > 0 else 0.0
                                supplement[t] = anchors[lo] + frac * (anchors[hi] - anchors[lo])
                                break

        return cls(
            cohorts=cohorts,
            kernel=kernel,
            collection=collection,
            model_years=model_years,
            start_year=start_year,
            scrap_imports_mt=imports,
            imports_provenance=imports_provenance,
            historical_scrap_supplement_mt=supplement,
            supplement_provenance=supplement_provenance,
        )

    def _validate(self) -> None:
        # Model-cohort double counting guard: model years and historical
        # years must be disjoint (enforced by HistoricalCohortSet already,
        # re-checked here for construction-time safety).
        overlap = set(self.cohorts.cohorts.keys()) & set(self.model_years)
        if overlap:
            raise ValueError(
                f"Cohort years {sorted(overlap)} overlap the model horizon: "
                "a production year can be historical OR modelled, never both."
            )

    # ------------------------------------------------------------------
    # Lifetime kernel access
    # ------------------------------------------------------------------

    def omega(self, age: float) -> float:
        return self.kernel.weight(age)

    def usable_factor(self, year: int) -> float:
        return self.collection.usable_factor(year)

    def imports_mt(self, year: int) -> float:
        return float(self.scrap_imports_mt.get(year, 0.0))

    # ------------------------------------------------------------------
    # Historical EOL (fixed contribution, precomputable)
    # ------------------------------------------------------------------

    def historical_eol_series(self, years: Optional[List[int]] = None) -> Dict[int, float]:
        years = years or self.model_years
        hist_years = self.cohorts.available_years()
        if not hist_years:
            return {t: 0.0 for t in years}
        hist_prod = np.array(
            [self.cohorts.production_mt(y) for y in hist_years], dtype=float
        )
        # W[t, j] = omega(t - tau_j); cohort EOL contribution only for
        # ages >= 0; omega(0) = 0 so same-year EOL is excluded by kernel.
        age_matrix = np.subtract.outer(
            np.array(years, dtype=float), np.array(hist_years, dtype=float)
        )
        weights = self.kernel.weights_for_ages(age_matrix)
        eol = weights @ hist_prod
        return {t: float(v) for t, v in zip(years, eol)}

    def historical_eol_mt(self, year: int) -> float:
        return self.historical_eol_series([year])[year]

    # ------------------------------------------------------------------
    # MILP constraint coefficients
    # ------------------------------------------------------------------

    def feedback_coefficient(self, year: int, cohort_year: int) -> float:
        """
        Coefficient of ACT[., cohort_year] in the scrap balance row of
        `year`: -CR_year * PY_year * omega(year - cohort_year).

        Only cohort_year < year (current-year production is never part of
        its own EOL; omega(0) = 0 anyway).
        """
        if cohort_year >= year:
            return 0.0
        return self.usable_factor(year) * self.omega(year - cohort_year)

    def supplement_mt(self, year: int) -> float:
        """Usable scrap supplement from pre-model cohort years (EXTERNAL_PENDING)."""
        return float(self.historical_scrap_supplement_mt.get(year, 0.0))

    def constraint_rhs(self, year: int) -> float:
        """
        Right-hand side of the scrap balance row for `year`:
        CR*PY*HistEOL_t + ScrapImports_t + HistoricalSupplement_t
        """
        return (
            self.usable_factor(year) * self.historical_eol_mt(year)
            + self.imports_mt(year)
            + self.supplement_mt(year)
        )

    def scrap_balance_rows(self, years, routes) -> List[dict]:
        """
        Precomputed row templates for the MILP (keys are (block,item,year)).

        Each row enforces:
            RES_scrap,t - Σ_{τ<t} Σ_i CR_t*PY_t*ω(t-τ)*ACT_i,τ
                <= CR_t*PY_t*HistEOL_t + Imports_t
        """
        rows = []
        for t in years:
            coeffs: Dict[tuple, float] = {("RES", "scrap", t): 1.0}
            for tau in years:
                if tau >= t:
                    continue
                w = self.feedback_coefficient(t, tau)
                if w == 0.0:
                    continue
                for i in routes:
                    coeffs[("ACT", i, tau)] = coeffs.get(("ACT", i, tau), 0.0) - w
            rows.append(
                {
                    "year": t,
                    "lb": -np.inf,
                    "ub": self.constraint_rhs(t),
                    "coeffs": coeffs,
                }
            )
        return rows

    # ------------------------------------------------------------------
    # Post-solve accounting
    # ------------------------------------------------------------------

    def account(
        self,
        act_mt_by_route: Dict[str, Dict[int, float]],
        res_scrap_use: Dict[int, float],
        years: Optional[List[int]] = None,
    ) -> ScrapAccounting:
        years = years or self.model_years
        total_prod = {
            t: sum(act_mt_by_route.get(i, {}).get(t, 0.0) for i in act_mt_by_route)
            for t in years
        }
        hist_eol = self.historical_eol_series(years)

        # Model cohort EOL: lagged convolution over past model years only.
        # Vectorised via a (years x cohorts) weight matrix; cohort tau
        # contributes only to years t > tau (current-year production is
        # never part of its own EOL — omega(0) = 0 as well).
        model_eol = {t: 0.0 for t in years}
        t_arr = np.array(years, dtype=float)
        tau_arr = np.array(years, dtype=float)
        age_matrix = t_arr[:, None] - tau_arr[None, :]      # [years x years]
        weight_matrix = self.kernel.weights_for_ages(age_matrix)
        prod_matrix = np.array([total_prod[tau] for tau in years], dtype=float)
        contrib = np.where(age_matrix > 0.0, weight_matrix * prod_matrix[None, :], 0.0)
        model_eol_arr = contrib.sum(axis=1)
        for idx, t in enumerate(years):
            model_eol[t] = float(model_eol_arr[idx])

        eol = {t: hist_eol[t] + model_eol[t] for t in years}
        collected = {t: self.collection.rate(t) * eol[t] for t in years}
        usable = {t: self.collection.yield_value(t) * collected[t] for t in years}
        use = {t: res_scrap_use.get(t, 0.0) for t in years}
        imports = {t: self.imports_mt(t) for t in years}
        # Include historical scrap supplement in supply (matches MILP constraint RHS)
        supplement = self.historical_scrap_supplement_mt or {t: 0.0 for t in years}
        effective_supply = {t: usable[t] + imports[t] + supplement.get(t, 0.0) for t in years}
        slack = {t: effective_supply[t] - use[t] for t in years}

        # In-use steel stock: cumulative production entering use minus
        # cumulative EOL. Only AVAILABLE historical cohorts are counted
        # (missing years are EXTERNAL_PENDING -> lower-bound stock).
        stock: Dict[int, float] = {}
        running = 0.0
        hist_by_year = self.cohorts.production_series()
        for t in years:
            entering = total_prod[t] + hist_by_year.get(t, 0.0)
            running += entering - eol[t]
            stock[t] = running

        data_gaps = [
            f"Historical production missing (EXTERNAL_PENDING, zero EOL "
            f"contribution, no fabrication): {self.cohorts.missing_years()[:10]}{'...' if len(self.cohorts.missing_years()) > 10 else ''}",
        ]
        if not self.cohorts.available_years():
            data_gaps.append(
                "No historical cohorts available: EOL from post-2024 model "
                "production only (Step 9 §14 Test 4 regime)."
            )

        provenance = {
            "historical_cohorts": "; ".join(
                sorted(
                    {
                        f"{y}:{p}"
                        for y, p in self.cohorts.provenance_summary().items()
                    }
                )
            )
            or "NONE (no available historical cohorts)",
            "lifetime": f"{self.kernel.distribution} "
            f"(shape={self.kernel.shape}, scale={self.kernel.scale}, "
            f"lifetime_years={self.kernel.lifetime_years}) "
            f"[{self.kernel.provenance}]",
            "collection_rate": self.collection.collection_provenance,
            "processing_yield": self.collection.yield_provenance,
            "scrap_imports": self.imports_provenance,
        }

        return ScrapAccounting(
            years=list(years),
            eol_generation_mt=eol,
            eol_historical_mt=hist_eol,
            eol_model_mt=model_eol,
            collected_scrap_mt=collected,
            usable_scrap_mt=usable,
            scrap_use_mt=use,
            scrap_imports_mt=imports,
            scrap_constraint_slack_mt=slack,
            in_use_stock_mt=stock,
            collection_loss_mt={t: eol[t] - collected[t] for t in years},
            processing_loss_mt={t: collected[t] - usable[t] for t in years},
            provenance=provenance,
            data_gaps=data_gaps,
            imports_included=any(v > 0 for v in imports.values()),
        )
