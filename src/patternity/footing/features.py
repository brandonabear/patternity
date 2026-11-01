"""Per-transition features: smooth, pattern-agnostic descriptions of what the feet do.

Several features are also scaled by speed (notes per second / 10). Nothing here
references tech-pattern timing cutoffs; those live in ``patternity.patterns.detector``.
"""

from __future__ import annotations

from patternity.footing.grace import HOLD_GRACE_SEC, ROLL_GRACE_SEC, Remaining
from patternity.footing.stance import (
    FootMove,
    FootPlacement,
    FootRow,
    PlayerOrientation,
)
from patternity.footing.transitions import anchored_mask
from patternity.simfile.notes import NoteRow

FEATURE_NAMES: tuple[str, ...] = (
    "same_foot",
    "same_foot_speed",
    "same_foot_after_release",
    "jack",
    "jack_speed",
    "jack_speed_sq",
    "switch",
    "switch_speed",
    "repeat_change",
    "travel",
    "travel_speed",
    "overlap",
    "crossed",
    "cross_entry",
    "inverted",
    "facing_flip",
    "twisted",
    "bracket",
    "bracket_speed",
    "jump",
    "jump_speed",
    "hold_bracket_tap",
    "mine_cued_switch",
    "mine_cued_same_foot",
    "cued_foot_moves",
    "cued_foot_stays",
    "hold_release",
    "early_release",
)
FEATURE_INDEX: dict[str, int] = {name: i for i, name in enumerate(FEATURE_NAMES)}

_MAX_NPS = 20.0
_FEET = (FootMove.LEFT, FootMove.RIGHT)
_FACING = frozenset({PlayerOrientation.FACING_LEFT, PlayerOrientation.FACING_RIGHT})


def speed(dt: float | None) -> float:
    """Smooth speed scale in [0, 2]: notes per second / 10, capped at 20 NPS."""
    if dt is None or dt <= 0.0:
        return 0.0
    return min(1.0 / dt, _MAX_NPS) / 10.0


def _placement(row: FootRow, foot: FootMove) -> FootPlacement:
    return row.stance.placement(foot)


def _displaced(curr: FootRow, foot: FootMove) -> bool:
    """A stationary foot whose panel the moving foot just took over (it has lifted)."""
    other = FootMove.RIGHT if foot == FootMove.LEFT else FootMove.LEFT
    return bool(curr.moved & other) and _placement(curr, foot).shares_panel_with(
        _placement(curr, other)
    )


def hits_mine(curr: FootRow, mine_mask: int) -> bool:
    """True if a foot that is down on this row covers a mine on this row."""
    for foot in _FEET:
        if not curr.moved & foot and _displaced(curr, foot):
            continue
        if _placement(curr, foot).mask & mine_mask:
            return True
    return False


def featurize(
    prev: FootRow,
    curr: FootRow,
    row: NoteRow,
    dt: float | None,
    grace_remaining: Remaining = (None, None, None, None),
) -> dict[str, float]:
    """Feature values for moving from ``prev`` to ``curr`` on ``row``."""
    moved = curr.moved
    if moved == FootMove.NONE:
        return {}

    feats: dict[str, float] = {}

    def add(name: str, value: float = 1.0) -> None:
        if value:
            feats[name] = feats.get(name, 0.0) + value

    spd = speed(dt)
    single = moved != FootMove.BOTH
    prev_foot = prev.last_press_foot
    cue = prev.mines_since_press | row.mine_mask

    anchored = anchored_mask(row)
    kept = {col for col, _ in curr.hold_owners}
    released_now = FootMove.NONE
    for col, foot in prev.hold_owners:
        bit = 1 << col
        if not anchored & bit or col in kept:
            continue
        released_now |= foot
        add("hold_release")
        rem = grace_remaining[col]
        if rem:
            window = ROLL_GRACE_SEC if row.roll_active_mask & bit else HOLD_GRACE_SEC
            add("early_release", rem / window)

    release_context = prev.released_since_press | released_now

    if single and prev_foot == moved:
        if release_context & ~moved:
            add("same_foot_after_release")
        else:
            add("same_foot")
            add("same_foot_speed", spd)
        if cue:
            add("mine_cued_same_foot")

    col = curr.last_press_col
    if (
        single
        and col is not None
        and col == prev.last_press_col
        and prev_foot in _FEET
    ):
        if prev_foot == moved:
            add("jack")
            add("jack_speed", spd)
            add("jack_speed_sq", spd * spd)
        else:
            add("switch")
            add("switch_speed", spd)
            if cue:
                add("mine_cued_switch")
        if (
            curr.last_repeat_jack is not None
            and prev.last_repeat_jack is not None
            and curr.last_repeat_jack != prev.last_repeat_jack
        ):
            add("repeat_change")

    travel = 0.0
    brackets = 0
    owners = {foot for _, foot in prev.hold_owners}
    for foot in _FEET:
        before = _placement(prev, foot)
        after = _placement(curr, foot)
        if moved & foot:
            travel += before.distance_to(after)
            if after.is_bracket:
                brackets += 1
            if before.mask & cue:
                add("cued_foot_moves")
            if foot in owners and after.is_bracket:
                add("hold_bracket_tap")
        elif after.mask & cue and not _displaced(curr, foot):
            add("cued_foot_stays")

    add("travel", travel)
    add("travel_speed", travel * spd)
    add("bracket", brackets)
    add("bracket_speed", brackets * spd)

    if not single:
        add("jump")
        add("jump_speed", spd)

    stance = curr.stance
    if single and stance.is_overlapping:
        add("overlap")
    if stance.is_crossed:
        add("crossed")
        if not prev.stance.is_crossed:
            add("cross_entry")
    if stance.orientation == PlayerOrientation.INVERTED:
        add("inverted")
    if (
        stance.orientation in _FACING
        and prev.stance.orientation in _FACING
        and stance.orientation != prev.stance.orientation
    ):
        add("facing_flip")
    if stance.orientation in _FACING and not stance.is_crossed:
        add("twisted")
    return feats
