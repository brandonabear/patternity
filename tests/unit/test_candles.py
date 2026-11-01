from patternity.footing import ResolvedStep
from patternity.footing.stance import FootMove, FootPlacement, FootRow, Stance
from patternity.patterns import PatternKind
from patternity.patterns.detector import detect_tech_patterns
from patternity.simfile import NoteRow


def _row(placement: FootPlacement) -> str:
    return "".join("1" if placement.mask >> col & 1 else "0" for col in range(4))


def _steps(moves: list[tuple[str, str, str]]) -> list[ResolvedStep]:
    """``(foot, left_panel, right_panel)`` per press row; the moving foot presses its panel."""
    steps = []
    for i, (foot, left, right) in enumerate(moves):
        moved = FootMove.LEFT if foot == "L" else FootMove.RIGHT
        panel = FootPlacement(left if foot == "L" else right)
        steps.append(
            ResolvedStep(
                index=i,
                note_row=NoteRow.from_str(_row(panel), beat=i * 0.5, timestamp=i * 0.25),
                foot_row=FootRow(
                    stance=Stance.from_feet(FootPlacement(left), FootPlacement(right)),
                    moved=moved,
                ),
            )
        )
    return steps


def _candle_rows(moves: list[tuple[str, str, str]]) -> list[int]:
    spans = detect_tech_patterns(_steps(moves)).spans
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
