from pathlib import Path

import pytest

from patternity.simfile import read_simfile
from patternity.training import (
    evaluate_annotated,
    format_report,
    load_corpus,
    load_holdout,
    parse_annotated_sm,
)
from patternity.training.annotations import AnnotatedChart
from patternity.training.evaluation import FixtureReport

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
    # Hold-out charts (holdout_corpus.txt): never trained on.
    "charts/kiss_me_more.ssc": 1.0,
    "charts/boomshakalaka.ssc": 1.0,
}
_MIN_PATTERN_F1 = 0.75


def _report(fixture_relpath: str) -> tuple[AnnotatedChart, FixtureReport]:
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


def test_holdout_charts_are_not_trained_on() -> None:
    assert not set(load_holdout(FIXTURES)) & set(load_corpus(FIXTURES))


def test_holdout_charts_have_accuracy_thresholds() -> None:
    assert set(load_holdout(FIXTURES)) <= set(_MIN_ACCURACY)
