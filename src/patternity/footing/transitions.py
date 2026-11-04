"""Hard physical rules: every legal next ``FootRow`` from a given one on a given row.

Each row is handled in three steps:

1. ``RowContext`` names the panel sets the rules talk about (pressed, held,
   releasable).
2. ``_candidates`` proposes every way the feet could move: one foot to any
   placement, or (for multi-panel rows) both feet to any pair of placements.
3. Each candidate must pass every rule in ``_RULES``; the survivors become the
   next ``FootRow`` states.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from itertools import product

from patternity.footing.stance import (
    ALL_PLACEMENTS,
    CARDINAL_PLACEMENTS,
    FootMove,
    FootPlacement,
    FootRow,
    Stance,
)
from patternity.simfile.notes import ANCHORED_NOTES, NoteRow, NoteType
from patternity.simfile.panels import PANELS, Panel

_TAILS = frozenset({NoteType.TAIL})


def held_panels(row: NoteRow) -> Panel:
    """Panels with a hold or roll already underway on this row, through its tail.

    A panel pressed on this row (a new head) is not held yet.
    """
    return (row.holds_active | row.rolls_active) & ~row.pressed


@dataclass(frozen=True, slots=True)
class RowContext:
    """The panel sets on one row that the transition rules refer to."""

    pressed: Panel  # Taps and hold/roll heads: a foot must land on each.
    held: Panel  # Holds/rolls already underway (see ``held_panels``).
    releasable: Panel  # Held panels in their grace window: the owner may leave early.
    must_stay_held: Panel  # Held panels that still need a foot on them.
    touchable: Panel  # Panels a moving foot may land on: pressed, or ones it is holding.

    @classmethod
    def from_row(cls, row: NoteRow, grace: Panel = Panel.NONE) -> RowContext:
        pressed = row.pressed
        held = held_panels(row)
        return cls(
            pressed=pressed,
            held=held,
            releasable=grace,
            must_stay_held=held & ~grace,
            touchable=pressed | held,
        )


@dataclass(frozen=True, slots=True)
class Candidate:
    """A proposed placement of both feet, and which foot or feet moved there."""

    left: FootPlacement
    right: FootPlacement
    moved: FootMove

    def placement(self, foot: FootMove) -> FootPlacement:
        return self.left if foot == FootMove.LEFT else self.right

    @property
    def landed(self) -> Panel:
        """Panels under the foot or feet that moved."""
        if self.moved == FootMove.LEFT:
            return self.left.panels
        if self.moved == FootMove.RIGHT:
            return self.right.panels
        return self.covered

    @property
    def covered(self) -> Panel:
        """Panels under either foot."""
        return self.left.panels | self.right.panels


def _candidates(
    prev: FootRow, ctx: RowContext, placements: tuple[FootPlacement, ...]
) -> Iterator[Candidate]:
    """Every way the feet could move on a press row, before any rule is applied.

    One foot moves to any placement while the other stays put; on rows with two or
    more presses, both feet may also move (a jump, or a bracket plus a tap).
    """
    stance = prev.stance
    for target in placements:
        yield Candidate(target, stance.right, FootMove.LEFT)
        yield Candidate(stance.left, target, FootMove.RIGHT)

    if len(ctx.pressed) >= 2:
        for left, right in product(placements, repeat=2):
            yield Candidate(left, right, FootMove.BOTH)


# --- Rules -------------------------------------------------------------------
# Each rule states one physical requirement for a candidate to be legal.

Rule = Callable[[FootRow, RowContext, Candidate], bool]


def presses_are_covered(prev: FootRow, ctx: RowContext, c: Candidate) -> bool:
    """Every pressed panel is under a foot that moved."""
    return ctx.pressed in c.landed


def moving_feet_touch_only_pressed_or_held(prev: FootRow, ctx: RowContext, c: Candidate) -> bool:
    """A moving foot only lands on pressed panels or panels it is holding."""
    return c.landed in ctx.touchable


def each_jumping_foot_presses(prev: FootRow, ctx: RowContext, c: Candidate) -> bool:
    """In a jump, each foot presses at least one pressed panel."""
    if c.moved != FootMove.BOTH:
        return True
    return bool(c.left.panels & ctx.pressed) and bool(c.right.panels & ctx.pressed)


def jumping_feet_dont_share_a_panel(prev: FootRow, ctx: RowContext, c: Candidate) -> bool:
    """In a jump, the feet land on different panels.

    Single-foot moves may land on the planted foot's panel (a footswitch).
    """
    return c.moved != FootMove.BOTH or not c.left.shares_panel_with(c.right)


def held_panels_stay_covered(prev: FootRow, ctx: RowContext, c: Candidate) -> bool:
    """Every held panel outside its grace window keeps a foot on it."""
    return ctx.must_stay_held in c.covered


def _anchored_owners(prev: FootRow, ctx: RowContext) -> Iterator[tuple[Panel, FootMove]]:
    """(panel, owning foot) for each hold that still needs its foot."""
    for panel, owner in prev.hold_owners:
        if panel in ctx.must_stay_held:
            yield panel, owner


def no_bracket_onto_held_panel(prev: FootRow, ctx: RowContext, c: Candidate) -> bool:
    """The foot that doesn't own a hold can't bracket onto its panel."""
    for panel, owner in _anchored_owners(prev, ctx):
        other = c.right if owner == FootMove.LEFT else c.left
        if other.is_bracket and panel in other.panels:
            return False
    return True


def hold_owner_stays_on_panel(prev: FootRow, ctx: RowContext, c: Candidate) -> bool:
    """The foot that owns a hold stays on its panel (no mid-hold switch).

    Holdswitches are still possible: they happen after the tail (or once the owner
    leaves in the grace window), when the hold no longer has an owner.
    """
    return all(panel in c.placement(owner).panels for panel, owner in _anchored_owners(prev, ctx))


_RULES: tuple[Rule, ...] = (
    presses_are_covered,
    moving_feet_touch_only_pressed_or_held,
    each_jumping_foot_presses,
    jumping_feet_dont_share_a_panel,
    held_panels_stay_covered,
    hold_owner_stays_on_panel,
    no_bracket_onto_held_panel,
)


# --- Next state ----------------------------------------------------------------


def _update_hold_owners(
    prev: FootRow, row: NoteRow, ctx: RowContext, stance: Stance, moved: FootMove
) -> tuple[tuple[Panel, FootMove], ...]:
    """Which foot owns each held panel after this row, as sorted (panel, foot) pairs."""
    # Holds still underway keep their owner...
    owners: dict[Panel, FootMove] = {
        panel: foot for panel, foot in prev.hold_owners if panel in ctx.held
    }
    # ...unless the owner stepped off during the grace window.
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
        tails = row.panels_with(_TAILS)
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

    # No new press: the feet stay put, but holds and mines still update.
    if not ctx.pressed:
        yield _emit_foot_row(prev, row, ctx, stance=prev.stance, moved=FootMove.NONE)
        return

    # Brackets (two panels under one foot) are excluded unless requested.
    placements = ALL_PLACEMENTS if allow_brackets else CARDINAL_PLACEMENTS

    for c in _candidates(prev, ctx, placements):
        if all(rule(prev, ctx, c) for rule in _RULES):
            stance = Stance.from_feet(c.left, c.right, prev.stance.orientation)
            yield _emit_foot_row(prev, row, ctx, stance=stance, moved=c.moved)
