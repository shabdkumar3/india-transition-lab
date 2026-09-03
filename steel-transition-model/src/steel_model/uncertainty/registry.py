"""
Uncertainty Registry — loads and queries the parameter uncertainty boundaries (Step 13).
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, model_validator
import yaml


class UncertaintyParameter(BaseModel):
    """Container for a single parameter's uncertainty metadata."""

    parameter_id: str
    base_value: Optional[float] = None
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    unit: str
    provenance: str
    uncertainty_basis: str
    source: str

    @model_validator(mode="after")
    def validate_bounds(self) -> UncertaintyParameter:
        if self.lower_bound is not None and self.upper_bound is not None:
            if self.lower_bound > self.upper_bound:
                raise ValueError(
                    f"Parameter '{self.parameter_id}' lower_bound ({self.lower_bound}) "
                    f"cannot exceed upper_bound ({self.upper_bound})."
                )
        return self


class UncertaintyRegistry:
    """Registry providing read-only access to all uncertain parameters."""

    def __init__(self, config_path: str) -> None:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Uncertainty registry config not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self._parameters: Dict[str, UncertaintyParameter] = {}
        for p_data in data.get("parameters", []):
            param = UncertaintyParameter(**p_data)
            self._parameters[param.parameter_id] = param

    def get_parameter(self, parameter_id: str) -> Optional[UncertaintyParameter]:
        """Return the UncertaintyParameter associated with parameter_id."""
        return self._parameters.get(parameter_id)

    def list_parameters(self) -> List[UncertaintyParameter]:
        """Return a list of all registered parameters."""
        return list(self._parameters.values())

    def get_eligible_parameters(self) -> List[UncertaintyParameter]:
        """Return parameters that have defined lower and upper bounds."""
        return [
            p for p in self._parameters.values()
            if p.lower_bound is not None and p.upper_bound is not None
        ]
