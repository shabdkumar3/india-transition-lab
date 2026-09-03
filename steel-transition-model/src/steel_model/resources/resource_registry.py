"""
Resource Registry — query interface for intensity coefficients.

Provides typed lookup methods for:
  - ResourceIntensity(i, r, t)
  - EnergySEC(i, t)
  - H2Intensity(i, t)  — steel-route H2 input
  - ElecForH2Steel(t)  — SYSTEM-LEVEL, combined here only
  - EmissionsIntensity(i, emission_type, t)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from steel_model.resources.resource_types import (
    ResourceIntensityRecord,
    EnergySECRecord,
    H2ElectrolysisRecord,
    EmissionsRecord,
    APPROVED_TECHNOLOGY_IDS,
)
from steel_model.resources.intensity_loader import IntensityDataset
from steel_model.resources.intensity_validator import IntensityValidator


class ResourceRegistry:
    """
    Immutable registry providing typed access to validated resource/intensity coefficients.
    """

    def __init__(self, dataset: IntensityDataset) -> None:
        # Validate on construction
        IntensityValidator.validate_all(dataset.resource_intensities, dataset.energy_sec)

        self._intensities: List[ResourceIntensityRecord] = dataset.resource_intensities
        self._sec: List[EnergySECRecord] = dataset.energy_sec
        self._h2_elec: Optional[H2ElectrolysisRecord] = dataset.h2_electrolysis
        self._emissions: List[EmissionsRecord] = dataset.emissions

        # Build lookup indices
        self._intensity_index: Dict[Tuple, ResourceIntensityRecord] = {}
        for r in self._intensities:
            key = (r.technology_id, r.resource_id, r.year_start, r.scenario)
            self._intensity_index[key] = r

        self._sec_index: Dict[Tuple, EnergySECRecord] = {}
        for r in self._sec:
            key = (r.technology_id, r.year_start, r.scenario)
            self._sec_index[key] = r

    # ──────────────────────────────────────────────────────────────────────────
    # Resource Intensity  ResourceIntensity(i, r, t)
    # ──────────────────────────────────────────────────────────────────────────

    def get_resource_intensity(
        self,
        technology_id: str,
        resource_id: str,
        year: int = 2024,
        scenario: str = "ALL",
    ) -> Optional[ResourceIntensityRecord]:
        """Return ResourceIntensityRecord for (technology, resource, year, scenario)."""
        key = (technology_id, resource_id, year, scenario)
        if key in self._intensity_index:
            return self._intensity_index[key]
        # Fallback: find the most recent record with year_start <= year
        candidates = [
            r for r in self._intensities
            if r.technology_id == technology_id
            and r.resource_id == resource_id
            and r.scenario == scenario
            and r.year_start <= year
            and (r.year_end is None or r.year_end >= year)
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda r: r.year_start, reverse=True)[0]

    def get_intensity_value(
        self,
        technology_id: str,
        resource_id: str,
        year: int = 2024,
        scenario: str = "ALL",
    ) -> Optional[float]:
        """
        Return the RAW stored numeric value for a record, or None if no record
        exists or the record's value field is None.

        NOTE (Step 13 remediation): this method returns the stored value
        REGARDLESS of provenance. A record marked EXTERNAL_PENDING may carry a
        retained working value (e.g. BF-BOF iron_ore 1.45); this method returns
        it. Provenance ELIGIBILITY for optimization is enforced by the
        provenance gate (steel_model.schema.provenance_policy) inside the
        optimization loader — never by this registry method.
        """
        rec = self.get_resource_intensity(technology_id, resource_id, year, scenario)
        if rec is None:
            return None
        return rec.value

    # ──────────────────────────────────────────────────────────────────────────
    # Energy SEC  EnergySEC(i, t)
    # ──────────────────────────────────────────────────────────────────────────

    def get_energy_sec(
        self,
        technology_id: str,
        year: int = 2024,
        scenario: str = "ALL",
    ) -> Optional[EnergySECRecord]:
        """Return EnergySECRecord for (technology, year, scenario)."""
        key = (technology_id, year, scenario)
        if key in self._sec_index:
            return self._sec_index[key]
        candidates = [
            r for r in self._sec
            if r.technology_id == technology_id
            and r.scenario == scenario
            and r.year_start <= year
            and (r.year_end is None or r.year_end >= year)
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda r: r.year_start, reverse=True)[0]

    # ──────────────────────────────────────────────────────────────────────────
    # H2 system-level combination  (ONLY here, never in route records)
    # ──────────────────────────────────────────────────────────────────────────

    def get_h2_electrolysis_intensity(self) -> Optional[float]:
        """Return H2 electrolysis electricity intensity in MWh/t H2 (system-level)."""
        if self._h2_elec is None:
            return None
        return self._h2_elec.value

    def calculate_elec_for_h2_steel(
        self,
        technology_id: str,
        year: int = 2024,
        scenario: str = "ALL",
    ) -> Optional[float]:
        """
        System-level combination (ONLY):
            ElecForH2Steel(t) = H2Intensity(i, t) [kg/t] × H2Elec [MWh/t H2] / 1000

        Returns MWh/t steel, or None if either component is unavailable.
        Note: This must NOT be added to electricity_route intensity.
        """
        h2_rec = self.get_resource_intensity(technology_id, "hydrogen", year, scenario)
        if h2_rec is None or h2_rec.value is None:
            return None

        h2_elec = self.get_h2_electrolysis_intensity()
        if h2_elec is None:
            return None

        # h2_rec.value is in kg H2/t steel, h2_elec is MWh/t H2
        return (h2_rec.value / 1000.0) * h2_elec

    # ──────────────────────────────────────────────────────────────────────────
    # Emissions
    # ──────────────────────────────────────────────────────────────────────────

    def get_emissions(
        self,
        technology_id: str,
        emission_type: str,
        year: int = 2024,
        scenario: str = "ALL",
    ) -> Optional[EmissionsRecord]:
        """Return EmissionsRecord for (technology, emission_type, year, scenario)."""
        candidates = [
            e for e in self._emissions
            if e.technology_id == technology_id
            and e.emission_type == emission_type
            and e.scenario == scenario
            and e.year_start <= year
            and (e.year_end is None or e.year_end >= year)
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda r: r.year_start, reverse=True)[0]

    # ──────────────────────────────────────────────────────────────────────────
    # Coverage summary
    # ──────────────────────────────────────────────────────────────────────────

    def get_coverage_summary(self) -> Dict[str, dict]:
        """Return a provenance coverage summary for all technologies."""
        summary = {}
        for tech in sorted(APPROVED_TECHNOLOGY_IDS):
            sec = self.get_energy_sec(tech)
            summary[tech] = {
                "energy_sec": {
                    "value": sec.value if sec else None,
                    "provenance": sec.provenance.value if sec else "MISSING",
                },
                "resource_intensities": {},
                "emissions": {},
            }
            for res in self._intensities:
                if res.technology_id == tech:
                    summary[tech]["resource_intensities"][res.resource_id] = {
                        "value": res.value,
                        "unit": res.unit,
                        "provenance": res.provenance.value,
                        "confidence": res.confidence,
                    }
            for em in self._emissions:
                if em.technology_id == tech:
                    summary[tech]["emissions"][em.emission_type] = {
                        "value": em.value,
                        "provenance": em.provenance.value,
                    }
        return summary
