from dataclasses import dataclass
from dataclasses import fields as _fields
from typing import Any

from patternity.simfile.notes import NoteRow, NoteType


@dataclass
class BasicMetrics:
    """Basic metrics for a chart."""

    taps: int = 0  # Press rows (a jump or hand is one tap).
    jumps: int = 0  # Press rows with two or more pressed panels.
    hands: int = 0  # Press rows with three or more panels pressed or held.
    holds: int = 0  # Hold heads.
    rolls: int = 0  # Roll heads.
    mines: int = 0
    lifts: int = 0
    fakes: int = 0
    steps: int = 0  # Pressed notes (a jump is two steps).

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
            # An ongoing hold occupies a foot or hand. Ongoing rolls are not counted.
            ongoing_holds = note_row.holds_active & ~note_row.pressed
            covered_panels = len(note_row.pressed | ongoing_holds)
            if covered_panels >= 3:
                self.hands += 1

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in _fields(self)}
