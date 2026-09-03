"""
Asset loader parsing YAML and CSV configuration files into validated AssetFleet instances.
"""

import os
from typing import Dict, Any, List
import pandas as pd
import yaml
from steel_model.assets.asset_types import CapacityRecord, ProductionRecord, AssetFleet
from steel_model.assets.asset_validator import AssetValidator
from steel_model.schema.provenance import ProvenanceClass


class AssetLoader:
    """
    Loads and validates asset records and production records from YAML configurations or CSV datasets.
    """

    @classmethod
    def load_from_yaml(cls, yaml_path: str) -> AssetFleet:
        """Load asset capacity records (and optional production records) from YAML."""
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"Asset YAML file not found at '{yaml_path}'")

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Invalid asset YAML structure in '{yaml_path}'.")

        fleet = AssetFleet()

        # Parse capacity assets
        if "assets" in data:
            for item in data["assets"]:
                prov_str = item.get("provenance", "PROJECT_PROPOSAL")
                item["provenance"] = ProvenanceClass(prov_str)

                record = CapacityRecord(**item)
                AssetValidator.validate_capacity_record(record)
                fleet.add_capacity_record(record)

        # Parse production records if present
        if "production_records" in data:
            for item in data["production_records"]:
                prov_str = item.get("provenance", "V4")
                item["provenance"] = ProvenanceClass(prov_str)

                prod_rec = ProductionRecord(**item)
                AssetValidator.validate_production_record(prod_rec)
                fleet.add_production_record(prod_rec)

        AssetValidator.validate_fleet(fleet)
        return fleet

    @classmethod
    def load_from_csv(cls, csv_path: str) -> AssetFleet:
        """Load asset capacity records from CSV."""
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Asset CSV file not found at '{csv_path}'")

        df = pd.read_csv(csv_path)
        fleet = AssetFleet()

        for _, row in df.iterrows():
            row_dict = row.to_dict()
            cleaned_dict = {k: (None if pd.isna(v) else v) for k, v in row_dict.items()}

            if "provenance" in cleaned_dict and cleaned_dict["provenance"]:
                cleaned_dict["provenance"] = ProvenanceClass(cleaned_dict["provenance"])

            if cleaned_dict.get("commissioning_year") is not None:
                cleaned_dict["commissioning_year"] = int(cleaned_dict["commissioning_year"])
            if cleaned_dict.get("retirement_year") is not None:
                cleaned_dict["retirement_year"] = int(cleaned_dict["retirement_year"])

            record = CapacityRecord(**cleaned_dict)
            AssetValidator.validate_capacity_record(record)
            fleet.add_capacity_record(record)

        AssetValidator.validate_fleet(fleet)
        return fleet
