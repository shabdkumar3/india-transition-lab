"""
Batch runner to execute multiple reproducible runs in sequence (Step 16).
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
import yaml

from steel_model.run import run_experiment, validate_config_dict
from steel_model.run_schemas import RunConfig


def run_batch(batch_config_path: str) -> None:
    """Validate and execute a batch of model runs sequentially."""
    if not os.path.exists(batch_config_path):
        raise FileNotFoundError(f"Batch config not found: '{batch_config_path}'")

    with open(batch_config_path, "r", encoding="utf-8") as f:
        batch_data = yaml.safe_load(f)

    run_paths = batch_data.get("runs", [])
    if not run_paths:
        print("[Batch] No runs found in batch config.")
        return

    print(f"[Batch] Found {len(run_paths)} runs. Starting validation pass...")

    # 1. Validation Pass
    invalid = []
    validated_configs = []
    
    for idx, rpath in enumerate(run_paths):
        # Resolve path relative to batch config location if needed
        full_path = rpath
        if not os.path.isabs(full_path):
            full_path = os.path.join(os.path.dirname(batch_config_path), full_path)
            if not os.path.exists(full_path):
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                full_path = os.path.join(project_root, rpath)
            
        if not os.path.exists(full_path):
            invalid.append((rpath, f"File does not exist: {full_path}"))
            continue

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                rdata = yaml.safe_load(f)
            run_cfg = RunConfig(**rdata)

            # Load and merge base config to validate
            base_config_path = run_cfg.base_config
            if not os.path.isabs(base_config_path):
                base_config_path = os.path.join(os.path.dirname(full_path), base_config_path)

            with open(base_config_path, "r", encoding="utf-8") as f:
                base_dict = yaml.safe_load(f)

            # Add overrides
            from steel_model.run import apply_overrides
            merged_dict = apply_overrides(base_dict, run_cfg.overrides)

            # Validate merged dict
            validate_config_dict(merged_dict, run_cfg)
            validated_configs.append((rpath, full_path))
        except Exception as exc:
            invalid.append((rpath, f"Validation error: {exc}"))

    if invalid:
        print("\n[Batch] Validation FAILED for the following configurations:")
        for rpath, err in invalid:
            print(f"  - {rpath}: {err}")
        print("\nAborting batch run.")
        sys.exit(1)

    print("[Batch] All configurations validated successfully. Starting execution...")

    # 2. Execution Pass
    results = {}
    for rpath, full_path in validated_configs:
        print(f"\n[Batch] Running: {rpath} ...")
        try:
            out_dir = run_experiment(full_path)
            # Read manifest to extract details
            manifest_path = os.path.join(out_dir, "run_manifest.json")
            with open(manifest_path, "r", encoding="utf-8") as mf:
                manifest_data = json.load(mf)
            
            results[rpath] = {
                "success": True,
                "status": manifest_data.get("solver_status"),
                "objective": manifest_data.get("objective"),
                "out_dir": out_dir,
            }
            print(f"[Batch] Success! Saved to {out_dir}")
        except Exception as exc:
            print(f"[Batch] FAILED to execute '{rpath}': {exc}", file=sys.stderr)
            traceback.print_exc()
            results[rpath] = {
                "success": False,
                "error": str(exc),
            }

    # 3. Print Summary
    print("\n" + "=" * 60)
    print("BATCH RUN SUMMARY REPORT")
    print("=" * 60)
    
    success_count = sum(1 for r in results.values() if r["success"])
    fail_count = len(results) - success_count
    print(f"Total Configs Checked : {len(run_paths)}")
    print(f"Successfully Solved   : {success_count}")
    print(f"Failed Runs           : {fail_count}")
    print("-" * 60)
    
    for rpath, res in results.items():
        if res["success"]:
            obj_str = f"{res['objective']:,.4f} M USD" if res["objective"] is not None else "None"
            print(f"  [PASS] {rpath:<35} | Status: {res['status']:<10} | Obj: {obj_str}")
        else:
            print(f"  [FAIL] {rpath:<35} | Error: {res['error']}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deterministic batch runner.")
    parser.add_argument("batch_config", help="Path to batch config YAML listing run configurations.")
    args = parser.parse_args()

    # Load json for manifest parsing
    import json
    try:
        run_batch(args.batch_config)
    except Exception as exc:
        print(f"[Error] Batch execution failed: {exc}")
        sys.exit(1)
