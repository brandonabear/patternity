"""Count direction shifts and candles on a resolved foot path."""

from __future__ import annotations

from patternity.footing.resolve import ResolvedStep
from patternity.footing.stance import (
    FootMove,
    FootPlacement,
    FootRow,
    PlayerOrientation,
)

_FACING = frozenset({PlayerOrientation.FACING_LEFT, PlayerOrientation.FACING_RIGHT})
_LEFT_PANEL = 0b0001
_RIGHT_PANEL = 0b1000
_CENTER_PANELS = 0b0110


def _placement_for(foot_row: FootRow, foot: FootMove) -> FootPlacement:
    return foot_row.stance.left if foot == FootMove.LEFT else foot_row.stance.right


def count_direction_shifts(steps: list[ResolvedStep]) -> int:
    """Press-row count of FACING_LEFT <-> FACING_RIGHT orientation changes."""
    shifts = 0
    prev_orientation: PlayerOrientation | None = None
    for step in steps:
        moved = step.foot_row.moved
        if moved == FootMove.NONE:
            continue
        orientation = step.foot_row.stance.orientation
        if (
            prev_orientation in _FACING
            and orientation in _FACING
            and orientation != prev_orientation
        ):
            shifts += 1
        prev_orientation = orientation
    return shifts


def _run_is_candle(placements: tuple[FootPlacement, ...]) -> bool:
    if not placements:
        return False
    had_left = any(p.mask & _LEFT_PANEL for p in placements)
    had_right = any(p.mask & _RIGHT_PANEL for p in placements)
    had_center = any(p.mask & _CENTER_PANELS for p in placements)
    had_up = any(p.mask & 0b0100 for p in placements)
    had_down = any(p.mask & 0b0010 for p in placements)
    side_to_side = had_left and had_right and had_center
    vertical_center = had_up and had_down
    return side_to_side or vertical_center


def _count_candles_for_foot(steps: list[ResolvedStep], foot: FootMove) -> int:
    candles = 0
    run: list[FootPlacement] = []
    for step in steps:
        if not step.foot_row.moved & foot:
            if run:
                candles += int(_run_is_candle(tuple(run)))
                run = []
            continue
        run.append(_placement_for(step.foot_row, foot))
    if run:
        candles += int(_run_is_candle(tuple(run)))
    return candles


def count_candles(steps: list[ResolvedStep]) -> int:
    """One candle per completed foot maneuver (side-to-side via center, or U then D)."""
    return _count_candles_for_foot(steps, FootMove.LEFT) + _count_candles_for_foot(
        steps, FootMove.RIGHT
    )
