"""
Demand loader for reading published Vol. 4 steel demand anchor points directly.
"""

import os
import pandas as pd
from typing import Dict
from .demand_types import DemandRecord, DemandDataset
from .demand_validator import DemandValidator
from steel_model.schema.provenance import ProvenanceClass


class DemandLoader:
    """
    Loads verified Vol. 4 baseline crude steel demand observations.
    Baseline loading strictly avoids silent interpolation or S-curve modification.
    """

    @classmethod
    def load_published_anchors(cls, csv_path: str) -> DemandDataset:
        """
        Load published Vol. 4 anchor points from CSV into a DemandDataset.
        Raises ValueError if validation fails. Does NOT invoke S-curve calibration.
        """
        errors = DemandValidator.validate_csv(csv_path)
        if errors:
            raise ValueError(f"Validation failed for demand CSV '{csv_path}':\n" + "\n".join(f"- {e}" for e in errors))

        df = pd.read_csv(csv_path)
        records = []

        for _, row in df.iterrows():
            rec = DemandRecord(
                year=int(row["year"]),
                scenario=str(row["scenario"]),
                demand_mt=float(row["demand_mt"]),
                source=str(row["source"]),
                source_page=str(row["source_page"]),
                provenance=ProvenanceClass(str(row["provenance"])),
                unit="Mt"
            )
            records.append(rec)

        return DemandDataset(records=records)

    @classmethod
    def get_anchor_dict(cls, csv_path: str, scenario: str = "CPS") -> Dict[int, float]:
        """Convenience method returning year -> demand_mt dictionary of published anchors."""
        ds = cls.load_published_anchors(csv_path)
        return ds.to_dict_map(scenario=scenario)
