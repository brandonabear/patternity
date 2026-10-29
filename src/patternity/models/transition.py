from collections.abc import Iterator

from patternity.models.engine import NoteRow
from patternity.models.stance import (
    ALL_PLACEMENTS,
    CARDINAL_PLACEMENTS,
    FootMove,
    FootPlacement,
    FootRow,
    Stance,
)


def _holds_preserved(
    prev_stance: Stance,
    next_left: FootPlacement,
    next_right: FootPlacement,
    ongoing_holds: int,
    allow_mid_hold_switches: bool,
) -> bool:
    """Check if ongoing holds remain covered (and stay on the same foot if switches are disallowed)."""
    # 1. Together, the two feet must cover every ongoing hold
    if ((next_left.mask | next_right.mask) & ongoing_holds) != ongoing_holds:
        return False

    # 2. If mid-hold switches are disallowed, neither foot can abandon a hold it was already holding
    if not allow_mid_hold_switches:
        left_was_holding = prev_stance.left.mask & ongoing_holds
        right_was_holding = prev_stance.right.mask & ongoing_holds
        if (next_left.mask & left_was_holding) != left_was_holding:
            return False
        if (next_right.mask & right_was_holding) != right_was_holding:
            return False

    return True


def iter_legal_transitions(
    prev: FootRow,
    row: NoteRow,
    *,
    allow_brackets: bool = True,
    allow_mid_hold_switches: bool = False,
) -> Iterator[FootRow]:
    """Yield all physically legal next `FootRow` states for `row` given `prev`."""
    press_mask = row.press_mask
    ongoing_holds = row.hold_active_mask & ~press_mask
    now = row.timestamp or 0.0

    # Case 1: No new presses on this row (e.g., tail-only or mine-only row)
    if press_mask == 0:
        yield FootRow(
            stance=prev.stance,
            moved=FootMove.NONE,
            left_time=prev.left_time,
            right_time=prev.right_time,
        )
        return

    placements = ALL_PLACEMENTS if allow_brackets else CARDINAL_PLACEMENTS
    prev_stance = prev.stance

    # Case 2: Single-foot moves (LEFT or RIGHT)
    for target in placements:
        # A single moving foot must press ALL new notes on this row, and any extra panel
        # in its bracket must be an ongoing hold (no bracketing empty panels for no reason).
        if (target.mask & press_mask) != press_mask:
            continue
        if (target.mask & ~press_mask & ~ongoing_holds) != 0:
            continue

        # 2a. Move LEFT foot to `target`, keep RIGHT foot at `prev_stance.right`
        if _holds_preserved(
            prev_stance, target, prev_stance.right, ongoing_holds, allow_mid_hold_switches
        ):
            yield FootRow(
                stance=Stance.from_feet(target, prev_stance.right, prev_stance.orientation),
                moved=FootMove.LEFT,
                left_time=now,
                right_time=prev.right_time,
            )

        # 2b. Move RIGHT foot to `target`, keep LEFT foot at `prev_stance.left`
        if _holds_preserved(
            prev_stance, prev_stance.left, target, ongoing_holds, allow_mid_hold_switches
        ):
            yield FootRow(
                stance=Stance.from_feet(prev_stance.left, target, prev_stance.orientation),
                moved=FootMove.RIGHT,
                left_time=prev.left_time,
                right_time=now,
            )

    # Case 3: Two-foot moves (BOTH — Jumps, Hands, Quads)
    if press_mask.bit_count() >= 2:
        allowed_panels = press_mask | ongoing_holds
        for left_p in placements:
            # Left foot must hit at least one new press and only touch allowed panels
            if not (left_p.mask & press_mask) or (left_p.mask & ~allowed_panels):
                continue

            for right_p in placements:
                # Right foot must hit at least one new press, only touch allowed panels,
                # and not overlap the left foot on a jump
                if (
                    not (right_p.mask & press_mask)
                    or (right_p.mask & ~allowed_panels)
                    or left_p.shares_panel_with(right_p)
                ):
                    continue

                # Together they must press all new notes and preserve ongoing holds
                if ((left_p.mask | right_p.mask) & press_mask) != press_mask:
                    continue
                if not _holds_preserved(
                    prev_stance, left_p, right_p, ongoing_holds, allow_mid_hold_switches
                ):
                    continue

                yield FootRow(
                    stance=Stance.from_feet(left_p, right_p, prev_stance.orientation),
                    moved=FootMove.BOTH,
                    left_time=now,
                    right_time=now,
                )
