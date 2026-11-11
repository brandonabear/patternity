"""Hard physical rules: what makes a proposed foot placement legal on a row.

``RowContext`` names the panel sets the rules talk about (pressed, held,
releasable), and ``Candidate`` is one proposed placement of both feet. Each rule
in ``RULES`` states one physical requirement; a candidate is legal only if it
passes all of them. ``transitions`` proposes the candidates and applies the rules.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from patternity.footing.stance import Foot, FootMove, FootPlacement, FootRow
from patternity.simfile.notes import NoteRow, Panel


def held_panels(row: NoteRow) -> Panel:
    """Panels with a hold or roll already underway on this row, through its tail.

    A panel is not considered held on the row where it is pressed (~row.passed).
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

    def placement(self, foot: Foot) -> FootPlacement:
        return self.left if foot is Foot.LEFT else self.right

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


def _anchored_owners(prev: FootRow, ctx: RowContext) -> Iterator[tuple[Panel, Foot]]:
    """(panel, owning foot) for each hold that still needs its foot."""
    for panel, owner in prev.hold_owners:
        if panel in ctx.must_stay_held:
            yield panel, owner


def no_bracket_onto_held_panel(prev: FootRow, ctx: RowContext, c: Candidate) -> bool:
    """The foot that doesn't own a hold can't bracket onto its panel."""
    for panel, owner in _anchored_owners(prev, ctx):
        other = c.placement(owner.other)
        if other.is_bracket and panel in other.panels:
            return False
    return True


def hold_owner_stays_on_panel(prev: FootRow, ctx: RowContext, c: Candidate) -> bool:
    """The foot that owns a hold stays on its panel (no mid-hold switch).

    Holdswitches are still possible: they happen after the tail (or once the owner
    leaves in the grace window), when the hold no longer has an owner.
    """
    return all(panel in c.placement(owner).panels for panel, owner in _anchored_owners(prev, ctx))


def hits_mine(curr: FootRow, mines: Panel) -> bool:
    """True if a foot that is down after the move stands on one of ``mines``.

    Not one of ``RULES``: stepping on a mine is avoidable rather than impossible,
    so the search keeps such moves as a penalized fallback.
    """
    return any(
        curr.stance.placement(foot).panels & mines for foot in Foot if not curr.is_displaced(foot)
    )


RULES: tuple[Rule, ...] = (
    presses_are_covered,
    moving_feet_touch_only_pressed_or_held,
    each_jumping_foot_presses,
    jumping_feet_dont_share_a_panel,
    held_panels_stay_covered,
    hold_owner_stays_on_panel,
    no_bracket_onto_held_panel,
)


def is_legal(prev: FootRow, ctx: RowContext, c: Candidate) -> bool:
    """True if the candidate passes every rule in ``RULES``."""
    return all(rule(prev, ctx, c) for rule in RULES)
