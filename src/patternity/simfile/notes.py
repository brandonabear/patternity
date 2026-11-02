from dataclasses import dataclass
from dataclasses import fields as _fields
from enum import StrEnum
from typing import Any, Literal


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
    hold_active_mask: int = 0
    roll_active_mask: int = 0

    @staticmethod
    def column_bit(col: int) -> int:
        return 1 << col

    @classmethod
    def column_active(cls, mask: int, col: int) -> bool:
        return bool(mask & cls.column_bit(col))

    @property
    def press_mask(self) -> int:
        """4-bit mask of columns requiring a foot press on this row (TAP, HOLD head, ROLL head)."""
        mask = 0
        for col, note in enumerate((self.left, self.down, self.up, self.right)):
            if note in PRESSABLE_NOTES:
                mask |= self.column_bit(col)
        return mask

    @property
    def mine_mask(self) -> int:
        """4-bit mask of columns containing a MINE on this row."""
        mask = 0
        for col, note in enumerate((self.left, self.down, self.up, self.right)):
            if note == NoteType.MINE:
                mask |= self.column_bit(col)
        return mask

    @classmethod
    def from_str(cls, row: str, **kwargs: Any) -> NoteRow:
        if not row:
            raise ValueError("Note rows cannot be empty.")
        left, down, up, right = (NoteType(char) for char in row)
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
            hold_active_mask=int(data.get("hold_active_mask", 0)),
            roll_active_mask=int(data.get("roll_active_mask", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for f in _fields(self):
            value = getattr(self, f.name)
            if value is None:
                continue
            if f.name in ("hold_active_mask", "roll_active_mask") and value == 0:
                continue
            if isinstance(value, StrEnum):
                result[f.name] = value.value
            else:
                result[f.name] = value
        return result


_NUM_COLUMNS = 4
_AnchorKind = Literal["idle", "hold", "roll"]


class AnchorTracker:
    """Per-column hold/roll state while parsing chart rows (``hold_active_mask`` /
    ``roll_active_mask``)."""

    def __init__(self) -> None:
        self._state: list[_AnchorKind] = ["idle"] * _NUM_COLUMNS

    def apply_heads(self, row: NoteRow) -> None:
        for col, note in enumerate((row.left, row.down, row.up, row.right)):
            match note:
                case NoteType.HOLD:
                    self._state[col] = "hold"
                case NoteType.ROLL:
                    self._state[col] = "roll"

    def snapshot(self) -> tuple[int, int]:
        hold_mask = 0
        roll_mask = 0

        for col in range(_NUM_COLUMNS):
            match self._state[col]:
                case "hold":
                    hold_mask |= NoteRow.column_bit(col)
                case "roll":
                    roll_mask |= NoteRow.column_bit(col)

        return hold_mask, roll_mask

    def apply_tails(self, row: NoteRow) -> None:
        for col, note in enumerate((row.left, row.down, row.up, row.right)):
            match note:
                case NoteType.TAIL:
                    self._state[col] = "idle"
