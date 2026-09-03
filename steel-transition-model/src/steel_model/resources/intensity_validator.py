"""
Validator for resource intensity, EnergySEC, H2 electrolysis, and emissions records.
"""

from typing import List, Set
from steel_model.resources.resource_types import (
    ResourceIntensityRecord,
    EnergySECRecord,
    H2ElectrolysisRecord,
    EmissionsRecord,
    APPROVED_TECHNOLOGY_IDS,
    APPROVED_RESOURCE_IDS,
)
from steel_model.schema.provenance import ProvenanceClass


class IntensityValidator:
    """
    Validates collections of resource/intensity records for completeness,
    provenance consistency, unit integrity, and separation rules.
    """

    REQUIRED_RESOURCES_PER_TECHNOLOGY = {
        "BF-BOF":        {"iron_ore", "scrap", "coking_coal", "electricity_route"},
        "Coal-DRI-EAF":  {"iron_ore", "scrap", "non_coking_coal", "electricity_route"},
        "Coal-DRI-IF":   {"iron_ore", "scrap", "non_coking_coal", "electricity_route"},
        "NG-DRI-EAF":    {"iron_ore", "scrap", "natural_gas",    "electricity_route"},
        "H2-DRI-EAF":    {"iron_ore", "scrap", "hydrogen",       "electricity_route"},
        "Scrap-EAF":     {"scrap",              "electricity_route"},
    }

    @classmethod
    def validate_no_duplicates(cls, records: List[ResourceIntensityRecord]) -> None:
        """Ensure no two records share the same (technology_id, resource_id, year_start, scenario)."""
        seen: Set[tuple] = set()
        for r in records:
            key = (r.technology_id, r.resource_id, r.year_start, r.scenario)
            if key in seen:
                raise ValueError(
                    f"Duplicate ResourceIntensityRecord: technology={r.technology_id}, "
                    f"resource={r.resource_id}, year_start={r.year_start}, scenario={r.scenario}"
                )
            seen.add(key)

    @classmethod
    def validate_provenance_mandatory(cls, records: List[ResourceIntensityRecord]) -> None:
        """Ensure every record has a provenance classification."""
        for r in records:
            if r.provenance is None:
                raise ValueError(
                    f"Missing provenance for {r.technology_id} / {r.resource_id}"
                )

    @classmethod
    def validate_units_consistent(cls, records: List[ResourceIntensityRecord]) -> None:
        """Verify unit consistency per resource_id across all technology records."""
        resource_units: dict = {}
        for r in records:
            if r.resource_id not in resource_units:
                resource_units[r.resource_id] = r.unit
            else:
                if resource_units[r.resource_id] != r.unit:
                    raise ValueError(
                        f"Unit inconsistency for resource '{r.resource_id}': "
                        f"'{resource_units[r.resource_id]}' vs '{r.unit}' in {r.technology_id}"
                    )

    @classmethod
    def validate_no_electricity_h2_in_routes(cls, records: List[ResourceIntensityRecord]) -> None:
        """Ensure electricity_h2 does not appear as a route-level intensity record."""
        for r in records:
            if r.resource_id == "electricity_h2":
                raise ValueError(
                    f"electricity_h2 found as route-level ResourceIntensityRecord in {r.technology_id}. "
                    "Electrolysis electricity must be handled at system level only."
                )

    @classmethod
    def validate_no_v4_claims_without_source(cls, records: List[ResourceIntensityRecord]) -> None:
        """Verify [V4] provenance records actually reference Vol. 4."""
        for r in records:
            if r.provenance == ProvenanceClass.V4:
                if "Vol. 4" not in r.source and "Sectoral Insights: Industry" not in r.source:
                    raise ValueError(
                        f"[V4] record for {r.technology_id}/{r.resource_id} does not reference Vol. 4 "
                        f"in source: '{r.source}'"
                    )

    @classmethod
    def validate_all_six_technologies_represented(
        cls, sec_records: List[EnergySECRecord]
    ) -> None:
        """Ensure all six approved technologies have an EnergySEC record."""
        present = {r.technology_id for r in sec_records}
        missing = APPROVED_TECHNOLOGY_IDS - present
        if missing:
            raise ValueError(
                f"Missing EnergySEC records for technologies: {sorted(missing)}"
            )

    @classmethod
    def validate_sec_separated_from_intensities(
        cls,
        intensity_records: List[ResourceIntensityRecord],
        sec_records: List[EnergySECRecord],
    ) -> None:
        """Verify that EnergySEC records are NOT mixed into resource intensity records."""
        for r in intensity_records:
            if "GJ/t steel" == r.unit and r.resource_id not in {"natural_gas"}:
                raise ValueError(
                    f"ResourceIntensityRecord {r.technology_id}/{r.resource_id} uses unit 'GJ/t steel' "
                    "which is the SEC unit. Only natural_gas may use GJ/t. "
                    "All other intensities must use physical units. Check if this should be EnergySECRecord."
                )

    @classmethod
    def validate_all(
        cls,
        intensity_records: List[ResourceIntensityRecord],
        sec_records: List[EnergySECRecord],
    ) -> None:
        """Run all validators against the complete resource/intensity dataset."""
        cls.validate_no_duplicates(intensity_records)
        cls.validate_provenance_mandatory(intensity_records)
        cls.validate_units_consistent(intensity_records)
        cls.validate_no_electricity_h2_in_routes(intensity_records)
        cls.validate_no_v4_claims_without_source(intensity_records)
        cls.validate_all_six_technologies_represented(sec_records)
        cls.validate_sec_separated_from_intensities(intensity_records, sec_records)
