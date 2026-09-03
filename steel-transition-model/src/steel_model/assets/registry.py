"""
AssetRegistry managing existing capacity Persistence, vintage distribution queries, and MILP capacity equation support.
"""

from typing import Dict, List, Optional, Tuple
from steel_model.assets.asset_types import AssetFleet, AssetRecord
from steel_model.assets.vintage_engine import VintageEngine


class AssetRegistry:
    """
    Central registry managing existing asset fleets, enforcing separation of existing capacity vs new investments.
    """

    def __init__(self, fleet: AssetFleet):
        self.fleet = fleet

    def get_surviving_capacity(self, year: int, technology: Optional[str] = None) -> float:
        """
        Calculate ExistingSurvivingCapacity(i, t) = sum_v ExistingCapacity(i, v) * Survival(v, t).
        """
        return VintageEngine.calculate_surviving_capacity(self.fleet, year=year, technology=technology)

    def get_total_starting_capacity(self, technology: Optional[str] = None) -> float:
        """Get total operational existing capacity in 2024."""
        return self.fleet.get_total_starting_capacity(technology=technology)

    def get_cumulative_retired_existing_capacity(self, year: int, technology: Optional[str] = None) -> float:
        """Calculate total cumulative retired existing capacity up to year t."""
        return VintageEngine.calculate_retired_capacity_cumulative(self.fleet, year=year, technology=technology)

    def calculate_installed_capacity(
        self,
        technology: str,
        year: int,
        cumulative_new_capacity: float = 0.0,
        retirement_of_new_capacity: float = 0.0,
    ) -> float:
        """
        Compute total installed capacity for future MILP integration:
        InstalledCapacity(i, t) = ExistingSurvivingCapacity(i, t) + CumulativeNewCapacity(i, t) - RetirementOfNewCapacity(i, t)
        """
        if cumulative_new_capacity < 0.0:
            raise ValueError(f"cumulative_new_capacity cannot be negative, got {cumulative_new_capacity}")
        if retirement_of_new_capacity < 0.0:
            raise ValueError(f"retirement_of_new_capacity cannot be negative, got {retirement_of_new_capacity}")

        surviving_existing = self.get_surviving_capacity(year=year, technology=technology)
        return surviving_existing + cumulative_new_capacity - retirement_of_new_capacity

    def get_technology_breakdown_2024(self) -> Dict[str, float]:
        """Return 2024 starting capacity breakdown across technologies."""
        technologies = {r.technology for r in self.fleet.records}
        return {tech: self.get_total_starting_capacity(tech) for tech in sorted(list(technologies))}
