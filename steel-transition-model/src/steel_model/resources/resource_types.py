"""
Resource/Intensity Engine — data model layer.

Strict separation is enforced:

1. ResourceIntensityRecord  — physical input requirement per tonne of crude steel
                              (iron ore, scrap, coal, natural gas, hydrogen).
2. EnergySECRecord          — total specific energy consumption (GJ/t steel).
   EnergySEC is NEVER used as a ResourceIntensity field.
3. ElectricityIntensityRecord — electricity consumed by the steel-making route itself
                                (MWh/t steel). EXCLUDES upstream electrolysis.
4. H2ElectrolysisRecord     — electricity consumed to produce green H2
                               (MWh/t H2, [V4] = 55). Combined with H2Intensity
                               ONLY at system level, NEVER inside a route record.
5. EmissionsRecord          — combustion + process CO2 intensities, kept separate.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from steel_model.schema.provenance import ProvenanceClass
from steel_model.technology_ids import CANONICAL_TECHNOLOGY_IDS


# ──────────────────────────────────────────────────────────────────────────────
# Approved technology and resource identifiers
# ──────────────────────────────────────────────────────────────────────────────

APPROVED_TECHNOLOGY_IDS = set(CANONICAL_TECHNOLOGY_IDS)

APPROVED_RESOURCE_IDS = {
    "iron_ore",
    "scrap",
    "coking_coal",
    "non_coking_coal",
    "natural_gas",
    "hydrogen",
    "electricity_route",      # electricity consumed by steelmaking route itself
    "electricity_h2",         # electricity consumed by H2 electrolysis (system level only)
    "coke",
    "limestone",
    "oxygen",
}

APPROVED_EMISSION_TYPES = {
    "combustion",    # CO2 from burning fuels (Scope 1 direct energy)
    "process",       # CO2 from IPPU / chemical reactions (e.g. limestone calcination, sinter)
}


def _validate_tech_id(v: str) -> str:
    if v not in APPROVED_TECHNOLOGY_IDS:
        raise ValueError(
            f"Invalid technology_id '{v}'. Approved: {sorted(APPROVED_TECHNOLOGY_IDS)}"
        )
    return v


def _validate_resource_id(v: str) -> str:
    if v not in APPROVED_RESOURCE_IDS:
        raise ValueError(
            f"Invalid resource_id '{v}'. Approved: {sorted(APPROVED_RESOURCE_IDS)}"
        )
    return v


# ──────────────────────────────────────────────────────────────────────────────
# 1. ResourceIntensityRecord
# ──────────────────────────────────────────────────────────────────────────────

class ResourceIntensityRecord(BaseModel):
    """
    Physical input requirement per tonne of crude steel output.

    ResourceIntensity(i, r, t) — unit depends on resource.

    This record MUST NOT be used for EnergySEC or electricity-for-H2.
    """

    technology_id: str = Field(..., description="Approved steel route ID.")
    resource_id: str = Field(..., description="Approved resource identifier.")
    value: Optional[float] = Field(..., description="Coefficient value; None if EXTERNAL_PENDING/UNKNOWN.")
    unit: str = Field(..., description="Physical unit of the resource intensity.")
    year_start: int = Field(2024, description="Start year of validity (default: base year 2024).")
    year_end: Optional[int] = Field(None, description="End year of validity; None = time-invariant.")
    scenario: str = Field("ALL", description="Scenario applicability: ALL, CPS, NZS, etc.")
    provenance: ProvenanceClass = Field(..., description="6-tier provenance taxonomy.")
    source: str = Field(..., description="Primary reference source.")
    source_page: Optional[str] = Field(None, description="Exact page or table reference.")
    source_definition: Optional[str] = Field(None, description="Exact definition as given in source.")
    confidence: str = Field("MEDIUM", description="HIGH / MEDIUM / LOW / PROPOSAL / PENDING.")
    uncertainty_min: Optional[float] = Field(None, description="Lower bound of uncertainty range.")
    uncertainty_max: Optional[float] = Field(None, description="Upper bound of uncertainty range.")
    derivation_formula: Optional[str] = Field(None, description="Formula if provenance is DERIVED.")
    notes: Optional[str] = Field(None, description="Scientific context or audit notes.")

    @field_validator("technology_id")
    @classmethod
    def check_technology_id(cls, v: str) -> str:
        return _validate_tech_id(v)

    @field_validator("resource_id")
    @classmethod
    def check_resource_id(cls, v: str) -> str:
        return _validate_resource_id(v)

    @field_validator("value")
    @classmethod
    def check_non_negative(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0.0:
            raise ValueError(f"ResourceIntensity value cannot be negative, got {v}")
        return v

    @model_validator(mode="after")
    def check_derived_has_formula(self) -> "ResourceIntensityRecord":
        if self.provenance == ProvenanceClass.DERIVED and not self.derivation_formula:
            raise ValueError("DERIVED ResourceIntensityRecord must specify derivation_formula.")
        return self

    @model_validator(mode="after")
    def check_electricity_h2_not_in_route(self) -> "ResourceIntensityRecord":
        """Prevent electricity_h2 from being used inside a route-level intensity record."""
        if self.resource_id == "electricity_h2":
            raise ValueError(
                "electricity_h2 (electrolysis electricity) must NOT be stored as a route-level "
                "ResourceIntensityRecord. Use H2ElectrolysisRecord and combine at system level only."
            )
        return self


# ──────────────────────────────────────────────────────────────────────────────
# 2. EnergySECRecord
# ──────────────────────────────────────────────────────────────────────────────

class EnergySECRecord(BaseModel):
    """
    Total Specific Energy Consumption for a steel route.

    EnergySEC(i, t)  [GJ/t steel]

    This is a SYSTEM-level summary metric. It is NEVER used as a resource
    intensity field and must not be decomposed into per-resource values here.
    """

    technology_id: str = Field(..., description="Approved steel route ID.")
    value: Optional[float] = Field(..., description="SEC in GJ/t steel; None if EXTERNAL_PENDING.")
    unit: str = Field("GJ/t steel", description="Must be GJ/t steel.")
    year_start: int = Field(2024, description="Start year of validity.")
    year_end: Optional[int] = Field(None, description="End year; None = time-invariant.")
    scenario: str = Field("ALL", description="Scenario scope.")
    provenance: ProvenanceClass = Field(..., description="6-tier provenance taxonomy.")
    source: str = Field(..., description="Primary reference source.")
    source_page: Optional[str] = Field(None, description="Exact page or table reference.")
    source_definition: Optional[str] = Field(None, description="Exact definition as given in source.")
    confidence: str = Field("MEDIUM", description="HIGH / MEDIUM / LOW / PROPOSAL / PENDING.")
    derivation_formula: Optional[str] = Field(None, description="Formula if provenance is DERIVED.")
    notes: Optional[str] = Field(None, description="Context or audit notes.")

    @field_validator("technology_id")
    @classmethod
    def check_technology_id(cls, v: str) -> str:
        return _validate_tech_id(v)

    @field_validator("unit")
    @classmethod
    def check_unit(cls, v: str) -> str:
        if v != "GJ/t steel":
            raise ValueError(f"EnergySECRecord unit must be 'GJ/t steel', got '{v}'.")
        return v

    @field_validator("value")
    @classmethod
    def check_non_negative(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0.0:
            raise ValueError(f"EnergySEC cannot be negative, got {v}")
        return v

    @model_validator(mode="after")
    def check_derived_has_formula(self) -> "EnergySECRecord":
        if self.provenance == ProvenanceClass.DERIVED and not self.derivation_formula:
            raise ValueError("DERIVED EnergySECRecord must specify derivation_formula.")
        return self


# ──────────────────────────────────────────────────────────────────────────────
# 3. H2ElectrolysisRecord  — system-level, not route-level
# ──────────────────────────────────────────────────────────────────────────────

class H2ElectrolysisRecord(BaseModel):
    """
    Electricity required to produce green hydrogen via electrolysis.

    H2Elec_intensity = 55 MWh/t H2  [V4]

    This is a SYSTEM-LEVEL parameter, not embedded inside H2-DRI-EAF route.
    Combination with H2Intensity(i, t) happens ONLY at system level:

        ElecForH2Steel(t) = H2AllocatedToSteel(t) × 55  [MWh/t H2]

    Never embed this inside a route electricity intensity record.
    """

    value: Optional[float] = Field(..., description="Electricity per tonne H2 produced [MWh/t H2].")
    unit: str = Field("MWh/t H2", description="Must be MWh/t H2.")
    year_start: int = Field(2024, description="Start year of validity.")
    year_end: Optional[int] = Field(None, description="End year; None = time-invariant.")
    scenario: str = Field("ALL", description="Scenario scope.")
    provenance: ProvenanceClass = Field(..., description="6-tier provenance taxonomy.")
    source: str = Field(..., description="Primary reference source.")
    source_page: Optional[str] = Field(None, description="Page or table reference.")
    source_definition: Optional[str] = Field(None, description="Definition as given in source.")
    confidence: str = Field("HIGH", description="Confidence level.")
    notes: Optional[str] = Field(None, description="Context notes.")

    @field_validator("unit")
    @classmethod
    def check_unit(cls, v: str) -> str:
        if v != "MWh/t H2":
            raise ValueError(f"H2ElectrolysisRecord unit must be 'MWh/t H2', got '{v}'.")
        return v

    @field_validator("value")
    @classmethod
    def check_non_negative(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0.0:
            raise ValueError(f"H2 electrolysis intensity cannot be negative, got {v}")
        return v


# ──────────────────────────────────────────────────────────────────────────────
# 4. EmissionsRecord
# ──────────────────────────────────────────────────────────────────────────────

class EmissionsRecord(BaseModel):
    """
    CO2 emission intensity for a steel route, separated by type.

    combustion_emissions: from fuel combustion (activity-based or fuel-input-based).
    process_emissions: from IPPU / chemical reactions (limestone, sinter, etc.).

    The two must never be summed without explicit documentation.
    """

    technology_id: str = Field(..., description="Approved steel route ID.")
    emission_type: str = Field(..., description="'combustion' or 'process'.")
    value: Optional[float] = Field(..., description="CO2 intensity in tCO2/t steel; None if UNKNOWN.")
    unit: str = Field("tCO2/t steel", description="Must be tCO2/t steel.")
    accounting_method: str = Field(
        ...,
        description="'activity_based', 'fuel_input_based', or 'process_based'."
    )
    year_start: int = Field(2024, description="Start year of validity.")
    year_end: Optional[int] = Field(None, description="End year; None = time-invariant.")
    scenario: str = Field("ALL", description="Scenario scope.")
    provenance: ProvenanceClass = Field(..., description="6-tier provenance taxonomy.")
    source: str = Field(..., description="Primary reference source.")
    source_page: Optional[str] = Field(None, description="Page or table reference.")
    source_definition: Optional[str] = Field(None, description="Definition as given in source.")
    confidence: str = Field("MEDIUM", description="Confidence level.")
    notes: Optional[str] = Field(None, description="Context or audit notes.")

    @field_validator("technology_id")
    @classmethod
    def check_technology_id(cls, v: str) -> str:
        return _validate_tech_id(v)

    @field_validator("emission_type")
    @classmethod
    def check_emission_type(cls, v: str) -> str:
        if v not in APPROVED_EMISSION_TYPES:
            raise ValueError(
                f"emission_type '{v}' not approved. Must be one of {sorted(APPROVED_EMISSION_TYPES)}"
            )
        return v

    @field_validator("unit")
    @classmethod
    def check_unit(cls, v: str) -> str:
        if v != "tCO2/t steel":
            raise ValueError(f"EmissionsRecord unit must be 'tCO2/t steel', got '{v}'.")
        return v

    @field_validator("value")
    @classmethod
    def check_non_negative(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0.0:
            raise ValueError(f"Emission intensity cannot be negative, got {v}")
        return v

    @field_validator("accounting_method")
    @classmethod
    def check_accounting_method(cls, v: str) -> str:
        allowed = {"activity_based", "fuel_input_based", "process_based"}
        if v not in allowed:
            raise ValueError(f"accounting_method '{v}' not in {sorted(allowed)}")
        return v
