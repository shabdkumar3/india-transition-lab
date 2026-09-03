"""
Technology loader for reading, parsing, and validating YAML technology configuration files.
"""

import os
import yaml
from typing import Dict, Any, List
from .validator import TechnologyValidator
from steel_model.schema.technology import TechnologyCard
from steel_model.schema.provenance import ProvenanceRecord, ProvenanceClass


class TechnologyLoader:
    """
    Handles loading and parsing of technology YAML cards from disk.
    """

    @classmethod
    def load_yaml_card(cls, file_path: str) -> Dict[str, Any]:
        """Load a single technology YAML file and validate its schema."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Technology YAML file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"YAML file {file_path} did not parse into a dictionary.")

        errors = TechnologyValidator.validate_card_dict(data)
        if errors:
            raise ValueError(f"Validation failed for {file_path}:\n" + "\n".join(f"- {e}" for e in errors))

        return data

    @classmethod
    def load_all_cards(cls, config_dir: str) -> Dict[str, Dict[str, Any]]:
        """Load all technology YAML cards from a target configuration directory."""
        if not os.path.exists(config_dir):
            raise FileNotFoundError(f"Technology configuration directory not found: {config_dir}")

        cards = {}
        for fname in sorted(os.listdir(config_dir)):
            if fname.endswith(".yaml") or fname.endswith(".yml"):
                full_path = os.path.join(config_dir, fname)
                card_data = cls.load_yaml_card(full_path)
                tech_id = card_data["technology_id"]

                if tech_id in cards:
                    raise ValueError(f"Duplicate technology_id '{tech_id}' found in {fname}")

                cards[tech_id] = card_data

        return cards

    @classmethod
    def to_technology_card_model(cls, data: Dict[str, Any]) -> TechnologyCard:
        """Convert a validated raw card dictionary into a TechnologyCard Pydantic object."""
        # Map physical resource intensities values
        res_intensities = {
            res: entry.get("value")
            for res, entry in data["resource_intensities"].items()
        }

        # Build provenance records list
        prov_records: List[ProvenanceRecord] = []
        for res_name, entry in data["resource_intensities"].items():
            if entry.get("provenance"):
                prov_records.append(
                    ProvenanceRecord(
                        parameter_name=f"resource_intensity.{res_name}",
                        technology=data["technology_id"],
                        resource=res_name,
                        value=entry.get("value"),
                        unit=entry.get("unit", "dimensionless"),
                        provenance=ProvenanceClass(entry["provenance"]),
                        source=entry.get("source", "Unknown"),
                        page_or_section=entry.get("page_or_section"),
                        derivation_formula=entry.get("derivation_formula"),
                    )
                )

        return TechnologyCard(
            route_id=data["technology_id"],
            route_name=data["technology_name"],
            energy_sec_gj_per_t=data["energy_sec"]["value"],
            resource_intensities=res_intensities,
            process_emission_factor_tco2_per_t=data["process_emissions"]["value"],
            combustion_emission_factor_tco2_per_t=data["combustion_emissions"]["value"],
            lifetime_years=data["lifetime_years"]["value"],
            availability_factor=data["availability_factor"]["value"],
            plf_cost_scaling=data["plf_cost_scaling"]["value"],
            commercialization_year=data["commercialization_year"],
            construction_lead_time_years=data.get("construction_lead_time_years", 3),
            capex_usd_per_t=data["economic_parameters"]["capex_usd_per_t"].get("value"),
            fom_usd_per_t_year=data["economic_parameters"]["fom_usd_per_t_year"].get("value"),
            vom_usd_per_t=data["economic_parameters"]["vom_usd_per_t"].get("value"),
            provenance_records=prov_records,
        )
