import math
import random
from pathlib import Path

import pytest

from patternity import Analyzer, analyze_chart, resolve_chart
from patternity.footing import FootingModel, resolve_trellis
from patternity.footing.features import FEATURE_NAMES, featurize
from patternity.footing.grace import hold_grace
from patternity.footing.rules import hits_mine
from patternity.footing.search import build_trellis, row_confidence, viterbi
from patternity.footing.stance import FootMove, FootRow
from patternity.footing.transitions import iter_legal_transitions
from patternity.patterns import PatternKind, detect_tech_patterns
from patternity.simfile import NoteRow, Panel
from patternity.training import (
    Example,
    leave_one_out,
    load_example,
    parse_annotated_sm,
    row_errors,
    train,
    trainer,
)
from patternity.training.annotations import AnnotationError
from patternity.training.trainer import NONNEGATIVE
from tests.helpers import chart_rows, chart_text, gold_steps


def _brute_force_min(rows: list[NoteRow], weights: list[float]) -> float:
    best = math.inf

    grace_rows = hold_grace(rows)

    def walk(i: int, prev: FootRow, cost: float, last_press: float | None) -> None:
        nonlocal best
        if i == len(rows):
            best = min(best, cost)
            return
        row = rows[i]
        now = row.timestamp
        dt = now - last_press if row.pressed and last_press is not None else None
        grace = grace_rows[i]
        for curr in iter_legal_transitions(prev, row, grace=grace.panels):
            if row.pressed and row.mines and hits_mine(curr, row.mines):
                continue
            feats = featurize(prev, curr, row, dt, grace_remaining=grace.remaining)
            edge = sum(weights[FEATURE_NAMES.index(k)] * v for k, v in feats.items())
            walk(i + 1, curr, cost + edge, now if row.pressed else last_press)

    walk(0, FootRow.initial(), 0.0, None)
    return best


@pytest.mark.parametrize(
    "rows",
    [
        pytest.param(["1000", "0100", "0100", "M010", "0001", "1100", "0010"], id="taps-and-mine"),
        pytest.param(["2000", "0100", "3010", "0002", "0100", "1003", "0010"], id="holds"),
        pytest.param(["4000", "0100", "3000", "0010", "0100", "0001"], id="roll-with-grace-window"),
        pytest.param(["1100", "0011", "1001", "0110", "0100", "1010"], id="brackets-and-jumps"),
        pytest.param(["0100", "0M00", "0100", "2001", "0100", "3M00", "0010"], id="mines-and-hold"),
    ],
)
def test_viterbi_matches_brute_force_over_all_paths(rows: list[str]) -> None:
    chart = parse_annotated_sm(chart_text([*rows, ","])).chart
    trellis = build_trellis(chart.notes)
    # The brute force knows nothing of relaxed fallbacks, so the chart must not need one.
    assert not trellis.relaxed_rows
    rng = random.Random(7)
    for _ in range(5):
        weights = [rng.uniform(-5, 20) for _ in FEATURE_NAMES]
        decoded = viterbi(trellis, weights)
        assert math.isclose(decoded.cost, _brute_force_min(chart.notes, weights), abs_tol=1e-6)


def test_confidence_is_infinite_when_only_one_foot_move_is_possible() -> None:
    # Left+Right cannot be bracketed, so the jump row is always BOTH.
    rows = ["1000", "1001", "0100", ","]
    chart = parse_annotated_sm(chart_text(rows)).chart
    trellis = build_trellis(chart.notes)
    confidence = row_confidence(trellis, FootingModel.default().vector())
    assert confidence[1] == math.inf
    assert confidence[0] is not None and 0.0 <= confidence[0] < math.inf


def test_physically_impossible_annotation_is_reported() -> None:
    rows = ["0002 // @foot=R", "1000 // @foot=R", "0003", ","]
    annotated = parse_annotated_sm(chart_text(rows))
    trellis = build_trellis(annotated.chart.notes)
    decoded = viterbi(
        trellis, FootingModel.default().vector(), allowed=annotated.tagged_assignments
    )
    assert decoded.relaxed_rows == (1,)


def test_switch_after_hold_release_needs_mine_cue() -> None:
    base = ["0020 // @foot=L", "0001 // @foot=R", "0030"]
    plain = gold_steps([*base, "0000", "0010 // @foot=R", "0000", "0000", "0000", ","], 200)
    cued = gold_steps([*base, "000M", "0010 // @foot=R", "0000", "0000", "0000", ","], 200)
    assert detect_tech_patterns(plain).footswitches == 0
    assert detect_tech_patterns(cued).footswitches == 1
    assert detect_tech_patterns(cued).doublesteps == 0


def test_same_foot_panel_change_is_doublestep() -> None:
    steps = gold_steps(["1000 // @foot=L", "0100 // @foot=R", "0001 // @foot=R", ","], 120)
    kinds = [span.kind for span in detect_tech_patterns(steps).spans]
    assert kinds == [PatternKind.DOUBLESTEP]


def test_stream_revisits_are_not_jacks_or_switches() -> None:
    # 0.075s apart (16ths at 200 BPM): D-U-D (same foot back on D) and D-U-L-D
    # (other foot onto D) are inside the time cutoffs but are plain stream.
    rows = [
        "0100 // @foot=L",
        "0010 // @foot=R",
        "0100 // @foot=L",
        "0001 // @foot=R",
        "1000 // @foot=L",
        "0100 // @foot=R",
        "0010 // @foot=L",
        "0100 // @foot=R",
        ",",
    ]
    tech = detect_tech_patterns(gold_steps(rows, 400))
    assert (tech.jacks, tech.footswitches, tech.sideswitches) == (0, 0, 0)


