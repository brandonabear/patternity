from dataclasses import dataclass
from dataclasses import fields as _fields
from typing import Any

from patternity.models.engine import NoteRow, NoteType

PRESSABLE_NOTES = {
    NoteType.TAP,
    NoteType.HOLD,
    NoteType.ROLL,
    NoteType.LIFT,
}


@dataclass
class BasicMetrics:
    """Basic metrics for a song.

    Basic metrics are counts of standard note types and steps.
    """

    taps: int = 0
    jumps: int = 0
    hands: int = 0
    holds: int = 0
    rolls: int = 0
    mines: int = 0
    lifts: int = 0
    fakes: int = 0
    steps: int = 0

    def add_note(self, note_row: NoteRow) -> None:
        panels = (note_row.left, note_row.down, note_row.up, note_row.right)
        for panel in panels:
            if panel in (NoteType.EMPTY, NoteType.TAIL):
                continue
            match panel:
                case NoteType.MINE:
                    self.mines += 1
                case NoteType.FAKE:
                    self.fakes += 1
                case NoteType.LIFT:
                    self.lifts += 1
                case NoteType.ROLL:
                    self.rolls += 1
                case NoteType.HOLD:
                    self.holds += 1
                case _:
                    continue

        active_panels = [p for p in panels if p in PRESSABLE_NOTES]
        self.steps += len(active_panels)
        match len(active_panels):
            case 0:
                pass
            case 1:
                self.taps += 1
            case 2:
                self.taps += 1
                self.jumps += 1
            case n if n >= 3:
                self.taps += 1
                self.hands += 1

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in _fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BasicMetrics:
        return cls(**{f.name: int(data.get(f.name, 0)) for f in _fields(cls)})


@dataclass
class TechMetrics:
    """Tech metrics for community-defined patterns."""

    crossovers: int = 0
    footswitches: int = 0
    sideswitches: int = 0
    jacks: int = 0
    brackets: int = 0
    doublesteps: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in _fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TechMetrics:
        return cls(**{f.name: int(data.get(f.name, 0)) for f in _fields(cls)})


@dataclass
class MovementMetrics:
    """Player movement metrics."""

    direction_shifts: int = 0
    turns: int = 0
    candles: int = 0
    total_cost: float = 0.0


@dataclass
class StreamMetrics:
    """Stream metrics for a song."""

    measures: int = 0
    avg_nps: float = 0.0
    max_nps: float = 0.0
    longest_stream_measures: float = 0.0
