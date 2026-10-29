from dataclasses import dataclass
from enum import StrEnum

from patternity.solver import ResolvedStep


class PatternKind(StrEnum):
    """Community tech pattern categories detected on a resolved foot path."""

    JACK = "jack"
    DOUBLESTEP = "doublestep"
    FOOTSWITCH = "footswitch"
    SIDESWITCH = "sideswitch"
    BRACKET = "bracket"
    CROSSOVER = "crossover"
    INVERTED_CROSSOVER = "inverted_crossover"


@dataclass(frozen=True, slots=True)
class PatternSpan:
    """One detected pattern instance anchored to chart beats and measures."""

    kind: PatternKind
    start_beat: float
    end_beat: float
    start_measure: int
    end_measure: int
    steps: tuple[ResolvedStep, ...]
