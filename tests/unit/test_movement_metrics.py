from patternity.footing import ResolvedStep
from patternity.footing.stance import FootMove, FootPlacement, FootRow, Stance
from patternity.metrics import MovementMetrics
from patternity.movement.detector import count_candles, count_direction_shifts
from patternity.simfile import NoteRow


def _press(
    left: FootPlacement,
    right: FootPlacement,
    *,
    moved: FootMove,
    index: int = 0,
) -> ResolvedStep:
    return ResolvedStep(
        index=index,
        note_row=NoteRow.from_str("0100"),
        foot_row=FootRow(
            stance=Stance.from_feet(left, right),
            moved=moved,
        ),
    )


def test_direction_shifts_facing_left_right_only() -> None:
    facing_left = Stance.from_feet(FootPlacement.D, FootPlacement.U)
    facing_right = Stance.from_feet(FootPlacement.U, FootPlacement.D)
    assert facing_left.orientation.value == "facing_left"
    assert facing_right.orientation.value == "facing_right"
    steps = [
        _press(FootPlacement.D, FootPlacement.U, moved=FootMove.LEFT, index=0),
        _press(FootPlacement.U, FootPlacement.D, moved=FootMove.RIGHT, index=1),
        _press(FootPlacement.D, FootPlacement.U, moved=FootMove.LEFT, index=2),
    ]
    assert count_direction_shifts(steps) == 2


def test_direction_shifts_ignores_neutral() -> None:
    neutral = Stance.from_feet(FootPlacement.L, FootPlacement.R)
    facing_left = Stance.from_feet(FootPlacement.D, FootPlacement.U)
    steps = [
        _press(FootPlacement.L, FootPlacement.R, moved=FootMove.LEFT, index=0),
        _press(FootPlacement.D, FootPlacement.U, moved=FootMove.RIGHT, index=1),
    ]
    assert neutral.orientation.value == "neutral"
    assert count_direction_shifts(steps) == 0


def test_candle_side_to_side_ldr_one_foot() -> None:
    steps = [
        _press(FootPlacement.L, FootPlacement.R, moved=FootMove.LEFT, index=0),
        _press(FootPlacement.D, FootPlacement.R, moved=FootMove.LEFT, index=1),
        _press(FootPlacement.R, FootPlacement.L, moved=FootMove.LEFT, index=2),
    ]
    assert count_candles(steps) == 1


def test_candle_vertical_u_d_right_foot() -> None:
    steps = [
        _press(FootPlacement.L, FootPlacement.U, moved=FootMove.RIGHT, index=0),
        _press(FootPlacement.L, FootPlacement.D, moved=FootMove.RIGHT, index=1),
    ]
    assert count_candles(steps) == 1


def test_candle_u_only_stream_not_counted() -> None:
    steps = [
        _press(FootPlacement.L, FootPlacement.U, moved=FootMove.RIGHT, index=0),
        _press(FootPlacement.L, FootPlacement.U, moved=FootMove.RIGHT, index=1),
    ]
    assert count_candles(steps) == 0


def test_candle_run_breaks_on_other_foot_press() -> None:
    steps = [
        _press(FootPlacement.L, FootPlacement.D, moved=FootMove.RIGHT, index=0),
        _press(FootPlacement.R, FootPlacement.D, moved=FootMove.LEFT, index=1),
        _press(FootPlacement.L, FootPlacement.U, moved=FootMove.RIGHT, index=2),
    ]
    assert count_candles(steps) == 0


def test_movement_metrics_from_decode_turns_alias() -> None:
    metrics = MovementMetrics.from_decode([], cost=1.0, feasible=True, crossover_count=3)
    assert metrics.turns == 3
    assert metrics.to_dict()["direction_shifts"] == 0
