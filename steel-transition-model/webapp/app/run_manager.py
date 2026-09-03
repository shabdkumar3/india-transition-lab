"""
India Steel Transition Lab — run manager (background job layer).

POST /api/runs must not block the request thread while HiGHS solves. A
lightweight in-process job layer (threading) is used; no Redis/Celery is
introduced. Runs execute through the EXISTING ``steel_model.run.run_experiment``
pipeline and are persisted under the existing results store.

Statuses: QUEUED -> RUNNING -> OPTIMAL | FEASIBLE | INFEASIBLE | FAILED
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from steel_model.run import RunConfig, run_experiment
from steel_model.uncertainty.pathway import PathwayScenarioEngine

from . import REPO_ROOT
from .scenarios import ScenarioValidationError, validate_run_request

logger = logging.getLogger("steel_lab.run_manager")

RUNTIME_DIR = REPO_ROOT / "webapp" / "runtime"
JOBS_FILE = RUNTIME_DIR / "jobs.json"
_GENERATED_CONFIG_DIR = RUNTIME_DIR / "generated_configs"

# Sci gate: do not promote EXTERNAL_PENDING values here. The pathway engine's
# documented CEEW EXTERNAL economics are the only values usable for the
# approved uncertainty-study diagnostic gate (Step 18).
COAL_DRI_IF_CAPEX = 61.5
COAL_DRI_IF_OPEX = 26.0

# Canonical run templates (RunConfig-shaped YAML under configs/runs/).
CANONICAL_RUN_CONFIGS = {
    "control": "configs/runs/mode_a_baseline.yaml",
    "cps": "configs/runs/mode_b_policy_cps.yaml",
    "nzs": "configs/runs/mode_b_policy_nzs.yaml",
    "custom": "configs/runs/mode_b_policy_cps.yaml",
}


def _now_iso() -> str:
    return datetime.datetime.now().isoformat()


def _map_solver_status(status: str) -> str:
    """Map the engine's solver_status label onto the API status vocabulary."""
    s = str(status or "").upper()
    if s == "OPTIMAL":
        return "OPTIMAL"
    if "INFEAS" in s:
        return "INFEASIBLE"
    if "ERROR" in s or "CRASH" in s or "FAIL" in s:
        return "FAILED"
    return "FEASIBLE"


