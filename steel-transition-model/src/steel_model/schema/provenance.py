"""
Data provenance schema enforcing 6-tier classification taxonomy for all model parameters.
"""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator


class ProvenanceClass(str, Enum):
    """Data provenance classification taxonomy."""
    V4 = "V4"
    TIMES = "TIMES"
    DERIVED = "DERIVED"
    EXTERNAL = "EXTERNAL"
    EXTERNAL_PENDING = "EXTERNAL_PENDING"
    EXTERNAL_CROSSREF = "EXTERNAL_CROSSREF"  # Cross-referenced from multiple sources
    PROJECT_PROPOSAL = "PROJECT_PROPOSAL"
    UNKNOWN = "UNKNOWN"


class ProvenanceRecord(BaseModel):
    """
    Metadata container storing parameter provenance, source references,
    derivation formulas, and uncertainty bounds.
    """
    parameter_name: str = Field(..., description="Unique name of the parameter")
    technology: Optional[str] = Field(None, description="Steel route ID if applicable")
    resource: Optional[str] = Field(None, description="Resource ID if applicable")
    year: Optional[int] = Field(None, description="Applicable year if time-dependent")
    scenario: Optional[str] = Field(None, description="Applicable scenario (CPS/NZS) if scenario-specific")
    value: Any = Field(..., description="Numerical or categorical parameter value")
    unit: str = Field(..., description="Physical or economic unit of measurement")
    provenance: ProvenanceClass = Field(..., description="6-tier provenance classification")
    source: str = Field(..., description="Authoritative source document or database title")
    page_or_section: Optional[str] = Field(None, description="Exact page, table, or section reference")
    derivation_formula: Optional[str] = Field(None, description="Formula used if provenance is DERIVED")
    uncertainty_min: Optional[float] = Field(None, description="Lower bound of uncertainty range")
    uncertainty_max: Optional[float] = Field(None, description="Upper bound of uncertainty range")
    notes: Optional[str] = Field(None, description="Additional context or scientific notes")

    @model_validator(mode="after")
    def validate_provenance_integrity(self) -> "ProvenanceRecord":
        """Enforce validation rules based on provenance tier."""
        if self.provenance == ProvenanceClass.DERIVED and not self.derivation_formula:
            raise ValueError("DERIVED parameters must specify a derivation_formula.")
        if self.provenance == ProvenanceClass.V4 and "Vol. 4" not in self.source and "Sectoral Insights: Industry" not in self.source:
            raise ValueError(f"[V4] parameters must reference Vol. 4 in source, got '{self.source}'")
        return self
