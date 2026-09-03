"""
Backend tests for the India Steel Transition Lab web API.

Covers: health, scenarios, validation gates (M1, EXTERNAL_PENDING, unknown
overrides, uncertainty dimensions), run lifecycle (real solve), recorded
results/diagnostics/benchmark/uncertainty/provenance, parameters, sources,
comparison, and download path-traversal protection.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from webapp.app.main import app  # noqa: E402
from webapp.app.data_store import FROZEN_BASELINE_OBJECTIVE  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _wait_for_terminal(client: TestClient, run_id: str, timeout: float = 240.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/runs/{run_id}")
        assert r.status_code == 200, r.text
        status = r.json()["status"]
        if status not in ("QUEUED", "RUNNING"):
            return r.json()
        time.sleep(0.5)
    raise AssertionError(f"Run {run_id} did not reach a terminal state within {timeout}s")


# ---------------------------------------------------------------------------
# Health & status
# ---------------------------------------------------------------------------
def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["engine_importable"] is True
    assert body["baseline_objective"] == pytest.approx(FROZEN_BASELINE_OBJECTIVE)


def test_status(client: TestClient) -> None:
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["baseline_objective"] == pytest.approx(FROZEN_BASELINE_OBJECTIVE)
    assert "methodology_strip" in body
    assert body["data_completeness"]["m1"] == "DEFERRED"


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
def test_scenarios_list(client: TestClient) -> None:
    r = client.get("/api/scenarios")
    assert r.status_code == 200
    ids = {s["id"] for s in r.json()}
    assert {"control", "cps", "nzs", "uncertainty_study", "custom"} <= ids
    for s in r.json():
        assert "description" in s and "modules" in s and "policy_rules" in s


def test_scenario_detail(client: TestClient) -> None:
    r = client.get("/api/scenarios/uncertainty_study")
    assert r.status_code == 200
    body = r.json()
    assert "uncertainty_dimensions" in body
    dims = body["uncertainty_dimensions"]
    assert set(dims) == {"policy", "scrap_level", "dri_alternative", "fleet_id"}
    assert dims["scrap_level"][0]["id"] == "SCRAP_LOW"
    assert dims["scrap_level"][0]["value"] == 1.0  # no hidden 1.08 base


def test_scenario_unknown_404(client: TestClient) -> None:
    assert client.get("/api/scenarios/nope").status_code == 404


# ---------------------------------------------------------------------------
# Validation gates
# ---------------------------------------------------------------------------
def test_m1_gate_blocked(client: TestClient) -> None:
    r = client.post(
        "/api/runs",
        json={"scenario_id": "cps", "overrides": {"use_m1_electrolyser_learning": True}},
    )
    assert r.status_code == 422
    assert "M1" in r.json()["detail"]


def test_external_pending_route_blocked(client: TestClient) -> None:
    r = client.post(
        "/api/runs",
        json={"scenario_id": "custom", "overrides": {"enabled_routes": ["BF-BOF", "Coal-DRI-IF"]}},
    )
    assert r.status_code == 422
    assert "EXTERNAL_PENDING" in r.json()["detail"]


def test_unknown_override_blocked(client: TestClient) -> None:
    r = client.post(
        "/api/runs",
        json={"scenario_id": "cps", "overrides": {"totally_unknown_key": 1}},
    )
    assert r.status_code == 422
    assert "UNKNOWN" in r.json()["detail"]


def test_unknown_scenario_blocked(client: TestClient) -> None:
    r = client.post("/api/runs", json={"scenario_id": "hack", "overrides": {}})
    assert r.status_code == 422


def test_uncertainty_dimension_validation(client: TestClient) -> None:
    r = client.post(
        "/api/runs",
        json={
            "scenario_id": "uncertainty_study",
            "uncertainty_params": {"policy": "CPS", "scrap_level": "SCRAP_MEGA"},
        },
    )
    assert r.status_code == 422
    assert "scrap_level" in r.json()["detail"]


def test_unknown_uncertainty_dimension_key(client: TestClient) -> None:
    r = client.post(
        "/api/runs",
        json={
            "scenario_id": "uncertainty_study",
            "uncertainty_params": {"magic_dimension": "x"},
        },
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Run lifecycle — real solve, baseline invariance through the API
# ---------------------------------------------------------------------------
def test_control_run_reproduces_baseline(client: TestClient) -> None:
    r = client.post("/api/runs", json={"scenario_id": "control", "overrides": {}})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "QUEUED"
    run_id = body["run_id"]

    terminal = _wait_for_terminal(client, run_id)
    assert terminal["status"] == "OPTIMAL", terminal
    assert terminal["objective"] == pytest.approx(FROZEN_BASELINE_OBJECTIVE, rel=1e-9)

    # results round-trip
    res = client.get(f"/api/runs/{run_id}/results")
    assert res.status_code == 200
    results = res.json()
    assert results["objective"] == pytest.approx(FROZEN_BASELINE_OBJECTIVE, rel=1e-9)
    assert results["solver_status"] == "OPTIMAL"
    assert len(results["yearly_results"]) == 47
    yr2024 = results["yearly_results"][0]
    assert yr2024["year"] == 2024
    # Baseline corner is 100% Scrap-EAF with null scrap intensity — reported
    # honestly as model output, with the incompleteness flags intact.
    assert results["data_completeness"] in ("INCOMPLETE", "COMPLETE")
    assert results["M1_state"] == "DEFERRED"

    # diagnostics / benchmark / uncertainty / provenance
    assert client.get(f"/api/runs/{run_id}/diagnostics").status_code == 200
    bm = client.get(f"/api/runs/{run_id}/benchmark").json()
    assert len(bm["rows"]) > 0
    unc = client.get(f"/api/runs/{run_id}/uncertainty").json()
    assert unc["metrics"]["n_valid_scenarios"] >= 24
    prov = client.get(f"/api/runs/{run_id}/provenance").json()
    assert prov["config_hash"]

    # files + downloads
    files = client.get(f"/api/runs/{run_id}/files").json()
    assert any(f["kind"] == "results" for f in files)
    dl = client.get(f"/api/runs/{run_id}/download/results.json")
    assert dl.status_code == 200


def test_path_traversal_blocked(client: TestClient) -> None:
    r = client.get("/api/runs/../../etc/passwd/download/x")
    assert r.status_code == 404  # unknown run, not a file read


def test_run_404(client: TestClient) -> None:
    assert client.get("/api/runs/does_not_exist_xyz").status_code == 404


# ---------------------------------------------------------------------------
# Recorded runs (existing results store)
# ---------------------------------------------------------------------------
def test_recorded_runs_listed(client: TestClient) -> None:
    r = client.get("/api/runs")
    assert r.status_code == 200
    runs = r.json()
    recorded = [x for x in runs if x["recorded"]]
    assert len(recorded) >= 1
    # latest recorded run's results must load
    latest = max(recorded, key=lambda x: x["created_at"])
    res = client.get(f"/api/runs/{latest['run_id']}/results")
    assert res.status_code == 200
    assert len(res.json()["yearly_results"]) == 47


# ---------------------------------------------------------------------------
# Parameters & sources
# ---------------------------------------------------------------------------
def test_parameters_endpoint(client: TestClient) -> None:
    r = client.get("/api/parameters")
    assert r.status_code == 200
    params = r.json()
    assert len(params) > 0
    pids = {p["parameter_id"] for p in params}
    # The three unresolved pathway dimensions are present and never shown as 0.
    assert "scrap_intensity_Scrap-EAF" in pids
    scrap = next(p for p in params if p["parameter_id"] == "scrap_intensity_Scrap-EAF")
    assert scrap["value"] is None
    assert scrap["status"] == "EXTERNAL_PENDING"
    # BF-BOF coking coal freeze is present.
    assert any("COKING" in p["parameter_id"] or "COKING_COAL" in p["parameter_id"] for p in params)


def test_parameter_detail(client: TestClient) -> None:
    r = client.get("/api/parameters/scrap_intensity_Scrap-EAF")
    assert r.status_code == 200
    p = r.json()
    # Bounds live in the detail dict (recorded source-supported bounds).
    assert p["detail"]["lower_bound"] == 1.0
    assert p["detail"]["upper_bound"] == 1.15
    assert p["value"] is None  # no frozen base


def test_parameter_unknown_404(client: TestClient) -> None:
    assert client.get("/api/parameters/nope").status_code == 404


def test_sources_endpoint(client: TestClient) -> None:
    r = client.get("/api/sources")
    assert r.status_code == 200
    sources = r.json()
    assert len(sources) > 0
    assert any(s["source_id"] == "IEA-ISTR-2020" for s in sources)


def test_source_detail(client: TestClient) -> None:
    r = client.get("/api/sources/IEA-ISTR-2020")
    assert r.status_code == 200
    assert r.json()["title"].startswith("Iron and Steel")


def test_source_unknown_404(client: TestClient) -> None:
    assert client.get("/api/sources/nope").status_code == 404


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def _pick_recorded_with_results(client: TestClient, n: int = 2) -> list:
    runs = client.get("/api/runs").json()
    recorded = [x for x in runs if x["recorded"]]
    picked = []
    for r_ in recorded:
        if client.get(f"/api/runs/{r_['run_id']}/results").status_code == 200:
            picked.append(r_["run_id"])
        if len(picked) >= n:
            break
    return picked


def test_compare_two_runs(client: TestClient) -> None:
    picked = _pick_recorded_with_results(client, 2)
    assert len(picked) >= 2
    a, b = picked[0], picked[1]
    r = client.post("/api/compare", json={"run_id_a": a, "run_id_b": b})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["metrics"]) >= 5
    assert any(m["metric"] == "objective" for m in body["metrics"])
    assert len(body["technology_changes"]) >= 3
    assert any("grows" in t["change_direction"] or t["change_direction"] == "unchanged" for t in body["technology_changes"])


def test_compare_missing_run(client: TestClient) -> None:
    picked = _pick_recorded_with_results(client, 1)
    assert picked
    r = client.post("/api/compare", json={"run_id_a": picked[0], "run_id_b": "nope"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Uncertainty recorded study
# ---------------------------------------------------------------------------
def test_uncertainty_endpoint(client: TestClient) -> None:
    r = client.get("/api/uncertainty")
    assert r.status_code == 200
    body = r.json()
    stats = body["metrics"]["technology_stats"]
    assert "BF-BOF" in stats
    assert stats["BF-BOF"]["presence_frequency"] == 1.0
    assert "fraction_of_tested_scenarios_above_threshold" in stats["BF-BOF"]
    assert len(body["scenarios"]) >= 24
    # No probability language in the recorded answers (recursively flattened;
    # recorded answers contain structured values, not only strings).
    def _flatten(obj) -> list:
        if isinstance(obj, dict):
            out = []
            for v in obj.values():
                out.extend(_flatten(v))
            return out
        if isinstance(obj, list):
            out = []
            for v in obj:
                out.extend(_flatten(v))
            return out
        return [str(obj)]

    joined = " ".join(_flatten(body["answers"])).lower()
    assert "probability" not in joined
    # Classification is derived from the engine (never reported as UNRESOLVED
    # across the board for the recorded study).
    bf = body["metrics"]["technology_stats"]["BF-BOF"]
    assert bf["classification"] in ("ROBUST", "CONDITIONALLY_ROBUST", "SENSITIVE", "UNRESOLVED")
    assert bf["classification"] != "UNRESOLVED"


def test_uncertainty_dimensions_endpoint(client: TestClient) -> None:
    r = client.get("/api/uncertainty/dimensions")
    assert r.status_code == 200
    body = r.json()
    assert body["scrap_levels"] == {"SCRAP_LOW": 1.0, "SCRAP_HIGH": 1.15}
    assert set(body["dri_alternatives"]) == {"DRI_IBM", "DRI_CEEW"}
    assert set(body["fleet_scenarios"]) == {
        "FLEET_CONSERVATIVE",
        "FLEET_CENTRAL",
        "FLEET_ALTERNATIVE",
    }


# ---------------------------------------------------------------------------
# Schema stability
# ---------------------------------------------------------------------------
def test_no_missing_to_zero_in_parameters(client: TestClient) -> None:
    """The unresolved pathway dimensions must have value None, never 0."""
    params = client.get("/api/parameters").json()
    pids = ["scrap_intensity_Scrap-EAF", "dri_charge_ratio_IF", "existing_capacity_BF-BOF_mt"]
    found = {p["parameter_id"]: p for p in params}
    for pid in pids:
        assert pid in found, f"missing {pid}"
        assert found[pid]["value"] is None, f"{pid} shows a value"
        assert found[pid]["status"] == "EXTERNAL_PENDING"


def test_compare_uses_stable_schema(client: TestClient) -> None:
    picked = _pick_recorded_with_results(client, 2)
    assert len(picked) >= 2
    r = client.post(
        "/api/compare",
        json={"run_id_a": picked[0], "run_id_b": picked[1]},
    )
    body = r.json()
    assert set(body.keys()) == {"run_a", "run_b", "metrics", "technology_changes", "notes"}
