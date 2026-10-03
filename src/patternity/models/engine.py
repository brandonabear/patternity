from dataclasses import dataclass
from dataclasses import fields as _fields
from enum import StrEnum
from typing import Any


class NoteType(StrEnum):
    EMPTY = "0"
    TAP = "1"
    HOLD = "2"
    TAIL = "3"
    ROLL = "4"
    MINE = "M"
    FAKE = "F"
    LIFT = "L"


@dataclass
class NoteRow:
    left: NoteType | None = None
    down: NoteType | None = None
    up: NoteType | None = None
    right: NoteType | None = None
    quantization: int | None = None
    beat: float | None = None
    measure: int | None = None

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
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for f in _fields(self):
            value = getattr(self, f.name)
            if value is None:
                continue
            if isinstance(value, StrEnum):
                result[f.name] = value.value
            else:
                result[f.name] = value
        return result
