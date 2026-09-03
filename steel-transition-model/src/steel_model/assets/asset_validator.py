"""
Validator module ensuring existing asset records comply with scientific, provenance, and data consistency rules.
"""

from typing import List, Union
from steel_model.assets.asset_types import (
    CapacityRecord,
    ProductionRecord,
    AssetFleet,
    ALLOWED_TECHNOLOGY_IDS,
)
from steel_model.schema.provenance import ProvenanceClass


class AssetValidator:
    """
    Validates asset collections, capacity records, and production records.
    """

    @classmethod
    def validate_capacity_record(cls, record: CapacityRecord) -> None:
        """Validate single CapacityRecord for internal consistency."""
        if record.capacity_mt_per_year < 0.0:
            raise ValueError(f"Asset '{record.asset_id}': capacity cannot be negative, got {record.capacity_mt_per_year}")

        if record.lifetime_years <= 0.0:
            raise ValueError(f"Asset '{record.asset_id}': lifetime_years must be > 0, got {record.lifetime_years}")

        if record.retirement_year is not None:
            if record.retirement_year < record.commissioning_year:
                raise ValueError(
                    f"Asset '{record.asset_id}': retirement_year ({record.retirement_year}) "
                    f"cannot be prior to commissioning_year ({record.commissioning_year})"
                )

        if record.technology not in ALLOWED_TECHNOLOGY_IDS:
            raise ValueError(f"Asset '{record.asset_id}': invalid technology ID '{record.technology}'")

        if record.technology == "UNKNOWN" and (not record.notes or len(record.notes.strip()) == 0):
            raise ValueError(f"Asset '{record.asset_id}': UNKNOWN technology mapping must specify an explicit reason in notes.")

        if record.provenance == ProvenanceClass.V4:
            # V4 facts must refer to Vol. 4 source text
            if "Vol. 4" not in record.source and "Industry Vol. 4" not in record.source:
                raise ValueError(f"Asset '{record.asset_id}': Provenance V4 requires Vol. 4 source reference.")

        # Rejection of Production-to-Capacity Derivation via 0.80 PLF
        if record.notes and "0.80 plf derivation" in record.notes.lower():
            raise ValueError(
                f"Asset '{record.asset_id}': Deriving capacity from production via 0.80 PLF is an unsupported derivation."
            )

    @classmethod
    def validate_production_record(cls, record: ProductionRecord) -> None:
        """Validate single ProductionRecord."""
        if record.production_mt < 0.0:
            raise ValueError(f"Production record for '{record.technology}' in year {record.year} cannot be negative.")
        if record.technology not in ALLOWED_TECHNOLOGY_IDS:
            raise ValueError(f"Production record: invalid technology ID '{record.technology}'")

    @classmethod
    def validate_record(cls, record: Union[CapacityRecord, ProductionRecord]) -> None:
        """Validate any asset or production record."""
        if isinstance(record, CapacityRecord):
            cls.validate_capacity_record(record)
        elif isinstance(record, ProductionRecord):
            cls.validate_production_record(record)

    @classmethod
    def validate_fleet(cls, fleet: AssetFleet) -> None:
        """Validate an entire AssetFleet for duplicate IDs and aggregate sanity."""
        seen_ids = set()
        for record in fleet.capacity_records:
            if record.asset_id in seen_ids:
                raise ValueError(f"Duplicate asset ID '{record.asset_id}' found in asset fleet.")
            seen_ids.add(record.asset_id)
            cls.validate_capacity_record(record)

        for prod_record in fleet.production_records:
            cls.validate_production_record(prod_record)
