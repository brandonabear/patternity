"""One minimal passage per feature: what ``featurize`` reports for its last press.

Rows are 8ths at 120 BPM (0.25 s apart, speed 0.4). A mine or tail row between
two presses doubles the gap (speed 0.2), and the first press has no speed.
"""

import math
from typing import cast

import pytest

from patternity.footing.features import Feature, featurize
from patternity.footing.grace import HOLD_GRACE_SEC, ROLL_GRACE_SEC, hold_grace
from patternity.footing.stance import FootMove, FootPlacement, FootRow
from patternity.footing.transitions import iter_legal_transitions
from tests.helpers import chart_rows

F = Feature
_ROWS_PER_MEASURE = 8
_FAST = 0.4  # Speed of presses one 8th apart.
_SLOW = 0.2  # Speed of presses two 8ths apart.
_DIAGONAL = math.sqrt(2)  # Between adjacent panels, e.g. Left to Down.
_ACROSS = 2.0  # Between opposite panels, e.g. Up to Down.
_TO_BRACKET = math.sqrt(0.5)  # From a panel onto a bracket that includes it.

# The stance after a press row: (feet that moved, left placement, right placement).
Step = tuple[str, str, str]
_MOVED = {"L": FootMove.LEFT, "R": FootMove.RIGHT, "B": FootMove.BOTH}


def _take(prev: FootRow, options: list[FootRow], step: Step) -> FootRow:
    moved, left, right = step
    want = (_MOVED[moved], FootPlacement(left), FootPlacement(right))
    for curr in options:
        if (curr.moved, curr.stance.left, curr.stance.right) == want:
            return curr
    raise AssertionError(f"{step} is not a legal move from {prev.stance}")


def _features(rows: list[str], path: list[Step]) -> dict[str, float]:
    """Features of the last press in ``rows`` when the feet follow ``path``.

    ``path`` has one step per press row; rows without a press are walked through.
    The feet start with the left foot on Left and the right foot on Right.
    """
    padding = ["0000"] * (_ROWS_PER_MEASURE - len(rows))
    notes = chart_rows([*rows, *padding, ","])
    grace_rows = hold_grace(notes)
    steps = iter(path)

    state = FootRow.initial()
    last_press: float | None = None
    feats: dict[str, float] = {}
    for row, grace in zip(notes, grace_rows, strict=True):
        options = list(iter_legal_transitions(state, row, grace=grace.panels))
        if not row.pressed:
            (state,) = options
            continue
        curr = _take(state, options, next(steps))
        dt = None if last_press is None else row.timestamp - last_press
        feats = featurize(state, curr, row, dt, grace_remaining=grace.remaining)
        state, last_press = curr, row.timestamp

    assert next(steps, None) is None, "path has more steps than there are press rows"
    return feats


