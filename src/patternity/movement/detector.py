"""Movement metrics derived from a decoded foot path."""

from collections.abc import Sequence

from patternity.analysis.metrics import MovementMetrics
from patternity.footing.resolve import FootingResult, ResolvedStep
from patternity.footing.stance import FootMove, PlayerOrientation

_FACING = frozenset({PlayerOrientation.FACING_LEFT, PlayerOrientation.FACING_RIGHT})


def count_direction_shifts(steps: Sequence[ResolvedStep]) -> int:
    """Press-row count of FACING_LEFT <-> FACING_RIGHT changes.

    Neutral and inverted rows are transition phases: they keep the last facing
    direction, so FACING_LEFT -> NEUTRAL -> FACING_RIGHT is one shift.
    """
    shifts = 0
    last_facing: PlayerOrientation | None = None
    for step in steps:
        if step.foot_row.moved == FootMove.NONE:
            continue
        orientation = step.foot_row.stance.orientation
        if orientation not in _FACING:
            continue
        if last_facing is not None and orientation != last_facing:
            shifts += 1
        last_facing = orientation
    return shifts


def detect_movement(resolved: FootingResult) -> MovementMetrics:
    return MovementMetrics(
        direction_shifts=count_direction_shifts(resolved.steps),
        total_cost=resolved.cost,
        foot_path_feasible=resolved.feasible,
    )
