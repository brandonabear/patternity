"""Tech-pattern cutoffs and pairing rules on hand-tagged paths.

Every path here comes from ``gold_steps`` (the ``@foot`` tags decide the feet),
so these tests don't depend on the trained weights.
"""

import pytest

from patternity.patterns import PatternKind, TechMetrics, detect_tech_patterns
from patternity.patterns.detector import ITG_FOOTSWITCH_CUTOFF_SEC, ITG_JACK_CUTOFF_SEC
from tests.helpers import gold_steps

_ROWS_PER_MEASURE = 16


def _tech(rows: list[str], bpm: float) -> TechMetrics:
    """Detect patterns on ``rows`` played as 16ths (``15 / bpm`` seconds apart)."""
    padding = ["0000"] * (_ROWS_PER_MEASURE - len(rows))
    return detect_tech_patterns(gold_steps([*rows, *padding, ","], bpm))


def _kinds(tech: TechMetrics) -> list[PatternKind]:
    return [span.kind for span in tech.spans]


def _sixteenth(bpm: float) -> float:
    return 15.0 / bpm


@pytest.mark.parametrize(("bpm", "jacks"), [(86.0, 1), (85.0, 0)])
def test_jack_cutoff(bpm: float, jacks: int) -> None:
    # 16ths at 86 BPM are 0.1744 s apart; at 85 BPM, 0.1765 s.
    assert (_sixteenth(bpm) < ITG_JACK_CUTOFF_SEC) == bool(jacks)
    assert _tech(["1000 // @foot=L", "1000 // @foot=L"], bpm).jacks == jacks


def test_mine_on_the_panel_restarts_the_jack_clock() -> None:
    # The presses are three 16ths apart (0.225 s, too slow), but the mine is
    # one 16th (0.075 s) before the second press.
    bpm = 200.0
    slow = ["1000 // @foot=L", "0000", "0000", "1000 // @foot=L"]
    mined = ["1000 // @foot=L", "0000", "M000", "1000 // @foot=L"]

    assert _tech(slow, bpm).jacks == 0
    assert _tech(mined, bpm).jacks == 1


def test_mine_on_another_panel_leaves_the_jack_clock_alone() -> None:
    rows = ["1000 // @foot=L", "0000", "0M00", "1000 // @foot=L"]
    assert _tech(rows, 200.0).jacks == 0


def test_mine_on_the_second_press_row_does_not_rule_out_a_jack() -> None:
    # A mine beside the second press only matters through the footing: if it
    # pushes the other foot onto the panel, the path is a footswitch, not a jack.
    # When the same foot repeats anyway, it is still a jack.
    assert _tech(["1000 // @foot=L", "1M00 // @foot=L"], 200.0).jacks == 1


def test_jack_can_start_from_a_jump() -> None:
    tech = _tech(["1001 // @feet=L,R", "1000 // @foot=L"], 200.0)
    assert _kinds(tech) == [PatternKind.JACK]


def test_jack_can_end_on_a_jump() -> None:
    tech = _tech(["1000 // @foot=L", "1001 // @feet=L,R"], 200.0)
    assert _kinds(tech) == [PatternKind.JACK]


def test_hold_tail_does_not_count_as_a_jack_press() -> None:
    # Head and press are four 16ths apart (0.3 s, too slow). The tail is one
    # 16th before the press, which would be a jack if tails counted as presses.
    rows = ["2000 // @foot=L", "0000", "0000", "3000", "1000 // @foot=L"]
    assert _tech(rows, 200.0).jacks == 0


@pytest.mark.parametrize(("bpm", "footswitches"), [(90.0, 1), (89.0, 0)])
def test_footswitch_cutoff_includes_exactly_a_third_of_a_second(
    bpm: float, footswitches: int
) -> None:
    # Two 16ths (an 8th) apart: exactly 1/3 s at 90 BPM, 0.337 s at 89 BPM.
    assert (2 * _sixteenth(bpm) < ITG_FOOTSWITCH_CUTOFF_SEC) == bool(footswitches)
    rows = ["0100 // @foot=L", "0000", "0100 // @foot=R"]
    assert _tech(rows, bpm).footswitches == footswitches


def test_footswitch_is_on_up_or_down_and_sideswitch_on_left_or_right() -> None:
    down = _tech(["0100 // @foot=L", "0100 // @foot=R"], 200.0)
    up = _tech(["0010 // @foot=R", "0010 // @foot=L"], 200.0)
    left = _tech(["1000 // @foot=L", "1000 // @foot=R"], 200.0)
    right = _tech(["0001 // @foot=R", "0001 // @foot=L"], 200.0)

    assert [(t.footswitches, t.sideswitches) for t in (down, up, left, right)] == [
        (1, 0),
        (1, 0),
        (0, 1),
        (0, 1),
    ]


def test_switch_pairs_only_with_the_very_next_press_row() -> None:
    # Left foot on Down, right foot on Up, then right foot on Down: the Down
    # presses are two press rows apart, so this is not a footswitch.
    rows = ["0100 // @foot=L", "0010 // @foot=R", "0100 // @foot=R"]
    assert _tech(rows, 200.0).footswitches == 0


def test_bracket_is_one_foot_on_two_pressed_panels() -> None:
    bracket = _tech(["0001 // @foot=R", "1100 // @feet=L,L"], 200.0)
    jump = _tech(["0001 // @foot=R", "1100 // @feet=L,R"], 200.0)

    assert (bracket.brackets, jump.brackets) == (1, 0)


def test_bracket_onto_a_held_panel_is_not_a_bracket() -> None:
    # The left foot holds Left and reaches Down with the same foot: it covers
    # two panels but presses only one.
    rows = ["2000 // @foot=L", "0100 // @foot=L", "3000"]
    assert _tech(rows, 200.0).brackets == 0
