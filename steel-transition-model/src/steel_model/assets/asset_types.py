"""
Pydantic data models for steel production records, capacity records, and asset fleet containers.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from steel_model.schema.provenance import ProvenanceClass
from steel_model.technology_ids import (
    CANONICAL_TECHNOLOGY_IDS,
    UNKNOWN_TECHNOLOGY_ID,
    normalize_technology_id,
)


ALLOWED_TECHNOLOGY_IDS = set(CANONICAL_TECHNOLOGY_IDS) | {UNKNOWN_TECHNOLOGY_ID}


class ProductionRecord(BaseModel):
    """
    Data record representing reported historical or projected crude steel production.
    Production records CANNOT be converted automatically into capacity records.
    """

    technology: str = Field(..., description="Approved technology ID or UNKNOWN.")
    year: int = Field(..., description="Observation year.")
    production_mt: float = Field(..., ge=0.0, description="Reported crude steel production in Mt/year.")
    source: str = Field(..., description="Primary reference source string.")
    source_reference: Optional[str] = Field(default=None, description="Page or table reference.")
    provenance: ProvenanceClass = Field(..., description="Strict 6-tier provenance taxonomy class.")
    notes: Optional[str] = Field(default=None, description="Context notes.")

    @field_validator("technology")
    def validate_technology(cls, v: str) -> str:
        return normalize_technology_id(v)


class CapacityRecord(BaseModel):
    """
    Data record representing operational steel production capacity or representative vintage cohort.
    """

    asset_id: str = Field(..., description="Unique alphanumeric identifier for the capacity record.")
    asset_name: str = Field(..., description="Human-readable asset or cohort name.")
    technology: str = Field(..., description="Approved technology ID or UNKNOWN.")
    technology_subtype: Optional[str] = Field(default=None, description="Subtype detail e.g. Coal-DRI, Gas-DRI.")
    capacity_mt_per_year: float = Field(..., ge=0.0, description="Annual crude steel capacity in Mt/year.")
    commissioning_year: int = Field(..., description="Four-digit commissioning year or cohort mid-year.")
    retirement_year: Optional[int] = Field(default=None, description="Explicit retirement year if known.")
    lifetime_years: float = Field(..., gt=0.0, description="Technical lifetime of asset in years.")
    availability_factor: float = Field(default=0.85, ge=0.0, le=1.0, description="Physical availability factor.")
    location: Optional[str] = Field(default=None, description="Geographic location or state.")
    owner: Optional[str] = Field(default=None, description="Operating company or owner name.")
    source: str = Field(..., description="Primary reference source string.")
    source_reference: Optional[str] = Field(default=None, description="Page or table reference.")
    provenance: ProvenanceClass = Field(..., description="Strict 6-tier provenance taxonomy class.")
    confidence: str = Field(default="PROPOSAL", description="Confidence level: HIGH, MEDIUM, LOW, PROPOSAL.")
    notes: Optional[str] = Field(default=None, description="Context notes; mandatory if technology is UNKNOWN.")

    @field_validator("technology")
    def validate_technology(cls, v: str) -> str:
        return normalize_technology_id(v)

    @field_validator("notes")
    def validate_notes_for_unknown(cls, v: Optional[str], info) -> Optional[str]:
        tech = info.data.get("technology")
        if tech == UNKNOWN_TECHNOLOGY_ID and (not v or len(v.strip()) == 0):
            raise ValueError("Explicit reason in 'notes' is mandatory when technology is UNKNOWN.")
        return v

    def get_effective_retirement_year(self) -> int:
        """Return explicit retirement year if provided, else commissioning_year + int(round(lifetime_years))."""
        if self.retirement_year is not None:
            return self.retirement_year
        return self.commissioning_year + int(round(self.lifetime_years))

    def is_surviving(self, year: int) -> bool:
        """Check if asset is operational/surviving at the given target year."""
        ret_year = self.get_effective_retirement_year()
        return self.commissioning_year <= year < ret_year


# Alias for backward compatibility
AssetRecord = CapacityRecord


class AssetFleet(BaseModel):
    """
    Container managing capacity records and production records separately.
    """

    capacity_records: List[CapacityRecord] = Field(default_factory=list)
    production_records: List[ProductionRecord] = Field(default_factory=list)

    @property
    def records(self) -> List[CapacityRecord]:
        """Backward compatibility property returning capacity records."""
        return self.capacity_records

    def add_capacity_record(self, record: CapacityRecord) -> None:
        """Add capacity record ensuring unique asset_id."""
        existing_ids = {r.asset_id for r in self.capacity_records}
        if record.asset_id in existing_ids:
            raise ValueError(f"Duplicate asset_id '{record.asset_id}' found in AssetFleet capacity records.")
        self.capacity_records.append(record)

    def add_production_record(self, record: ProductionRecord) -> None:
        """Add production record to production fleet."""
        self.production_records.append(record)

    def add_record(self, record: CapacityRecord) -> None:
        """Alias for add_capacity_record."""
        self.add_capacity_record(record)

    def get_total_starting_capacity(self, technology: Optional[str] = None) -> float:
        """Get total initial operational capacity in base year 2024."""
        total = 0.0
        for r in self.capacity_records:
            if technology is None or r.technology == technology:
                if r.is_surviving(2024):
                    total += r.capacity_mt_per_year
        return total

    def get_surviving_capacity(self, year: int, technology: Optional[str] = None) -> float:
        """Calculate surviving capacity at target year."""
        total = 0.0
        for r in self.capacity_records:
            if technology is None or r.technology == technology:
                if r.is_surviving(year):
                    total += r.capacity_mt_per_year
        return total
