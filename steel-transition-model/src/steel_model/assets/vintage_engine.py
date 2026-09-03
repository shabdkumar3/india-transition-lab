"""
Vintage Engine computing surviving existing capacity, retired capacity, and cohort dynamics over time.
"""

from typing import Dict, List, Tuple
from steel_model.assets.asset_types import AssetFleet, AssetRecord


class VintageEngine:
    """
    Computes capacity survival, retirement curves, and vintage distributions for existing assets.
    """

    @classmethod
    def get_existing_capacity_by_vintage(cls, fleet: AssetFleet) -> Dict[Tuple[str, int], float]:
        """
        Extract ExistingCapacity(i, v) mapping technology ID i and commissioning vintage v to total capacity.
        """
        vintage_map: Dict[Tuple[str, int], float] = {}
        for record in fleet.records:
            key = (record.technology, record.commissioning_year)
            vintage_map[key] = vintage_map.get(key, 0.0) + record.capacity_mt_per_year
        return vintage_map

    @classmethod
    def calculate_surviving_capacity(
        cls, fleet: AssetFleet, year: int, technology: str = None
    ) -> float:
        """
        Calculate SurvivingCapacity(i, t) = sum_v ExistingCapacity(i, v) * Survival(v, t).
        """
        return fleet.get_surviving_capacity(year=year, technology=technology)

    @classmethod
    def calculate_retired_capacity_cumulative(
        cls, fleet: AssetFleet, year: int, technology: str = None
    ) -> float:
        """
        Calculate total cumulative retired existing capacity up to year t:
        Sum of capacity of records with commissioning_year <= year and effective_retirement_year <= year.
        """
        total_retired = 0.0
        for record in fleet.records:
            if technology is None or record.technology == technology:
                ret_year = record.get_effective_retirement_year()
                if record.commissioning_year <= year and ret_year <= year:
                    total_retired += record.capacity_mt_per_year
        return total_retired

    @classmethod
    def get_surviving_capacity_trajectory(
        cls, fleet: AssetFleet, start_year: int = 2024, end_year: int = 2070
    ) -> Dict[str, Dict[int, float]]:
        """
        Generates annual surviving capacity trajectories per technology:
        result[tech][year] = surviving_capacity_mt.
        """
        technologies = {r.technology for r in fleet.records}
        trajectory: Dict[str, Dict[int, float]] = {tech: {} for tech in technologies}

        for y in range(start_year, end_year + 1):
            for tech in technologies:
                trajectory[tech][y] = fleet.get_surviving_capacity(year=y, technology=tech)

        return trajectory
