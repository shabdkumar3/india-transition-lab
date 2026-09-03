"""
Optional S-Curve diagnostic module calibrating logistic saturation model against Vol. 4 anchor points.
"""

from typing import Dict, Any, Tuple
import numpy as np
from .demand_types import DemandDataset


class SCurveDiagnostic:
    """
    Diagnostic module implementing Vol. 4 logistic S-curve methodology.
    This module is strictly diagnostic and NEVER overwrites the baseline demand dataset.

    Source Note: Vol. 4 p. 64 reports 'saturation around 450 kg/capita'.
    This 450 kg/capita refers to apparent FINISHED steel consumption per capita.
    Crude steel production (821 Mt in 2070) includes yield losses (~11.2%).
    Converting 821 Mt crude steel via crude-to-finished yield (~0.88) yields ~447 kg finished steel/capita.
    """

    SOURCE_REPORTED_FINISHED_SATURATION: float = 450.0  # kg finished steel / capita (Vol. 4 p. 64)
    DEFAULT_CRUDE_TO_FINISHED_YIELD: float = 0.88       # Yield conversion factor [PROJECT PROPOSAL]
    PROJECT_DIAGNOSTIC_CRUDE_SATURATION: float = 550.0   # Crude steel saturation ceiling

    # Default Population (Millions) from Vol. 4 Annex I
    DEFAULT_POPULATION: Dict[int, float] = {
        2024: 1411.0,  # 2025 value (1411M) as proxy for 2024 baseline
        2050: 1596.0,  # 2050 milestone
        2070: 1616.0,  # Interpolated 2070 population [DERIVED]
        2075: 1621.0,  # 2075 milestone
    }

    # Default GDP per capita trajectory (PPP constant 2021 int USD)
    DEFAULT_GDP_PER_CAPITA: Dict[int, float] = {
        2024: 9000.0,
        2050: 38000.0,
        2070: 75000.0,
    }

    @classmethod
    def fit_calibration(
        cls,
        anchor_demand: Dict[int, float],
        population: Dict[int, float] = DEFAULT_POPULATION,
        gdp_per_capita: Dict[int, float] = DEFAULT_GDP_PER_CAPITA,
        use_finished_steel_yield: bool = True,
        custom_saturation: float = None,
    ) -> Tuple[float, float, Dict[str, Any]]:
        """
        Fit logistic regression parameters a and b on anchor points:
        ln(S_t / (S_o - S_t)) = a * ln(GDP_per_capita_t) + b
        Returns (a, b, diagnostic_metrics).
        """
        years = sorted(list(anchor_demand.keys()))
        ln_gdp = []
        logit_s = []
        published_s = []

        if custom_saturation is not None:
            S_o = custom_saturation
            is_finished = False
        elif use_finished_steel_yield:
            S_o = cls.SOURCE_REPORTED_FINISHED_SATURATION
            is_finished = True
        else:
            S_o = cls.PROJECT_DIAGNOSTIC_CRUDE_SATURATION
            is_finished = False

        yield_factor = cls.DEFAULT_CRUDE_TO_FINISHED_YIELD if is_finished else 1.0

        for y in years:
            crude_demand_mt = anchor_demand[y]
            pop_m = population[y]
            gdp_cap = gdp_per_capita[y]

            # Convert Mt demand to kg/capita (finished or crude depending on yield_factor)
            s_t = (crude_demand_mt * yield_factor * 1e9) / (pop_m * 1e6)
            published_s.append(s_t)

            if s_t >= S_o:
                raise ValueError(
                    f"Per capita steel demand {s_t:.2f} kg/capita exceeds saturation limit {S_o} kg/capita in year {y}. "
                    f"Note: Vol. 4's 450 kg/capita saturation refers to FINISHED steel consumption (enable use_finished_steel_yield=True)."
                )

            logit_val = np.log(s_t / (S_o - s_t))
            logit_s.append(logit_val)
            ln_gdp.append(np.log(gdp_cap))

        x = np.array(ln_gdp)
        y_val = np.array(logit_s)

        # Linear regression: y_val = a * x + b
        A = np.vstack([x, np.ones(len(x))]).T
        a_param, b_param = np.linalg.lstsq(A, y_val, rcond=None)[0]

        # Calculate reconstructed crude demand at anchor years
        reconstructed_mt = {}
        residuals = {}

        for y in years:
            gdp_cap = gdp_per_capita[y]
            pop_m = population[y]

            logit_pred = a_param * np.log(gdp_cap) + b_param
            s_pred = S_o * np.exp(logit_pred) / (1 + np.exp(logit_pred))

            # Convert finished steel back to crude steel Mt
            pred_crude_mt = (s_pred * pop_m * 1e6) / (yield_factor * 1e9)
            reconstructed_mt[y] = float(pred_crude_mt)
            residuals[y] = float(pred_crude_mt - anchor_demand[y])

        # R-squared fit quality
        ss_res = sum(r**2 for r in residuals.values())
        published_mt_vals = list(anchor_demand.values())
        mean_mt = np.mean(published_mt_vals)
        ss_tot = sum((val - mean_mt)**2 for val in published_mt_vals)
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0

        metrics = {
            "a_parameter": float(a_param),
            "b_parameter": float(b_param),
            "saturation_limit_used": float(S_o),
            "is_finished_steel_basis": is_finished,
            "yield_factor_used": float(yield_factor),
            "reconstructed_demand_mt": reconstructed_mt,
            "residuals_mt": residuals,
            "r_squared": float(r_squared),
            "provenance": "DERIVED_DIAGNOSTIC",
        }

        return float(a_param), float(b_param), metrics

    @classmethod
    def run_diagnostic(cls, dataset: DemandDataset, scenario: str = "CPS") -> Dict[str, Any]:
        """Run diagnostic assessment on loaded dataset for a given scenario."""
        anchor_dict = dataset.to_dict_map(scenario=scenario)
        a, b, metrics = cls.fit_calibration(anchor_dict, use_finished_steel_yield=True)
        return metrics
