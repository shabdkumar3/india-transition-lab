"""
M1 OLS Log-Log Wright's Law Estimator (Step 12).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import scipy.stats as stats

from steel_model.ml.m1_spec import (
    MIN_OBSERVATIONS_FOR_FIT,
    MIN_TIME_SPAN_YEARS,
    M1Output,
    M1Provenance,
    M1Segment,
)


def fit_m1_estimator(df: pd.DataFrame, segment: M1Segment) -> M1Output:
    """Fit OLS log-log Wright's Law regression on electrolyser cost vs capacity.

    ln(Cost_t) = alpha - b_elec * ln(CumCap_t) + epsilon_t
    """
    # 1. Filter segment
    if segment == M1Segment.ALKALINE:
        sub = df[df["technology_type"].str.lower() == "alkaline"].copy()
    elif segment == M1Segment.PEM:
        sub = df[df["technology_type"].str.lower() == "pem"].copy()
    elif segment == M1Segment.POOLED_WITH_INDICATOR:
        sub = df[df["technology_type"].str.lower().isin(["alkaline", "pem"])].copy()
    else:
        raise ValueError(f"Unknown segment: {segment}")

    n_obs = len(sub)
    if n_obs < MIN_OBSERVATIONS_FOR_FIT:
        raise ValueError(
            f"Insufficient observations: got {n_obs}, min required {MIN_OBSERVATIONS_FOR_FIT}"
        )

    years = sub["year"].unique()
    span = max(years) - min(years)
    if span < MIN_TIME_SPAN_YEARS:
        raise ValueError(
            f"Insufficient time span: got {span} years, min required {MIN_TIME_SPAN_YEARS}"
        )

    # Sort chronologically to prevent temporal validation leakage
    sub = sub.sort_values("year").reset_index(drop=True)

    y = np.log(sub["cost_usd_per_kwe"].values)
    x = np.log(sub["cumulative_capacity_gw"].values)

    # 2. Fit OLS model
    if segment in (M1Segment.ALKALINE, M1Segment.PEM):
        X = np.column_stack([np.ones(len(x)), x])
        coefs = np.linalg.solve(X.T @ X, X.T @ y)
        alpha, beta = coefs[0], coefs[1]

        y_pred = alpha + beta * x
        residuals = y - y_pred
        rss = np.sum(residuals ** 2)
        df_error = n_obs - 2
        s2 = rss / df_error

        x_mean = np.mean(x)
        x_var_sum = np.sum((x - x_mean) ** 2)
        se_beta = np.sqrt(s2 / x_var_sum)

        t_crit = stats.t.ppf(0.975, df=df_error)
        b_elec = -beta
        b_min = b_elec - t_crit * se_beta
        b_max = b_elec + t_crit * se_beta

    else:
        # Pooled indicator: y = alpha_0 + alpha_1 * PEM + beta * x
        is_pem = (sub["technology_type"].str.lower() == "pem").astype(float).values
        X = np.column_stack([np.ones(len(x)), is_pem, x])
        coefs = np.linalg.solve(X.T @ X, X.T @ y)
        alpha_0, alpha_1, beta = coefs[0], coefs[1], coefs[2]

        y_pred = alpha_0 + alpha_1 * is_pem + beta * x
        residuals = y - y_pred
        rss = np.sum(residuals ** 2)
        df_error = n_obs - 3
        s2 = rss / df_error

        cov_matrix = np.linalg.inv(X.T @ X) * s2
        se_beta = np.sqrt(cov_matrix[2, 2])

        t_crit = stats.t.ppf(0.975, df=df_error)
        b_elec = -beta
        b_min = b_elec - t_crit * se_beta
        b_max = b_elec + t_crit * se_beta

    # 3. Temporal Walk-Forward Validation
    errors = []
    # Start walk-forward after 10 observations to allow model to initialize
    for t_idx in range(10, n_obs):
        train_sub = sub.iloc[:t_idx]
        test_sub = sub.iloc[t_idx : t_idx + 1]

        train_y = np.log(train_sub["cost_usd_per_kwe"].values)
        train_x = np.log(train_sub["cumulative_capacity_gw"].values)

        if segment in (M1Segment.ALKALINE, M1Segment.PEM):
            X_tr = np.column_stack([np.ones(len(train_x)), train_x])
            coefs_tr = np.linalg.solve(X_tr.T @ X_tr, X_tr.T @ train_y)
            pred_y = coefs_tr[0] + coefs_tr[1] * np.log(
                test_sub["cumulative_capacity_gw"].values[0]
            )
        else:
            train_is_pem = (
                (train_sub["technology_type"].str.lower() == "pem")
                .astype(float)
                .values
            )
            X_tr = np.column_stack([np.ones(len(train_x)), train_is_pem, train_x])
            coefs_tr = np.linalg.solve(X_tr.T @ X_tr, X_tr.T @ train_y)
            test_is_pem = float(
                test_sub["technology_type"].str.lower().values[0] == "pem"
            )
            pred_y = (
                coefs_tr[0]
                + coefs_tr[1] * test_is_pem
                + coefs_tr[2] * np.log(test_sub["cumulative_capacity_gw"].values[0])
            )

        actual_y = np.log(test_sub["cost_usd_per_kwe"].values[0])
        errors.append(actual_y - pred_y)

    errors = np.array(errors)
    wf_rmse_log = np.sqrt(np.mean(errors ** 2)) if len(errors) > 0 else 0.0
    wf_mae_log = np.mean(np.abs(errors)) if len(errors) > 0 else 0.0

    # 4. Diagnostics & R-squared
    y_mean = np.mean(y)
    tss = np.sum((y - y_mean) ** 2)
    r2 = 1.0 - (rss / tss) if tss > 0.0 else 0.0

    source_ids = list(sub["source_id"].unique())
    time_span = f"{min(sub['year'])}-{max(sub['year'])}"

    return M1Output(
        b_elec=b_elec,
        LR_elec=1.0 - 2.0 ** (-b_elec),
        uncertainty_interval=(b_min, b_max),
        provenance=M1Provenance.GLOBAL_STATISTICAL_ESTIMATE_APPLIED_TO_INDIA_SCENARIO,
        source_ids=source_ids,
        n_observations=n_obs,
        time_span=time_span,
        segment=segment,
        model_form="OLS log-log (Wright's law)",
        currency_basis="2019 USD",
        validation_metrics={
            "r2": float(r2),
            "walk_forward_rmse_log": float(wf_rmse_log),
            "walk_forward_mae_log": float(wf_mae_log),
            "rss": float(rss),
        },
        mode="MODE_B",
    )
