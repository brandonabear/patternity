"""Tech-pattern spans and the detector that tags them on a resolved foot path.

The detector lives in ``patternity.patterns.detector`` and is not re-exported here:
``patternity.metrics`` depends on the span types, and the detector depends on
``patternity.metrics``.
"""

from patternity.patterns.spans import PatternKind, PatternSpan

__all__ = ["PatternKind", "PatternSpan"]
