from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from patternity.footing.resolve import ResolvedStep


class PatternKind(StrEnum):
    """Community tech pattern categories detected on a resolved foot path."""

    JACK = "jack"
    DOUBLESTEP = "doublestep"
    FOOTSWITCH = "footswitch"
    SIDESWITCH = "sideswitch"
    BRACKET = "bracket"
    CROSSOVER = "crossover"
    INVERTED_CROSSOVER = "inverted_crossover"
    CANDLE = "candle"


@dataclass(frozen=True, slots=True)
class PatternSpan:
    """One detected pattern instance: its kind and the steps it covers, in chart order."""

    kind: PatternKind
    steps: tuple[ResolvedStep, ...]

    @property
    def start_beat(self) -> float:
        return self.steps[0].note_row.beat

    @property
    def end_beat(self) -> float:
        return self.steps[-1].note_row.beat

    @property
    def start_measure(self) -> int:
        return self.steps[0].note_row.measure

    @property
    def end_measure(self) -> int:
        return self.steps[-1].note_row.measure
