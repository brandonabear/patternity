"""Movement metrics derived from a decoded foot path."""

from collections.abc import Sequence

from patternity.footing.resolve import FootingResult, ResolvedStep
from patternity.footing.stance import FootMove, PlayerOrientation
from patternity.metrics import MovementMetrics

_FACING = frozenset({PlayerOrientation.FACING_LEFT, PlayerOrientation.FACING_RIGHT})


def count_direction_shifts(steps: Sequence[ResolvedStep]) -> int:
    """Press-row count of FACING_LEFT <-> FACING_RIGHT orientation changes."""
    shifts = 0
    prev: PlayerOrientation | None = None
    for step in steps:
        if step.foot_row.moved == FootMove.NONE:
            continue
        orientation = step.foot_row.stance.orientation
        if prev in _FACING and orientation in _FACING and orientation != prev:
            shifts += 1
        prev = orientation
    return shifts


def detect_movement(resolved: FootingResult) -> MovementMetrics:
    return MovementMetrics(
        direction_shifts=count_direction_shifts(resolved.steps),
        total_cost=resolved.cost,
        foot_path_feasible=resolved.feasible,
    )
