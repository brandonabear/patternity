"""Tech-pattern analysis for StepMania charts.

Pipeline: ``simfile`` (parse) -> ``footing`` (decode a foot path) -> ``patterns``
(tag tech on that path) -> ``analysis``. ``training`` fits the footing weights.
"""

from patternity.analysis import ChartAnalysis, analyze_chart
from patternity.footing import FootingModel, resolve_chart
from patternity.patterns import detect_tech_patterns
from patternity.simfile import Panel, parse_simfile, read_simfile

__all__ = [
    "ChartAnalysis",
    "FootingModel",
    "Panel",
    "analyze_chart",
    "detect_tech_patterns",
    "parse_simfile",
    "read_simfile",
    "resolve_chart",
]
