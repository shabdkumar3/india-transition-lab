"""
Technology card schema defining attributes and resource intensities for steel production routes.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field, model_validator
from .provenance import ProvenanceRecord


class TechnologyCard(BaseModel):
    """
    Data container for a steel production route technology card, storing thermodynamic,
    physical, economic, and availability parameters along with their provenance records.
    """
    route_id: str = Field(..., description="Unique technology route identifier (e.g. BF-BOF, H2-DRI-EAF)")
    route_name: str = Field(..., description="Full descriptive name of the route")
    energy_sec_gj_per_t: float = Field(..., ge=0.0, description="Specific Energy Consumption in GJ / t crude steel")
    resource_intensities: Dict[str, Optional[float]] = Field(
        default_factory=dict,
        description="Map of physical resource input intensities. Pending coefficients remain explicit as null."
    )
    process_emission_factor_tco2_per_t: float = Field(..., ge=0.0, description="Process IPPU emission factor in tCO2 / t steel")
    combustion_emission_factor_tco2_per_t: float = Field(..., ge=0.0, description="Direct combustion emission factor in tCO2 / t steel")
    lifetime_years: int = Field(..., gt=0, description="Technical operating lifetime in years")
    availability_factor: float = Field(0.90, ge=0.0, le=1.0, description="Physical availability operating bound")
    plf_cost_scaling: float = Field(0.80, ge=0.0, le=1.0, description="Uniform PLF investment capacity scaling factor")
    commercialization_year: int = Field(2024, description="Earliest year technology can be commissioned")
    construction_lead_time_years: int = Field(3, ge=0, description="Construction lead time in years")
    capex_usd_per_t: Optional[float] = Field(None, ge=0.0, description="Capital expenditure in USD / t annual capacity")
    fom_usd_per_t_year: Optional[float] = Field(None, ge=0.0, description="Fixed O&M cost in USD / t capacity / year")
    vom_usd_per_t: Optional[float] = Field(None, ge=0.0, description="Variable O&M cost in USD / t steel produced")
    provenance_records: List[ProvenanceRecord] = Field(default_factory=list, description="Associated provenance records")

    @model_validator(mode="after")
    def validate_resource_intensity_keys(self) -> "TechnologyCard":
        """Verify that mandatory physical resources are represented."""
        expected_resources = {"iron_ore", "scrap", "hydrogen", "electricity"}
        missing = expected_resources - set(self.resource_intensities.keys())
        if missing:
            raise ValueError(f"TechnologyCard '{self.route_id}' is missing required resource intensity keys: {missing}")
        return self
