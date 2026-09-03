"""
Canonical steel route identifiers and explicit legacy alias handling.
"""

from __future__ import annotations

from typing import Dict


CANONICAL_TECHNOLOGY_IDS = (
    "BF-BOF",
    "Coal-DRI-EAF",
    "Coal-DRI-IF",
    "NG-DRI-EAF",
    "H2-DRI-EAF",
    "Scrap-EAF",
)

LEGACY_TECHNOLOGY_ID_ALIASES: Dict[str, str] = {
    "BF_BOF": "BF-BOF",
    "COAL_DRI_EAF": "Coal-DRI-EAF",
    "COAL_DRI_IF": "Coal-DRI-IF",
    "NG_DRI_EAF": "NG-DRI-EAF",
    "H2_DRI_EAF": "H2-DRI-EAF",
    "SCRAP_EAF": "Scrap-EAF",
}

UNKNOWN_TECHNOLOGY_ID = "UNKNOWN"


def normalize_technology_id(raw_technology_id: str) -> str:
    """
    Convert an explicitly-supported legacy alias into the canonical route ID.
    """
    if raw_technology_id == UNKNOWN_TECHNOLOGY_ID:
        return raw_technology_id
    if raw_technology_id in CANONICAL_TECHNOLOGY_IDS:
        return raw_technology_id
    if raw_technology_id in LEGACY_TECHNOLOGY_ID_ALIASES:
        return LEGACY_TECHNOLOGY_ID_ALIASES[raw_technology_id]
    raise ValueError(
        f"Invalid technology ID '{raw_technology_id}'. "
        f"Supported canonical IDs: {list(CANONICAL_TECHNOLOGY_IDS)}. "
        f"Supported legacy aliases: {sorted(LEGACY_TECHNOLOGY_ID_ALIASES)}"
    )
