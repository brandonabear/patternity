from patternity.footing.resolve import FootingResult
from patternity.movement import count_direction_shifts, detect_movement
from tests.helpers import synthetic_steps


def test_direction_shifts_facing_left_right_only() -> None:
    steps = synthetic_steps(
        [
            ("L", "D", "U"),
            ("R", "U", "D"),
            ("L", "D", "U"),
        ]
    )
    assert count_direction_shifts(steps) == 2


def test_direction_shifts_neutral_alone_is_not_a_shift() -> None:
    steps = synthetic_steps(
        [
            ("L", "L", "R"),
            ("R", "D", "U"),
            ("L", "L", "R"),
        ]
    )
    assert count_direction_shifts(steps) == 0


def test_direction_shifts_remember_facing_through_neutral() -> None:
    steps = synthetic_steps(
        [
            ("L", "D", "U"),
            ("L", "L", "R"),
            ("R", "U", "D"),
            ("R", "L", "R"),
            ("R", "L", "D"),
            ("L", "U", "D"),
        ]
    )
    assert count_direction_shifts(steps) == 1


def test_direction_shifts_remember_facing_through_inverted() -> None:
    steps = synthetic_steps(
        [
            ("L", "D", "U"),
            ("L", "R", "L"),
            ("R", "U", "D"),
        ]
    )
    assert count_direction_shifts(steps) == 1


def test_detect_movement_reports_cost_and_feasibility() -> None:
    result = FootingResult(steps=[], cost=12.5, relaxed_rows=(3,))
    assert detect_movement(result).to_dict() == {
        "direction_shifts": 0,
        "total_cost": 12.5,
        "foot_path_feasible": False,
    }
