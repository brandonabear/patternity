"""A mine on the switched panel restarts the clock for footswitches and sideswitches alike."""

from patternity.patterns import TechMetrics, detect_tech_patterns
from tests.helpers import gold_steps

_BPM = 240.0  # 8ths are 0.125 s apart.


def _tech(rows: list[str]) -> TechMetrics:
    padding = ["0000"] * (8 - len(rows))
    return detect_tech_patterns(gold_steps([*rows, *padding, ","], _BPM))


def _down_switch(between: str) -> TechMetrics:
    # Left then right foot on Down, 0.375 s apart, which on its own is too slow
    # to count (the cutoff is 1/3 s). ``between`` falls 0.25 s before the switch.
    return _tech(["0100 // @foot=L", between, "0000", "0100 // @foot=R"])


def _right_switch(between: str) -> TechMetrics:
    # The left foot crosses to Right; the right foot takes Right over 0.375 s later.
    crossover = ["1000 // @foot=L", "0100 // @foot=R", "0001 // @foot=L"]
    return _tech([*crossover, between, "0000", "0001 // @foot=R"])


def test_slow_footswitch_does_not_count() -> None:
    assert _down_switch("M000").footswitches == 0


def test_mine_on_the_panel_restarts_the_footswitch_clock() -> None:
    assert _down_switch("0M00").footswitches == 1


def test_slow_sideswitch_does_not_count() -> None:
    assert _right_switch("M000").sideswitches == 0


def test_mine_on_the_panel_restarts_the_sideswitch_clock() -> None:
    assert _right_switch("000M").sideswitches == 1
