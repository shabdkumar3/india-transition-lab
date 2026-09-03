"""
Type definitions for steel demand observations and datasets.
"""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field, model_validator
from steel_model.schema.provenance import ProvenanceClass


class DemandRecord(BaseModel):
    """
    Single steel demand observation record with mandatory provenance metadata.
    """
    year: int = Field(..., ge=2000, le=2100, description="Observation year")
    scenario: str = Field(..., description="Scenario identifier (CPS or NZS)")
    demand_mt: float = Field(..., ge=0.0, description="Crude steel demand in Million Tonnes (Mt)")
    source: str = Field(..., description="Authoritative source document title")
    source_page: str = Field(..., description="Exact page or table reference in source document")
    provenance: ProvenanceClass = Field(..., description="Provenance classification (must be V4 for published baseline)")
    unit: str = Field("Mt", description="Physical unit of demand (must be Mt)")

    @model_validator(mode="after")
    def validate_demand_record(self) -> "DemandRecord":
        """Enforce unit and provenance rules."""
        if self.unit != "Mt":
            raise ValueError(f"Demand unit must be 'Mt', got '{self.unit}'")
        if self.scenario not in ["CPS", "NZS"]:
            raise ValueError(f"Scenario must be 'CPS' or 'NZS', got '{self.scenario}'")
        return self


class DemandDataset(BaseModel):
    """
    Container storing collection of demand records.
    """
    records: List[DemandRecord] = Field(default_factory=list, description="Demand observation records")

    def get_demand(self, year: int, scenario: str = "CPS") -> Optional[float]:
        """Retrieve demand in Mt for a specific year and scenario, or None if absent."""
        for rec in self.records:
            if rec.year == year and rec.scenario == scenario:
                return rec.demand_mt
        return None

    def get_anchor_years(self, scenario: str = "CPS") -> List[int]:
        """Return list of available anchor years for a scenario."""
        return sorted([rec.year for rec in self.records if rec.scenario == scenario])

    def has_year(self, year: int, scenario: str = "CPS") -> bool:
        """Check if demand value exists for a specific year and scenario."""
        return self.get_demand(year, scenario) is not None

    def to_dict_map(self, scenario: str = "CPS") -> Dict[int, float]:
        """Return a mapping of year -> demand_mt for a given scenario."""
        return {rec.year: rec.demand_mt for rec in self.records if rec.scenario == scenario}
