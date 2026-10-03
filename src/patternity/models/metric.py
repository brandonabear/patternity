from dataclasses import dataclass, field
from dataclasses import fields as _fields
from typing import Any

from patternity.models.song import Difficulty, GrooveRadar, Song


@dataclass
class BasicMetrics:
    taps: int = 0
    jumps: int = 0
    hands: int = 0
    holds: int = 0
    rolls: int = 0
    mines: int = 0
    lifts: int = 0
    fakes: int = 0
    steps: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in _fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BasicMetrics:
        return cls(**{f.name: int(data.get(f.name, 0)) for f in _fields(cls)})


@dataclass
class TechMetrics:
    crossovers: int = 0
    left_candles: int = 0
    right_candles: int = 0
    footswitches: int = 0
    sideswitches: int = 0
    jacks: int = 0
    brackets: int = 0
    facing_shifts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in _fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TechMetrics:
        return cls(**{f.name: int(data.get(f.name, 0)) for f in _fields(cls)})


@dataclass
class StreamSegment:
    start_beat: float
    end_beat: float
    start_time: float
    end_time: float
    note_count: int
    measures: float
    avg_sps: float

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in _fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StreamSegment:
        return cls(
            start_beat=float(data["start_beat"]),
            end_beat=float(data["end_beat"]),
            start_time=float(data["start_time"]),
            end_time=float(data["end_time"]),
            note_count=int(data["note_count"]),
            measures=float(data["measures"]),
            avg_sps=float(data["avg_sps"]),
        )


@dataclass
class DensityMetrics:
    peak_nps: float = 0.0
    avg_nps: float = 0.0
    total_stream_measures: float = 0.0
    stream_segments: list[StreamSegment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "peak_nps": self.peak_nps,
            "avg_nps": self.avg_nps,
            "total_stream_measures": self.total_stream_measures,
            "stream_segments": [s.to_dict() for s in self.stream_segments],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DensityMetrics:
        return cls(
            peak_nps=float(data.get("peak_nps", 0.0)),
            avg_nps=float(data.get("avg_nps", 0.0)),
            total_stream_measures=float(data.get("total_stream_measures", 0.0)),
            stream_segments=[
                StreamSegment.from_dict(s) for s in data.get("stream_segments", [])
            ],
        )


@dataclass
class ChartAnalysisResult:
    difficulty: Difficulty
    rating: float
    duration_seconds: float
    counts: BasicMetrics
    tech: TechMetrics
    density: DensityMetrics
    min_stream_sps: float
    min_stream_measures: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "difficulty": self.difficulty.value,
            "rating": self.rating,
            "duration_seconds": self.duration_seconds,
            "min_stream_sps": self.min_stream_sps,
            "min_stream_measures": self.min_stream_measures,
            "counts": self.counts.to_dict(),
            "tech": self.tech.to_dict(),
            "density": self.density.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChartAnalysisResult:
        return cls(
            difficulty=Difficulty(str(data["difficulty"])),
            rating=float(data["rating"]),
            duration_seconds=float(data["duration_seconds"]),
            counts=BasicMetrics.from_dict(data["counts"]),
            tech=TechMetrics.from_dict(data["tech"]),
            density=DensityMetrics.from_dict(data["density"]),
            min_stream_sps=float(data["min_stream_sps"]),
            min_stream_measures=float(data["min_stream_measures"]),
        )

    def format_reports(self) -> str:
        """Return a formatted string with chart analysis statistics."""
        lines = [
            f"=== {self.difficulty} ({self.rating}) Analysis ===",
            f"Steps: {self.counts.steps}",
            f"Taps: {self.counts.taps} | Jumps: {self.counts.jumps} | Hands: {self.counts.hands}",
            f"Peak NPS: {self.density.peak_nps}",
            f"Average NPS: {self.density.avg_nps}",
            f"Crossover Steps: {self.tech.crossovers}",
            f"Jacks: {self.tech.jacks} | Footswitches: {self.tech.footswitches}",
            f"Candles (L/R): {self.tech.left_candles} / {self.tech.right_candles}",
            f"Facing Shifts: {self.tech.facing_shifts}",
            f"Total Stream Measures: {self.density.total_stream_measures}",
        ]
        return "\n".join(lines)

    def format_radar(self, radar: GrooveRadar) -> str:
        """Return a formatted string with Groove Radar statistics."""
        lines = [
            "\n=== Radar Statistics ===",
            f"Steps: {radar.steps}",
            f"Taps: {radar.taps}",
            f"Jumps: {radar.jumps}",
            f"Hands: {radar.hands}",
            "",
            "",
        ]
        return "\n".join(lines)


@dataclass
class AnalyzedSong:
    song: Song
    analyses: list[ChartAnalysisResult | None] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        charts: list[dict[str, Any]] = []
        for i, chart in enumerate(self.song.charts):
            chart_dict = chart.to_dict()
            analysis = self.analyses[i] if i < len(self.analyses) else None
            if analysis is not None:
                chart_dict["analysis"] = analysis.to_dict()
            charts.append(chart_dict)
        return {
            "header": self.song.header.to_dict(),
            "charts": charts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalyzedSong:
        chart_dicts = data.get("charts", [])
        song = Song.from_dict(
            {
                "header": data["header"],
                "charts": [
                    {k: v for k, v in chart.items() if k != "analysis"}
                    for chart in chart_dicts
                ],
            }
        )
        analyses: list[ChartAnalysisResult | None] = []
        for chart in chart_dicts:
            raw = chart.get("analysis")
            if raw is None:
                analyses.append(None)
            else:
                analyses.append(ChartAnalysisResult.from_dict(raw))
        return cls(song=song, analyses=analyses)