class RunManager:
    """Thread-safe background run execution with JSON persistence."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        _GENERATED_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if JOBS_FILE.exists():
            try:
                with open(JOBS_FILE, "r", encoding="utf-8") as f:
                    self._jobs = json.load(f)
            except Exception:
                self._jobs = {}
        # Any job that was RUNNING when the server last died -> FAILED.
        for jid, job in self._jobs.items():
            if job.get("status") in ("QUEUED", "RUNNING"):
                job["status"] = "FAILED"
                job["error"] = job.get("error") or "Server restarted before run completed."
                job["finished_at"] = _now_iso()
        self._save()

    def _save(self) -> None:
        with open(JOBS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._jobs, f, indent=2)

    # ------------------------------------------------------------------
    # job API
    # ------------------------------------------------------------------
    def create_job(
        self, scenario_id: str, overrides: Dict[str, Any], uncertainty_params: Dict[str, str]
    ) -> str:
        with self._lock:
            validate_run_request(scenario_id, overrides, uncertainty_params)
            run_id = f"web_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{scenario_id}"
            suffix = 0
            while run_id in self._jobs:
                suffix += 1
                run_id = f"web_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{scenario_id}_{suffix}"
            self._jobs[run_id] = {
                "run_id": run_id,
                "scenario_id": scenario_id,
                "status": "QUEUED",
                "created_at": _now_iso(),
                "started_at": None,
                "finished_at": None,
                "error": None,
                "objective": None,
                "overrides": overrides,
                "uncertainty_params": uncertainty_params,
                "results_dir": None,
            }
            self._save()
            logger.info("Queued run %s (scenario=%s)", run_id, scenario_id)
            thread = threading.Thread(target=self._execute, args=(run_id,), daemon=True)
            thread.start()
            return run_id

    def get_job(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(run_id)
            return dict(job) if job else None

    def list_jobs(self) -> list:
        with self._lock:
            return [
                {k: v for k, v in j.items() if k not in ("overrides", "uncertainty_params")}
                for j in self._jobs.values()
            ]

    # ------------------------------------------------------------------
    # execution
    # ------------------------------------------------------------------
    def _execute(self, run_id: str) -> None:
        with self._lock:
            job = self._jobs[run_id]
            job["status"] = "RUNNING"
            job["started_at"] = _now_iso()
            self._save()
            scenario_id = job["scenario_id"]
            overrides = job["overrides"]
            uncertainty_params = job["uncertainty_params"]

        logger.info("Executing run %s", run_id)
        try:
            config_path = self._build_run_config(run_id, scenario_id, overrides, uncertainty_params)
            results_dir = run_experiment(str(config_path))
            with self._lock:
                job = self._jobs[run_id]
                job["results_dir"] = results_dir
                manifest_path = Path(results_dir) / "run_manifest.json"
                if manifest_path.exists():
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    job["objective"] = manifest.get("objective")
                    job["status"] = _map_solver_status(str(manifest.get("solver_status", "")))
                else:
                    job["status"] = "FAILED"
                    job["error"] = "Run completed without a manifest."
                job["finished_at"] = _now_iso()
                self._save()
            logger.info("Run %s finished: %s", run_id, job["status"])
        except ScenarioValidationError as exc:
            self._fail(run_id, str(exc))
        except Exception as exc:  # noqa: BLE001 — propagate as FAILED
            logger.exception("Run %s failed", run_id)
            self._fail(run_id, f"{type(exc).__name__}: {exc}")

    def _fail(self, run_id: str, message: str) -> None:
        with self._lock:
            job = self._jobs.get(run_id)
            if job is None:
                return
            job["status"] = "FAILED"
            job["error"] = message
            job["finished_at"] = _now_iso()
            self._save()

    # ------------------------------------------------------------------
    # run config construction (whitelisted, gate-checked)
    # ------------------------------------------------------------------
    def _build_run_config(
        self,
        run_id: str,
        scenario_id: str,
        overrides: Dict[str, Any],
        uncertainty_params: Dict[str, str],
    ) -> Path:
        """Build a RunConfig YAML under webapp/runtime/generated_configs."""
        if scenario_id == "uncertainty_study":
            return self._build_uncertainty_config(run_id, uncertainty_params)
        return self._build_standard_config(run_id, scenario_id, overrides)

    def _build_standard_config(
        self, run_id: str, scenario_id: str, overrides: Dict[str, Any]
    ) -> Path:
        """Build a RunConfig from a canonical template + validated user overrides.

        The canonical configs/runs/*.yaml files are themselves RunConfig-shaped;
        ``run_experiment`` loads ``base_config`` as a *plain optimization config*,
        so we resolve the template's base_config to the real optimization config
        (configs/optimization/*.yaml) and carry the template's overrides.

        Step 27: if ``demand_anchors_mt`` is in overrides, we patch the base
        config's ``scenarios`` list directly (demand anchors live inside a list
        element, so they can't be expressed as a dot-notation override key).
        The patched base is written as a separate generated file; the override
        key is then removed before handing the remainder to RunConfig.
        """
        template_path = REPO_ROOT / CANONICAL_RUN_CONFIGS[scenario_id]
        template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
        base_config = template["base_config"]
        base_path = (template_path.parent / base_config).resolve()
        if not base_path.exists():
            raise ScenarioValidationError(f"Template base config missing: {base_path}")

        merged_overrides = dict(template.get("overrides", {}))
        merged_overrides.update(overrides)

        # Step 27: demand_anchors_mt override — patch base config scenarios in-place.
        demand_anchors = merged_overrides.pop("demand_anchors_mt", None)
        if demand_anchors is not None:
            # Load, patch, and write a modified base config.
            base_dict = yaml.safe_load(base_path.read_text(encoding="utf-8"))
            # Convert string keys to int (JSON round-trips may stringify them).
            anchors_int = {int(k): float(v) for k, v in demand_anchors.items()}
            scenarios = base_dict.get("scenarios", [])
            for sc in scenarios:
                sc["demand_anchors_mt"] = anchors_int
            patched_path = _GENERATED_CONFIG_DIR / f"{run_id}_base_patched.yaml"
            patched_path.write_text(yaml.safe_dump(base_dict, sort_keys=False), encoding="utf-8")
            base_path = patched_path

        cfg = RunConfig(
            base_config=str(base_path),
            overrides=merged_overrides,
            allow_external_pending=False,
            diagnostic_overrides={},
            random_seed=None,
            intensities_path=None,
        )
        path = _GENERATED_CONFIG_DIR / f"{run_id}.yaml"
        path.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
        return path

    def _build_uncertainty_config(
        self, run_id: str, uncertainty_params: Dict[str, str]
    ) -> Path:
        """Build the representative uncertainty-study member config.

        Uses the EXISTING PathwayScenarioEngine (source-backed bounds only) to
        produce a full merged optimization-config dict, which is written as the
        RunConfig base with no overrides. Coal-DRI-IF is enabled only through the
        engine's documented CEEW EXTERNAL economics (approved diagnostic gate);
        the engine's merged dict already carries those values, and the RunConfig
        records them as diagnostic overrides to satisfy run.py's EXTERNAL_PENDING
        gate without inventing anything.
        """
        policy = uncertainty_params.get("policy", "CPS")
        scrap_level = uncertainty_params.get("scrap_level", "SCRAP_LOW")
        dri_alternative = uncertainty_params.get("dri_alternative", "DRI_IBM")
        if dri_alternative == "NONE":
            dri_alternative = None
        fleet_id = uncertainty_params.get("fleet_id", "FLEET_CENTRAL")

        engine = PathwayScenarioEngine()
        cfg = engine.build_config(
            policy=policy,
            scrap_level=scrap_level,
            dri_alternative=dri_alternative,
            fleet_id=fleet_id,
        )
        # The merged dict is a full optimization config; label mode/scenario
        # so the run manifest is honest (Mode B policy run).
        cfg["mode"] = "MODE_B"
        cfg["scenario_name"] = policy

        diagnostic_overrides = {}
        if dri_alternative is not None:
            # Approved Step-18 diagnostic gate: documented CEEW EXTERNAL values.
            diagnostic_overrides = {
                "capex_Coal-DRI-IF": COAL_DRI_IF_CAPEX,
                "opex_Coal-DRI-IF": COAL_DRI_IF_OPEX,
            }

        # Write the merged optimization config as the base.
        base_path = _GENERATED_CONFIG_DIR / f"{run_id}_merged.yaml"
        base_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

        run_cfg = RunConfig(
            base_config=str(base_path),
            overrides={},
            allow_external_pending=True,
            diagnostic_overrides=diagnostic_overrides,
            random_seed=None,
            intensities_path=None,
        )
        path = _GENERATED_CONFIG_DIR / f"{run_id}.yaml"
        path.write_text(run_cfg.model_dump_json(indent=2), encoding="utf-8")
        return path


manager = RunManager()
