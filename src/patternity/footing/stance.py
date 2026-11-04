from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntFlag, StrEnum

from patternity.simfile.panels import Panel


class PlayerOrientation(StrEnum):
    """Player orientation on a 4-panel pad."""

    NEUTRAL = "neutral"
    FACING_LEFT = "facing_left"
    FACING_RIGHT = "facing_right"
    INVERTED = "inverted"

    @property
    def is_facing(self) -> bool:
        """Turned sideways: facing left or facing right."""
        return self in (PlayerOrientation.FACING_LEFT, PlayerOrientation.FACING_RIGHT)


class FootPlacement(StrEnum):
    """Physical placement of a foot on a 4-panel pad."""

    L = "L"
    D = "D"
    U = "U"
    R = "R"
    # Bracket pairs
    LD = "LD"
    RD = "RD"
    LU = "LU"
    RU = "RU"

    @property
    def panels(self) -> Panel:
        """Panels under this foot placement (two for a bracket)."""
        return _PLACEMENT_PANELS[self]

    @property
    def coords(self) -> tuple[float, float]:
        """Representative (x, y) position for orientation math."""
        return _PLACEMENT_COORDS[self]

    def shares_panel_with(self, other: FootPlacement) -> bool:
        """True if both foot placements include at least one common panel."""
        return bool(self.panels & other.panels)

    @property
    def is_bracket(self) -> bool:
        """True if this foot placement bridges two adjacent panels."""
        return len(self.value) == 2

    def distance_to(self, other: FootPlacement) -> float:
        """Euclidean distance between two foot placements on the pad."""
        return math.dist(self.coords, other.coords)


_PLACEMENT_PANELS: dict[FootPlacement, Panel] = {
    FootPlacement.L: Panel.L,
    FootPlacement.D: Panel.D,
    FootPlacement.U: Panel.U,
    FootPlacement.R: Panel.R,
    FootPlacement.LD: Panel.L | Panel.D,
    FootPlacement.LU: Panel.L | Panel.U,
    FootPlacement.RD: Panel.R | Panel.D,
    FootPlacement.RU: Panel.R | Panel.U,
}

_PLACEMENT_COORDS: dict[FootPlacement, tuple[float, float]] = {
    FootPlacement.L: (-1.0, 0.0),
    FootPlacement.D: (0.0, -1.0),
    FootPlacement.U: (0.0, 1.0),
    FootPlacement.R: (1.0, 0.0),
    FootPlacement.LD: (-0.5, -0.5),
    FootPlacement.LU: (-0.5, 0.5),
    FootPlacement.RD: (0.5, -0.5),
    FootPlacement.RU: (0.5, 0.5),
}

PANELS_TO_PLACEMENT: dict[Panel, FootPlacement] = {
    panels: placement for placement, panels in _PLACEMENT_PANELS.items()
}
ALL_PLACEMENTS: tuple[FootPlacement, ...] = tuple(FootPlacement)
CARDINAL_PLACEMENTS: tuple[FootPlacement, ...] = (
    FootPlacement.L,
    FootPlacement.D,
    FootPlacement.U,
    FootPlacement.R,
)


def compute_orientation(
    left: FootPlacement,
    right: FootPlacement,
    prev_orientation: PlayerOrientation = PlayerOrientation.NEUTRAL,
) -> PlayerOrientation:
    """Derive body orientation from left and right foot coordinates.

    Assumes ``left``/``right`` don't overlap (see ``Stance`` docstring); the
    dx/dy sign logic still runs and returns a definite value for overlapping
    placements, but "which way are the hips facing" isn't a coherent question
    there, so the result shouldn't be trusted in that case.
    """
    lx, ly = left.coords
    rx, ry = right.coords
    dx = rx - lx
    dy = ry - ly

    # Change in dy indicates left/right orientation
    if dy > 0:
        return PlayerOrientation.FACING_LEFT
    if dy < 0:
        return PlayerOrientation.FACING_RIGHT

    # Change in dx indicates forward/backward orientation
    if dx > 0:
        return PlayerOrientation.NEUTRAL
    if dx < 0:
        return PlayerOrientation.INVERTED

    # dx=0, dy=0 occurs with repeated steps, footswitches, etc.
    return prev_orientation


