"""
Vol.4 benchmark register (Step 14).

Loads the machine-readable register of PUBLISHED Vol.4 quantities from
configs/benchmark/vol4_register.yaml and exposes typed accessors. The
register is the single source of truth for the Vol.4 side of every
benchmark comparison; it is validated on load (no missing sections) so a
comparison can never silently compare against an empty number.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

import yaml

_DEFAULT_REGISTER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "configs", "benchmark", "vol4_register.yaml",
)


class Vol4Register:
    """Read-only accessor over the published Vol.4 benchmark quantities."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        path = config_path or _DEFAULT_REGISTER
        if not os.path.exists(path):
            raise FileNotFoundError(f"Vol.4 benchmark register not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f)
        self._require("demand", "technology_mix_2070", "scrap_share",
                      "emission_intensity", "final_energy_mtoe",
                      "green_h2_steel_mt", "route_sec_gj_t")

    def _require(self, *sections: str) -> None:
        missing = [s for s in sections if s not in self._data]
        if missing:
            raise ValueError(
                f"Vol.4 register missing required sections: {missing}"
            )

    # ---- demand -----------------------------------------------------
    def demand_anchor(self, year: int, scenario: str = "BOTH") -> Optional[float]:
        """Published crude steel production anchor (Mt)."""
        for row in self._data["demand"]:
            if int(row["year"]) == year and row["scenario"] in ("BOTH", scenario):
                return float(row["value"])
        return None

    # ---- technology mix 2070 ----------------------------------------
    def mix_share_2070(self, scenario: str, route: str) -> Optional[float]:
        """Vol.4 published 2070 route share of production (None if not published)."""
        table = self._data["technology_mix_2070"].get(scenario)
        if table is None:
            return None
        return table.get(route)

    def mix_note_2070(self, scenario: str) -> str:
        return str(self._data["technology_mix_2070"].get(scenario, {}).get("note", ""))

    # ---- scrap share ------------------------------------------------
    def scrap_share(self, year: int, scenario: str) -> Optional[float]:
        for row in self._data["scrap_share"]:
            if int(row["year"]) == year:
                return row.get(scenario)
        return None

    # ---- emission intensity -----------------------------------------
    def emission_intensity(self, year: int, scenario: str) -> Optional[float]:
        """Derived sector-average CO2 intensity: 2.54 x (1 - reduction)."""
        base = float(self._data["emission_intensity"]["base_2025"])
        red = self._data["emission_intensity"]["reduction"].get(scenario, {})
        if year not in red:
            return None
        return round(base * (1.0 - float(red[year])), 6)

    # ---- energy -----------------------------------------------------
    def final_energy_mtoe(self, year: int, scenario: str) -> Optional[float]:
        for row in self._data["final_energy_mtoe"]:
            if int(row["year"]) == year:
                return row.get(scenario)
        return None

    def coal_use_mtoe(self, year: int, scenario: str) -> Optional[float]:
        for row in self._data["coal_use_mtoe"]:
            if int(row["year"]) == year:
                return row.get(scenario)
        return None

    def electricity_mtoe(self, year: int, scenario: str) -> Optional[float]:
        for row in self._data["electricity_mtoe"]:
            if int(row["year"]) == year:
                return row.get(scenario)
        return None

    def green_h2_steel_mt(self, year: int, scenario: str) -> Optional[float]:
        for row in self._data["green_h2_steel_mt"]:
            if int(row["year"]) == year:
                return row.get(scenario)
        return None

    # ---- SEC --------------------------------------------------------
    def route_sec_gj_t(self, route: str) -> Optional[float]:
        return self._data["route_sec_gj_t"].get(route)

    # ---- investment -------------------------------------------------
    def investment(self, key: str) -> Optional[float]:
        return self._data["investment_usd_trillion"].get(key)

    def fleet_context(self, key: str) -> Optional[float]:
        return self._data["fleet_context"].get(key)
