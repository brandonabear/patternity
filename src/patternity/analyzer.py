from enum import StrEnum
from typing import Any

from patternity.models.engine import NoteType
from patternity.models.metric import BasicMetrics
from patternity.models.song import Chart


class Foot(StrEnum):
    LEFT = "L"
    RIGHT = "R"


class Analyzer:
    def __init__(
        self,
        min_stream_nps: float = 7.0,
        min_stream_measures: float = 1.0,
    ):
        self.min_stream_nps = min_stream_nps
        self.min_stream_measures = min_stream_measures
        self.basic_metrics = BasicMetrics()

    def analyze(self, chart: Chart) -> dict[str, Any]:
        for note_row in chart.notes:
            self.basic_metrics.add_note(note_row)