from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntFlag, StrEnum


class PlayerOrientation(StrEnum):
    """Player orientation on a 4-panel pad."""

    NEUTRAL = "neutral"
    FACING_LEFT = "facing_left"
    FACING_RIGHT = "facing_right"
    INVERTED = "inverted"


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
    def mask(self) -> int:
        """4-bit LDUR mask for panels covered by this placement."""
        return _PLACEMENT_MASKS[self]

    @property
    def coords(self) -> tuple[float, float]:
        """Representative (x, y) position for orientation math."""
        return _PLACEMENT_COORDS[self]

    def shares_panel_with(self, other: FootPlacement) -> bool:
        """True if both placements include at least one common panel."""
        return bool(self.mask & other.mask)

    @property
    def is_bracket(self) -> bool:
        """True if this placement bridges two adjacent panels."""
        return len(self.value) == 2

    def distance_to(self, other: FootPlacement) -> float:
        """Euclidean distance between two placements on the pad."""
        return math.dist(self.coords, other.coords)


_PLACEMENT_MASKS: dict[FootPlacement, int] = {
    FootPlacement.L: 0b0001,
    FootPlacement.D: 0b0010,
    FootPlacement.U: 0b0100,
    FootPlacement.R: 0b1000,
    FootPlacement.LD: 0b0011,
    FootPlacement.LU: 0b0101,
    FootPlacement.RD: 0b1010,
    FootPlacement.RU: 0b1100,
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

MASK_TO_PLACEMENT: dict[int, FootPlacement] = {
    mask: placement for placement, mask in _PLACEMENT_MASKS.items()
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
    """Derive body orientation from left and right foot coordinates."""
    lx, ly = left.coords
    rx, ry = right.coords
    dx = rx - lx
    dy = ry - ly

    if dx > 0:
        return PlayerOrientation.NEUTRAL

    # Both feet occupy the exact same placement (e.g., footswitch overlap)
    if dx == 0 and dy == 0:
        return prev_orientation

    # dx <= 0: Feet are aligned vertically (dx == 0) or crossed horizontally (dx < 0)
    if dy > 0:
        return PlayerOrientation.FACING_LEFT
    if dy < 0:
        return PlayerOrientation.FACING_RIGHT

    # dx < 0 and dy == 0 (e.g., left=R, right=L)
    return PlayerOrientation.INVERTED


@dataclass(frozen=True, slots=True)
class Stance:
    """Combined physical posture of both feet and derived hip orientation."""

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
    def covered_mask(self) -> int:
        """Combined 4-bit mask of all panels currently covered by either foot."""
        return self.left.mask | self.right.mask

    @property
    def is_overlapping(self) -> bool:
        """True if both feet share at least one panel (geometric overlap, not a tech count)."""
        return self.left.shares_panel_with(self.right)

    @property
    def is_crossed(self) -> bool:
        """True if the left foot is strictly right of the right foot (geometric cross)."""
        return self.left.coords[0] > self.right.coords[0]

    def covers_mask(self, required_mask: int) -> bool:
        """True if this stance covers all bits in `required_mask`."""
        return (self.covered_mask & required_mask) == required_mask


class FootMove(IntFlag):
    """Bitflag identifying which foot/feet were used in a given NoteRow."""

    NONE = 0
    LEFT = 1
    RIGHT = 2
    BOTH = LEFT | RIGHT


@dataclass(frozen=True, slots=True)
class FootRow:
    """Trellis node: stance plus the minimal history transition features read.

    We include all fields so node merge in Viterbi occurs only when two nodes 
    have identical scores.

    stance: The position of the player at the current FootRow
    moved: The footing used to obtain the current position.
    mines_since_press: 
    last_press_col: The most recently pressed column
    last_press_foot: The most recent footing of the last pressed column
    hold_owners: Foot/Feet currently anchored by a hold or roll
    released_since_press:
    last_repeat_jack: Flag indicating if last press repeated the preceding panel/foot
    """

    stance: Stance
    moved: FootMove
    mines_since_press: int = 0
    last_press_col: int | None = None
    last_press_foot: FootMove | None = None
    hold_owners: tuple[tuple[int, FootMove], ...] = ()
    released_since_press: FootMove = FootMove.NONE
    last_repeat_jack: bool | None = None

    @classmethod
    def initial(cls) -> FootRow:
        """Default starting node before the first note of a chart (L on Left, R on Right)."""
        return cls(
            stance=Stance.from_feet(FootPlacement.L, FootPlacement.R),
            moved=FootMove.NONE,
        )

    def hold_owner_for(self, col: int) -> FootMove | None:
        for owned_col, foot in self.hold_owners:
            if owned_col == col:
                return foot
        return None

    def active_columns_mask(self) -> int:
        """4-bit mask of panels actively pressed on this specific row."""
        mask = 0
        if self.moved & FootMove.LEFT:
            mask |= self.stance.left.mask
        if self.moved & FootMove.RIGHT:
            mask |= self.stance.right.mask
        return mask
