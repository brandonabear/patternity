from dataclasses import dataclass, field
from typing import Any

from patternity.patterns.spans import PatternKind, PatternSpan


@dataclass
class TechMetrics:
    """Tech pattern detections for a chart.

    Spans are the source of truth; aggregate counts are derived for reports.
    """

    spans: list[PatternSpan] = field(default_factory=list)

    def count(self, kind: PatternKind) -> int:
        """Return count of a given pattern across all spans."""
        return sum(1 for span in self.spans if span.kind == kind)

    @property
    def crossovers(self) -> int:
        return self.count(PatternKind.CROSSOVER) + self.count(PatternKind.INVERTED_CROSSOVER)

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

    @property
    def candles(self) -> int:
        return self.count(PatternKind.CANDLE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "crossovers": self.crossovers,
            "footswitches": self.footswitches,
            "sideswitches": self.sideswitches,
            "jacks": self.jacks,
            "brackets": self.brackets,
            "doublesteps": self.doublesteps,
            "candles": self.candles,
        }
