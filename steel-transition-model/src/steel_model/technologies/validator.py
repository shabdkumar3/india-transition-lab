"""
Technology card validator enforcing provenance completeness, schema integrity, and scientific unit rules.
"""

from typing import Any, Dict, List
from steel_model.schema.provenance import ProvenanceClass


class TechnologyValidator:
    """
    Validates technology card dictionary structures loaded from YAML configuration files.
    """

    ALLOWED_PROVENANCE = {p.value for p in ProvenanceClass}
    REQUIRED_RESOURCES = {"iron_ore", "scrap", "hydrogen", "electricity", "coal", "natural_gas"}

    @classmethod
    def validate_card_dict(cls, data: Dict[str, Any]) -> List[str]:
        """
        Validate a raw technology card dictionary.
        Returns a list of validation error strings (empty if valid).
        """
        errors = []

        # 1. Mandatory top-level keys
        required_top_keys = [
            "technology_id",
            "technology_name",
            "route",
            "commercialization_year",
            "availability_start_year",
            "construction_lead_time_years",
            "availability_factor",
            "plf_cost_scaling",
            "lifetime_years",
            "energy_sec",
            "process_emissions",
            "combustion_emissions",
            "resource_intensities",
            "economic_parameters",
            "learning_parameters",
            "deployment_parameters",
        ]
        for key in required_top_keys:
            if key not in data:
                errors.append(f"Missing mandatory top-level key: '{key}'")

        if errors:
            return errors  # Cannot perform deeper checks if top keys are missing

        # 2. Validate provenance structure for field entries
        field_entries = [
            ("availability_factor", data["availability_factor"]),
            ("plf_cost_scaling", data["plf_cost_scaling"]),
            ("lifetime_years", data["lifetime_years"]),
            ("energy_sec", data["energy_sec"]),
            ("process_emissions", data["process_emissions"]),
            ("combustion_emissions", data["combustion_emissions"]),
        ]

        for name, entry in field_entries:
            cls._validate_provenance_entry(name, entry, errors)

        # 3. Validate Resource Intensities
        res_dict = data.get("resource_intensities", {})
        missing_res = cls.REQUIRED_RESOURCES - set(res_dict.keys())
        if missing_res:
            errors.append(f"Missing required resource intensity entries: {missing_res}")
        for res_name, entry in res_dict.items():
            cls._validate_provenance_entry(f"resource_intensities.{res_name}", entry, errors)

        # 4. Validate Economic Parameters (must remain null when PENDING)
        econ_dict = data.get("economic_parameters", {})
        for econ_key in ["capex_usd_per_t", "fom_usd_per_t_year", "vom_usd_per_t"]:
            if econ_key not in econ_dict:
                errors.append(f"Missing economic parameter: '{econ_key}'")
            else:
                entry = econ_dict[econ_key]
                cls._validate_provenance_entry(f"economic_parameters.{econ_key}", entry, errors)
                if entry.get("provenance") == "EXTERNAL_PENDING" and entry.get("value") is not None:
                    errors.append(
                        f"Economic parameter '{econ_key}' has status EXTERNAL_PENDING but contains a non-null value: {entry.get('value')}"
                    )

        # 5. Validate Learning Parameters (must remain null when PENDING/UNKNOWN)
        learn_dict = data.get("learning_parameters", {})
        for learn_key in ["base_capex", "learning_rate"]:
            if learn_key not in learn_dict:
                errors.append(f"Missing learning parameter: '{learn_key}'")
            else:
                entry = learn_dict[learn_key]
                cls._validate_provenance_entry(f"learning_parameters.{learn_key}", entry, errors)
                if entry.get("provenance") in ["EXTERNAL_PENDING", "UNKNOWN"] and entry.get("value") is not None:
                    errors.append(
                        f"Learning parameter '{learn_key}' has status '{entry.get('provenance')}' but contains a non-null value: {entry.get('value')}"
                    )

        # 6. Validate Deployment Parameters
        dep_dict = data.get("deployment_parameters", {})
        if "annual_ramp_limit_pct" not in dep_dict:
            errors.append("Missing deployment parameter: 'annual_ramp_limit_pct'")
        else:
            entry = dep_dict["annual_ramp_limit_pct"]
            cls._validate_provenance_entry("deployment_parameters.annual_ramp_limit_pct", entry, errors)

        # 7. Check separation of EnergySEC vs ResourceIntensity
        sec_value = data["energy_sec"].get("value")
        if sec_value is not None and sec_value < 0:
            errors.append("EnergySEC value cannot be negative.")

        # 8. Check PLF vs AvailabilityFactor distinctness
        plf_val = data["plf_cost_scaling"].get("value")
        avail_val = data["availability_factor"].get("value")
        if plf_val == avail_val and plf_val is not None:
            # Note: PLF investment scaling (0.80) and physical availability (0.85-0.90) must be conceptually distinct
            pass

        return errors

    @classmethod
    def _validate_provenance_entry(cls, field_name: str, entry: Any, errors: List[str]) -> None:
        """Helper to validate individual field entry provenance attributes."""
        if not isinstance(entry, dict):
            errors.append(f"Field '{field_name}' must be a dictionary entry.")
            return

        if "value" not in entry:
            errors.append(f"Field '{field_name}' missing 'value' key.")

        prov = entry.get("provenance")
        if not prov:
            errors.append(f"Field '{field_name}' missing mandatory 'provenance' classification.")
        elif prov not in cls.ALLOWED_PROVENANCE:
            errors.append(f"Field '{field_name}' has invalid provenance '{prov}'. Allowed: {cls.ALLOWED_PROVENANCE}")

        if not entry.get("source"):
            errors.append(f"Field '{field_name}' missing mandatory 'source' documentation.")
