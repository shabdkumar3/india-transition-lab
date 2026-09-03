"""
Technology registry managing technology cards across the modeling engine.
"""

from typing import Dict, Any, List, Optional
from .loader import TechnologyLoader
from steel_model.schema.technology import TechnologyCard
from steel_model.technology_ids import CANONICAL_TECHNOLOGY_IDS


class TechnologyRegistry:
    """
    Central registry for managing registered steel route technology cards.
    """

    EXPECTED_ROUTES = list(CANONICAL_TECHNOLOGY_IDS)

    def __init__(self, config_dir: Optional[str] = None):
        self._cards: Dict[str, Dict[str, Any]] = {}
        if config_dir:
            self.load_from_dir(config_dir)

    def load_from_dir(self, config_dir: str) -> None:
        """Load and register all technology cards from configuration directory."""
        self._cards = TechnologyLoader.load_all_cards(config_dir)
        self.verify_completeness()

    def get_technology(self, route_id: str) -> Dict[str, Any]:
        """Retrieve raw technology card dict for a route."""
        if route_id not in self._cards:
            raise KeyError(f"Technology route '{route_id}' not found in registry. Available: {list(self._cards.keys())}")
        return self._cards[route_id]

    def get_technology_model(self, route_id: str) -> TechnologyCard:
        """Retrieve technology card as a validated Pydantic model."""
        raw_card = self.get_technology(route_id)
        return TechnologyLoader.to_technology_card_model(raw_card)

    def list_technologies(self) -> List[str]:
        """List all registered technology route IDs."""
        return list(self._cards.keys())

    def get_all_cards(self) -> Dict[str, Dict[str, Any]]:
        """Return all raw technology cards."""
        return self._cards

    def verify_completeness(self) -> None:
        """Verify that all 6 core steel route technologies are present in registry."""
        missing = set(self.EXPECTED_ROUTES) - set(self._cards.keys())
        if missing:
            raise ValueError(f"Technology registry missing required route cards: {missing}")
