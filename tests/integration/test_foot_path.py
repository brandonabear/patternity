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
    "patterns/candles.sm": 1.0,
    "patterns/crossovers.sm": 1.0,
    "charts/burger.ssc": 1.0,
    "charts/hoot.ssc": 1.0,
    "charts/move_mint.ssc": 1.0,
    "charts/too_much.ssc": 1.0,
    "charts/godspeed.ssc": 1.0,
    "charts/mazy_metroplex.ssc": 1.0,
}

# Hold-out charts (holdout_corpus.txt) are never trained on. These are the
# accuracies measured with the packaged weights, recorded as a floor so a
# retrain that generalizes worse fails. They are not targets: tuning features
# or annotations until a hold-out reaches 1.0 makes it a training chart.
_HOLDOUT_ACCURACY = {
    "charts/kiss_me_more.ssc": 1.0,
    "charts/boomshakalaka.ssc": 1.0,
    # 3 of its 4 annotated rows: line 505 is tagged LEFT (a bracket), decoded as a jump.
    "charts/senpai_notice_me.ssc": 0.75,
}
_ACCURACY_FLOOR = _MIN_ACCURACY | _HOLDOUT_ACCURACY

# Exact (true positives, false positives, false negatives) per scored pattern
# kind against the @pattern tags; a kind not listed must score (0, 0, 0). This
# is a ratchet: update a line when a count improves, and give a reason when one
# gets worse.
#
# Known misses pinned here rather than hidden:
# - False-positive candles on hoot, move_mint, too_much and mazy_metroplex are
#   candles the chart doesn't tag, not wrong detections.
# - hoot misses its 3 tagged jacks.
# - jacks.sm has one detected jack with no tag.
# - senpai_notice_me's bracket miss and extra candle follow from its one
#   misfooted row (see _HOLDOUT_ACCURACY).
_PATTERN_SCORES: dict[str, dict[str, tuple[int, int, int]]] = {
    "patterns/footswitches.sm": {
        "jack": (4, 0, 0),
        "footswitch": (11, 0, 0),
        "doublestep": (3, 0, 0),
        "candle": (8, 0, 0),
    },
    "patterns/jacks.sm": {"jack": (3, 1, 0), "candle": (2, 0, 0)},
    "patterns/brackets.sm": {"footswitch": (1, 0, 0), "bracket": (11, 0, 0), "candle": (7, 0, 0)},
    "patterns/sideswitches.sm": {"jack": (1, 0, 0), "sideswitch": (1, 0, 0), "candle": (1, 0, 0)},
    "patterns/doublesteps.sm": {"doublestep": (4, 0, 0)},
    "patterns/candles.sm": {"doublestep": (2, 0, 0), "candle": (5, 0, 0)},
    "patterns/crossovers.sm": {"candle": (10, 0, 0)},
    "charts/burger.ssc": {
        "footswitch": (60, 0, 0),
        "doublestep": (20, 0, 0),
        "bracket": (14, 0, 0),
        "candle": (56, 0, 0),
    },
    "charts/hoot.ssc": {
        "jack": (0, 0, 3),
        "footswitch": (57, 0, 0),
        "sideswitch": (2, 0, 0),
        "doublestep": (1, 0, 0),
        "bracket": (5, 0, 0),
        "candle": (0, 37, 0),
    },
    "charts/move_mint.ssc": {
        "footswitch": (6, 0, 0),
        "sideswitch": (9, 0, 0),
        "candle": (0, 12, 0),
    },
    "charts/too_much.ssc": {
        "jack": (20, 0, 0),
        "footswitch": (9, 0, 0),
        "doublestep": (29, 0, 0),
        "candle": (0, 13, 0),
    },
    "charts/godspeed.ssc": {"bracket": (4, 0, 0)},
    "charts/mazy_metroplex.ssc": {"jack": (8, 0, 0), "bracket": (4, 0, 0), "candle": (0, 4, 0)},
    "charts/kiss_me_more.ssc": {
        "jack": (5, 0, 0),
        "footswitch": (4, 0, 0),
        "doublestep": (13, 0, 0),
        "bracket": (7, 0, 0),
        "candle": (36, 0, 0),
    },
    "charts/boomshakalaka.ssc": {
        "footswitch": (24, 0, 0),
        "sideswitch": (22, 0, 0),
        "doublestep": (1, 0, 0),
        "bracket": (4, 0, 0),
        "candle": (76, 0, 1),
    },
    "charts/senpai_notice_me.ssc": {"bracket": (2, 0, 1), "candle": (0, 1, 0)},
}


def _report(fixture_relpath: str) -> tuple[AnnotatedChart, FixtureReport]:
    annotated = parse_annotated_sm(read_simfile(FIXTURES / fixture_relpath))
    return annotated, evaluate_annotated(fixture_relpath, annotated)


@pytest.mark.regression
@pytest.mark.parametrize("fixture_relpath", sorted(_ACCURACY_FLOOR))
def test_foot_accuracy_meets_threshold(fixture_relpath: str) -> None:
    annotated, report = _report(fixture_relpath)
    assert not report.impossible_annotations, format_report(report, annotated)
    assert report.accuracy >= _ACCURACY_FLOOR[fixture_relpath], format_report(report, annotated)


@pytest.mark.regression
@pytest.mark.parametrize("fixture_relpath", sorted(_PATTERN_SCORES))
def test_pattern_tags_match_labels(fixture_relpath: str) -> None:
    annotated, report = _report(fixture_relpath)
    actual = {
        kind.value: counts
        for kind, score in report.patterns.items()
        if any(counts := (score.true_positives, score.false_positives, score.false_negatives))
    }
    assert actual == _PATTERN_SCORES[fixture_relpath], format_report(report, annotated)


def test_holdout_charts_are_not_trained_on() -> None:
    assert not set(load_holdout(FIXTURES)) & set(load_corpus(FIXTURES))


def test_holdout_charts_have_a_recorded_accuracy() -> None:
    assert set(load_holdout(FIXTURES)) == set(_HOLDOUT_ACCURACY)


def test_training_charts_have_accuracy_thresholds() -> None:
    assert set(load_corpus(FIXTURES)) <= set(_MIN_ACCURACY)


def test_every_chart_with_a_threshold_has_pattern_scores() -> None:
    assert set(_PATTERN_SCORES) == set(_ACCURACY_FLOOR)
