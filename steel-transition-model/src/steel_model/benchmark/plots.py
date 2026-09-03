"""
Compact benchmark plots (Step 14 §16).

Five small plots. Explicitly NOT full-page screenshots. When definitions do
not match, the plot carries a NOT_COMPARABLE annotation instead of implying
agreement.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROUTES = ("BF-BOF", "NG-DRI-EAF", "H2-DRI-EAF", "Scrap-EAF")


def _save(fig, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def plot_demand(register, inputs: Any, out_path: str) -> None:
    model_years = list(inputs.years)
    model_path = [float(inputs.demand_mt.get(t)) for t in model_years]
    anchors = {y: register.demand_anchor(y) for y in (2024, 2050, 2070)}
    fig, ax = plt.subplots(figsize=(5.0, 3.2))
    ax.plot(model_years, model_path, label="model (piecewise-linear)", color="#1f77b4")
    ax.scatter(list(anchors), list(anchors.values()), marker="o", color="#d62728",
               zorder=5, label="Vol.4 anchors")
    for y, v in anchors.items():
        ax.annotate(f"{v:.0f}", (y, v), textcoords="offset points", xytext=(0, 6),
                    fontsize=8, ha="center")
    ax.set_title("Steel production: Vol.4 vs model (MATCH at anchors)")
    ax.set_xlabel("Year"); ax.set_ylabel("Mt crude steel")
    ax.legend(fontsize=7); ax.grid(alpha=0.3)
    _save(fig, out_path)


def plot_technology_shares(register, result: Any, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(5.0, 3.2))
    x = list(range(len(ROUTES)))
    width = 0.2
    for scenario, off, color in (("CPS", -width, "#9467bd"), ("NZS", 0.0, "#2ca02c")):
        vals = [register.mix_share_2070(scenario, r) or 0.0 for r in ROUTES]
        ax.bar([xi + off for xi in x], vals, width, label=f"Vol.4 {scenario}", color=color)
    ctrl = [float(result.production_share(r)[2070]) for r in ROUTES]
    ax.bar([xi + width for xi in x], ctrl, width, label="model control (cornered)", color="#d62728")
    ax.set_xticks(x); ax.set_xticklabels(ROUTES, fontsize=7, rotation=20)
    ax.set_ylabel("share of 2070 production"); ax.set_title("2070 technology mix (DATA-LIMITED)")
    ax.legend(fontsize=7); ax.grid(axis="y", alpha=0.3)
    _save(fig, out_path)


def plot_emissions(register, inputs: Any, result: Any, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(5.0, 3.2))
    combos = [(s, y) for s in ("CPS", "NZS") for y in (2050, 2070)]
    demand = {t: float(inputs.demand_mt.get(t, 0.0)) for t in inputs.years}
    for i, (scenario, yr) in enumerate(combos):
        vol4 = register.emission_intensity(yr, scenario) or 0.0
        co2 = result.co2_total_mt.get(yr)
        ours = (co2 / demand[yr]) if (co2 is not None and demand[yr]) else 0.0
        ax.bar(i - 0.2, vol4, width=0.35, color="#2ca02c" if scenario == "NZS" else "#9467bd",
               label="Vol.4" if i == 0 else None)
        ax.bar(i + 0.2, ours, width=0.35, color="#d62728",
               label="model (cornered mix)" if i == 0 else None)
    ax.set_xticks(range(len(combos)))
    ax.set_xticklabels([f"{s}{y}" for s, y in combos], fontsize=8)
    ax.set_ylabel("tCO2/t crude steel"); ax.set_title("Sector CO2 intensity (DATA-LIMITED)")
    ax.legend(fontsize=7); ax.grid(axis="y", alpha=0.3)
    _save(fig, out_path)


def plot_h2(register, result: Any, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(5.0, 3.2))
    combos = [(s, y) for s in ("CPS", "NZS") for y in (2050, 2070)]
    for i, (scenario, yr) in enumerate(combos):
        vol4 = register.green_h2_steel_mt(yr, scenario) or 0.0
        ours = result.res_use.get("hydrogen", {}).get(yr, 0.0)
        ax.bar(i - 0.2, vol4, width=0.35, color="#2ca02c" if scenario == "NZS" else "#9467bd",
               label="Vol.4" if i == 0 else None)
        ax.bar(i + 0.2, ours, width=0.35, color="#d62728",
               label="model (H2-DRI not represented)" if i == 0 else None)
    ax.set_xticks(range(len(combos)))
    ax.set_xticklabels([f"{s}{y}" for s, y in combos], fontsize=8)
    ax.set_ylabel("Mt H2/yr (steel)"); ax.set_title("Green H2 in steel (NOT_COMPARABLE)")
    ax.legend(fontsize=7); ax.grid(axis="y", alpha=0.3)
    _save(fig, out_path)


def plot_cost_ablation(ablation_rows: List[Dict], out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(5.0, 3.2))
    labels = [r["layer"] for r in ablation_rows]
    objs = [r.get("objective") for r in ablation_rows]
    colors = []
    for r in ablation_rows:
        st = r["status"]
        colors.append("#7f7f7f" if st == "published_target" else
                      "#d62728" if st == "solved" else
                      "#ff9896" if st in ("infeasible", "deferred", "not_run") else "#c7c7c7")
    ax.bar(labels, [o if o is not None else 0.0 for o in objs], color=colors)
    for i, o in enumerate(objs):
        if o is not None:
            ax.text(i, o, f"{o:,.0f}", ha="center", va="bottom", fontsize=7)
    ax.set_ylabel("discounted system cost (M USD, model only)")
    ax.set_title("Ablation cost — no comparable Vol.4 system cost")
    ax.text(0.02, 0.95, "NOT_COMPARABLE: Vol.4 publishes industry investment (USD tn), "
                        "not a steel system cost", transform=ax.transAxes,
            fontsize=6.5, va="top", color="#555555")
    ax.grid(axis="y", alpha=0.3)
    _save(fig, out_path)