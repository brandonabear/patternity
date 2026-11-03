import math
import random

from patternity.footing import FootingModel
from patternity.footing.features import FEATURE_NAMES, featurize, hits_mine
from patternity.footing.grace import hold_grace
from patternity.footing.search import build_trellis, row_confidence, viterbi
from patternity.footing.stance import FootMove, FootRow
from patternity.footing.transitions import iter_legal_transitions
from patternity.patterns import PatternKind
from patternity.patterns.detector import detect_tech_patterns
from patternity.simfile import NoteRow
from patternity.training import Example, parse_annotated_sm, row_errors, train
from tests.helpers import chart_text, gold_steps


def _brute_force_min(rows: list[NoteRow], weights: list[float]) -> float:
    best = math.inf

    grace_rows = hold_grace(rows)

    def walk(i: int, prev: FootRow, cost: float, last_press: float | None) -> None:
        nonlocal best
        if i == len(rows):
            best = min(best, cost)
            return
        row = rows[i]
        now = row.timestamp or 0.0
        dt = now - last_press if row.press_mask and last_press is not None else None
        grace_mask, grace_remaining = grace_rows[i]
        for curr in iter_legal_transitions(prev, row, grace=grace_mask):
            if row.press_mask and row.mine_mask and hits_mine(curr, row.mine_mask):
                continue
            feats = featurize(prev, curr, row, dt, grace_remaining=grace_remaining)
            edge = sum(weights[FEATURE_NAMES.index(k)] * v for k, v in feats.items())
            walk(i + 1, curr, cost + edge, now if row.press_mask else last_press)

    walk(0, FootRow.initial(), 0.0, None)
    return best


def test_viterbi_matches_brute_force_over_all_paths() -> None:
    rows = ["1000", "0100", "0100", "M010", "0001", "1100", "0010", ","]
    chart = parse_annotated_sm(chart_text(rows)).chart
    rng = random.Random(7)
    for _ in range(5):
        weights = [rng.uniform(-5, 20) for _ in FEATURE_NAMES]
        trellis = build_trellis(chart.notes)
        decoded = viterbi(trellis, weights)
        assert math.isclose(
            decoded.cost, _brute_force_min(chart.notes, weights), abs_tol=1e-6
        )


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
    plain = gold_steps(
        [*base, "0000", "0010 // @foot=R", "0000", "0000", "0000", ","], 200
    )
    cued = gold_steps(
        [*base, "000M", "0010 // @foot=R", "0000", "0000", "0000", ","], 200
    )
    assert detect_tech_patterns(plain).footswitches == 0
    assert detect_tech_patterns(cued).footswitches == 1
    assert detect_tech_patterns(cued).doublesteps == 0


def test_same_foot_panel_change_is_doublestep() -> None:
    steps = gold_steps(
        ["1000 // @foot=L", "0100 // @foot=R", "0001 // @foot=R", ","], 120
    )
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
