"""Tech-pattern spans and the detector that tags them on a resolved foot path."""

from patternity.patterns.detector import detect_tech_patterns
from patternity.patterns.metrics import TechMetrics
from patternity.patterns.spans import PatternKind, PatternSpan

__all__ = ["PatternKind", "PatternSpan", "TechMetrics", "detect_tech_patterns"]
