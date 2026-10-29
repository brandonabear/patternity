from typing import Any

from patternity.detector import detect_tech_patterns
from patternity.models.engine import TimingEngine
from patternity.models.metric import BasicMetrics, MovementMetrics, TechMetrics
from patternity.models.song import Chart, Header
from patternity.solver import CostWeights, resolve_chart


class Analyzer:
    def __init__(
        self,
        header: Header,
        chart: Chart,
        min_stream_nps: float = 7.0,
        min_stream_measures: float = 1.0,
        min_jack_nps: float = 5.7,
        *,
        cost_weights: CostWeights | None = None,
        beam_width: int | None = 16,
        allow_brackets: bool = True,
    ) -> None:
        self.chart = chart
        self.min_stream_nps = min_stream_nps
        self.min_stream_measures = min_stream_measures
        self.min_jack_nps = min_jack_nps
        self.cost_weights = cost_weights or CostWeights()
        self.beam_width = beam_width
        self.allow_brackets = allow_brackets
        self.timing_engine = TimingEngine(bpms=header.bpms, stops=header.stops)
        self.basic_metrics = BasicMetrics()
        self.tech_metrics = TechMetrics()
        self.movement_metrics = MovementMetrics()

    def analyze(self) -> dict[str, Any]:
        for note_row in self.chart.notes:
            self.basic_metrics.add_note(note_row)

        resolved = resolve_chart(
            self.chart.notes,
            weights=self.cost_weights,
            beam_width=self.beam_width,
            allow_brackets=self.allow_brackets,
        )
        self.tech_metrics = detect_tech_patterns(resolved.steps)

        if resolved.steps:
            self.movement_metrics.total_cost = resolved.steps[-1].cumulative_cost
        self.movement_metrics.foot_path_feasible = not resolved.used_fallback

        return {
            "basic": self.basic_metrics.to_dict(),
            "tech": self.tech_metrics.to_dict(),
            "movement": {
                "total_cost": self.movement_metrics.total_cost,
                "foot_path_feasible": self.movement_metrics.foot_path_feasible,
            },
        }
