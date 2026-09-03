"""
Demand validator enforcing schema integrity, anchor point correctness, and provenance rules.
"""

import os
import pandas as pd
from typing import List, Dict, Any
from steel_model.schema.provenance import ProvenanceClass


class DemandValidator:
    """
    Validates steel demand datasets against Vol. 4 published anchor points and schema rules.
    """

    EXPECTED_COLUMNS = ["year", "scenario", "demand_mt", "source", "source_page", "provenance"]
    EXPECTED_ANCHORS: Dict[int, float] = {
        2024: 144.29,
        2050: 624.00,
        2070: 821.00,
    }

    @classmethod
    def validate_csv(cls, csv_path: str) -> List[str]:
        """
        Validate demand CSV file on disk. Returns list of error strings (empty if valid).
        """
        errors = []

        if not os.path.exists(csv_path):
            return [f"Demand CSV file not found: '{csv_path}'"]

        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            return [f"Failed to parse CSV file '{csv_path}': {e}"]

        # 1. Check required columns
        missing_cols = set(cls.EXPECTED_COLUMNS) - set(df.columns)
        if missing_cols:
            errors.append(f"Missing required CSV columns: {missing_cols}")
            return errors

        # 2. Check for empty file
        if df.empty:
            errors.append("Demand CSV file is empty.")
            return errors

        # 3. Check for duplicates
        duplicates = df[df.duplicated(subset=["year", "scenario"], keep=False)]
        if not duplicates.empty:
            errors.append(f"Duplicate (year, scenario) records found: {duplicates[['year', 'scenario']].to_dict('records')}")

        # 4. Validate non-negative demand values
        negative_rows = df[df["demand_mt"] < 0]
        if not negative_rows.empty:
            errors.append(f"Negative demand values found in rows: {negative_rows['year'].tolist()}")

        # 5. Validate scenarios
        invalid_scenarios = df[~df["scenario"].isin(["CPS", "NZS"])]
        if not invalid_scenarios.empty:
            errors.append(f"Invalid scenarios found: {invalid_scenarios['scenario'].unique().tolist()}")

        # 6. Validate provenance
        invalid_prov = df[df["provenance"] != "V4"]
        if not invalid_prov.empty:
            errors.append(f"Non-V4 provenance found in baseline demand CSV: {invalid_prov['provenance'].unique().tolist()}")

        # 7. Validate anchor values for both scenarios
        for scenario in ["CPS", "NZS"]:
            scenario_df = df[df["scenario"] == scenario]
            year_map = dict(zip(scenario_df["year"], scenario_df["demand_mt"]))

            for anchor_year, expected_val in cls.EXPECTED_ANCHORS.items():
                if anchor_year not in year_map:
                    errors.append(f"Missing mandatory anchor year {anchor_year} for scenario '{scenario}'.")
                else:
                    actual_val = year_map[anchor_year]
                    if abs(actual_val - expected_val) > 1e-4:
                        errors.append(
                            f"Mismatch for anchor year {anchor_year} ({scenario}): expected {expected_val} Mt, got {actual_val} Mt"
                        )

        return errors
