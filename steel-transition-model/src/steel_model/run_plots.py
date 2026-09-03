"""
Standard plot generator for experiment runs (Step 16).
"""

from __future__ import annotations

import os
from typing import Any, List
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

# Styling
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial']


def generate_run_plots(
    results_df: pd.DataFrame,
    output_dir: str,
) -> None:
    """Generate the six standard compact plots for the run results."""
    os.makedirs(output_dir, exist_ok=True)
    if results_df.empty:
        return

    years = results_df["year"].values

    # 1. Technology Share Plot
    fig, ax = plt.subplots(figsize=(6, 3.5), dpi=300)
    share_cols = [c for c in results_df.columns if c.startswith("share_")]
    for col in share_cols:
        tech_name = col.replace("share_", "")
        ax.plot(years, results_df[col] * 100, label=tech_name, marker="o", linewidth=1.5, markersize=4)
    ax.set_title("Technology Production Shares", fontsize=10, fontweight="bold", color="#1D3557")
    ax.set_xlabel("Year", fontsize=8)
    ax.set_ylabel("Share (%)", fontsize=8)
    ax.legend(loc="upper left", frameon=True, fontsize=7)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "tech_share.png"))
    plt.close()

    # 2. Production/Capacity Plot
    fig, ax = plt.subplots(figsize=(6, 3.5), dpi=300)
    prod_cols = [c for c in results_df.columns if c.startswith("prod_")]
    for col in prod_cols:
        tech_name = col.replace("prod_", "")
        ax.plot(years, results_df[col], label=f"{tech_name} Prod", marker="s", linewidth=1.5, markersize=4)
    ax.set_title("Route Production Trajectories", fontsize=10, fontweight="bold", color="#1D3557")
    ax.set_xlabel("Year", fontsize=8)
    ax.set_ylabel("Production (Mt/year)", fontsize=8)
    ax.legend(loc="upper left", frameon=True, fontsize=7)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "production_capacity.png"))
    plt.close()

    # 3. H2 Demand Plot
    fig, ax = plt.subplots(figsize=(6, 3.5), dpi=300)
    ax.plot(years, results_df["H2"], color="#457B9D", marker="^", linewidth=1.5, markersize=4)
    ax.set_title("Hydrogen Consumption", fontsize=10, fontweight="bold", color="#1D3557")
    ax.set_xlabel("Year", fontsize=8)
    ax.set_ylabel("H2 Demand (Mt/year)", fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "h2_demand.png"))
    plt.close()

    # 4. Electricity Demand Plot
    fig, ax = plt.subplots(figsize=(6, 3.5), dpi=300)
    ax.plot(years, results_df["electricity"], color="#2A9D8F", marker="d", linewidth=1.5, markersize=4)
    ax.set_title("Electricity Consumption", fontsize=10, fontweight="bold", color="#1D3557")
    ax.set_xlabel("Year", fontsize=8)
    ax.set_ylabel("Electricity Demand (TWh/year)", fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "electricity_demand.png"))
    plt.close()

    # 5. CO2 Emissions Plot
    fig, ax = plt.subplots(figsize=(6, 3.5), dpi=300)
    ax.plot(years, results_df["CO2"], color="#E76F51", marker="o", linewidth=1.5, markersize=4)
    ax.set_title("Total CO2 Emissions", fontsize=10, fontweight="bold", color="#1D3557")
    ax.set_xlabel("Year", fontsize=8)
    ax.set_ylabel("CO2 Emissions (Mt/year)", fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "co2.png"))
    plt.close()

    # 6. Investment/Cost Plot
    fig, ax = plt.subplots(figsize=(6, 3.5), dpi=300)
    ax.plot(years, results_df["investment"], color="#E9C46A", label="Investment (CAPEX)", marker="x", linewidth=1.5, markersize=4)
    if "total_cost" in results_df.columns and not results_df["total_cost"].isna().all():
        ax.plot(years, results_df["total_cost"], color="#264653", label="Total Cost", marker="o", linewidth=1.5, markersize=4)
    ax.set_title("Investment & Total Costs", fontsize=10, fontweight="bold", color="#1D3557")
    ax.set_xlabel("Year", fontsize=8)
    ax.set_ylabel("Cost (M USD/year)", fontsize=8)
    ax.legend(loc="upper left", frameon=True, fontsize=7)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "investment_cost.png"))
    plt.close()
