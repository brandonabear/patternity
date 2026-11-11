from dataclasses import dataclass
from dataclasses import fields as _fields
from typing import Any

from patternity.simfile.notes import NoteRow, NoteType


@dataclass
class BasicMetrics:
    """Basic metrics for a chart."""

    taps: int = 0  # Count of pressable rows (jumps/hands = 1)
    jumps: int = 0  # Count of pressable notes
    hands: int = 0
    holds: int = 0
    rolls: int = 0
    mines: int = 0
    lifts: int = 0
    fakes: int = 0
    steps: int = 0

    def add_note(self, note_row: NoteRow) -> None:
        heads = 0
        for panel in note_row.notes:
            match panel:
                case NoteType.MINE:
                    self.mines += 1
                case NoteType.FAKE:
                    self.fakes += 1
                case NoteType.LIFT:
                    self.lifts += 1
                case NoteType.ROLL:
                    self.rolls += 1
                    heads += 1
                case NoteType.HOLD:
                    self.holds += 1
                    heads += 1
                case NoteType.TAP:
                    heads += 1
                case _:
                    # Empty panels and hold/roll tails count toward nothing.
                    continue

        self.steps += heads
        if heads:
            self.taps += 1
            if heads >= 2:
                self.jumps += 1
            ongoing_holds = note_row.holds_active & ~note_row.pressed
            covered_panels = len(note_row.pressed | ongoing_holds)
            if covered_panels >= 3:
                self.hands += 1

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in _fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BasicMetrics:
        kwargs = {f.name: int(data.get(f.name, 0)) for f in _fields(cls)}
        return cls(**kwargs)
