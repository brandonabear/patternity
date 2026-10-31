from patternity.footing.stance import FootPlacement, PlayerOrientation, Stance


def test_foot_placement_mask_and_coords() -> None:
    assert FootPlacement.L.mask == 0b0001
    assert FootPlacement.LD.mask == 0b0011
    assert FootPlacement.L.coords == (-1.0, 0.0)


def test_foot_placement_shares_panel() -> None:
    assert FootPlacement.LD.shares_panel_with(FootPlacement.D)
    assert not FootPlacement.L.shares_panel_with(FootPlacement.R)


def test_stance_covered_mask_and_crossed() -> None:
    stance = Stance.from_feet(FootPlacement.R, FootPlacement.L)
    assert stance.is_crossed
    assert stance.covered_mask == (FootPlacement.R.mask | FootPlacement.L.mask)
    assert stance.orientation == PlayerOrientation.INVERTED
