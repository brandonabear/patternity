from patternity.footing.stance import FootPlacement, PlayerOrientation, Stance
from patternity.simfile.notes import Panel


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
