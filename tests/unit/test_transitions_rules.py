from patternity.footing.stance import FootMove, FootPlacement, FootRow, Stance
from patternity.footing.transitions import (
    Candidate,
    RowContext,
    each_jumping_foot_presses,
    held_panels_stay_covered,
    hold_owner_stays_on_panel,
    iter_legal_transitions,
    jumping_feet_dont_share_a_panel,
    moving_feet_touch_only_pressed_or_held,
    no_bracket_onto_held_panel,
    presses_are_covered,
)
from patternity.simfile import NoteRow, Panel

P = FootPlacement
START = FootRow.initial()  # L on Left, R on Right


def _ctx(pressed: Panel, held: Panel = Panel.NONE, releasable: Panel = Panel.NONE) -> RowContext:
    return RowContext(
        pressed=pressed,
        held=held,
        releasable=releasable,
        must_stay_held=held & ~releasable,
        touchable=pressed | held,
    )


def _holding_left() -> FootRow:
    """Left foot holding the Left panel, right foot on Right."""
    return FootRow(
        stance=Stance.from_feet(P.L, P.R),
        moved=FootMove.LEFT,
        hold_owners=((Panel.L, FootMove.LEFT),),
    )


def test_row_context_from_row() -> None:
    row = NoteRow.from_str("0100", holds_active=Panel.L | Panel.D)
    ctx = RowContext.from_row(row, grace=Panel.L)
    assert ctx.pressed == Panel.D
    assert ctx.held == Panel.L  # Down is a new press, not held yet
    assert ctx.must_stay_held == Panel.NONE
    assert ctx.touchable == Panel.L | Panel.D


def test_presses_are_covered() -> None:
    ctx = _ctx(Panel.U)
    assert presses_are_covered(START, ctx, Candidate(P.U, P.R, FootMove.LEFT))
    # The planted right foot doesn't count: only moving feet press.
    assert not presses_are_covered(START, ctx, Candidate(P.D, P.U, FootMove.LEFT))


def test_moving_feet_touch_only_pressed_or_held() -> None:
    ctx = _ctx(Panel.U, held=Panel.L)
    assert moving_feet_touch_only_pressed_or_held(START, ctx, Candidate(P.LU, P.R, FootMove.LEFT))
    assert not moving_feet_touch_only_pressed_or_held(
        START, ctx, Candidate(P.L, P.RU, FootMove.RIGHT)
    )


def test_each_jumping_foot_presses() -> None:
    ctx = _ctx(Panel.L | Panel.R)
    assert each_jumping_foot_presses(START, ctx, Candidate(P.L, P.R, FootMove.BOTH))
    assert not each_jumping_foot_presses(START, ctx, Candidate(P.LD, P.U, FootMove.BOTH))
    # Not a jump: the rule doesn't apply.
    assert each_jumping_foot_presses(START, ctx, Candidate(P.D, P.U, FootMove.LEFT))


def test_jumping_feet_dont_share_a_panel() -> None:
    ctx = _ctx(Panel.L | Panel.D)
    assert jumping_feet_dont_share_a_panel(START, ctx, Candidate(P.L, P.D, FootMove.BOTH))
    assert not jumping_feet_dont_share_a_panel(START, ctx, Candidate(P.LD, P.D, FootMove.BOTH))
    # A single-foot move may land on the planted foot's panel (a footswitch).
    assert jumping_feet_dont_share_a_panel(START, ctx, Candidate(P.R, P.R, FootMove.LEFT))


def test_held_panels_stay_covered() -> None:
    ctx = _ctx(Panel.U, held=Panel.L)
    assert held_panels_stay_covered(START, ctx, Candidate(P.L, P.U, FootMove.RIGHT))
    assert not held_panels_stay_covered(START, ctx, Candidate(P.U, P.R, FootMove.LEFT))
    released = _ctx(Panel.U, held=Panel.L, releasable=Panel.L)
    assert held_panels_stay_covered(START, released, Candidate(P.U, P.R, FootMove.LEFT))


def test_hold_owner_stays_on_panel() -> None:
    prev = _holding_left()
    ctx = _ctx(Panel.U, held=Panel.L)
    assert hold_owner_stays_on_panel(prev, ctx, Candidate(P.L, P.U, FootMove.RIGHT))
    # The right foot takes over the held panel: a mid-hold switch.
    assert not hold_owner_stays_on_panel(prev, ctx, Candidate(P.U, P.L, FootMove.BOTH))


def test_no_bracket_onto_held_panel() -> None:
    prev = _holding_left()
    ctx = _ctx(Panel.U, held=Panel.L)
    assert no_bracket_onto_held_panel(prev, ctx, Candidate(P.L, P.U, FootMove.RIGHT))
    assert not no_bracket_onto_held_panel(prev, ctx, Candidate(P.L, P.LU, FootMove.RIGHT))


def test_iter_legal_transitions_keeps_hold_owner_on_panel() -> None:
    prev = _holding_left()
    row = NoteRow.from_str("0010", holds_active=Panel.L)
    nexts = {(n.stance.left, n.stance.right) for n in iter_legal_transitions(prev, row)}
    assert nexts == {(P.L, P.U), (P.LU, P.R)}
