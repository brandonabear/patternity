"""Tech-pattern analysis for StepMania charts.

Pipeline: ``simfile`` (parse) -> ``footing`` (decode a foot path) -> ``patterns``
(tag tech on that path) -> ``analysis``. ``training`` fits the footing weights.
"""

from patternity.analysis import Analyzer
from patternity.footing import FootingModel, resolve_chart
from patternity.patterns.detector import detect_tech_patterns
from patternity.simfile import Panel, StepmaniaFileParser, read_simfile

__all__ = [
    "Analyzer",
    "FootingModel",
    "Panel",
    "StepmaniaFileParser",
    "detect_tech_patterns",
    "read_simfile",
    "resolve_chart",
]
