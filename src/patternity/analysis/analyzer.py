from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from patternity.analysis.metrics import BasicMetrics
from patternity.footing import FootingModel, resolve_chart
from patternity.movement import MovementMetrics, detect_movement
from patternity.patterns import TechMetrics, detect_tech_patterns
from patternity.simfile.notes import NoteRow
from patternity.simfile.song import Chart


@dataclass(frozen=True, slots=True)
class ChartAnalysis:
    """Every metric computed for one chart."""

    basic: BasicMetrics
    tech: TechMetrics
    movement: MovementMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "basic": self.basic.to_dict(),
            "tech": self.tech.to_dict(),
            "movement": self.movement.to_dict(),
        }


def count_basic(rows: Sequence[NoteRow]) -> BasicMetrics:
    """Basic metrics from chart notation alone; footing plays no part."""
    basic = BasicMetrics()
    for row in rows:
        basic.add_note(row)
    return basic


def analyze_chart(
    chart: Chart,
    model: FootingModel | None = None,
    *,
    allow_brackets: bool = True,
) -> ChartAnalysis:
    """Decode the chart's footing and compute all metrics."""
    resolved = resolve_chart(
        chart.notes, model, allow_brackets=allow_brackets, with_confidence=False
    )
    return ChartAnalysis(
        basic=count_basic(chart.notes),
        tech=detect_tech_patterns(resolved.steps),
        movement=detect_movement(resolved),
    )


class Analyzer:
    """Earlier entry point, kept for existing callers; prefer ``analyze_chart``."""

    def __init__(
        self,
        chart: Chart,
        *,
        model: FootingModel | None = None,
        allow_brackets: bool = True,
    ) -> None:
        self.chart = chart
        self.model = model
        self.allow_brackets = allow_brackets

    def analyze(self) -> dict[str, Any]:
        return analyze_chart(
            self.chart, self.model, allow_brackets=self.allow_brackets
        ).to_dict()
