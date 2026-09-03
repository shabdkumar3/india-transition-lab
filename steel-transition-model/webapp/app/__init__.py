"""
India Steel Transition Lab — FastAPI backend package.

The backend is a thin REST/JSON wrapper around the EXISTING `steel_model`
research engine. It contains NO scientific logic of its own: scenario
validation delegates to the engine's own gates, and run execution invokes
``steel_model.run.run_experiment`` in a background job layer.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Import bootstrap: make the repo's `src/` importable so `import steel_model`
# works exactly like the repository test-suite (tests/conftest.py) does.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Matches steel_model/run.py MODEL_VERSION (the canonical run pipeline).
MODEL_VERSION = "0.16.0"
