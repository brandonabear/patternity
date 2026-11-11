from dataclasses import dataclass
from dataclasses import fields as _fields
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


class InvalidNoteRow(ValueError):
    """A note row that is not four columns of known note characters."""


@dataclass
class NoteRow:
    left: NoteType | None = None
    down: NoteType | None = None
    up: NoteType | None = None
    right: NoteType | None = None
    quantization: int | None = None
    beat: float | None = None
    measure: int | None = None
    timestamp: float | None = None
    # Panels with a hold / roll underway on this row (heads and tails included).
    holds_active: Panel = Panel.NONE
    rolls_active: Panel = Panel.NONE

    @property
    def notes(self) -> tuple[NoteType | None, NoteType | None, NoteType | None, NoteType | None]:
        """The four columns in LDUR order (pair with ``PANELS``)."""
        return (self.left, self.down, self.up, self.right)

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
    def from_str(cls, row: str, **kwargs: Any) -> NoteRow:
        if len(row) != _NUM_COLUMNS:
            raise InvalidNoteRow(f"expected {_NUM_COLUMNS} columns, got {row!r}")
        try:
            left, down, up, right = (NoteType(char) for char in row)
        except ValueError:
            raise InvalidNoteRow(f"unsupported note character in {row!r}") from None
        return cls(left=left, down=down, up=up, right=right, **kwargs)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NoteRow:
        return cls(
            left=NoteType(data["left"]) if data.get("left") else None,
            down=NoteType(data["down"]) if data.get("down") else None,
            up=NoteType(data["up"]) if data.get("up") else None,
            right=NoteType(data["right"]) if data.get("right") else None,
            quantization=data.get("quantization"),
            beat=data.get("beat"),
            measure=data.get("measure"),
            timestamp=data.get("timestamp"),
            holds_active=Panel(int(data.get(_HOLDS_KEY, 0))),
            rolls_active=Panel(int(data.get(_ROLLS_KEY, 0))),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for f in _fields(self):
            value = getattr(self, f.name)
            if value is None:
                continue
            if isinstance(value, Panel):
                # Stored as plain ints under their original JSON keys, omitted when empty.
                if value:
                    result[_ACTIVE_JSON_KEYS[f.name]] = int(value)
            elif isinstance(value, StrEnum):
                result[f.name] = value.value
            else:
                result[f.name] = value
        return result


# JSON keys for the active hold / roll panels (kept from the earlier mask fields).
_HOLDS_KEY = "hold_active_mask"
_ROLLS_KEY = "roll_active_mask"
_ACTIVE_JSON_KEYS = {"holds_active": _HOLDS_KEY, "rolls_active": _ROLLS_KEY}

_NUM_COLUMNS = 4
_AnchorKind = Literal["idle", "hold", "roll"]


class AnchorTracker:
    """Per-column hold/roll state while parsing chart rows (``holds_active`` /
    ``rolls_active``)."""

    def __init__(self) -> None:
        self._state: list[_AnchorKind] = ["idle"] * _NUM_COLUMNS

    def apply_heads(self, row: NoteRow) -> None:
        for col, note in enumerate(row.notes):
            match note:
                case NoteType.HOLD:
                    self._state[col] = "hold"
                case NoteType.ROLL:
                    self._state[col] = "roll"

    def snapshot(self) -> tuple[Panel, Panel]:
        """Panels with a hold underway and panels with a roll underway."""
        holds = Panel.NONE
        rolls = Panel.NONE

        for panel, state in zip(PANELS, self._state, strict=True):
            match state:
                case "hold":
                    holds |= panel
                case "roll":
                    rolls |= panel

        return holds, rolls

    def apply_tails(self, row: NoteRow) -> None:
        for col, note in enumerate(row.notes):
            match note:
                case NoteType.TAIL:
                    self._state[col] = "idle"
