from patternity.footing.stance import (
    Foot,
    FootMove,
    FootPlacement,
    PlayerOrientation,
    Repeat,
    Stance,
)
from patternity.simfile.notes import Panel
from tests.helpers import gold_steps


def test_foot_placement_panels_and_coords() -> None:
    assert FootPlacement.L.panels == Panel.L
    assert FootPlacement.LD.panels == Panel.L | Panel.D
    assert FootPlacement.L.coords == (-1.0, 0.0)


def test_foot_placement_shares_panel() -> None:
    assert FootPlacement.LD.shares_panel_with(FootPlacement.D)
    assert not FootPlacement.L.shares_panel_with(FootPlacement.R)


def test_stance_covered_and_crossed() -> None:
    stance = Stance.from_feet(FootPlacement.R, FootPlacement.L)
    assert stance.is_crossed
    assert stance.covered == Panel.L | Panel.R
    assert stance.orientation == PlayerOrientation.INVERTED


def test_foot_and_foot_move_agree() -> None:
    assert Foot.LEFT.other is Foot.RIGHT and Foot.RIGHT.other is Foot.LEFT
    assert FootMove.NONE.feet == ()
    assert FootMove.BOTH.feet == (Foot.LEFT, Foot.RIGHT)
    for foot in Foot:
        assert foot.move.feet == (foot,)
        assert FootMove.BOTH.includes(foot) and not FootMove.NONE.includes(foot)
        assert not foot.move.includes(foot.other)


def test_stance_placement_by_foot() -> None:
    stance = Stance.from_feet(FootPlacement.LU, FootPlacement.D)
    assert stance.placement(Foot.LEFT) == FootPlacement.LU
    assert stance.placement(Foot.RIGHT) == FootPlacement.D


def _repeats(rows: list[str]) -> list[Repeat]:
    return [step.foot_row.last_repeat for step in gold_steps(rows)]


def test_repeat_tracks_jacks_and_switches_on_consecutive_press_rows() -> None:
    rows = [
        "0100 // @foot=L",
        "0100 // @foot=L",  # same foot, same panel
        "000M",  # no press: carried forward
        "0100 // @foot=R",  # other foot takes over
        "0010 // @foot=L",  # new panel
        "0110 // @feet=L,R",  # jump
        "0100 // @foot=L",  # a panel from the jump, but a jump is never repeated
        ",",
    ]
    assert _repeats(rows) == [
        Repeat.NONE,
        Repeat.JACK,
        Repeat.JACK,
        Repeat.SWITCH,
        Repeat.NONE,
        Repeat.NONE,
        Repeat.NONE,
    ]
