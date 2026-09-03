"""
Canonical reproducible experiment runner (Step 16).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import platform
import sys
import tempfile
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml
from pydantic import ValidationError

from steel_model.optimization.model import BaselineMILP, load_baseline_inputs
from steel_model.schema.config import ModelConfig, ModelMode, ScenarioConfig
from steel_model.run_schemas import RunConfig, RunManifest, RunResultSchema, YearResultRecord
from steel_model.run_plots import generate_run_plots
from steel_model.explainability import (
    generate_technology_diagnostics,
    detect_technology_shifts,
    run_constraint_diagnostics,
    run_crossover_analysis,
    generate_pathway_events,
    generate_benchmark_diagnostics,
    generate_scrap_waypoint_diagnostics,
    export_explainability_results,
)

MODEL_VERSION = "0.16.0"


def file_sha256(path: str) -> str:
    """Calculate SHA256 hash of a file."""
    if not os.path.exists(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def deep_merge(dict1: dict, dict2: dict) -> dict:
    """Recursively merge dict2 into dict1."""
    out = dict1.copy()
    for k, v in dict2.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def apply_overrides(base_dict: dict, overrides: dict) -> dict:
    """Apply overrides (supporting dot notation) to a dictionary."""
    merged = base_dict.copy()
    for key, value in overrides.items():
        if "." in key:
            parts = key.split(".")
            curr = merged
            for part in parts[:-1]:
                curr = curr.setdefault(part, {})
            curr[parts[-1]] = value
        else:
            if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
                merged[key] = deep_merge(merged[key], value)
            else:
                merged[key] = value
    return merged


def validate_config_dict(cfg_dict: dict, run_cfg: RunConfig) -> ModelConfig:
    """Validate configuration dict using schema/config Pydantic models."""
    scenario_fields = {
        "scenario_name": cfg_dict.get("scenario_name", "CPS"),
        "discount_rate": cfg_dict.get("discount_rate", {}).get("value", 0.08) if isinstance(cfg_dict.get("discount_rate"), dict) else cfg_dict.get("discount_rate", 0.08),
        "start_year": cfg_dict.get("horizon", {}).get("start_year", 2024),
        "end_year": cfg_dict.get("horizon", {}).get("end_year", 2070),
        "use_endogenous_learning": cfg_dict.get("use_endogenous_learning", False),
        "use_dynamic_scrap": cfg_dict.get("use_dynamic_scrap", False),
        "use_m1_electrolyser_learning": cfg_dict.get("use_m1_electrolyser_learning", False),
        "use_exogenous_electrolyser_cost_curve": cfg_dict.get("use_exogenous_electrolyser_cost_curve", False),
        "use_deployment_dynamics": cfg_dict.get("use_deployment_dynamics", False),
        "benchmark_slack_penalty": cfg_dict.get("benchmark_slack_penalty", 1000.0),
    }

    if "mode" in cfg_dict:
        mode_str = cfg_dict["mode"]
    else:
        if (scenario_fields["use_endogenous_learning"] or 
            scenario_fields["use_dynamic_scrap"] or 
            scenario_fields["use_deployment_dynamics"]):
            mode_str = "MODE_B"
        else:
            mode_str = "MODE_A"

    # Instantiate ModelConfig to run Pydantic validators
    scenario_cfg = ScenarioConfig(**scenario_fields)
    model_cfg = ModelConfig(
        mode=ModelMode(mode_str),
        scenario=scenario_cfg,
        technology_routes=cfg_dict.get("enabled_routes", ["BF-BOF", "NG-DRI-EAF", "Scrap-EAF"]),
    )

    # Rejection of EXTERNAL_PENDING parameters without overrides
    # A route with pending economics is accepted if EITHER:
    #   (a) run_cfg.allow_external_pending = true AND diagnostic_overrides provide
    #       capex_{route} / opex_{route} keys, OR
    #   (b) The merged base config's economics section provides CAPEX and OPEX
    #       for the route directly (PROJECT_PROPOSAL economics in base config).
    pending_routes = ["Coal-DRI-EAF", "Coal-DRI-IF", "H2-DRI-EAF"]
    economics_in_cfg = cfg_dict.get("economics", {})
    capex_in_cfg = economics_in_cfg.get("capex_annualised_usd_per_t", {})
    opex_in_cfg = economics_in_cfg.get("opex_fixed_usd_per_t", {})
    for r in model_cfg.technology_routes:
        if r in pending_routes:
            # Accept if economics are directly in base config (PROJECT_PROPOSAL)
            if r in capex_in_cfg and r in opex_in_cfg:
                continue
            # Accept if allow_external_pending flag is set with diagnostic overrides
            if not run_cfg.allow_external_pending:
                raise ValueError(
                    f"Route '{r}' contains EXTERNAL_PENDING parameters and cannot be "
                    "enabled without setting allow_external_pending = true, OR by "
                    "providing CAPEX/OPEX directly in the base config economics section."
                )
            capex_ovr = run_cfg.diagnostic_overrides.get(f"capex_{r}")
            opex_ovr = run_cfg.diagnostic_overrides.get(f"opex_{r}")
            if capex_ovr is None and opex_ovr is None:
                raise ValueError(
                    f"Route '{r}' is enabled with allow_external_pending = true, "
                    f"but no overrides are provided in diagnostic_overrides."
                )

    # Reject UNKNOWN parameters entering overrides or diagnostic_overrides
    known_fields = set(ModelConfig.model_fields.keys()).union(ScenarioConfig.model_fields.keys())
    # Add baseline model input names that are commonly overridden
    known_fields.update([
        "horizon", "discount_rate", "enabled_routes", "resource_prices",
        "economics", "availability", "lifetime_years", "start_years",
        # Step 9/10/11 module flags (both naming conventions accepted)
        "dynamic_scrap", "deployment_dynamics", "endogenous_learning",
        "use_dynamic_scrap", "use_deployment_dynamics", "use_endogenous_learning",
        "use_exogenous_electrolyser_cost_curve", "use_m1_electrolyser_learning",
        "static_scrap_cap", "mode_b_policy",
        # Step 20 realism enhancements
        "carbon_price", "h2_supply_cap", "stranded_asset_cost",
        "resource_price_trajectories",
        # Step 21 realism enhancements (batch 2)
        "grid_emission_intensity", "construction_lead_time", "wacc_premium",
        "policy_incentives", "green_steel_premium",
        # Step 22: Technology ramp limits
        "technology_ramp_limits",
        # Step 22B: CCUS
        "ccus",
        # Step 24: SEC improvement trajectory (NITI V4-sourced)
        "sec_improvement",
        # Scenario/mode
        "mode", "scenario_name",
    ])
    for key in run_cfg.overrides:
        base_key = key.split(".")[0]
        if base_key not in known_fields:
            raise ValueError(f"UNKNOWN parameter '{key}' cannot enter optimization.")

    return model_cfg


def get_git_metadata() -> Tuple[bool, Optional[str], Optional[str]]:
    """Retrieve git metadata securely without throwing exceptions."""
    import subprocess
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
        return True, commit, branch
    except Exception:
        return False, None, None


# ──────────────────────────────────────────────────────────────────────────────
# MAIN RUNNER ENGINE
# ──────────────────────────────────────────────────────────────────────────────

def run_experiment(config_path: str) -> str:
    """
    Execute a reproducible experiment run.

    Returns the directory path containing the run results.
    """
    start_time = time.time()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Load RunConfig
    with open(config_path, "r", encoding="utf-8") as f:
        run_data = yaml.safe_load(f)
    run_cfg = RunConfig(**run_data)

    # Verify base config exists
    base_config_path = run_cfg.base_config
    if not os.path.isabs(base_config_path):
        base_config_path = os.path.join(os.path.dirname(config_path), base_config_path)
    if not os.path.exists(base_config_path):
        raise FileNotFoundError(f"Base config not found: '{base_config_path}'")

    # 2. Load and merge configurations
    with open(base_config_path, "r", encoding="utf-8") as f:
        base_dict = yaml.safe_load(f)

    # Merge overrides
    merged_dict = apply_overrides(base_dict, run_cfg.overrides)

    # Merge diagnostic overrides if allowed
    if run_cfg.allow_external_pending:
        # Apply overrides to enabled_routes / economics
        enabled = merged_dict.setdefault("enabled_routes", [])
        for k, v in run_cfg.diagnostic_overrides.items():
            if k.startswith("capex_"):
                route = k.replace("capex_", "")
                if route not in enabled:
                    enabled.append(route)
                merged_dict.setdefault("economics", {}).setdefault("capex_annualised_usd_per_t", {})[route] = v
            elif k.startswith("opex_"):
                route = k.replace("opex_", "")
                if route not in enabled:
                    enabled.append(route)
                merged_dict.setdefault("economics", {}).setdefault("opex_fixed_usd_per_t", {})[route] = v

    # 3. Validate configuration
    model_cfg = validate_config_dict(merged_dict, run_cfg)

    # 4. Generate Hashes and Run ID
    config_hash = hashlib.sha256(yaml.dump(merged_dict, sort_keys=True).encode()).hexdigest()
    
    # Input files hashes
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if run_cfg.intensities_path:
        intensities_path = run_cfg.intensities_path
        if not os.path.isabs(intensities_path):
            intensities_path = os.path.join(os.path.dirname(config_path), intensities_path)
    else:
        intensities_path = os.path.join(project_root, "configs", "resources", "steel_intensities.yaml")
    assets_path = os.path.join(project_root, "configs", "assets", "existing_assets.yaml")
    demand_path = os.path.join(project_root, "data", "processed", "steel_demand.csv")

    data_hash_combined = (
        file_sha256(intensities_path) +
        file_sha256(assets_path) +
        file_sha256(demand_path)
    )
    data_hash = hashlib.sha256(data_hash_combined.encode()).hexdigest()

    config_name = os.path.splitext(os.path.basename(config_path))[0]
    run_id = f"{timestamp}_{config_name}_{config_hash[:8]}"

    results_dir = os.path.join(project_root, "results", run_id)
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(os.path.join(results_dir, "logs"), exist_ok=True)
    os.makedirs(os.path.join(results_dir, "plots"), exist_ok=True)
    os.makedirs(os.path.join(results_dir, "diagnostics"), exist_ok=True)

    # Set up run log
    log_path = os.path.join(results_dir, "logs", "run.log")
    
    def log(msg: str, level: str = "INFO") -> None:
        with open(log_path, "a", encoding="utf-8") as lf:
            formatted = f"[{level}] {datetime.datetime.now().isoformat()} - {msg}\n"
            lf.write(formatted)
            print(formatted.strip())

    log("Starting experiment run...")
    log(f"Run ID: {run_id}")
    log(f"Configuration loaded: {config_path}")
    log(f"Base Configuration: {run_cfg.base_config}")
    log(f"Config Hash: {config_hash}")
    log(f"Data Hash: {data_hash}")

    # 5. Initialize & Solve Model
    # Write merged configuration to temporary file to load via load_baseline_inputs
    temp_fd, temp_path = tempfile.mkstemp(suffix=".yaml")
    os.close(temp_fd)
    try:
        with open(temp_path, "w", encoding="utf-8") as temp_f:
            yaml.dump(merged_dict, temp_f)

        log("Loading baseline inputs...")
        inputs = load_baseline_inputs(temp_path, intensities_path, scenario=model_cfg.scenario.scenario_name)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    log(f"Solver initiated. Mode: {model_cfg.mode.value}. Scenario: {model_cfg.scenario.scenario_name}")
    
    # Run solver
    solver_status = "NOT_RUN"
    termination_reason = ""
    objective = None
    res = None
    success = False

    try:
        milp = BaselineMILP(inputs)
        res = milp.solve()
        solver_status = res.status_label.upper()
        termination_reason = res.message
        objective = res.objective_value
        success = (res.status == 0)
        log(f"Solver complete. Status: {solver_status}. Objective: {objective}")
    except Exception as e:
        solver_status = "ERROR"
        termination_reason = str(e)
        log(f"Solver CRASHED: {e}", "ERROR")
        with open(log_path, "a", encoding="utf-8") as lf:
            traceback.print_exc(file=lf)

    # 6. Capture Diagnostics & Explainability
    if success and res is not None:
        log("Running explainability diagnostics...")
        diagnostics = generate_technology_diagnostics(inputs, res)
        shifts = detect_technology_shifts(inputs, res)
        constraints = run_constraint_diagnostics(inputs, res)
        crossovers = run_crossover_analysis(inputs, "BF-BOF", "NG-DRI-EAF")
        events = generate_pathway_events(shifts, constraints)
        benchmarks = generate_benchmark_diagnostics(inputs, os.path.join(project_root, "data", "benchmark"))
        scrap_waypoints = generate_scrap_waypoint_diagnostics(inputs, res)

        log("Exporting explainability results...")
        export_explainability_results(
            diagnostics, shifts, constraints, crossovers, events, benchmarks, os.path.join(results_dir, "diagnostics")
        )

        # Gate C: export scrap waypoint diagnostics (NZS post-solve comparison).
        if scrap_waypoints:
            diag_dir = os.path.join(results_dir, "diagnostics")
            with open(os.path.join(diag_dir, "scrap_waypoint_diagnostics.json"), "w", encoding="utf-8") as jf:
                json.dump([w.model_dump() for w in scrap_waypoints], jf, indent=2)
            pd.DataFrame([w.model_dump() for w in scrap_waypoints]).to_csv(
                os.path.join(diag_dir, "scrap_waypoint_diagnostics.csv"), index=False
            )

        # 7. Construct Result Schema
        yearly_results = []
        for t in inputs.years:
            # Map canonical tech data
            production = {r: res.production_mt(r).get(t, 0.0) if r in inputs.routes else 0.0 for r in inputs.all_routes}
            capacity = {r: res.cap_mt.get(r, {}).get(t, 0.0) if r in inputs.routes else 0.0 for r in inputs.all_routes}
            ncap = {r: res.ncap_mt.get(r, {}).get(t, 0.0) if r in inputs.routes else 0.0 for r in inputs.all_routes}
            retirement = {r: res.ret_mt.get(r, {}).get(t, 0.0) if r in inputs.routes else 0.0 for r in inputs.all_routes}
            shares = {r: res.production_share(r).get(t, 0.0) if r in inputs.routes else 0.0 for r in inputs.all_routes}

            # Resources
            h2_val = res.res_use.get("hydrogen", {}).get(t, 0.0)
            elec_val = res.res_use.get("electricity_route", {}).get(t, 0.0)
            coal_val = res.res_use.get("coking_coal", {}).get(t, 0.0) + res.res_use.get("non_coking_coal", {}).get(t, 0.0)
            gas_val = res.res_use.get("natural_gas", {}).get(t, 0.0)
            ore_val = res.res_use.get("iron_ore", {}).get(t, 0.0)
            scrap_val = res.res_use.get("scrap", {}).get(t, 0.0)

            co2_val = res.co2_total_mt.get(t, 0.0)
            investment_val = sum(res.ncap_mt[r][t] * (inputs.capex_annualised_usd_per_t[r][t] if isinstance(inputs.capex_annualised_usd_per_t[r], dict) else inputs.capex_annualised_usd_per_t[r]) for r in inputs.routes)

            # Decompose costs per year
            total_cost_val = 0.0
            incomplete_economics = False
            for r in inputs.routes:
                from steel_model.explainability.costs import decompose_route_cost
                r_cost = decompose_route_cost(inputs, r, t, production[r], capacity[r])["effective_cost"]
                if r_cost is None:
                    incomplete_economics = True
                else:
                    total_cost_val += r_cost

            yearly_results.append(
                YearResultRecord(
                    year=t,
                    production=production,
                    capacity=capacity,
                    new_capacity=ncap,
                    retirement=retirement,
                    technology_shares=shares,
                    H2=h2_val,
                    electricity=elec_val,
                    coal=coal_val,
                    gas=gas_val,
                    ore=ore_val,
                    scrap=scrap_val,
                    CO2=co2_val,
                    investment=investment_val,
                    total_cost=None if incomplete_economics else total_cost_val,
                )
            )

        # Technology Space Completeness
        tech_space = "INCOMPLETE" if any(r in ["Coal-DRI-EAF", "Coal-DRI-IF", "H2-DRI-EAF"] for r in inputs.routes) else "COMPLETE"

        res_schema = RunResultSchema(
            scenario=model_cfg.scenario.scenario_name,
            mode=model_cfg.mode.value,
            solver_status=solver_status,
            objective=objective,
            data_completeness="INCOMPLETE" if any(r == "Scrap-EAF" for r in inputs.routes) else "COMPLETE",
            source_completeness="INCOMPLETE",
            optimization_eligibility="ELIGIBLE",
            technology_space_completeness=tech_space,
            M1_state="DEFERRED" if not model_cfg.scenario.use_m1_electrolyser_learning else "ACTIVE",
            existing_route_capacity_state="UNRESOLVED",
            economically_complete=dict(res.economically_complete),
            interpretation=list(res.interpretation),
            yearly_results=yearly_results,
        )

        # Save JSON results
        results_json_path = os.path.join(results_dir, "results.json")
        with open(results_json_path, "w", encoding="utf-8") as jf:
            jf.write(res_schema.model_dump_json(indent=2))

        # Save CSV results
        csv_rows = []
        for yr in res_schema.yearly_results:
            row = {
                "year": yr.year,
                "H2": yr.H2,
                "electricity": yr.electricity,
                "coal": yr.coal,
                "gas": yr.gas,
                "ore": yr.ore,
                "scrap": yr.scrap,
                "CO2": yr.CO2,
                "investment": yr.investment,
                "total_cost": yr.total_cost,
            }
            # Append route-specific keys
            for r in inputs.all_routes:
                row[f"prod_{r}"] = yr.production.get(r, 0.0)
                row[f"cap_{r}"] = yr.capacity.get(r, 0.0)
                row[f"ncap_{r}"] = yr.new_capacity.get(r, 0.0)
                row[f"ret_{r}"] = yr.retirement.get(r, 0.0)
                row[f"share_{r}"] = yr.technology_shares.get(r, 0.0)
            csv_rows.append(row)

        results_csv_path = os.path.join(results_dir, "results.csv")
        pd.DataFrame(csv_rows).to_csv(results_csv_path, index=False)

        # 8. Generate standard plots
        log("Generating standard compact plots...")
        generate_run_plots(pd.DataFrame(csv_rows), os.path.join(results_dir, "plots"))

    # 9. Save config snapshot
    config_snapshot_path = os.path.join(results_dir, "config_snapshot.yaml")
    with open(config_snapshot_path, "w", encoding="utf-8") as csf:
        yaml.dump(merged_dict, csf)

    # 10. Save Run Manifest
    git_avail, git_hash, git_branch = get_git_metadata()
    manifest = RunManifest(
        run_id=run_id,
        timestamp=datetime.datetime.now().isoformat(),
        model_version=MODEL_VERSION,
        code_version=git_hash if git_hash else "1.0.0",
        config_path=config_path,
        config_hash=config_hash,
        data_hash=data_hash,
        parameter_registry_version="Step6_ParameterFreeze",
        scenario=model_cfg.scenario.scenario_name,
        mode=model_cfg.mode.value,
        enabled_modules=[
            m for m, active in [
                ("scrap", model_cfg.scenario.use_dynamic_scrap),
                ("deployment", model_cfg.scenario.use_deployment_dynamics),
                ("learning", model_cfg.scenario.use_endogenous_learning),
                ("M1", model_cfg.scenario.use_m1_electrolyser_learning),
            ] if active
        ],
        solver="HiGHS (scipy.optimize.milp)",
        solver_version=platform.python_version(),
        solver_options=merged_dict.get("solver_options", {}),
        objective=objective,
        solver_status=solver_status,
        termination_reason=termination_reason,
        random_seed=run_cfg.random_seed,
        environment_metadata={
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "system": platform.system(),
        },
        git_available=git_avail,
        git_commit_hash=git_hash,
        git_branch=git_branch,
    )

    manifest_path = os.path.join(results_dir, "run_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as mf:
        mf.write(manifest.model_dump_json(indent=2))

    log(f"Experiment finished successfully in {time.time() - start_time:.2f} seconds.")
    return results_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deterministic India Steel Transition Model Runner.")
    parser.add_argument("--config", required=True, help="Path to experiment run configuration YAML file.")
    args = parser.parse_args()
    
    try:
        path = run_experiment(args.config)
        print(f"\n[Success] Experiment results saved to: {path}")
    except Exception as exc:
        print(f"\n[Error] Experiment execution FAILED: {exc}")
        traceback.print_exc()
        sys.exit(1)
