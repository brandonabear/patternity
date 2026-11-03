from patternity.patterns import PatternKind
from patternity.patterns.detector import detect_tech_patterns
from tests.helpers import synthetic_steps


def _candle_rows(moves: list[tuple[str, str, str]]) -> list[int]:
    spans = detect_tech_patterns(synthetic_steps(moves)).spans
    return [s.steps[-1].index for s in spans if s.kind == PatternKind.CANDLE]


def test_up_right_down_stream_is_a_left_foot_candle() -> None:
    assert _candle_rows([("L", "U", "R"), ("R", "U", "R"), ("L", "D", "R")]) == [2]


def test_left_down_right_crossover_is_a_candle() -> None:
    assert _candle_rows([("L", "L", "D"), ("R", "L", "D"), ("L", "R", "D")]) == [2]


def test_anchored_left_with_right_foot_up_then_down() -> None:
    assert _candle_rows([("L", "L", "R"), ("R", "L", "U"), ("R", "L", "D")]) == [2]


def test_adjacent_panels_are_not_candles() -> None:
    assert _candle_rows([("L", "L", "R"), ("R", "L", "R"), ("L", "D", "R")]) == []


def test_bracket_keeping_a_panel_is_not_a_candle() -> None:
    assert _candle_rows([("L", "LU", "R"), ("R", "LU", "R"), ("L", "LD", "R")]) == []
