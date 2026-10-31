from typing import Any

from patternity.footing import FootingModel, resolve_chart
from patternity.metrics import BasicMetrics, MovementMetrics, TechMetrics
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
        for note_row in self.chart.notes:
            self.basic_metrics.add_note(note_row)

        resolved = resolve_chart(
            self.chart.notes,
            self.model,
            allow_brackets=self.allow_brackets,
            with_confidence=False,
        )
        self.tech_metrics = detect_tech_patterns(resolved.steps)
        self.movement_metrics.total_cost = resolved.cost
        self.movement_metrics.foot_path_feasible = resolved.feasible

        return {
            "basic": self.basic_metrics.to_dict(),
            "tech": self.tech_metrics.to_dict(),
            "movement": self.movement_metrics.to_dict(),
        }
