from enum import StrEnum
from typing import Any

from patternity.models.engine import TimingEngine
from patternity.models.metric import BasicMetrics
from patternity.models.song import Chart, Header


class Foot(StrEnum):
    LEFT = "L"
    RIGHT = "R"


class Analyzer:
    def __init__(
        self,
        header: Header,
        chart: Chart,
        min_stream_nps: float = 7.0,
        min_stream_measures: float = 1.0,
    ) -> None:
        self.chart = chart
        self.min_stream_nps = min_stream_nps
        self.min_stream_measures = min_stream_measures
        self.timing_engine = TimingEngine(bpms=header.bpms, stops=header.stops)
        self.basic_metrics = BasicMetrics()

    def analyze(self) -> dict[str, Any]:
        for note_row in self.chart.notes:
            elapsed_time = self.timing_engine.convert_beat_to_seconds(note_row.beat)
            self.basic_metrics.add_note(note_row)
