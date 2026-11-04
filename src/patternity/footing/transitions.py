"""Every legal next ``FootRow`` from a given one on a given row.

Each row is handled in three steps:

1. ``RowContext`` (from ``rules``) names the panel sets the rules talk about
   (pressed, held, releasable).
2. ``_candidates`` proposes every way the feet could move: one foot to any
   placement, or (for multi-panel rows) both feet to any pair of placements.
3. Each candidate must pass every rule in ``rules.RULES``; illegal footing
   states are removed from consideration of Viterbi.
"""

from __future__ import annotations

from collections.abc import Iterator
from itertools import product

from patternity.footing.rules import Candidate, RowContext, is_legal
from patternity.footing.stance import (
    ALL_PLACEMENTS,
    CARDINAL_PLACEMENTS,
    FootMove,
    FootPlacement,
    FootRow,
    Stance,
)
from patternity.simfile.notes import ANCHORED_NOTES, PANELS, TAIL_NOTES, NoteRow, Panel


def _candidates(
    prev: FootRow, ctx: RowContext, placements: tuple[FootPlacement, ...]
) -> Iterator[Candidate]:
    """Every way the feet could move on a press row, before any rule is applied.

    One foot moves to any placement while the other stays put; on rows with two or
    more presses, both feet may also move (a jump or a hand).
    """
    stance = prev.stance
    for target in placements:
        yield Candidate(target, stance.right, FootMove.LEFT)
        yield Candidate(stance.left, target, FootMove.RIGHT)

    if len(ctx.pressed) >= 2:
        for left, right in product(placements, repeat=2):
            yield Candidate(left, right, FootMove.BOTH)


def _update_hold_owners(
    prev: FootRow, row: NoteRow, ctx: RowContext, stance: Stance, moved: FootMove
) -> tuple[tuple[Panel, FootMove], ...]:
    """Which foot owns each held panel after this row, as sorted (panel, foot) pairs."""
    # Active holds retain ownership
    owners: dict[Panel, FootMove] = {
        panel: foot for panel, foot in prev.hold_owners if panel in ctx.held
    }

    # Check for foot removal in grace period (remove ownership)
    for panel, foot in list(owners.items()):
        if panel in ctx.releasable and panel not in stance.placement(foot).panels:
            del owners[panel]

    # A new hold or roll head is owned by the foot that pressed it.
    for panel, note in zip(PANELS, row.notes, strict=True):
        if note not in ANCHORED_NOTES:
            continue
        if moved & FootMove.LEFT and panel in stance.left.panels:
            owners[panel] = FootMove.LEFT
        elif moved & FootMove.RIGHT and panel in stance.right.panels:
            owners[panel] = FootMove.RIGHT

    return tuple(sorted(owners.items()))


def _emit_foot_row(
    prev: FootRow, row: NoteRow, ctx: RowContext, *, stance: Stance, moved: FootMove
) -> FootRow:
    """Build the next FootRow after a move.

    A no-move row only carries state forward (mines, hold releases). A press row
    resets the since-press fields and records the new press.
    """
    hold_owners = _update_hold_owners(prev, row, ctx, stance, moved)

    if moved == FootMove.NONE:
        # A hold or roll tail on this row releases its owner. The release is
        # remembered until the next press so the cost features can see it.
        tails = row.panels_with(TAIL_NOTES)
        released = prev.released_since_press
        for panel, owner in prev.hold_owners:
            if panel in tails:
                released |= owner

        return FootRow(
            stance=stance,
            moved=moved,
            mines_since_press=prev.mines_since_press | row.mines,
            last_press=prev.last_press,
            last_press_foot=prev.last_press_foot,
            hold_owners=hold_owners,
            released_since_press=released,
            last_repeat_jack=prev.last_repeat_jack,
        )

    # Only a single-panel press is tracked for jacks and switches.
    last_press = ctx.pressed if len(ctx.pressed) == 1 else Panel.NONE

    # repeat_jack: True if the same foot presses the same panel again (a jack),
    # False if the other foot takes over the panel (a switch), and None when
    # that comparison doesn't apply (a multi-panel row, a jump, or a new panel).
    repeat_jack = None
    if (
        last_press
        and last_press == prev.last_press
        and moved != FootMove.BOTH
        and prev.last_press_foot in (FootMove.LEFT, FootMove.RIGHT)
    ):
        repeat_jack = moved == prev.last_press_foot

    return FootRow(
        stance=stance,
        moved=moved,
        mines_since_press=Panel.NONE,
        last_press=last_press,
        last_press_foot=moved,
        hold_owners=hold_owners,
        last_repeat_jack=repeat_jack,
    )


def iter_legal_transitions(
    prev: FootRow,
    row: NoteRow,
    *,
    allow_brackets: bool = True,
    grace: Panel = Panel.NONE,
) -> Iterator[FootRow]:
    """Yield all physically legal next `FootRow` states for `row` given `prev`.

    A row with no press keeps both feet in place (``moved == NONE``). Otherwise each
    candidate from ``_candidates`` that passes every rule is yielded, in order.
    """
    ctx = RowContext.from_row(row, grace)

    # No change in footing
    if not ctx.pressed:
        yield _emit_foot_row(prev, row, ctx, stance=prev.stance, moved=FootMove.NONE)
        return

    # Brackets (two panels under one foot) are excluded unless requested.
    placements = ALL_PLACEMENTS if allow_brackets else CARDINAL_PLACEMENTS

    for c in _candidates(prev, ctx, placements):
        if is_legal(prev, ctx, c):
            stance = Stance.from_feet(c.left, c.right, prev.stance.orientation)
            yield _emit_foot_row(prev, row, ctx, stance=stance, moved=c.moved)
