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
    "same_foot",  # The same foot presses twice in a row (any panels).
    "same_foot_speed",  # Same, scaled by speed.
    "same_foot_after_release",  # Same, but the other foot just released a hold, including a
    # grace-window release on this row (natural after a hold).
    "jack",  # Same foot, same panel, consecutive presses.
    "jack_speed",  # Same, scaled by speed.
    "jack_speed_sq",  # Same, scaled by speed squared, so fast jacks cost disproportionately more.
    "switch",  # Other foot, same panel, consecutive presses.
    "switch_speed",  # Same, scaled by speed.
    "repeat_change",  # A same-panel run changes technique midway (jack then switch, or the reverse).
    "travel",  # Distance the moving foot travels.
    "travel_speed",  # Same, scaled by speed.
    "overlap",  # Both feet end up sharing a panel area during a single-foot press.
    "crossed",  # The stance is crossed.
    "cross_entry",  # Same, but only on the step that enters the crossed stance.
    "inverted",  # Fully backwards stance.
    "facing_flip",  # Turning from facing one side to facing the other.
    "twisted",  # Facing sideways without being crossed.
    "bracket",  # A foot lands on a two-panel bracket.
    "bracket_speed",  # Same, scaled by speed.
    "jump",  # Both feet press on the same row.
    "jump_speed",  # Same, scaled by speed.
    "hold_bracket_tap",  # A foot that owns a hold brackets to tap another panel.
    "mine_cued_switch",  # A switch with a mine cue since the last press.
    "mine_cued_same_foot",  # A same-foot repeat with a mine cue since the last press.
    "cued_foot_moves",  # A foot standing on a mine-cued panel moves off it.
    "cued_foot_stays",  # A foot standing on a mine-cued panel stays on it.
    "hold_release",  # A foot leaves a hold or roll it owns during the grace window (tail row included).
    "early_release",  # Same, scaled by how early: seconds left to the tail / grace window (0 on
    # the tail row, up to 1).
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

    press_col = curr.last_press_col
    if (
        single
        and press_col is not None
        and press_col == prev.last_press_col
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
