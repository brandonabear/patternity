from pathlib import Path

import pytest

from patternity.simfile import read_simfile
from patternity.training import evaluate_annotated, format_report, parse_annotated_sm

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

# Minimum per-row foot accuracy with the packaged weights. Raise these as the
# model improves; lowering one needs a reason (new annotations, new fixture).
_MIN_ACCURACY = {
    "patterns/footswitches.sm": 1.0,
    "patterns/jacks.sm": 1.0,
    "patterns/brackets.sm": 1.0,
    "patterns/sideswitches.sm": 1.0,
    "patterns/doublesteps.sm": 1.0,
    "charts/burger.ssc": 1.0,
}
_MIN_PATTERN_F1 = 0.75


def _report(fixture_relpath: str):  # type: ignore[no-untyped-def]
    annotated = parse_annotated_sm(read_simfile(FIXTURES / fixture_relpath))
    return annotated, evaluate_annotated(fixture_relpath, annotated)


@pytest.mark.regression
@pytest.mark.parametrize("fixture_relpath", sorted(_MIN_ACCURACY))
def test_foot_accuracy_meets_threshold(fixture_relpath: str) -> None:
    annotated, report = _report(fixture_relpath)
    assert not report.impossible_annotations, format_report(report, annotated)
    assert report.accuracy >= _MIN_ACCURACY[fixture_relpath], format_report(
        report, annotated
    )


@pytest.mark.regression
@pytest.mark.parametrize("fixture_relpath", sorted(_MIN_ACCURACY))
def test_pattern_tags_match_labels(fixture_relpath: str) -> None:
    annotated, report = _report(fixture_relpath)
    for kind, score in report.patterns.items():
        if not (score.true_positives or score.false_negatives):
            continue
        f1 = 2 * score.precision * score.recall / (score.precision + score.recall or 1)
        assert f1 >= _MIN_PATTERN_F1, f"{kind}: " + format_report(report, annotated)
