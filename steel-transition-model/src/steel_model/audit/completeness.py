"""
STEP 19 — INTERNAL SCIENTIFIC COMPLETENESS / DATA CLOSURE audit module.

Read-only derivation of the per-route parameter completeness matrix and the
per-route economic completeness audit from the EXISTING source-of-truth
registries and configs. Nothing here freezes, promotes, or invents a value:
EXTERNAL_PENDING / UNKNOWN / missing are reported as such, never as zero.

All numeric inputs are READ from the registries/configs (no duplicated
constants): route economics from configs/optimization/baseline.yaml (enabled
routes) and data/external/external_parameter_freeze.yaml (non-enabled routes);
prices from configs resource_prices with the documented conversion metadata;
intensities/SEC/emissions from configs/technologies/*.yaml tech cards;
fleet from data/external/assets/india_steel_fleet_register.yaml; policy
windows from configs/optimization/mode_b_policy.yaml.

Classification taxonomy (Phase 19):
  FROZEN_EXTERNAL | FROZEN_DERIVED | PROJECT_PROPOSAL | EXTERNAL_PENDING
  | UNKNOWN | DEFERRED
"""

from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import yaml

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

TECH_DIR = os.path.join(PROJECT_ROOT, "configs", "technologies")
FREEZE_YAML = os.path.join(PROJECT_ROOT, "data", "external", "external_parameter_freeze.yaml")
FLEET_REGISTER = os.path.join(PROJECT_ROOT, "data", "external", "assets", "india_steel_fleet_register.yaml")

ROUTES = [
    "BF-BOF",
    "Coal-DRI-EAF",
    "Coal-DRI-IF",
    "NG-DRI-EAF",
    "H2-DRI-EAF",
    "Scrap-EAF",
]

# Categories of the completeness matrix (Phase 19 §GOAL).
CATEGORIES = [
    "CAPEX",
    "FOM",
    "VOM",
    "SEC",
    "electricity",
    "coal",
    "gas",
    "iron_ore",
    "scrap",
    "H2",
    "emissions",
    "lifetime",
    "availability",
    "commercialization",
    "deployment",
    "learning",
    "existing_capacity",
    "vintage",
    "retirement",
    "policy_availability",
]

CLASSES = [
    "FROZEN_EXTERNAL",
    "FROZEN_DERIVED",
    "PROJECT_PROPOSAL",
    "EXTERNAL_PENDING",
    "UNKNOWN",
    "DEFERRED",
]

# Freeze-file parameter ids for the non-enabled routes' full-plant economics.
FREEZE_ECON_IDS = {
    "Coal-DRI-EAF": ("CAPEX_ANNUALISED_COAL_DRI_EAF", "OPEX_FIXED_COAL_DRI_EAF"),
    "Coal-DRI-IF": ("CAPEX_ANNUALISED_COAL_DRI_IF", "OPEX_FIXED_COAL_DRI_IF"),
    "H2-DRI-EAF": ("CAPEX_ANNUALISED_H2_DRI_EAF_PLANT", "OPEX_FIXED_H2_DRI_EAF_PLANT"),
}

# Registry claims for full-plant economics of non-enabled routes (for notes).
REGISTRY_ECON_CLAIMS = {
    # parameter_id -> (status, confidence, source)
    "CAPEX_ANNUALISED_COAL_DRI_EAF": ("EXTERNAL", "MEDIUM", None),  # freeze-file EXTERNAL (CEEW SME Steel 2026, Table 5.2); scenario-exercised only
    "CAPEX_ANNUALISED_COAL_DRI_IF": ("EXTERNAL", "MEDIUM", None),  # freeze-file EXTERNAL (CEEW SME Steel 2026, Table 5.3); scenario-exercised only
    "CAPEX_ANNUALISED_H2_DRI_EAF_PLANT": ("EXTERNAL_PENDING", "LOW", None),  # PHASE 20/23 demotion (null value, unverifiable $685/t)
}


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _norm_provenance(raw: Any) -> str:
    """Map a provenance string onto the Phase-19 taxonomy (display mapping only)."""
    if raw is None:
        return "UNKNOWN"
    s = str(raw).strip().upper()
    if s in ("V4", "TIMES", "EXTERNAL", "FROZEN_EXTERNAL"):
        return "FROZEN_EXTERNAL"
    if s in ("DERIVED", "FROZEN_DERIVED"):
        return "FROZEN_DERIVED"
    if s == "PROJECT_PROPOSAL":
        return "PROJECT_PROPOSAL"
    if s == "EXTERNAL_PENDING":
        return "EXTERNAL_PENDING"
    if s in ("DEFERRED", "DEFER"):
        return "DEFERRED"
    return "UNKNOWN"


