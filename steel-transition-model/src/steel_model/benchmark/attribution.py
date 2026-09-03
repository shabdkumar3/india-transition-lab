"""
Difference attribution (Step 14 §12).

For every MATERIAL DIFFERENCE a row is added: difference -> potential driver
-> evidence -> confidence. Drivers are drawn from a fixed vocabulary; every
attribution must carry evidence (a file/counterfactual reference) and a
confidence level. Causality is NEVER claimed from simultaneous movement
alone — an attribution without evidence is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from steel_model.benchmark.definitions import ComparisonStatus

DRIVER_VOCABULARY = (
    "demand_path",
    "technology_economics",
    "existing_assets",
    "resource_intensities",
    "scrap_accounting",
    "deployment_constraints",
    "learning",
    "m1",
    "optimization_formulation",
    "scenario_assumptions",
    "data_completeness",
)

CONFIDENCE_LEVELS = ("HIGH", "MEDIUM", "LOW")


@dataclass(frozen=True)
class Attribution:
    metric: str
    year: int
    scenario: str
    difference_description: str
    driver: str
    evidence: str
    confidence: str

    def __post_init__(self) -> None:
        if self.driver not in DRIVER_VOCABULARY:
            raise ValueError(f"driver '{self.driver}' not in vocabulary")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"confidence '{self.confidence}' not in {CONFIDENCE_LEVELS}")
        if not self.evidence.strip():
            raise ValueError("attribution without evidence is rejected (no-causality rule)")


# Pre-built, evidence-backed attributions for the MATERIAL DIFFERENCES that
# the Step 14 comparison produces. Each evidence string points at a file or a
# reproducible counterfactual, never at simultaneous movement alone.
MATERIAL_DIFFERENCE_ATTRIBUTIONS: List[Attribution] = [
    Attribution(
        metric="technology_share", year=2070, scenario="NZS",
        difference_description="model 100% Scrap-EAF vs Vol.4 ~40% scrap / 50% H2-DRI / 10% BF-BOF+CCS",
        driver="scrap_accounting",
        evidence="Scrap-EAF/scrap intensity is null (EXTERNAL_PENDING); STEP13 audit counterfactual: "
                 "injecting 1.08 t/t flips the mix to 100% BF-BOF (STEP13_SCIENTIFIC_SANITY_AUDIT.md §1; "
                 "diagnostic_scrap_intensity.yaml)",
        confidence="HIGH",
    ),
    Attribution(
        metric="technology_share", year=2070, scenario="NZS",
        difference_description="model 100% Scrap-EAF vs Vol.4 ~40% scrap / 50% H2-DRI / 10% BF-BOF+CCS",
        driver="existing_assets",
        evidence="route-level existing capacity unresolved (existing_route_capacity_available=False); "
                 "2024 solution builds a new fleet (free fleet replacement), removing any sunk-cost "
                 "advantage of incumbent BF-BOF (STEP13_SCIENTIFIC_SANITY_AUDIT.md §3)",
        confidence="MEDIUM",
    ),
    Attribution(
        metric="technology_share", year=2070, scenario="NZS",
        difference_description="model H2-DRI-EAF = 0 vs Vol.4 50%",
        driver="technology_economics",
        evidence="H2-DRI-EAF full-plant economics EXTERNAL_PENDING; M1 deferred (no real b_elec); "
                 "route not represented (technology_space_completeness=INCOMPLETE)",
        confidence="HIGH",
    ),
    Attribution(
        metric="technology_share", year=2070, scenario="NZS",
        difference_description="model BF-BOF = 0 vs Vol.4 10% (CCS-equipped)",
        driver="technology_economics",
        evidence="no CCUS representation in the model; Vol.4 NZS BF-BOF share assumes CCUS (prose p.66)",
        confidence="HIGH",
    ),
    Attribution(
        metric="technology_share", year=2070, scenario="CPS",
        difference_description="model 100% Scrap-EAF vs Vol.4 50% BF-BOF / 25% H2 / 7% NG / 18% scrap",
        driver="scrap_accounting",
        evidence="null Scrap-EAF scrap intensity removes the ~250 USD/t x ~1.08 t/t scrap cost term; "
                 "counterfactual flip reproduced from config (diagnostic_scrap_intensity.yaml)",
        confidence="HIGH",
    ),
    Attribution(
        metric="co2_intensity", year=2050, scenario="NZS",
        difference_description="model 0.05 tCO2/t vs Vol.4 0.66 tCO2/t",
        driver="scrap_accounting",
        evidence="cornered all-Scrap-EAF mix (0.05 tCO2/t) follows from the missing scrap cost term; "
                 "with physical scrap intensity the mix flips to BF-BOF and CO2 rises to ~2.54 tCO2/t",
        confidence="HIGH",
    ),
    Attribution(
        metric="co2_total", year=2050, scenario="NZS",
        difference_description="model 31.2 Mt vs Vol.4-derived ~412 Mt CO2",
        driver="scrap_accounting",
        evidence="same mechanism as co2_intensity; arithmetic on a degenerate mix "
                 "(STEP13_SCIENTIFIC_SANITY_AUDIT.md §8)",
        confidence="HIGH",
    ),
    Attribution(
        metric="scrap_share_production", year=2050, scenario="NZS",
        difference_description="model 100% vs Vol.4 30% scrap share",
        driver="scrap_accounting",
        evidence="Mode A has no physical scrap availability constraint; RES_scrap = 0 because the "
                 "Scrap-EAF scrap intensity is null (STEP13_SCIENTIFIC_SANITY_AUDIT.md §2)",
        confidence="HIGH",
    ),
    Attribution(
        metric="scrap_share_production", year=2050, scenario="NZS",
        difference_description="model 100% vs Vol.4 30% scrap share",
        driver="optimization_formulation",
        evidence="linear cost-minimization without an emissions/availability constraint corners on the "
                 "cheapest new-build route (STEP13_SCIENTIFIC_SANITY_AUDIT.md §1)",
        confidence="MEDIUM",
    ),
    Attribution(
        metric="final_energy_steel", year=2070, scenario="CPS",
        difference_description="model ~27 Mtoe vs Vol.4 251 Mtoe (not comparable)",
        driver="data_completeness",
        evidence="model tracks only enabled-route SEC (Scrap-EAF 1.4 GJ/t); Vol.4 boundary includes "
                 "captive power and all routes (prose p.66-67)",
        confidence="MEDIUM",
    ),
]


def attribution_table(rows: List[Dict]) -> List[Dict]:
    """Return the attribution rows for all MATERIAL DIFFERENCE rows in the
    comparison table, enriched with the driver/evidence/confidence columns."""
    material = [r for r in rows if r.get("comparison_status") == ComparisonStatus.MATERIAL_DIFFERENCE.value]
    out = []
    for row in material:
        matches = [
            a for a in MATERIAL_DIFFERENCE_ATTRIBUTIONS
            if a.metric == row["metric"] and a.year == row["year"] and a.scenario == row["scenario"]
        ]
        if not matches:
            out.append({
                **{k: row.get(k) for k in ("metric", "year", "scenario", "ours", "vol4")},
                "driver": "unattributed",
                "evidence": "no evidence-backed driver on file (attribution deferred)",
                "confidence": None,
            })
            continue
        for a in matches:
            out.append({
                "metric": row["metric"],
                "year": row["year"],
                "scenario": row["scenario"],
                "ours": row.get("ours"),
                "vol4": row.get("vol4"),
                "difference_description": a.difference_description,
                "driver": a.driver,
                "evidence": a.evidence,
                "confidence": a.confidence,
            })
    return out
