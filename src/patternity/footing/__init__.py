"""Footing inference: exact Viterbi over legal foot states with learned linear costs.

- ``stance``: foot geometry and the search state (``FootRow``).
- ``rules``: hard physical rules for whether a foot placement is legal.
- ``transitions``: candidate moves filtered by the rules, every legal next state.
- ``features``: smooth, pattern-agnostic description of each transition.
- ``search``: trellis, Viterbi, per-row confidence.
- ``model``: learned weights (``FootingModel``).
- ``resolve``: ``resolve_chart``, the public entry point.
"""

from patternity.footing.model import FootingModel
from patternity.footing.resolve import (
    FootingResult,
    ResolvedStep,
    resolve_chart,
    resolve_trellis,
)
from patternity.footing.stance import Foot, FootMove, FootPlacement, FootRow, Stance

__all__ = [
    "Foot",
    "FootMove",
    "FootPlacement",
    "FootRow",
    "FootingModel",
    "FootingResult",
    "ResolvedStep",
    "Stance",
    "resolve_chart",
    "resolve_trellis",
]
