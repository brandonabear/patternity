from typing import Any

from patternity.analysis.metrics import BasicMetrics, MovementMetrics, TechMetrics
from patternity.footing import FootingModel, resolve_chart
from patternity.movement import detect_movement
from patternity.patterns.detector import detect_tech_patterns
from patternity.simfile.song import Chart


class Analyzer:
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
        self.basic_metrics = BasicMetrics()
        self.tech_metrics = TechMetrics()
        self.movement_metrics = MovementMetrics()

    def analyze(self) -> dict[str, Any]:
        """Decode the chart and compute all metrics.

        Not idempotent: basic metrics accumulate into ``self.basic_metrics``, so a
        second call double-counts them. Call once per ``Analyzer``.
        """
        resolved = resolve_chart(
            self.chart.notes,
            self.model,
            allow_brackets=self.allow_brackets,
            with_confidence=False,
        )
        for step in resolved.steps:
            self.basic_metrics.add_note(step.note_row)
        self.tech_metrics = detect_tech_patterns(resolved.steps)
        self.movement_metrics = detect_movement(resolved)

        return {
            "basic": self.basic_metrics.to_dict(),
            "tech": self.tech_metrics.to_dict(),
            "movement": self.movement_metrics.to_dict(),
        }
