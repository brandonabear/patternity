import itertools
import math
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


class TimingEngine:
    """Track elapsed beats and seconds."""

    def __init__(
        self,
        bpms: dict[float, float] | None,
        stops: dict[float, float] | None,
    ):
        self.bpms = (
            sorted([*bpms.items(), (math.inf, math.nan)], key=lambda x: x[0])
            if bpms
            else []
        )
        self.stops = sorted(stops.items(), key=lambda x: x[0]) if stops else []

    def convert_beat_to_seconds(self, target_beat: float) -> float:
        """Convert a target beat to elapsed seconds.

        Only handles BPM changes and stops.
        """

        # Calculate elapsed time across BPM changes.
        elapsed_time = 0.0
        for (current_beat, current_bpm), (next_beat, next_bpm) in itertools.pairwise(
            self.bpms
        ):
            if target_beat <= current_beat:
                break
            if target_beat <= next_beat:
                elapsed_time += (target_beat - current_beat) * (60.0 / current_bpm)
                break
            elapsed_time += (next_beat - current_beat) * (60.0 / current_bpm)

        # Append elapsed time across stops.
        for stop_beat, stop_duration in self.stops:
            if stop_beat <= target_beat:
                elapsed_time += stop_duration
            else:
                break

        return elapsed_time
