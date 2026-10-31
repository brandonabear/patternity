from dataclasses import dataclass, field
from dataclasses import fields as _fields
from typing import Any

from patternity.patterns.spans import PatternKind, PatternSpan
from patternity.simfile.notes import NoteRow, NoteType


@dataclass
class BasicMetrics:
    """Basic metrics for a chart."""

    taps: int = 0  # Count of pressable rows (jumps/hands = 1)
    jumps: int = 0 # Count of pressable notes
    hands: int = 0
    holds: int = 0 
    rolls: int = 0 
    mines: int = 0
    lifts: int = 0
    fakes: int = 0
    steps: int = 0

    def add_note(self, note_row: NoteRow) -> None:
        panels = (note_row.left, note_row.down, note_row.up, note_row.right)
        heads = 0
        for panel in panels:
            # Skip empty rows early
            if panel == NoteType.EMPTY:
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
                    heads += 1
                case NoteType.HOLD:
                    self.holds += 1
                    heads += 1
                case NoteType.TAP:
                    heads += 1
                case _:
                    continue

        self.steps += heads
        if heads:
            self.taps += 1
            if heads >= 2:
                self.jumps += 1
            ongoing_holds = note_row.hold_active_mask & ~note_row.press_mask
            covered_panels = (note_row.press_mask | ongoing_holds).bit_count()
            if covered_panels >= 3:
                self.hands += 1

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in _fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BasicMetrics:
        kwargs = {f.name: int(data.get(f.name, 0)) for f in _fields(cls)}
        return cls(**kwargs)


@dataclass
class TechMetrics:
    """Tech pattern detections for a chart.

    Spans are the source of truth; aggregate counts are derived for reports.
    """

    spans: list[PatternSpan] = field(default_factory=list)

    def count(self, kind: PatternKind) -> int:
        return sum(1 for span in self.spans if span.kind == kind)

    @property
    def crossovers(self) -> int:
        return self.count(PatternKind.CROSSOVER) + self.count(
            PatternKind.INVERTED_CROSSOVER
        )

    @property
    def footswitches(self) -> int:
        return self.count(PatternKind.FOOTSWITCH)

    @property
    def sideswitches(self) -> int:
        return self.count(PatternKind.SIDESWITCH)

    @property
    def jacks(self) -> int:
        return self.count(PatternKind.JACK)

    @property
    def brackets(self) -> int:
        return self.count(PatternKind.BRACKET)

    @property
    def doublesteps(self) -> int:
        return self.count(PatternKind.DOUBLESTEP)

    def to_dict(self) -> dict[str, Any]:
        return {
            "crossovers": self.crossovers,
            "footswitches": self.footswitches,
            "sideswitches": self.sideswitches,
            "jacks": self.jacks,
            "brackets": self.brackets,
            "doublesteps": self.doublesteps,
        }


@dataclass
class MovementMetrics:
    """Player movement metrics from foot-path resolution."""

    direction_shifts: int = 0
    turns: int = 0
    candles: int = 0
    total_cost: float = 0.0
    foot_path_feasible: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cost": self.total_cost,
            "foot_path_feasible": self.foot_path_feasible,
        }
