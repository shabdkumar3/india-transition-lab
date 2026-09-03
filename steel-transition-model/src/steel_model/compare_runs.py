"""
Utility to compare two experiment runs (Step 16).
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def compare_runs(path1: str, path2: str) -> None:
    """Compare two run results folders and print objective, share, H2, electricity, and CO2 differences."""
    # Resolve paths
    results_json1 = os.path.join(path1, "results.json") if os.path.isdir(path1) else path1
    results_json2 = os.path.join(path2, "results.json") if os.path.isdir(path2) else path2

    if not os.path.exists(results_json1):
        raise FileNotFoundError(f"Results JSON not found: {results_json1}")
    if not os.path.exists(results_json2):
        raise FileNotFoundError(f"Results JSON not found: {results_json2}")

    with open(results_json1, "r", encoding="utf-8") as f:
        r1 = json.load(f)
    with open(results_json2, "r", encoding="utf-8") as f:
        r2 = json.load(f)

    # 1. Feasibility Difference
    status1 = r1.get("solver_status", "UNKNOWN")
    status2 = r2.get("solver_status", "UNKNOWN")
    print(f"=== Feasibility Difference ===")
    print(f"Run 1 Status: {status1}")
    print(f"Run 2 Status: {status2}")
    if status1 != status2:
        print(f"WARNING: Feasibility mismatch! {status1} vs {status2}")
    print()

    # 2. Objective Difference
    obj1 = r1.get("objective")
    obj2 = r2.get("objective")
    print(f"=== Objective Difference ===")
    if obj1 is not None and obj2 is not None:
        diff = obj2 - obj1
        pct = (diff / obj1 * 100) if obj1 != 0.0 else 0.0
        print(f"Run 1: {obj1:,.4f} M USD")
        print(f"Run 2: {obj2:,.4f} M USD")
        print(f"Diff : {diff:+,.4f} M USD ({pct:+.4f}%)")
    else:
        print(f"Run 1: {obj1}")
        print(f"Run 2: {obj2}")
    print()

    # 3. Yearly differences (H2, Electricity, CO2, Investment)
    y1 = {yr["year"]: yr for yr in r1.get("yearly_results", [])}
    y2 = {yr["year"]: yr for yr in r2.get("yearly_results", [])}
    common_years = sorted(list(set(y1.keys()).intersection(y2.keys())))

    if not common_years:
        print("Error: No overlapping years found between runs.")
        return

    print(f"=== Core Resources and Emissions Differences (Selected Years) ===")
    headers = f"{'Year':<6} | {'H2 Diff (Mt)':<15} | {'Elec Diff (TWh)':<15} | {'CO2 Diff (Mt)':<15} | {'Inv Diff (M USD)':<15}"
    print(headers)
    print("-" * len(headers))
    for yr in common_years:
        if yr in (2024, 2030, 2040, 2050, 2060, 2070):
            d1 = y1[yr]
            d2 = y2[yr]
            h2_diff = d2.get("H2", 0.0) - d1.get("H2", 0.0)
            elec_diff = d2.get("electricity", 0.0) - d1.get("electricity", 0.0)
            co2_diff = d2.get("CO2", 0.0) - d1.get("CO2", 0.0)
            inv_diff = d2.get("investment", 0.0) - d1.get("investment", 0.0)
            print(f"{yr:<6} | {h2_diff:+15.4f} | {elec_diff:+15.4f} | {co2_diff:+15.4f} | {inv_diff:+15.4f}")
    print()

    # 4. Tech Share Differences
    print(f"=== Technology Share Differences ===")
    all_techs = set()
    for yr in common_years:
        all_techs.update(y1[yr].get("technology_shares", {}).keys())
        all_techs.update(y2[yr].get("technology_shares", {}).keys())

    for tech in sorted(list(all_techs)):
        # print max absolute difference across all years
        max_diff = 0.0
        max_year = 2024
        for yr in common_years:
            s1 = y1[yr].get("technology_shares", {}).get(tech, 0.0)
            s2 = y2[yr].get("technology_shares", {}).get(tech, 0.0)
            diff = abs(s2 - s1)
            if diff > max_diff:
                max_diff = diff
                max_year = yr
        s1_max = y1[max_year].get("technology_shares", {}).get(tech, 0.0)
        s2_max = y2[max_year].get("technology_shares", {}).get(tech, 0.0)
        print(f"  {tech:<15}: Max Share Diff = {s2_max - s1_max:+.4f} in {max_year}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare two model run folders.")
    parser.add_argument("run1", help="Path to first run directory (or results.json).")
    parser.add_argument("run2", help="Path to second run directory (or results.json).")
    args = parser.parse_args()

    try:
        compare_runs(args.run1, args.run2)
    except Exception as exc:
        print(f"[Error] Comparison failed: {exc}")
        sys.exit(1)
