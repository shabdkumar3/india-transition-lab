"""
Ablation analysis (Step 14 §13): one methodological layer at a time.

Layers: Vol.4 benchmark (target) -> control MILP -> +scrap (Mode B dynamic
scrap) -> +deployment (lead times / ceilings) -> +learning (endogenous).

Honest findings this module surfaces:
  - +scrap (Mode B) is vacuous on the mix because the Scrap-EAF scrap
    intensity is null, so the scrap availability constraint is not binding.
  - +deployment is INFEASIBLE without route-level existing capacity
    (2024 demand cannot be served under construction lead times).
  - +learning is DEFERRED: steel-route learning rates are EXTERNAL_PENDING;
    no rates are fabricated.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from steel_model.benchmark.vol4_register import Vol4Register

LAYERS = ("control", "scrap", "deployment", "learning")


def _summary(result: Any, inputs: Any) -> Dict[str, Optional[float]]:
    if result.status != 0 or result.objective_value is None:
        return {"objective": None, "mix_2050": None, "mix_2070": None,
                "co2_2050": None, "co2_2070": None, "scrap_share_2050": None}
    demand = {t: float(inputs.demand_mt.get(t, 0.0)) for t in inputs.years}
    return {
        "objective": round(float(result.objective_value), 2),
        "mix_2050": {r: round(float(result.production_share(r)[2050]), 4) for r in result.routes},
        "mix_2070": {r: round(float(result.production_share(r)[2070]), 4) for r in result.routes},
        "co2_2050": round(float(result.co2_total_mt.get(2050, 0.0)), 2),
        "co2_2070": round(float(result.co2_total_mt.get(2070, 0.0)), 2),
        "scrap_share_2050": round(float(result.production_share("Scrap-EAF")[2050]), 4),
    }


def build_ablation(
    register: Vol4Register,
    runs: Dict[str, Any],  # layer -> (inputs, result) OR (inputs, None, note)
) -> List[Dict[str, Any]]:
    """Build ablation rows. runs['deployment']/['learning'] may carry
    (inputs, result_or_None, status_note) via dict value."""
    rows: List[Dict[str, Any]] = []

    # Target row (Vol.4) — no run, published values only.
    target = {
        "layer": "vol4_benchmark",
        "status": "published_target",
        "objective": None,
        "mix_2050": "not published numerically (Figure 3.5 chart)",
        "mix_2070": {"BF-BOF": 0.10, "H2-DRI-EAF": 0.50, "Scrap-EAF": 0.40},
        "co2_2050": None,
        "co2_2070": None,
        "scrap_share_2050": register.scrap_share(2050, "NZS"),
        "note": "Vol.4 NZS reference (prose p.66): 10% BF-BOF+CCS / 50% H2-DRI / 40% scrap",
    }
    rows.append(target)

    for layer in ("control", "scrap", "deployment", "learning"):
        entry = runs.get(layer)
        if entry is None:
            rows.append({
                "layer": layer, "status": "not_run", "objective": None,
                "mix_2050": None, "mix_2070": None, "co2_2050": None,
                "co2_2070": None, "scrap_share_2050": None,
                "note": "layer not run",
            })
            continue
        inputs, result, note = entry
        if result is None:
            status = "deferred" if (note or "").startswith("DEFERRED") else "not_run"
            rows.append({
                "layer": layer, "status": status,
                "objective": None, "mix_2050": None, "mix_2070": None,
                "co2_2050": None, "co2_2070": None, "scrap_share_2050": None,
                "note": note,
            })
            continue
        s = _summary(result, inputs)
        if s["objective"] is None:
            rows.append({
                "layer": layer, "status": "infeasible", "objective": None,
                "mix_2050": None, "mix_2070": None, "co2_2050": None,
                "co2_2070": None, "scrap_share_2050": None, "note": note or "infeasible",
            })
            continue
        rows.append({
            "layer": layer, "status": "solved",
            **s,
            "note": note or "",
        })
    return rows


def to_csv(rows: List[Dict[str, Any]], path: str) -> None:
    import csv
    os.makedirs(os.path.dirname(path), exist_ok=True)
    keys = ["layer", "status", "objective", "mix_2050", "mix_2070",
            "co2_2050", "co2_2070", "scrap_share_2050", "note"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: json.dumps(r.get(k)) if isinstance(r.get(k), (dict,)) else r.get(k)
                             for k in keys})


def to_json(rows: List[Dict[str, Any]], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)