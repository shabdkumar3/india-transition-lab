"""
Compact Diagnostic Plots (Step 15 §13).

Six diagnostic plots:
1. Technology share over time (stacked area)
2. Capacity additions/retirements (bar)
3. Effective cost by technology (line)
4. Constraint pressure (heatmap or grouped bar)
5. Vol4 vs model difference (bar with status)
6. Sensitivity driver contribution (tornado)

Plots must have:
- units
- source/model status
- clear legend
- readable axis labels

Explicitly NOT giant pages of plots.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from steel_model.diagnostics.pathway_record import PathwayRecords
from steel_model.diagnostics.vol4_integration import Vol4DifferenceLink


def _save(fig, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def plot_technology_shares(
    records: PathwayRecords,
    out_path: str,
) -> None:
    """Plot 1: Technology share over time (stacked area)."""
    # Get enabled routes with data
    routes = sorted(set(r.technology for r in records.records if r.share is not None))
    years = sorted(set(r.year for r in records.records))

    fig, ax = plt.subplots(figsize=(6.0, 3.5))

    # Build share matrix
    share_matrix = np.zeros((len(routes), len(years)))
    for i, route in enumerate(routes):
        for j, year in enumerate(years):
            rec = records.get(route, year)
            if rec and rec.share is not None:
                share_matrix[i, j] = rec.share

    # Stacked area
    colors = plt.cm.Set3(np.linspace(0, 1, len(routes)))
    bottom = np.zeros(len(years))
    for i, route in enumerate(routes):
        ax.fill_between(years, bottom, bottom + share_matrix[i],
                        label=route, color=colors[i], alpha=0.8)
        bottom += share_matrix[i]

    ax.set_xlabel("Year")
    ax.set_ylabel("Share of production")
    ax.set_title("Technology Share Over Time (MODEL — DATA-LIMITED)")
    ax.legend(fontsize=7, loc="upper left", ncol=2)
    ax.grid(alpha=0.3)
    ax.set_ylim(0, 1.05)

    _save(fig, out_path)


def plot_capacity_changes(
    records: PathwayRecords,
    out_path: str,
) -> None:
    """Plot 2: Capacity additions and retirements."""
    routes = sorted(set(r.technology for r in records.records))
    years = sorted(set(r.year for r in records.records))

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.0), sharey=True)

    for idx, (block, attr, title) in enumerate([
        ("NCAP", "new_capacity_mt", "New Capacity Additions"),
        ("RET", "retired_capacity_mt", "Retirements"),
    ]):
        ax = axes[idx]
        x = np.arange(len(years))
        width = 0.15

        for i, route in enumerate(routes):
            vals = []
            for year in years:
                rec = records.get(route, year)
                val = getattr(rec, attr) if rec else None
                vals.append(val if val is not None else 0.0)

            ax.bar(x + i * width, vals, width, label=route if idx == 0 else None, alpha=0.8)

        ax.set_xticks(x)
        ax.set_xticklabels(years, fontsize=8)
        ax.set_title(title)
        ax.set_ylabel("Mt/yr" if idx == 0 else "")
        ax.grid(axis="y", alpha=0.3)

    axes[0].legend(fontsize=6, loc="upper left")
    fig.suptitle("Capacity Changes (MODEL — DATA-LIMITED)", fontsize=10)
    plt.tight_layout()

    _save(fig, out_path)


def plot_effective_costs(
    records: PathwayRecords,
    out_path: str,
) -> None:
    """Plot 3: Effective cost by technology over time."""
    routes = sorted(set(r.technology for r in records.records if r.effective_cost_usd_per_t is not None))
    years = sorted(set(r.year for r in records.records))

    fig, ax = plt.subplots(figsize=(6.0, 3.5))

    for route in routes:
        costs = []
        for year in years:
            rec = records.get(route, year)
            costs.append(rec.effective_cost_usd_per_t if rec else None)

        valid = [(y, c) for y, c in zip(years, costs) if c is not None]
        if valid:
            y_vals, c_vals = zip(*valid)
            ax.plot(y_vals, c_vals, marker="o", label=route, linewidth=1.5)

    ax.set_xlabel("Year")
    ax.set_ylabel("Effective cost (USD/t)")
    ax.set_title("Effective Cost by Technology (MODEL — DATA-LIMITED)")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)

    _save(fig, out_path)


def plot_constraint_pressures(
    records: PathwayRecords,
    out_path: str,
) -> None:
    """Plot 4: Constraint pressure heatmap."""
    # For simplicity, create a grouped bar of capacity pressure per route × year
    routes = sorted(set(r.technology for r in records.records))
    years = sorted(set(r.year for r in records.records))

    fig, ax = plt.subplots(figsize=(6.0, 3.5))

    x = np.arange(len(years))
    width = 0.15

    for i, route in enumerate(routes):
        pressures = []
        for year in years:
            rec = records.get(route, year)
            # We don't have pressure in PathwayRecord directly; would need
            # to compute from constraints module. Placeholder.
            pressures.append(0.0)

        ax.bar(x + i * width, pressures, width, label=route, alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(years, fontsize=8)
    ax.set_ylabel("Pressure (used/available)")
    ax.set_title("Constraint Pressure (PLACEHOLDER — needs constraint data)")
    ax.legend(fontsize=7)
    ax.grid(axis="y", alpha=0.3)

    _save(fig, out_path)


def plot_vol4_comparison(
    links: List[Vol4DifferenceLink],
    out_path: str,
) -> None:
    """Plot 5: Vol.4 vs model difference with status annotations."""
    # Filter to MATERIAL_DIFFERENCE and key metrics
    key_metrics = [
        "technology_share", "scrap_share_production",
        "co2_intensity", "co2_total", "green_h2_steel"
    ]

    plot_data = [l for l in links if l.metric in key_metrics and l.comparison_status in ("MATERIAL_DIFFERENCE", "NOT_COMPARABLE")]

    if not plot_data:
        fig, ax = plt.subplots(figsize=(5.0, 3.0))
        ax.text(0.5, 0.5, "No Vol.4 comparison data to plot", ha="center", va="center")
        _save(fig, out_path)
        return

    fig, ax = plt.subplots(figsize=(6.0, 3.5))

    x_labels = []
    model_vals = []
    vol4_vals = []
    colors = []

    for i, link in enumerate(plot_data):
        label = f"{link.metric[:15]}\n{link.year}{link.scenario[:3]}"
        x_labels.append(label)
        model_vals.append(link.model_value)
        vol4_vals.append(link.vol4_value)
        colors.append("#d62728" if link.comparison_status == "MATERIAL_DIFFERENCE" else "#ff7f0e")

    x = np.arange(len(x_labels))
    width = 0.35

    ax.bar(x - width/2, model_vals, width, label="Model", color="#1f77b4", alpha=0.8)
    ax.bar(x + width/2, vol4_vals, width, label="Vol.4", color="#d62728", alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, fontsize=7, rotation=30, ha="right")
    ax.set_ylabel("Value (metric-dependent units)")
    ax.set_title("Vol.4 vs Model — Key Differences")
    ax.legend(fontsize=7)
    ax.grid(axis="y", alpha=0.3)

    # Add status annotations
    for i, link in enumerate(plot_data):
        status = link.comparison_status[0]  # M, N, U
        ax.annotate(status, (i, max(model_vals[i], vol4_vals[i])),
                    textcoords="offset points", xytext=(0, 5),
                    ha="center", fontsize=8, fontweight="bold",
                    color="red" if link.comparison_status == "MATERIAL_DIFFERENCE" else "orange")

    plt.tight_layout()
    _save(fig, out_path)


def plot_sensitivity_tornado(
    sensitivity_results: Dict[str, float],
    out_path: str,
) -> None:
    """Plot 6: Sensitivity driver contribution (tornado chart)."""
    if not sensitivity_results:
        fig, ax = plt.subplots(figsize=(5.0, 3.0))
        ax.text(0.5, 0.5, "No sensitivity data", ha="center", va="center")
        _save(fig, out_path)
        return

    # Sort by absolute impact
    sorted_items = sorted(sensitivity_results.items(), key=lambda x: abs(x[1]), reverse=True)
    labels = [k for k, v in sorted_items]
    values = [v for k, v in sorted_items]

    fig, ax = plt.subplots(figsize=(5.0, max(3.0, len(labels) * 0.3)))

    colors = ["#d62728" if v < 0 else "#2ca02c" for v in values]
    y_pos = np.arange(len(labels))

    ax.barh(y_pos, values, color=colors, alpha=0.7)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Objective change (M USD)")
    ax.set_title("Sensitivity Tornado (OAT)")
    ax.grid(axis="x", alpha=0.3)
    ax.axvline(0, color="black", linewidth=0.5)

    plt.tight_layout()
    _save(fig, out_path)