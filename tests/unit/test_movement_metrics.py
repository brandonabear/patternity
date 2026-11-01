from patternity.footing import ResolvedStep
from patternity.footing.resolve import FootingResult
from patternity.footing.stance import FootMove, FootPlacement, FootRow, Stance
from patternity.movement import count_direction_shifts, detect_movement
from patternity.simfile import NoteRow


def _press(left: FootPlacement, right: FootPlacement, moved: FootMove, index: int) -> ResolvedStep:
    return ResolvedStep(
        index=index,
        note_row=NoteRow.from_str("0100"),
        foot_row=FootRow(stance=Stance.from_feet(left, right), moved=moved),
    )


def test_direction_shifts_facing_left_right_only() -> None:
    steps = [
        _press(FootPlacement.D, FootPlacement.U, FootMove.LEFT, 0),
        _press(FootPlacement.U, FootPlacement.D, FootMove.RIGHT, 1),
        _press(FootPlacement.D, FootPlacement.U, FootMove.LEFT, 2),
    ]
    assert count_direction_shifts(steps) == 2


def test_direction_shifts_neutral_alone_is_not_a_shift() -> None:
    steps = [
        _press(FootPlacement.L, FootPlacement.R, FootMove.LEFT, 0),
        _press(FootPlacement.D, FootPlacement.U, FootMove.RIGHT, 1),
        _press(FootPlacement.L, FootPlacement.R, FootMove.LEFT, 2),
    ]
    assert count_direction_shifts(steps) == 0


def test_direction_shifts_remember_facing_through_neutral() -> None:
    steps = [
        _press(FootPlacement.D, FootPlacement.U, FootMove.LEFT, 0),
        _press(FootPlacement.L, FootPlacement.R, FootMove.LEFT, 1),
        _press(FootPlacement.U, FootPlacement.D, FootMove.RIGHT, 2),
        _press(FootPlacement.L, FootPlacement.R, FootMove.RIGHT, 3),
        _press(FootPlacement.L, FootPlacement.D, FootMove.RIGHT, 4),
        _press(FootPlacement.U, FootPlacement.D, FootMove.LEFT, 5),
    ]
    assert count_direction_shifts(steps) == 1


def test_direction_shifts_remember_facing_through_inverted() -> None:
    steps = [
        _press(FootPlacement.D, FootPlacement.U, FootMove.LEFT, 0),
        _press(FootPlacement.R, FootPlacement.L, FootMove.LEFT, 1),
        _press(FootPlacement.U, FootPlacement.D, FootMove.RIGHT, 2),
    ]
    assert count_direction_shifts(steps) == 1


def test_detect_movement_reports_cost_and_feasibility() -> None:
    result = FootingResult(steps=[], cost=12.5, relaxed_rows=(3,))
    assert detect_movement(result).to_dict() == {
        "direction_shifts": 0,
        "total_cost": 12.5,
        "foot_path_feasible": False,
    }
