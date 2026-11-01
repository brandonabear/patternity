from patternity.analysis import TechMetrics
from patternity.patterns import PatternKind, PatternSpan


def _span(kind: PatternKind) -> PatternSpan:
    return PatternSpan(
        kind=kind,
        start_beat=0.0,
        end_beat=0.0,
        start_measure=0,
        end_measure=0,
        steps=(),
    )


def test_tech_metrics_counts_derived_from_spans() -> None:
    metrics = TechMetrics(
        spans=[
            _span(PatternKind.BRACKET),
            _span(PatternKind.BRACKET),
            _span(PatternKind.CROSSOVER),
            _span(PatternKind.INVERTED_CROSSOVER),
            _span(PatternKind.JACK),
        ]
    )
    assert metrics.brackets == 2
    assert metrics.crossovers == 2
    assert metrics.jacks == 1
    assert metrics.to_dict()["doublesteps"] == 0
