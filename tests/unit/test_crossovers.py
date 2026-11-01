from patternity.footing import ResolvedStep
from patternity.footing.stance import FootMove, FootPlacement, FootRow, Stance
from patternity.patterns import PatternKind
from patternity.patterns.detector import detect_tech_patterns
from patternity.simfile import NoteRow

_CROSSOVER_KINDS = (PatternKind.CROSSOVER, PatternKind.INVERTED_CROSSOVER)


def _steps(moves: list[tuple[str, str, str]]) -> list[ResolvedStep]:
    """``(foot, left_panel, right_panel)`` per press row; the moving foot presses its panel."""
    steps = []
    for i, (foot, left, right) in enumerate(moves):
        moved = FootMove.LEFT if foot == "L" else FootMove.RIGHT
        panel = FootPlacement(left if foot == "L" else right)
        row = "".join("1" if panel.mask >> col & 1 else "0" for col in range(4))
        steps.append(
            ResolvedStep(
                index=i,
                note_row=NoteRow.from_str(row, beat=i * 0.5, timestamp=i * 0.25),
                foot_row=FootRow(
                    stance=Stance.from_feet(FootPlacement(left), FootPlacement(right)),
                    moved=moved,
                ),
            )
        )
    return steps


def _crossover_rows(moves: list[tuple[str, str, str]]) -> list[tuple[str, int]]:
    spans = detect_tech_patterns(_steps(moves)).spans
    return [(s.kind.value, s.steps[-1].index) for s in spans if s.kind in _CROSSOVER_KINDS]


def test_crossover_anchors_on_first_crossed_step() -> None:
    moves = [("L", "D", "R"), ("R", "D", "L"), ("L", "D", "L"), ("R", "D", "R")]
    assert _crossover_rows(moves) == [("crossover", 1)]


def test_uncrossing_while_still_turned_ends_the_crossover() -> None:
    moves = [
        ("L", "U", "R"),
        ("R", "U", "L"),
        ("L", "U", "L"),
        ("R", "U", "D"),
        ("L", "R", "D"),
        ("R", "R", "D"),
        ("L", "L", "D"),
    ]
    assert _crossover_rows(moves) == [("crossover", 1), ("crossover", 4)]


def test_turning_while_crossed_is_a_new_crossover() -> None:
    moves = [("L", "D", "R"), ("R", "D", "L"), ("L", "R", "L"), ("R", "R", "D")]
    assert _crossover_rows(moves) == [
        ("crossover", 1),
        ("inverted_crossover", 2),
        ("crossover", 3),
    ]