class FootMove(IntFlag):
    """Bitflag identifying which foot/feet were used in a given NoteRow."""

    NONE = 0
    LEFT = 1
    RIGHT = 2
    BOTH = LEFT | RIGHT


@dataclass(frozen=True, slots=True)
class Stance:
    """Combined physical posture of both feet and derived hip orientation.

    Player orientation is only guaranteed with legal footing when built using
    `from_feet` method; the dataclass itself does not validate it. Direct
    construction does not guard against illegal stances like the following:
    Stance(
        left=FootPlacement.LU,
        right=FootPlacement.U,
        orientation=PlayerOrientation.INVERTED
    )

    Always construct Stance via `from_feet`.
    """

    left: FootPlacement
    right: FootPlacement
    orientation: PlayerOrientation

    @classmethod
    def from_feet(
        cls,
        left: FootPlacement = FootPlacement.L,
        right: FootPlacement = FootPlacement.R,
        prev_orientation: PlayerOrientation = PlayerOrientation.NEUTRAL,
    ) -> Stance:
        """Construct a Stance and automatically resolve its orientation."""
        return cls(
            left=left,
            right=right,
            orientation=compute_orientation(left, right, prev_orientation),
        )

    @property
    def covered(self) -> Panel:
        """Panels currently under either foot."""
        return self.left.panels | self.right.panels

    @property
    def is_overlapping(self) -> bool:
        """True if both feet share at least one panel (geometric overlap, not a tech count)."""
        return self.left.shares_panel_with(self.right)

    @property
    def is_crossed(self) -> bool:
        """True if the left foot is strictly right of the right foot (geometric cross)."""
        return self.left.coords[0] > self.right.coords[0]

    def covers(self, required: Panel) -> bool:
        """True if every panel in ``required`` is under a foot."""
        return required in self.covered

    def placement(self, foot: FootMove) -> FootPlacement:
        """Placement of a single foot (``LEFT`` or ``RIGHT``)."""
        return self.left if foot == FootMove.LEFT else self.right


@dataclass(frozen=True, slots=True)
class FootRow:
    """Trellis node: stance plus the minimal history transition features read.

    Every field takes part in equality and hashing, so Viterbi merges two nodes
    only when their state is identical (and therefore so are all future costs).

    stance: The position of the player at the current FootRow
    moved: The footing used to obtain the current position.
    mines_since_press: Panels that had a mine since the last press row
    last_press: The panel of the most recent press row (NONE unless a single panel)
    last_press_foot: The most recent footing of the last pressed column
    hold_owners: Sorted (panel, foot) pairs: which foot is anchored to each held panel
    released_since_press: Feet that released a hold/roll tail since the last press row
    last_repeat_jack: Flag indicating if last press repeated the preceding panel/foot
    """

    stance: Stance
    moved: FootMove
    mines_since_press: Panel = Panel.NONE
    last_press: Panel = Panel.NONE
    last_press_foot: FootMove | None = None
    hold_owners: tuple[tuple[Panel, FootMove], ...] = ()
    released_since_press: FootMove = FootMove.NONE
    last_repeat_jack: bool | None = None

    @classmethod
    def initial(cls) -> FootRow:
        """Default starting node before the first note of a chart (L on Left, R on Right)."""
        return cls(
            stance=Stance.from_feet(FootPlacement.L, FootPlacement.R),
            moved=FootMove.NONE,
        )

    def hold_owner_for(self, panel: Panel) -> FootMove | None:
        """The foot anchored to the hold or roll on ``panel``, if any."""
        for owned, foot in self.hold_owners:
            if owned == panel:
                return foot
        return None

    def pressed_panels(self) -> Panel:
        """Panels under the foot or feet that moved on this row."""
        pressed = Panel.NONE
        if self.moved & FootMove.LEFT:
            pressed |= self.stance.left.panels
        if self.moved & FootMove.RIGHT:
            pressed |= self.stance.right.panels
        return pressed
