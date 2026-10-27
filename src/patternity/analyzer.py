from typing import Any

from patternity.models.engine import TimingEngine
from patternity.models.metric import BasicMetrics, MovementMetrics, TechMetrics
from patternity.models.song import Chart, Header


class Analyzer:
    def __init__(
        self,
        header: Header,
        chart: Chart,
        min_stream_nps: float = 7.0,
        min_stream_measures: float = 1.0,
        min_jack_nps: float = 5.7,
    ) -> None:
        self.chart = chart
        self.min_stream_nps = min_stream_nps
        self.min_stream_measures = min_stream_measures
        self.min_jack_nps = min_jack_nps
        self.timing_engine = TimingEngine(bpms=header.bpms, stops=header.stops)
        self.basic_metrics = BasicMetrics()
        self.tech_metrics = TechMetrics()
        self.movement_metrics = MovementMetrics()
        self.foot_path_feasible = True

    def analyze(self) -> dict[str, Any]:
        for note_row in self.chart.notes:
            self.basic_metrics.add_note(note_row)

        return {
            "basic": self.basic_metrics.to_dict(),
            "tech": self.tech_metrics.to_dict(),
            "movement": {
                "total_cost": self.movement_metrics.total_cost,
                "foot_path_feasible": self.foot_path_feasible,
            },
        }
