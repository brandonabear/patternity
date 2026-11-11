from patternity.footing.features import featurize
from patternity.footing.grace import (
    HOLD_GRACE_SEC,
    ROLL_GRACE_SEC,
    GraceWindow,
    hold_grace,
)
from patternity.footing.stance import Foot, FootMove, FootPlacement, FootRow, Stance
from patternity.footing.transitions import iter_legal_transitions
from patternity.simfile import NoteRow, Panel
from tests.helpers import chart_rows


def _rows(rows: list[str], bpm: float = 150.0) -> list[NoteRow]:
    """Defaults to 150 BPM, where 8ths are 0.2 s apart."""
    return chart_rows(rows, bpm)


def _left_holding_left() -> FootRow:
    return FootRow(
        stance=Stance.from_feet(FootPlacement.L, FootPlacement.R),
        moved=FootMove.LEFT,
        last_press_moved=FootMove.LEFT,
        hold_owners=((Panel.L, Foot.LEFT),),
    )


def _left_presses_down(rows: list[NoteRow], i: int) -> dict[str, float] | None:
    grace = hold_grace(rows)[i]
    prev = _left_holding_left()
    for curr in iter_legal_transitions(prev, rows[i], grace=grace.panels):
        if curr.moved == FootMove.LEFT and curr.stance.left == FootPlacement.D:
            assert curr.hold_owners == ()
            return featurize(prev, curr, rows[i], 0.2, grace_remaining=grace.remaining)
    return None


def test_grace_covers_tail_row_and_rows_inside_window() -> None:
    # 8ths at 150 BPM are 0.2s apart: head, inside window, tail.
    rows = _rows(["2000", "0100", "3000", "0000"] * 2 + [","])
    grace = hold_grace(rows)
    assert grace[0] == GraceWindow()
    assert grace[1].panels == Panel.L
    left = grace[1].remaining[0]
    assert left is not None and 0.0 < left <= HOLD_GRACE_SEC
    assert grace[2] == GraceWindow(Panel.L, (0.0, None, None, None))


def test_tail_row_release_costs_hold_release_only() -> None:
    rows = _rows(["2000", "3100", ","])
    feats = _left_presses_down(rows, 1)
    assert feats is not None
    assert feats["hold_release"] == 1.0
    assert "early_release" not in feats


def test_release_inside_window_adds_early_release() -> None:
    rows = _rows(["2000", "0100", "3000", "0000"] * 2 + [","])
    feats = _left_presses_down(rows, 1)
    assert feats is not None
    assert feats["hold_release"] == 1.0
    assert 0.0 < feats["early_release"] <= 1.0


def test_owner_cannot_leave_before_window() -> None:
    # 16ths at 150 BPM are 0.1s apart; the tap is 1.0s before the tail.
    rows = _rows(
        ["2000"] + ["0000"] * 3 + ["0100"] + ["0000"] * 9 + ["3000", "0000", ","]
    )
    press = next(i for i, r in enumerate(rows) if r.pressed == Panel.D)
    assert not hold_grace(rows)[press].panels
    assert _left_presses_down(rows, press) is None


def test_roll_uses_roll_window() -> None:
    # 0.33s before the tail: outside the hold window, inside the roll window.
    rows = _rows(["4000", "0100", "3000", ","], bpm=240.0)
    gap = rows[2].timestamp - rows[1].timestamp
    assert HOLD_GRACE_SEC < gap <= ROLL_GRACE_SEC
    assert hold_grace(rows)[1].panels == Panel.L
