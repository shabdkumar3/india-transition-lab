"""
Loader for resource intensity, EnergySEC, H2 electrolysis, and emissions records
from the steel_intensities.yaml configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional
import yaml

from steel_model.resources.resource_types import (
    ResourceIntensityRecord,
    EnergySECRecord,
    H2ElectrolysisRecord,
    EmissionsRecord,
)
from steel_model.schema.provenance import ProvenanceClass


@dataclass
class IntensityDataset:
    """Container holding all parsed resource/intensity records."""
    resource_intensities: List[ResourceIntensityRecord] = field(default_factory=list)
    energy_sec: List[EnergySECRecord] = field(default_factory=list)
    h2_electrolysis: Optional[H2ElectrolysisRecord] = None
    emissions: List[EmissionsRecord] = field(default_factory=list)


def _parse_provenance(raw: dict, key: str = "provenance") -> ProvenanceClass:
    val = raw.get(key, "UNKNOWN")
    return ProvenanceClass(val)


class IntensityLoader:
    """
    Parses steel_intensities.yaml into validated typed records.
    """

    @classmethod
    def load(cls, yaml_path: str) -> IntensityDataset:
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"Intensity YAML not found: '{yaml_path}'")

        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict):
            raise ValueError(f"Invalid YAML structure in '{yaml_path}'.")

        dataset = IntensityDataset()

        # --- H2 Electrolysis (system-level singleton) ---
        if "h2_electrolysis" in raw:
            h = raw["h2_electrolysis"]
            dataset.h2_electrolysis = H2ElectrolysisRecord(
                value=h.get("value"),
                unit=h.get("unit", "MWh/t H2"),
                year_start=h.get("year_start", 2024),
                year_end=h.get("year_end"),
                scenario=h.get("scenario", "ALL"),
                provenance=_parse_provenance(h),
                source=h.get("source", ""),
                source_page=h.get("source_page"),
                source_definition=h.get("source_definition"),
                confidence=h.get("confidence", "HIGH"),
                notes=h.get("notes"),
            )

        # --- Energy SEC records ---
        for item in raw.get("energy_sec", []):
            rec = EnergySECRecord(
                technology_id=item["technology_id"],
                value=item.get("value"),
                unit=item.get("unit", "GJ/t steel"),
                year_start=item.get("year_start", 2024),
                year_end=item.get("year_end"),
                scenario=item.get("scenario", "ALL"),
                provenance=_parse_provenance(item),
                source=item.get("source", ""),
                source_page=item.get("source_page"),
                source_definition=item.get("source_definition"),
                confidence=item.get("confidence", "MEDIUM"),
                derivation_formula=item.get("derivation_formula"),
                notes=item.get("notes"),
            )
            dataset.energy_sec.append(rec)

        # --- Resource intensity records ---
        for item in raw.get("resource_intensities", []):
            rec = ResourceIntensityRecord(
                technology_id=item["technology_id"],
                resource_id=item["resource_id"],
                value=item.get("value"),
                unit=item.get("unit", "t/t steel"),
                year_start=item.get("year_start", 2024),
                year_end=item.get("year_end"),
                scenario=item.get("scenario", "ALL"),
                provenance=_parse_provenance(item),
                source=item.get("source", ""),
                source_page=item.get("source_page"),
                source_definition=item.get("source_definition"),
                confidence=item.get("confidence", "MEDIUM"),
                uncertainty_min=item.get("uncertainty_min"),
                uncertainty_max=item.get("uncertainty_max"),
                derivation_formula=item.get("derivation_formula"),
                notes=item.get("notes"),
            )
            dataset.resource_intensities.append(rec)

        # --- Emissions records ---
        for item in raw.get("emissions", []):
            rec = EmissionsRecord(
                technology_id=item["technology_id"],
                emission_type=item["emission_type"],
                value=item.get("value"),
                unit=item.get("unit", "tCO2/t steel"),
                accounting_method=item.get("accounting_method", "activity_based"),
                year_start=item.get("year_start", 2024),
                year_end=item.get("year_end"),
                scenario=item.get("scenario", "ALL"),
                provenance=_parse_provenance(item),
                source=item.get("source", ""),
                source_page=item.get("source_page"),
                source_definition=item.get("source_definition"),
                confidence=item.get("confidence", "MEDIUM"),
                notes=item.get("notes"),
            )
            dataset.emissions.append(rec)

        return dataset