CASES = [
    pytest.param(
        ["0010"],
        [("R", "L", "U")],
        {F.TRAVEL: _DIAGONAL, F.TWISTED: 1},
        id="first press: travel, turned sideways, no speed yet",
    ),
    pytest.param(
        ["1000", "0100"],
        [("L", "L", "R"), ("L", "D", "R")],
        {
            F.SAME_FOOT: 1,
            F.SAME_FOOT_SPEED: _FAST,
            F.TRAVEL: _DIAGONAL,
            F.TRAVEL_SPEED: _DIAGONAL * _FAST,
            F.TWISTED: 1,
        },
        id="same foot twice, on different panels",
    ),
    pytest.param(
        ["0002", "0100", "0003", "1000"],
        [("R", "L", "R"), ("L", "D", "R"), ("L", "L", "R")],
        {
            F.SAME_FOOT_AFTER_RELEASE: 1,
            F.TRAVEL: _DIAGONAL,
            F.TRAVEL_SPEED: _DIAGONAL * _SLOW,
        },
        id="same foot twice after the other foot let go of a hold",
    ),
    pytest.param(
        ["1000", "1000"],
        [("L", "L", "R"), ("L", "L", "R")],
        {
            F.SAME_FOOT: 1,
            F.SAME_FOOT_SPEED: _FAST,
            F.JACK: 1,
            F.JACK_SPEED: _FAST,
            F.JACK_SPEED_SQ: _FAST * _FAST,
        },
        id="jack",
    ),
    pytest.param(
        ["0100", "0100"],
        [("L", "D", "R"), ("R", "D", "D")],
        {
            F.SWITCH: 1,
            F.SWITCH_SPEED: _FAST,
            F.TRAVEL: _DIAGONAL,
            F.TRAVEL_SPEED: _DIAGONAL * _FAST,
            F.OVERLAP: 1,
            F.TWISTED: 1,
        },
        id="switch: the other foot takes over the panel",
    ),
    pytest.param(
        ["0100", "0100", "0100"],
        [("L", "D", "R"), ("L", "D", "R"), ("R", "D", "D")],
        {
            F.SWITCH: 1,
            F.SWITCH_SPEED: _FAST,
            F.REPEAT_CHANGE: 1,
            F.TRAVEL: _DIAGONAL,
            F.TRAVEL_SPEED: _DIAGONAL * _FAST,
            F.OVERLAP: 1,
            F.TWISTED: 1,
        },
        id="jack then switch on one panel",
    ),
    pytest.param(
        ["0100", "0001"],
        [("R", "L", "D"), ("L", "R", "D")],
        {
            F.TRAVEL: _ACROSS,
            F.TRAVEL_SPEED: _ACROSS * _FAST,
            F.CROSSED: 1,
            F.CROSS_ENTRY: 1,
        },
        id="crossing over",
    ),
    pytest.param(
        ["0100", "0001", "1000"],
        [("R", "L", "D"), ("L", "R", "D"), ("R", "R", "L")],
        {
            F.TRAVEL: _DIAGONAL,
            F.TRAVEL_SPEED: _DIAGONAL * _FAST,
            F.CROSSED: 1,
            F.INVERTED: 1,
        },
        id="staying crossed, now fully backwards",
    ),
    pytest.param(
        ["0010", "0100"],
        [("R", "L", "U"), ("R", "L", "D")],
        {
            F.SAME_FOOT: 1,
            F.SAME_FOOT_SPEED: _FAST,
            F.TRAVEL: _ACROSS,
            F.TRAVEL_SPEED: _ACROSS * _FAST,
            F.FACING_FLIP: 1,
            F.TWISTED: 1,
        },
        id="turning from facing left to facing right",
    ),
    pytest.param(
        ["0001", "1100"],
        [("R", "L", "R"), ("L", "LD", "R")],
        {
            F.TRAVEL: _TO_BRACKET,
            F.TRAVEL_SPEED: _TO_BRACKET * _FAST,
            F.BRACKET: 1,
            F.BRACKET_SPEED: _FAST,
            F.TWISTED: 1,
        },
        id="bracket",
    ),
    pytest.param(
        ["1000", "1001"],
        [("L", "L", "R"), ("B", "L", "R")],
        {F.JUMP: 1, F.JUMP_SPEED: _FAST},
        id="jump",
    ),
    pytest.param(
        ["2000", "0100"],
        [("L", "L", "R"), ("L", "LD", "R")],
        {
            F.SAME_FOOT: 1,
            F.SAME_FOOT_SPEED: _FAST,
            F.TRAVEL: _TO_BRACKET,
            F.TRAVEL_SPEED: _TO_BRACKET * _FAST,
            F.BRACKET: 1,
            F.BRACKET_SPEED: _FAST,
            F.HOLD_BRACKET_TAP: 1,
            F.TWISTED: 1,
        },
        id="foot holding a panel brackets to tap another",
    ),
    pytest.param(
        ["0100", "0M00", "0100"],
        [("L", "D", "R"), ("R", "D", "D")],
        {
            F.SWITCH: 1,
            F.SWITCH_SPEED: _SLOW,
            F.MINE_CUED_SWITCH: 1,
            F.TRAVEL: _DIAGONAL,
            F.TRAVEL_SPEED: _DIAGONAL * _SLOW,
            F.OVERLAP: 1,
            F.TWISTED: 1,
        },
        id="switch after a mine",
    ),
    pytest.param(
        ["1000", "M000", "0100"],
        [("L", "L", "R"), ("L", "D", "R")],
        {
            F.SAME_FOOT: 1,
            F.SAME_FOOT_SPEED: _SLOW,
            F.MINE_CUED_SAME_FOOT: 1,
            F.CUED_FOOT_MOVES: 1,
            F.TRAVEL: _DIAGONAL,
            F.TRAVEL_SPEED: _DIAGONAL * _SLOW,
            F.TWISTED: 1,
        },
        id="mine under a foot, and that foot steps off",
    ),
    pytest.param(
        ["1000", "M000", "0001"],
        [("L", "L", "R"), ("R", "L", "R")],
        {F.CUED_FOOT_STAYS: 1},
        id="mine under a foot, and that foot stays",
    ),
    pytest.param(
        ["2000", "3100"],
        [("L", "L", "R"), ("L", "D", "R")],
        {
            F.HOLD_RELEASE: 1,
            F.SAME_FOOT: 1,
            F.SAME_FOOT_SPEED: _FAST,
            F.TRAVEL: _DIAGONAL,
            F.TRAVEL_SPEED: _DIAGONAL * _FAST,
            F.TWISTED: 1,
        },
        id="leaving a hold on its tail row",
    ),
    pytest.param(
        ["2000", "0100", "3000"],
        [("L", "L", "R"), ("L", "D", "R")],
        {
            F.HOLD_RELEASE: 1,
            F.EARLY_RELEASE: 0.25 / HOLD_GRACE_SEC,
            F.SAME_FOOT: 1,
            F.SAME_FOOT_SPEED: _FAST,
            F.TRAVEL: _DIAGONAL,
            F.TRAVEL_SPEED: _DIAGONAL * _FAST,
            F.TWISTED: 1,
        },
        id="leaving a hold one 8th before its tail",
    ),
    pytest.param(
        ["4000", "0100", "3000"],
        [("L", "L", "R"), ("L", "D", "R")],
        {
            F.HOLD_RELEASE: 1,
            F.EARLY_RELEASE: 0.25 / ROLL_GRACE_SEC,
            F.SAME_FOOT: 1,
            F.SAME_FOOT_SPEED: _FAST,
            F.TRAVEL: _DIAGONAL,
            F.TRAVEL_SPEED: _DIAGONAL * _FAST,
            F.TWISTED: 1,
        },
        id="leaving a roll one 8th before its tail",
    ),
]


@pytest.mark.parametrize(("rows", "path", "expected"), CASES)
def test_featurize(rows: list[str], path: list[Step], expected: dict[Feature, float]) -> None:
    assert _features(rows, path) == pytest.approx(expected)


def test_every_feature_has_a_case() -> None:
    expectations = [cast(dict[Feature, float], case.values[2]) for case in CASES]
    covered = {feature for expected in expectations for feature in expected}
    assert covered == set(Feature)


def test_row_without_a_press_has_no_features() -> None:
    (mine_row,) = chart_rows(["M000", ","])
    start = FootRow.initial()
    (stayed,) = iter_legal_transitions(start, mine_row)
    assert featurize(start, stayed, mine_row, None) == {}
