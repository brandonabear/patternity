from dataclasses import dataclass
from enum import IntFlag, StrEnum
from typing import Any, Literal


class Panel(IntFlag):
    """A set of pad panels (empty, one panel, or several).

    This is the one place the bit layout lives: each panel is one bit, in the
    LDUR column order StepMania uses (Left = bit 0 ... Right = bit 3). Everywhere
    else, treat a ``Panel`` value as a set of panels:

    - ``Panel.U in pressed``: is Up pressed?
    - ``Panel.L | Panel.U``: both panels.
    - ``pressed in covered``: is every pressed panel covered? (subset)
    - ``held & ~releasable``: held panels that are not releasable.
    - ``len(pressed)``, ``for panel in pressed``: count and iterate.
    """

    NONE = 0
    L = 1
    D = 2
    U = 4
    R = 8

    @classmethod
    def at(cls, col: int) -> Panel:
        """The single panel at column index ``col`` (0-3, LDUR order)."""
        return PANELS[col]

    @property
    def column(self) -> int:
        """Column index (0-3, LDUR order) of a single panel."""
        return PANELS.index(self)


# Single panels in column (LDUR) order; zip with per-column data such as
# ``NoteRow.notes``.
PANELS: tuple[Panel, ...] = (Panel.L, Panel.D, Panel.U, Panel.R)


class NoteType(StrEnum):
    EMPTY = "0"
    TAP = "1"
    HOLD = "2"
    TAIL = "3"
    ROLL = "4"
    MINE = "M"
    FAKE = "F"
    LIFT = "L"


PRESSABLE_NOTES = frozenset({NoteType.TAP, NoteType.HOLD, NoteType.ROLL})
ANCHORED_NOTES = frozenset({NoteType.HOLD, NoteType.ROLL})
TAIL_NOTES = frozenset({NoteType.TAIL})
MINE_NOTES = frozenset({NoteType.MINE})


# One note per column, in LDUR order (pair with ``PANELS``).
Columns = tuple[NoteType, NoteType, NoteType, NoteType]

_NUM_COLUMNS = len(PANELS)


class InvalidNoteRow(ValueError):
    """A note row that is not four columns of known note characters."""


def parse_columns(text: str) -> Columns:
    """The four notes of a row as written in a simfile, e.g. ``"1M20"``."""
    if len(text) != _NUM_COLUMNS:
        raise InvalidNoteRow(f"expected {_NUM_COLUMNS} columns, got {text!r}")
    try:
        left, down, up, right = (NoteType(char) for char in text)
    except ValueError:
        raise InvalidNoteRow(f"unsupported note character in {text!r}") from None
    return (left, down, up, right)


@dataclass(frozen=True, slots=True)
class NoteRow:
    """One non-empty chart row: its notes, and where and when it falls."""

    notes: Columns
    measure: int
    quantization: int
    beat: float
    # Seconds from beat 0 (see ``TimingEngine``).
    timestamp: float
    # Panels with a hold / roll underway on this row (heads and tails included).
    holds_active: Panel = Panel.NONE
    rolls_active: Panel = Panel.NONE

    def panels_with(self, kinds: frozenset[NoteType]) -> Panel:
        """Panels whose note on this row is one of ``kinds``."""
        found = Panel.NONE
        for panel, note in zip(PANELS, self.notes, strict=True):
            if note in kinds:
                found |= panel
        return found

    @property
    def pressed(self) -> Panel:
        """Panels requiring a foot press on this row (TAP, HOLD head, ROLL head)."""
        return self.panels_with(PRESSABLE_NOTES)

    @property
    def mines(self) -> Panel:
        """Panels with a MINE on this row."""
        return self.panels_with(MINE_NOTES)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NoteRow:
        left, down, up, right = (NoteType(data[key]) for key in _COLUMN_KEYS)
        return cls(
            notes=(left, down, up, right),
            measure=int(data["measure"]),
            quantization=int(data["quantization"]),
            beat=float(data["beat"]),
            timestamp=float(data["timestamp"]),
            holds_active=Panel(int(data.get(_HOLDS_KEY, 0))),
            rolls_active=Panel(int(data.get(_ROLLS_KEY, 0))),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            key: note.value for key, note in zip(_COLUMN_KEYS, self.notes, strict=True)
        }
        result |= {
            "quantization": self.quantization,
            "beat": self.beat,
            "measure": self.measure,
            "timestamp": self.timestamp,
        }
        # Active panels are stored as plain ints, omitted when empty.
        if self.holds_active:
            result[_HOLDS_KEY] = int(self.holds_active)
        if self.rolls_active:
            result[_ROLLS_KEY] = int(self.rolls_active)
        return result


# JSON keys: one per column, and the active hold / roll panels (names kept from
# the earlier mask fields).
_COLUMN_KEYS = ("left", "down", "up", "right")
_HOLDS_KEY = "hold_active_mask"
_ROLLS_KEY = "roll_active_mask"

_AnchorKind = Literal["idle", "hold", "roll"]


class AnchorTracker:
    """Per-column hold/roll state while parsing chart rows, in order."""

    def __init__(self) -> None:
        self._state: list[_AnchorKind] = ["idle"] * _NUM_COLUMNS

    def advance(self, notes: Columns) -> tuple[Panel, Panel]:
        """Feed the next row; return its ``(holds_active, rolls_active)`` panels.

        A hold counts as active on both its head row and its tail row.
        """
        self._apply_heads(notes)
        active = self._snapshot()
        self._apply_tails(notes)
        return active

    def _apply_heads(self, notes: Columns) -> None:
        for col, note in enumerate(notes):
            match note:
                case NoteType.HOLD:
                    self._state[col] = "hold"
                case NoteType.ROLL:
                    self._state[col] = "roll"

    def _snapshot(self) -> tuple[Panel, Panel]:
        holds = Panel.NONE
        rolls = Panel.NONE

        for panel, state in zip(PANELS, self._state, strict=True):
            match state:
                case "hold":
                    holds |= panel
                case "roll":
                    rolls |= panel

        return holds, rolls

    def _apply_tails(self, notes: Columns) -> None:
        for col, note in enumerate(notes):
            match note:
                case NoteType.TAIL:
                    self._state[col] = "idle"