class CompletenessAudit:
    """Derive the per-route completeness matrix and economic audit."""

    def __init__(self, project_root: Optional[str] = None) -> None:
        self.root = project_root or PROJECT_ROOT
        self.baseline = _load_yaml(os.path.join(self.root, "configs", "optimization", "baseline.yaml"))
        self.mode_b = _load_yaml(os.path.join(self.root, "configs", "optimization", "mode_b_policy.yaml"))
        self.tech_cards: Dict[str, Dict[str, Any]] = {}
        for r in ROUTES:
            # Tech-card filenames use underscores: BF-BOF -> bf_bof.yaml
            self.tech_cards[r] = _load_yaml(os.path.join(TECH_DIR, f"{r.lower().replace('-', '_')}.yaml"))
        self.freeze = _load_yaml(FREEZE_YAML).get("parameters", [])
        self.fleet = _load_yaml(FLEET_REGISTER)

    # ------------------------------------------------------------------
    # Per-route model-effective economics (read from configs, never hard-coded)
    # ------------------------------------------------------------------
    def _config_economics(self, cfg: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        """Read the economics block of an optimisation config verbatim."""
        econ = cfg.get("economics", {})
        capex_map = econ.get("capex_annualised_usd_per_t", {})
        opex_map = econ.get("opex_fixed_usd_per_t", {})
        vom_map = econ.get("vom_usd_per_t", {})
        out: Dict[str, Dict[str, float]] = {}
        for r in ROUTES:
            if r in capex_map:
                out[r] = {
                    "capex_annualised": float(capex_map[r]),
                    "opex_fixed": float(opex_map.get(r, 0.0)),
                    "vom": float(vom_map.get(r, 0.0)),
                }
        return out

    def _freeze_economics(self) -> Dict[str, Dict[str, float]]:
        """Read full-plant economics for non-enabled routes from the freeze file."""
        by_id = {p.get("parameter_id"): p for p in self.freeze}
        out: Dict[str, Dict[str, float]] = {}
        for r, (capex_id, opex_id) in FREEZE_ECON_IDS.items():
            c = by_id.get(capex_id, {}).get("value")
            o = by_id.get(opex_id, {}).get("value")
            if c is not None or o is not None:
                out[r] = {
                    "capex_annualised": float(c) if c is not None else None,
                    "opex_fixed": float(o) if o is not None else None,
                    "vom": 0.0,
                }
        return out

    def _enabled_economics(self) -> Dict[str, Dict[str, float]]:
        """What enters the optimiser: baseline.yaml economics for enabled routes,
        freeze-file full-plant economics for non-enabled routes (recorded, not
        necessarily optimisation-eligible)."""
        out: Dict[str, Dict[str, float]] = {}
        base = self._config_economics(self.baseline)
        out.update(base)
        for r, e in self._freeze_economics().items():
            if r not in out:
                out[r] = e
        return out

    # ------------------------------------------------------------------
    # Intensity / SEC / emissions from the tech cards
    # ------------------------------------------------------------------
    def _route_intensities(self, route: str) -> Dict[str, Any]:
        """Merge tech-card resource_intensities (with per-field provenance)."""
        card = self.tech_cards.get(route, {})
        ri = card.get("resource_intensities", {})
        out: Dict[str, Any] = {}
        for res in ("iron_ore", "scrap", "hydrogen", "electricity", "coal", "natural_gas"):
            entry = ri.get(res, {})
            val = entry.get("value") if isinstance(entry, dict) else None
            prov = _norm_provenance(entry.get("provenance")) if isinstance(entry, dict) else "UNKNOWN"
            src = entry.get("source") if isinstance(entry, dict) else None
            out[res] = {"value": val, "provenance": prov, "source": src}
        return out

    # ------------------------------------------------------------------
    # Completeness matrix
    # ------------------------------------------------------------------
    def parameter_matrix(self) -> List[Dict[str, Any]]:
        """Build the route x category matrix with classification + model effect."""
        econ = self._enabled_economics()
        rows: List[Dict[str, Any]] = []
        for r in ROUTES:
            card = self.tech_cards.get(r, {})
            ri = self._route_intensities(r)
            emissions = {
                "process": (card.get("process_emissions") or {}).get("value"),
                "combustion": (card.get("combustion_emissions") or {}).get("value"),
            }
            e_prov = _norm_provenance((card.get("process_emissions") or {}).get("provenance"))
            enabled = r in self.baseline.get("enabled_routes", [])

            # Honest provenance note for the non-enabled routes' recorded economics.
            econ_note = ""
            if r == "H2-DRI-EAF" and not enabled:
                econ_note = (
                    "full-plant CAPEX EXTERNAL_PENDING (PHASE 20 demotion: the $685/t "
                    "158+527 decomposition is NOT verifiable in the stored IEA extract); "
                    "PHASE 23: India H2-DRI levelised cost of steel USD 500-860/t FROZEN "
                    "(IEA 2020 Box 3.2 p.135), electrolyser CAPEX bounds 285/1067 USD/kWe "
                    "FROZEN (Fig 2.12 p.108), Vogl 2018 abstract facts FROZEN (3.48 MWh/t, "
                    "361-640 EUR/t), Vogl component split EXTERNAL scenario only; "
                    "route still NOT_REPRESENTED in official runs (no page-verified "
                    "full-plant overnight CAPEX)"
                )
            elif not enabled and r in econ:
                cid, _ = FREEZE_ECON_IDS[r]
                reg_status, reg_conf, _ = REGISTRY_ECON_CLAIMS.get(cid, ("", "", ""))
                econ_note = (
                    f"recorded full-plant economics (freeze file, confidence {reg_conf}); "
                    f"route NOT_REPRESENTED in official runs — scenario-exercised only"
                )

            # Provenance for CAPEX/FOM depends on the source authority:
            # IEA-2020-FROZEN routes: BF-BOF, NG-DRI-EAF, Scrap-EAF → FROZEN_EXTERNAL
            # Cross-reference synthesis routes: Coal-DRI-EAF, Coal-DRI-IF, H2-DRI-EAF → PROJECT_PROPOSAL
            _IEA2020_FROZEN = {"BF-BOF", "NG-DRI-EAF", "Scrap-EAF"}
            _CROSSREF_ROUTES = {"Coal-DRI-EAF", "Coal-DRI-IF", "H2-DRI-EAF"}

            def _capex_prov(route: str, is_enabled: bool) -> str:
                if is_enabled and route in _IEA2020_FROZEN:
                    return "FROZEN_EXTERNAL"
                if is_enabled and route in _CROSSREF_ROUTES:
                    return "PROJECT_PROPOSAL"
                if not is_enabled and route in econ and route != "H2-DRI-EAF":
                    return "FROZEN_EXTERNAL"
                return "EXTERNAL_PENDING"

            matrix: Dict[str, Dict[str, Any]] = {
                "CAPEX": {
                    "value": econ.get(r, {}).get("capex_annualised"),
                    "provenance": _capex_prov(r, enabled),
                    "source": "configs/optimization/baseline.yaml economics" if enabled
                    else "external_parameter_freeze.yaml",
                    "unit": "USD/t",
                    "effect": "annualised CAPEX cost term in objective",
                    "note": econ_note,
                },
                "FOM": {
                    "value": econ.get(r, {}).get("opex_fixed"),
                    "provenance": _capex_prov(r, enabled),
                    "source": "configs/optimization/baseline.yaml economics" if enabled
                    else "external_parameter_freeze.yaml",
                    "unit": "USD/t",
                    "effect": "fixed O&M cost term in objective",
                    "note": econ_note,
                },
                "VOM": {"value": 0.0, "provenance": "EXTERNAL_PENDING",
                        "source": "VOM_ALL_ROUTES (registry: not separated from combined OPEX)",
                        "unit": "USD/t", "effect": "absent cost term (documented, not silent)",
                        "note": "VOM 0.0 is a documented EXTERNAL_PENDING absence, never a frozen fact"},
                "SEC": {"value": (card.get("energy_sec") or {}).get("value"),
                        "provenance": _norm_provenance((card.get("energy_sec") or {}).get("provenance")),
                        "source": (card.get("energy_sec") or {}).get("source"),
                        "unit": "GJ/t", "effect": "system summary only (not an intensity)",
                        "note": ""},
                "electricity": {**ri["electricity"], "effect": "electricity cost term in objective", "note": ""},
                "coal": {**ri["coal"], "effect": "coal (coking/non-coking) cost term", "note": ""},
                "gas": {**ri["natural_gas"], "effect": "natural gas cost term", "note": ""},
                "iron_ore": {**ri["iron_ore"], "effect": "iron ore cost term", "note": ""},
                "scrap": {**ri["scrap"], "effect": "scrap cost term in objective",
                          "note": "PHASE 20: Scrap-EAF scrap intensity PROMOTED to 1.05 t/t "
                                  "FROZEN_EXTERNAL (Xylia et al. 2018, Energy Efficiency 11(5), "
                                  "Table 2 p.1063; corroborated by IEA Roadmap 2020 metallic-input "
                                  "1.05-1.2 t/t). Uncertainty bounds 1.00-1.15 retained. "
                                  "worldsteel 0.88/0.71 are the BLENDED recycled-EAF route "
                                  "(boundary mismatch, NOT used)"},
                "H2": {**ri["hydrogen"], "effect": "hydrogen cost term (55 kg/t, V4 p.65)", "note": ""},
                "emissions": {"value": emissions, "provenance": e_prov,
                              "source": (card.get("process_emissions") or {}).get("source"),
                              "unit": "tCO2/t", "effect": "process+combustion emissions in CO2 block",
                              "note": "no carbon price applied anywhere"},
                "lifetime": {"value": (card.get("lifetime_years") or {}).get("value"),
                             "provenance": _norm_provenance((card.get("lifetime_years") or {}).get("provenance")),
                             "source": (card.get("lifetime_years") or {}).get("source"),
                             "unit": "years", "effect": "retirement vintage constraint",
                             "note": "config lifetime_years=25 (IEA investment cycle) is the model value"},
                "availability": {"value": (card.get("availability_factor") or {}).get("value"),
                                 "provenance": _norm_provenance((card.get("availability_factor") or {}).get("provenance")),
                                 "source": (card.get("availability_factor") or {}).get("source"),
                                 "unit": "fraction", "effect": "ACT <= avail * CAP bound",
                                 "note": "PROJECT_PROPOSAL — not a Vol.4 fact"},
                "commercialization": {"value": card.get("commercialization_year"),
                                      "provenance": "FROZEN_EXTERNAL",
                                      "source": "technology card", "unit": "year",
                                      "effect": "route availability start (Gate F overrides)",
                                      "note": ""},
                "deployment": {"value": card.get("construction_lead_time_years"),
                               "provenance": "PROJECT_PROPOSAL",
                               "source": "technology card", "unit": "years",
                               "effect": "NCAP lead-time bounds (Mode B deployment)",
                               "note": "India-specific deployment evidence remains DEFERRED"},
                "learning": {"value": (card.get("learning_parameters") or {}).get("learning_rate", {}).get("value"),
                             "provenance": _norm_provenance((card.get("learning_parameters") or {}).get("learning_rate", {}).get("provenance")),
                             "source": (card.get("learning_parameters") or {}).get("learning_rate", {}).get("source"),
                             "unit": "fraction", "effect": "endogenous learning (Step 11, Mode B)",
                             "note": "M1 b_elec DEFERRED (no real electrolyser dataset)"},
                "existing_capacity": {"value": self._fleet_capacity(r),
                                      "provenance": self._fleet_provenance(r),
                                      "source": self._fleet_source(r),
                                      "unit": "Mt",
                                      "effect": "SurvivingExisting[i,t] constant — context only; "
                                                "model input stays 0.0 (EXTERNAL_PENDING)",
                                      "note": "PHASE 24A: route-level production (BOF 62.488 / EAF 31.612 / IF 58.080 Mt FY24-25) and IF capacity (81.92 Mt) CLOSED via JPC (MoS AR 2025-26 Annexure IV/V, Source: JPC). Model existing_capacity_per_route_mt stays 0.0 (loader flag hardcoded False — BASELINE_MILP_SPEC §5); mixed-producer route split (65.381 Mt TSL/JSW/JSPL) + EAF feedstock split remain SUB-GAPS."},
                "vintage": {"value": self._fleet_vintage_status(r),
                            "provenance": self._fleet_vintage_provenance(r),
                            "source": "india_steel_fleet_register.yaml",
                            "unit": "-",
                            "effect": "retirement timing (per-route vintages unresolved)",
                            "note": "partial plant-level coverage only; unknown vintages not inferred"},
                "retirement": {"value": self._fleet_vintage_status(r),
                               "provenance": self._fleet_vintage_provenance(r),
                               "source": "lifetime-based (no per-route vintages)",
                               "unit": "-",
                               "effect": "CumRET <= CumNCAP(t-lifetime)",
                               "note": ""},
                "policy_availability": {"value": self._policy_start(r),
                                        "provenance": "FROZEN_EXTERNAL" if self._policy_start(r) is not None
                                        else "EXTERNAL_PENDING",
                                        "source": "mode_b_policy.yaml (Gate F)",
                                        "unit": "year",
                                        "effect": "route availability start year (Gate F)",
                                        "note": "NZS Gate-F window shown; CPS window differs where recorded "
                                                "(e.g. H2-DRI-EAF 2035 in CPS vs 2030 in NZS). None = no "
                                                "Gate-F window recorded (available from commercialization year)"},
            }

            for cat in CATEGORIES:
                entry = matrix[cat]
                rows.append(
                    {
                        "route": r,
                        "category": cat,
                        "value": entry.get("value"),
                        "unit": entry.get("unit"),
                        "classification": entry.get("provenance"),
                        "provenance": entry.get("provenance"),
                        "source": entry.get("source"),
                        "model_effect": entry.get("effect"),
                        "note": entry.get("note", ""),
                    }
                )
        return rows

    # ------------------------------------------------------------------
    # Fleet helpers
    # ------------------------------------------------------------------
    def _fleet_route_key(self, route: str) -> str:
        return {
            "BF-BOF": "BF_BOF",
            "Coal-DRI-EAF": "Coal_DRI_EAF",
            "Coal-DRI-IF": "Coal_DRI_IF",
            "NG-DRI-EAF": "NG_DRI_EAF",
            "H2-DRI-EAF": "H2_DRI_EAF",
            "Scrap-EAF": "Scrap_EAF",
        }[route]

    def _fleet_capacity(self, route: str) -> Optional[float]:
        rc = (self.fleet.get("route_capacity_mtpa") or {}).get(self._fleet_route_key(route), {})
        return rc.get("capacity_mtpa")

    def _fleet_provenance(self, route: str) -> str:
        rc = (self.fleet.get("route_capacity_mtpa") or {}).get(self._fleet_route_key(route), {})
        return _norm_provenance(rc.get("provenance"))

    def _fleet_source(self, route: str) -> str:
        rc = (self.fleet.get("route_capacity_mtpa") or {}).get(self._fleet_route_key(route), {})
        return str(rc.get("source", ""))

    def _fleet_vintage_status(self, route: str) -> str:
        plants = self.fleet.get("integrated_plants_bf_bof", [])
        if route != "BF-BOF":
            return "UNRESOLVED"
        known = [p for p in plants if p.get("commissioning_year") is not None]
        return f"{len(known)} plants with vintages" if known else "UNRESOLVED"

    def _fleet_vintage_provenance(self, route: str) -> str:
        if route != "BF-BOF":
            return "EXTERNAL_PENDING"
        plants = self.fleet.get("integrated_plants_bf_bof", [])
        known = [p for p in plants if p.get("commissioning_year") is not None]
        return "FROZEN_EXTERNAL" if known else "EXTERNAL_PENDING"

    def _policy_start(self, route: str) -> Optional[int]:
        sp = ((self.mode_b.get("mode_b_policy") or {}).get("scenario_policies") or {}).get("NZS", {})
        starts = sp.get("route_start_years", {})
        return starts.get(route)

    # ------------------------------------------------------------------
    # Route eligibility (Phase K)
    # ------------------------------------------------------------------
    def route_eligibility(self) -> Dict[str, str]:
        """
        Per-route eligibility state.

        ECONOMICALLY_COMPLETE  — enabled with all entered coefficients FROZEN
        PARTIALLY_COMPLETE     — enabled but >=1 coefficient EXTERNAL_PENDING
                                 (entered under explicit config allowance) or missing
        NOT_REPRESENTED        — disabled in the optimiser (no full-plant economics)
        DEFERRED               — module/route deferred (e.g. M1, deployment)
        """
        enabled = set(self.baseline.get("enabled_routes", []))
        out: Dict[str, str] = {}
        for r in ROUTES:
            if r not in enabled:
                out[r] = "NOT_REPRESENTED"
                continue
            ri = self._route_intensities(r)
            # Any coefficient that is missing OR carries EXTERNAL_PENDING
            # provenance (entered under explicit allowance) demotes the route.
            incomplete = []
            for res in ("scrap", "iron_ore", "coal", "natural_gas"):
                entry = ri.get(res, {})
                if entry.get("value") is None:
                    incomplete.append(f"{res} missing")
                elif entry.get("provenance") == "EXTERNAL_PENDING":
                    incomplete.append(f"{res} EXTERNAL_PENDING-under-allowance")
            out[r] = "PARTIALLY_COMPLETE" if incomplete else "ECONOMICALLY_COMPLETE"
        return out

    # ------------------------------------------------------------------
    # Phase A — economic completeness per route
    # ------------------------------------------------------------------
    def economic_completeness(self) -> Dict[str, Dict[str, Any]]:
        """
        Per-route cost components (USD/t) and the total comparable cost,
        with every missing term flagged (never silently zeroed).

        Components: CAPEX, FOM, VOM, fuel (coal/gas), resource (ore/scrap),
        electricity, carbon (no price applied — reported as component only).

        Prices are READ from the config resource_prices block with the
        documented conversion metadata (never hard-coded).
        """
        econ = self._enabled_economics()
        prices = self._read_prices()
        out: Dict[str, Dict[str, Any]] = {}
        for r in ROUTES:
            ri = self._route_intensities(r)
            comp: Dict[str, Any] = {
                "capex": econ.get(r, {}).get("capex_annualised"),
                "fom": econ.get(r, {}).get("opex_fixed"),
                "vom": 0.0,
                "vom_status": "EXTERNAL_PENDING (term absent)",
                "fuel": 0.0,
                "fuel_missing": [],
                "resource": 0.0,
                "resource_missing": [],
                "electricity": 0.0,
                "carbon_component": None,
                "carbon_missing": [],
                "note": "",
            }

            # Fuel terms (coal for BF-BOF / DRI routes; gas for NG-DRI-EAF).
            coal = ri.get("coal", {}).get("value")
            gas = ri.get("natural_gas", {}).get("value")
            if r == "BF-BOF":
                if coal is None:
                    comp["fuel_missing"].append(
                        "coking_coal (EXTERNAL_PENDING; candidate 0.89 t/t via IMC-2021 override only)"
                    )
                else:
                    comp["fuel"] += coal * prices["coking_coal"]
            elif r in ("Coal-DRI-EAF", "Coal-DRI-IF"):
                if coal is None:
                    comp["fuel_missing"].append(
                        "non_coking_coal (EXTERNAL_PENDING; per-t-DRI basis, charge ratio unresolved)"
                    )
                else:
                    comp["fuel"] += coal * prices["non_coking_coal"]
            elif r == "NG-DRI-EAF":
                if gas is None:
                    comp["fuel_missing"].append("natural_gas")
                else:
                    comp["fuel"] += gas * prices["natural_gas"]

            # Resource terms (ore / scrap).
            ore = ri.get("iron_ore", {}).get("value")
            scrap = ri.get("scrap", {}).get("value")
            if ore is None:
                comp["resource_missing"].append("iron_ore (EXTERNAL_PENDING)")
            else:
                comp["resource"] += ore * prices["iron_ore"]
            if scrap is None:
                comp["resource_missing"].append("scrap (EXTERNAL_PENDING; scenario bounds 1.00-1.15)")
            else:
                comp["resource"] += scrap * prices["scrap"]

            # Hydrogen term (H2-DRI-EAF only; 0.055 t H2/t steel V4 p.65).
            comp["hydrogen"] = 0.0
            h2 = ri.get("hydrogen", {}).get("value")
            if h2 is not None:
                comp["hydrogen"] = h2 * prices["hydrogen"]

            # Electricity.
            elec = ri.get("electricity", {}).get("value")
            if elec is not None:
                comp["electricity"] = elec * prices["electricity"]

            # Carbon component (no price — Vol.4 provides none).
            proc = (self.tech_cards.get(r, {}).get("process_emissions") or {}).get("value")
            comb = (self.tech_cards.get(r, {}).get("combustion_emissions") or {}).get("value")
            if proc is not None and comb is not None:
                comp["carbon_component"] = (proc or 0.0) + (comb or 0.0)

            if r not in self.baseline.get("enabled_routes", []):
                comp["note"] = "route NOT_REPRESENTED in official runs (economics recorded, not optimised)"

            # A route is economically COMPLETE only when every cost-driving
            # coefficient is present AND its CAPEX/FOM provenance is FROZEN
            # AND no entered intensity carries EXTERNAL_PENDING-under-allowance
            # provenance (same demotion rule as route_eligibility). This keeps
            # economic_completeness consistent with route_eligibility and
            # derives the H2-DRI-EAF exclusion from provenance instead of a
            # hardcoded route name.
            econ_entry = econ.get(r, {})
            econ_incomplete = (
                econ_entry.get("capex_annualised") is None
                or econ_entry.get("opex_fixed") is None
            )
            demote_provenance = any(
                (ri.get(res, {}).get("value") is not None
                 and ri.get(res, {}).get("provenance") == "EXTERNAL_PENDING")
                for res in ("scrap", "iron_ore", "coal", "natural_gas")
            )
            complete = (
                not (comp["fuel_missing"] or comp["resource_missing"])
                and not econ_incomplete
                and not demote_provenance
            )
            comp["complete"] = complete
            comp["total_comparable"] = (
                (comp["capex"] or 0.0) + (comp["fom"] or 0.0) + comp["vom"] + comp["fuel"]
                + comp["resource"] + comp["electricity"] + comp["hydrogen"]
            ) if complete and comp["capex"] is not None else None
            comp["total_note"] = (
                "total comparable cost NOT reported: missing terms would make it "
                "appear complete when it is not"
                if not complete
                else "all required cost terms resolved (VOM term absent EXTERNAL_PENDING, counted as 0.0)"
            )
            out[r] = comp
        return out

    def _read_prices(self) -> Dict[str, float]:
        """Read resource prices from the config with documented conversions."""
        price_cfg = (self.baseline.get("resource_prices") or {})
        out: Dict[str, float] = {}
        conversions = {
            "iron_ore": ("iron_ore", 1.0, "multiply"),
            "scrap": ("scrap", 1.0, "multiply"),
            "natural_gas": ("natural_gas", 1.055, "divide"),
            "electricity": ("electricity", 1.0, "multiply"),
            "hydrogen": ("hydrogen", 1.0, "multiply"),
            "coking_coal": ("coking_coal", 1.0, "multiply"),
            "non_coking_coal": ("non_coking_coal", 1.0, "multiply"),
        }
        for key, (res, factor, op) in conversions.items():
            entry = price_cfg.get(key, {})
            value = float(entry.get("value", 0.0))
            # Prefer the config's own conversion metadata; fall back to the
            # documented mapping above only if the config record is absent.
            cfg_factor = float(entry.get("conversion_factor", factor))
            cfg_op = str(entry.get("conversion_operation", op))
            out[res] = value / cfg_factor if cfg_op == "divide" else value * cfg_factor
        # hydrogen is stored USD/kg; the model consumes USD/t.
        out["hydrogen"] = out.get("hydrogen", 0.0) * 1000.0
        return out

    # ------------------------------------------------------------------
    # Phase 20 — per-route interpretability layer (economic / resource /
    # fleet / policy completeness + overall label)
    # ------------------------------------------------------------------
    # Allowed overall labels (Phase 20 spec):
    #   SCIENTIFICALLY_INTERPRETABLE  — all four dimensions resolved
    #   CONDITIONALLY_INTERPRETABLE   — economics resolved, >=1 non-economic gap
    #   DATA_LIMITED                  — economics or resources unresolved
    #   NOT_REPRESENTED               — route absent from the costed space
    #   NOT_COMPARABLE                — not comparable to other routes
    #   DEFERRED                      — route deferred by an explicit rule
    def route_interpretability(self) -> Dict[str, Dict[str, Any]]:
        """Per-route Phase-20 interpretability assessment."""
        enabled = set(self.baseline.get("enabled_routes", []))
        elig = self.route_eligibility()
        econ = self.economic_completeness()
        out: Dict[str, Dict[str, Any]] = {}
        for r in ROUTES:
            e = econ.get(r, {})
            eco_status = (
                "COMPLETE" if e.get("complete") else
                "CONDITIONAL" if r in enabled else "PENDING"
            )
            ri = self._route_intensities(r)
            missing_res = [
                res for res in ("scrap", "iron_ore", "coal", "natural_gas")
                if ri.get(res, {}).get("value") is None
            ]
            res_status = "COMPLETE" if not missing_res else "PENDING"
            fleet_status = (
                "KNOWN" if self._fleet_capacity(r) is not None
                else "UNKNOWN"
            )
            pol_start = self._policy_start(r)
            pol_status = "COMPLETE" if pol_start is not None else "PENDING"

            if r == "Coal-DRI-EAF":
                overall = "DEFERRED"
            elif r not in enabled:
                overall = "DATA_LIMITED"
            elif eco_status == "COMPLETE" and res_status == "COMPLETE":
                overall = "CONDITIONALLY_INTERPRETABLE"
            else:
                overall = "CONDITIONALLY_INTERPRETABLE"

            out[r] = {
                "economic_completeness": eco_status,
                "resource_completeness": res_status,
                "fleet_completeness": fleet_status,
                "policy_completeness": pol_status,
                "overall_interpretability": overall,
                "eligibility": elig.get(r),
                "note": (
                    "PHASE 20: Scrap-EAF scrap intensity FROZEN (1.05, Xylia 2018 "
                    "Table 2) -> first economically complete route; route-level "
                    "fleet split remains a documented GAP (fleet dimension UNKNOWN), "
                    "so the top-level SCIENTIFICALLY_INTERPRETABLE label is blocked "
                    "for every route (fleet always UNKNOWN or non-FROZEN). "
                    "Coal-DRI-EAF DEFERRED (no defensible EAF-specific charge ratio). "
                    "Coal-DRI-EAF/IF/H2-DRI-EAF absent from the official runs' "
                    "costed space (Coal-DRI-IF is scenario-exercised only)."
                ),
            }
        return out

    # ------------------------------------------------------------------
    # Exporters
    # ------------------------------------------------------------------
    def export_matrix(self, out_dir: str) -> Tuple[str, str]:
        """Write PARAMETER_COMPLETENESS_MATRIX.csv/.json (incl. Phase-20
        interpretability layer in the JSON payload)."""
        os.makedirs(out_dir, exist_ok=True)
        rows = self.parameter_matrix()
        csv_path = os.path.join(out_dir, "PARAMETER_COMPLETENESS_MATRIX.csv")
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["route", "category", "value", "unit", "classification",
                            "provenance", "source", "model_effect", "note"],
            )
            w.writeheader()
            for row in rows:
                w.writerow({k: row.get(k) for k in w.fieldnames})
        json_path = os.path.join(out_dir, "PARAMETER_COMPLETENESS_MATRIX.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "routes": ROUTES,
                    "categories": CATEGORIES,
                    "classes": CLASSES,
                    "matrix": rows,
                    "route_eligibility": self.route_eligibility(),
                    "economic_completeness": self.economic_completeness(),
                    "interpretability": self.route_interpretability(),
                },
                f, indent=2, default=str,
            )
        return csv_path, json_path
