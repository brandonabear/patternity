"""Trellis fallbacks and options that the fixture charts rarely reach."""

import math

import pytest

from patternity import resolve_chart
from patternity.footing import FootingModel
from patternity.footing.rules import hits_mine
from patternity.footing.search import RELAXED_PENALTY, build_trellis, row_confidence, viterbi
from patternity.footing.stance import FootMove
from patternity.patterns import detect_tech_patterns
from tests.helpers import chart_rows

# One foot holds Right, so the other has to press Left, and the mine on Right
# lands under the holding foot whichever foot that is.
_UNAVOIDABLE_MINE = ["0002", "100M", "0003", ","]


def test_unavoidable_mine_is_stepped_on_at_a_penalty() -> None:
    rows = chart_rows(_UNAVOIDABLE_MINE)
    trellis = build_trellis(rows)

    assert trellis.relaxed_rows == [1]
    layer = trellis.layers[1]
    assert layer.states and all(penalty == RELAXED_PENALTY for penalty in layer.penalty)
    # The press still happens: these are the mine-hitting moves, not a stay-put.
    assert all(state.moved in (FootMove.LEFT, FootMove.RIGHT) for state in layer.states)
    assert all(hits_mine(state, rows[1].mines) for state in layer.states)


def test_unavoidable_mine_makes_the_path_infeasible() -> None:
    zero_weights = FootingModel()
    result = resolve_chart(chart_rows(_UNAVOIDABLE_MINE), zero_weights)

    assert (result.feasible, result.relaxed_rows) == (False, (1,))
    assert result.cost == RELAXED_PENALTY


def test_avoidable_mine_is_never_stepped_on() -> None:
    # The left foot could take Down, leaving the right foot on the Right mine,
    # but the right foot can take it instead.
    rows = chart_rows(["010M", ","])
    trellis = build_trellis(rows)

    assert trellis.relaxed_rows == []
    assert not any(hits_mine(state, rows[0].mines) for state in trellis.layers[0].states)


def test_without_brackets_a_two_panel_row_is_always_a_jump() -> None:
    rows = chart_rows(["1100", "0011", ","])

    with_brackets = build_trellis(rows)
    without = build_trellis(rows, allow_brackets=False)

    def placements(trellis) -> set[bool]:
        return {
            placement.is_bracket
            for layer in trellis.layers
            for state in layer.states
            for placement in (state.stance.left, state.stance.right)
        }

    assert placements(with_brackets) == {True, False}
    assert placements(without) == {False}
    assert all(state.moved == FootMove.BOTH for layer in without.layers for state in layer.states)


def test_without_brackets_no_bracket_is_counted() -> None:
    rows = chart_rows(["1100", "0011", "1100", ","])
    result = resolve_chart(rows, allow_brackets=False)
    assert detect_tech_patterns(result.steps).brackets == 0


def test_confidence_is_none_on_rows_without_a_press() -> None:
    rows = chart_rows(["1000", "0M00", "2000", "0100", "3000", ","])
    confidence = row_confidence(build_trellis(rows), FootingModel.default().vector())

    assert [value is None for value in confidence] == [False, True, False, False, True]


def test_confidence_is_the_extra_cost_of_the_cheapest_other_foot_move() -> None:
    rows = chart_rows(["1000", "0100", "0100", "0011", "1000", "0001", ","])
    trellis = build_trellis(rows)
    weights = FootingModel.default().vector()
    best = viterbi(trellis, weights)

    # Recompute each margin the slow way: force every other foot move on the
    # row and take the cheapest result.
    expected = []
    for i, state in enumerate(best.states(trellis)):
        others = [
            forced.cost
            for move in (FootMove.LEFT, FootMove.RIGHT, FootMove.BOTH)
            if move != state.moved
            and not (forced := viterbi(trellis, weights, allowed={i: move})).relaxed_rows
        ]
        expected.append(min(others, default=math.inf) - best.cost)

    assert row_confidence(trellis, weights) == pytest.approx(expected)
    assert all(margin > 0.0 for margin in expected)