def test_training_fits_a_small_fixture() -> None:
    rows = [
        "1000 // @foot=L",
        "0100 // @foot=R",
        "0010 // @foot=L",
        "0001 // @foot=R",
        "0100 // @foot=L",
        "0100 // @foot=L",
        "0001 // @foot=R",
        "1000 // @foot=L",
        ",",
    ]
    annotated = parse_annotated_sm(chart_text(rows, 150))
    example = Example("jacks", annotated, build_trellis(annotated.chart.notes))
    model = train([example], epochs=20)
    assert row_errors(example, model.vector()) == 0
    assert set(model.weights) == set(FEATURE_NAMES)
    assert example.gold[5] == FootMove.LEFT


def test_training_with_zero_epochs_returns_unconverged_zero_weights() -> None:
    annotated = parse_annotated_sm(chart_text(["1000 // @foot=L", "0100 // @foot=R", ","]))
    example = Example("tiny", annotated, build_trellis(annotated.chart.notes))
    model = train([example], epochs=0)
    assert model.metadata["trainer"] == "averaged-structured-perceptron"
    assert all(weight == 0.0 for weight in model.weights.values())


def test_loading_a_training_example_rejects_impossible_annotations(tmp_path: Path) -> None:
    # The right foot is holding Right, so it cannot also tap Left.
    rows = ["0002 // @foot=R", "1000 // @foot=R", "0003", ","]
    path = tmp_path / "impossible.sm"
    path.write_text(chart_text(rows), encoding="utf-8")
    with pytest.raises(AnnotationError, match=r"impossible\.sm.*line\(s\) \d+"):
        load_example(path)


def test_hold_tail_on_its_own_row_exempts_the_doublestep() -> None:
    rows = ["2000 // @foot=L", "0100 // @foot=R", "3000", "0001 // @foot=R", ","]
    assert detect_tech_patterns(gold_steps(rows)).doublesteps == 0


def test_hold_tail_on_the_press_row_is_a_hold_cued_doublestep() -> None:
    rows = ["2000 // @foot=L", "0100 // @foot=R", "3001 // @foot=R", "0000", ","]
    assert detect_tech_patterns(gold_steps(rows)).doublesteps == 1


def test_row_with_no_legal_state_stays_put_like_a_no_press_row() -> None:
    # Three presses can't be covered without brackets, so row 1 is relaxed. The
    # hold tail on that row must still be recorded as the left foot's release.
    rows = chart_rows(["2000", "3111", "0100", ","])
    trellis = build_trellis(rows, allow_brackets=False)

    assert trellis.relaxed_rows == [1]
    stayed = trellis.layers[1].states
    assert all(state.moved == FootMove.NONE for state in stayed)
    # Either foot may have taken the hold; whichever did is the one released.
    assert all(state.released_since_press == state.owners_of(Panel.L) for state in stayed)
    assert all(state.hold_owner_for(Panel.L) is None for state in trellis.layers[2].states)


def test_packaged_weights_name_exactly_the_features() -> None:
    assert set(FootingModel.default().weights) == set(FEATURE_NAMES)


def test_packaged_weights_respect_the_nonnegative_features() -> None:
    weights = FootingModel.default().weights
    negative = {name: weights[name] for name in NONNEGATIVE if weights[name] < 0.0}
    assert not negative


def test_weights_for_an_unknown_feature_are_rejected() -> None:
    with pytest.raises(ValueError, match="not_a_feature"):
        FootingModel.from_dict({"weights": {"travel": 1.0, "not_a_feature": 2.0}})


def test_weights_missing_a_feature_default_to_zero() -> None:
    model = FootingModel.from_dict({"weights": {"travel": 1.5}})
    assert model.vector()[FEATURE_NAMES.index("travel")] == 1.5
    assert sum(model.vector()) == 1.5


def test_lifts_and_fakes_are_counted_but_never_stepped_on() -> None:
    chart = parse_annotated_sm(chart_text(["1000", "0L0F", "0100", ","])).chart
    basic = analyze_chart(chart).basic

    assert (basic.lifts, basic.fakes, basic.taps) == (1, 1, 2)
    moves = [step.foot_row.moved for step in resolve_chart(chart.notes).steps]
    assert moves[1] == FootMove.NONE


def test_analyzer_wrapper_matches_analyze_chart_and_is_repeatable() -> None:
    chart = parse_annotated_sm(chart_text(["1000", "0100", "0110", ","])).chart
    analyzer = Analyzer(chart)

    assert analyzer.analyze() == analyzer.analyze() == analyze_chart(chart).to_dict()


def test_resolve_trellis_matches_resolve_chart() -> None:
    rows = chart_rows(["1000", "0100", "0110", "0001", ","])
    assert resolve_trellis(build_trellis(rows)) == resolve_chart(rows)


def test_empty_chart_resolves_to_an_empty_feasible_path() -> None:
    result = resolve_chart([])
    assert (result.steps, result.cost, result.feasible) == ([], 0.0, True)


def test_leave_one_out_passes_training_options_through(mocker) -> None:
    rows = ["1000 // @foot=L", "0100 // @foot=R", ","]
    examples = [
        Example(name, annotated, build_trellis(annotated.chart.notes))
        for name in ("a", "b")
        for annotated in [parse_annotated_sm(chart_text(rows))]
    ]
    spy = mocker.spy(trainer, "train")

    leave_one_out(examples, epochs=3, margin=2.0, learning_rate=0.5, seed=9)

    assert [call.kwargs for call in spy.call_args_list] == [
        {"epochs": 3, "margin": 2.0, "learning_rate": 0.5, "seed": 9}
    ] * 2
