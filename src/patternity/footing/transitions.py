from collections.abc import Iterator

from patternity.footing.stance import (
    ALL_PLACEMENTS,
    CARDINAL_PLACEMENTS,
    FootMove,
    FootPlacement,
    FootRow,
    Stance,
)
from patternity.simfile.notes import NoteRow, NoteType

_ANCHOR_HEADS = frozenset({NoteType.HOLD, NoteType.ROLL})


def anchored_mask(row: NoteRow) -> int:
    """Panels held or rolled through this row without a new press (tails included)."""
    return (row.hold_active_mask | row.roll_active_mask) & ~row.press_mask


def _holds_preserved(
    prev: FootRow,
    next_left: FootPlacement,
    next_right: FootPlacement,
    anchored: int,
    allow_mid_hold_switches: bool,
    grace: int,
) -> bool:
    """Anchored panels stay covered, and by their owning foot unless switches are allowed."""
    required = anchored & ~grace
    if ((next_left.mask | next_right.mask) & required) != required:
        return False
    for col, owner in prev.hold_owners:
        bit = 1 << col
        if not anchored & bit:
            continue
        if grace & bit:
            continue
        placement = next_left if owner == FootMove.LEFT else next_right
        other = next_right if owner == FootMove.LEFT else next_left
        if not allow_mid_hold_switches and not placement.mask & bit:
            return False
        if other.is_bracket and other.mask & bit:
            return False
    return True


def _single_press_col(press_mask: int) -> int | None:
    if press_mask.bit_count() != 1:
        return None
    return press_mask.bit_length() - 1


def _update_hold_owners(
    prev: FootRow,
    row: NoteRow,
    stance: Stance,
    moved: FootMove,
    anchored: int,
    grace: int,
) -> tuple[tuple[int, FootMove], ...]:
    owners: dict[int, FootMove] = {
        col: foot for col, foot in prev.hold_owners if (1 << col) & anchored
    }
    for col, foot in list(owners.items()):
        bit = 1 << col
        placement = stance.left if foot == FootMove.LEFT else stance.right
        if grace & bit and not placement.mask & bit:
            del owners[col]
    panels = (row.left, row.down, row.up, row.right)
    for col, note in enumerate(panels):
        if note not in _ANCHOR_HEADS:
            continue
        bit = 1 << col
        if moved & FootMove.LEFT and stance.left.mask & bit:
            owners[col] = FootMove.LEFT
        elif moved & FootMove.RIGHT and stance.right.mask & bit:
            owners[col] = FootMove.RIGHT
    return tuple(sorted(owners.items()))


def _emit_foot_row(
    prev: FootRow,
    row: NoteRow,
    *,
    stance: Stance,
    moved: FootMove,
    anchored: int,
    grace: int,
) -> FootRow:
    if moved == FootMove.NONE:
        released = prev.released_since_press
        panels = (row.left, row.down, row.up, row.right)
        for col, owner in prev.hold_owners:
            if panels[col] == NoteType.TAIL:
                released |= owner
        return FootRow(
            stance=stance,
            moved=moved,
            mines_since_press=prev.mines_since_press | row.mine_mask,
            last_press_col=prev.last_press_col,
            last_press_foot=prev.last_press_foot,
            hold_owners=_update_hold_owners(prev, row, stance, moved, anchored, grace),
            released_since_press=released,
            last_repeat_jack=prev.last_repeat_jack,
        )
    press_col = _single_press_col(row.press_mask)
    repeat_jack = None
    if (
        press_col is not None
        and press_col == prev.last_press_col
        and moved != FootMove.BOTH
        and prev.last_press_foot in (FootMove.LEFT, FootMove.RIGHT)
    ):
        repeat_jack = moved == prev.last_press_foot
    return FootRow(
        stance=stance,
        moved=moved,
        mines_since_press=0,
        last_press_col=press_col,
        last_press_foot=moved,
        hold_owners=_update_hold_owners(prev, row, stance, moved, anchored, grace),
        last_repeat_jack=repeat_jack,
    )


def iter_legal_transitions(
    prev: FootRow,
    row: NoteRow,
    *,
    allow_brackets: bool = True,
    allow_mid_hold_switches: bool = False,
    grace: int = 0,
) -> Iterator[FootRow]:
    """Yield all physically legal next `FootRow` states for `row` given `prev`."""
    press_mask = row.press_mask
    anchored = anchored_mask(row)

    if press_mask == 0:
        yield _emit_foot_row(
            prev,
            row,
            stance=prev.stance,
            moved=FootMove.NONE,
            anchored=anchored,
            grace=grace,
        )
        return

    placements = ALL_PLACEMENTS if allow_brackets else CARDINAL_PLACEMENTS
    prev_stance = prev.stance

    for target in placements:
        if (target.mask & press_mask) != press_mask:
            continue
        if (target.mask & ~press_mask & ~anchored) != 0:
            continue

        if _holds_preserved(
            prev,
            target,
            prev_stance.right,
            anchored,
            allow_mid_hold_switches,
            grace,
        ):
            yield _emit_foot_row(
                prev,
                row,
                stance=Stance.from_feet(
                    target, prev_stance.right, prev_stance.orientation
                ),
                moved=FootMove.LEFT,
                anchored=anchored,
                grace=grace,
            )

        if _holds_preserved(
            prev,
            prev_stance.left,
            target,
            anchored,
            allow_mid_hold_switches,
            grace,
        ):
            yield _emit_foot_row(
                prev,
                row,
                stance=Stance.from_feet(
                    prev_stance.left, target, prev_stance.orientation
                ),
                moved=FootMove.RIGHT,
                anchored=anchored,
                grace=grace,
            )

    if press_mask.bit_count() >= 2:
        allowed_panels = press_mask | anchored
        for left_p in placements:
            if not (left_p.mask & press_mask) or (left_p.mask & ~allowed_panels):
                continue

            for right_p in placements:
                if (
                    not (right_p.mask & press_mask)
                    or (right_p.mask & ~allowed_panels)
                    or left_p.shares_panel_with(right_p)
                ):
                    continue

                if ((left_p.mask | right_p.mask) & press_mask) != press_mask:
                    continue
                if not _holds_preserved(
                    prev,
                    left_p,
                    right_p,
                    anchored,
                    allow_mid_hold_switches,
                    grace,
                ):
                    continue

                yield _emit_foot_row(
                    prev,
                    row,
                    stance=Stance.from_feet(left_p, right_p, prev_stance.orientation),
                    moved=FootMove.BOTH,
                    anchored=anchored,
                    grace=grace,
                )
