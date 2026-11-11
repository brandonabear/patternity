"""Per-transition features: smooth, pattern-agnostic descriptions of what the feet do.

Several features are also scaled by speed (notes per second / 10). Nothing here
references tech-pattern timing cutoffs; those live in ``patternity.patterns.detector``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from patternity.footing.grace import HOLD_GRACE_SEC, ROLL_GRACE_SEC, Remaining
from patternity.footing.rules import held_panels
from patternity.footing.stance import (
    Foot,
    FootMove,
    FootPlacement,
    FootRow,
    PlayerOrientation,
    Repeat,
)
from patternity.simfile.notes import NoteRow, Panel


class Feature(StrEnum):
    """What the feet do on one transition. Each has one learned weight."""

    # The same foot presses twice in a row (any panels).
    SAME_FOOT = "same_foot"
    SAME_FOOT_SPEED = "same_foot_speed"  # Scaled by speed.
    # Same, but the other foot just released a hold, including a grace-window
    # release on this row (natural after a hold).
    SAME_FOOT_AFTER_RELEASE = "same_foot_after_release"

    # Same foot, same panel, consecutive presses.
    JACK = "jack"
    JACK_SPEED = "jack_speed"  # Scaled by speed.
    # Scaled by speed squared, so fast jacks cost disproportionately more.
    JACK_SPEED_SQ = "jack_speed_sq"

    # Other foot, same panel, consecutive presses.
    SWITCH = "switch"
    SWITCH_SPEED = "switch_speed"  # Scaled by speed.
    # A same-panel run changes technique midway (jack then switch, or the reverse).
    REPEAT_CHANGE = "repeat_change"

    # Distance the moving foot travels.
    TRAVEL = "travel"
    TRAVEL_SPEED = "travel_speed"  # Scaled by speed.

    # Both feet end up sharing a panel area during a single-foot press.
    OVERLAP = "overlap"
    # The stance is crossed.
    CROSSED = "crossed"
    # Same, but only on the step that enters the crossed stance.
    CROSS_ENTRY = "cross_entry"
    # Fully backwards stance.
    INVERTED = "inverted"
    # Turning from facing one side to facing the other.
    FACING_FLIP = "facing_flip"
    # Facing sideways without being crossed.
    TWISTED = "twisted"

    # A foot lands on a two-panel bracket.
    BRACKET = "bracket"
    BRACKET_SPEED = "bracket_speed"  # Scaled by speed.
    # Both feet press on the same row.
    JUMP = "jump"
    JUMP_SPEED = "jump_speed"  # Scaled by speed.
    # A foot that owns a hold brackets to tap another panel.
    HOLD_BRACKET_TAP = "hold_bracket_tap"

    # A switch with a mine cue since the last press.
    MINE_CUED_SWITCH = "mine_cued_switch"
    # A same-foot repeat with a mine cue since the last press.
    MINE_CUED_SAME_FOOT = "mine_cued_same_foot"
    # A foot standing on a mine-cued panel moves off it.
    CUED_FOOT_MOVES = "cued_foot_moves"
    # A foot standing on a mine-cued panel stays on it.
    CUED_FOOT_STAYS = "cued_foot_stays"

    # A foot leaves a hold or roll it owns during the grace window (tail row included).
    HOLD_RELEASE = "hold_release"
    # Same, scaled by how early: seconds left to the tail / grace window (0 on
    # the tail row, up to 1).
    EARLY_RELEASE = "early_release"


# Feature names in weight-vector order.
FEATURE_NAMES: tuple[str, ...] = tuple(feature.value for feature in Feature)
FEATURE_INDEX: dict[str, int] = {name: i for i, name in enumerate(FEATURE_NAMES)}

_MAX_NPS = 20.0


def speed(dt: float | None) -> float:
    """Smooth speed scale in [0, 2]: notes per second / 10, capped at 20 NPS."""
    if dt is None or dt <= 0.0:
        return 0.0
    return min(1.0 / dt, _MAX_NPS) / 10.0


def _placement(row: FootRow, foot: Foot) -> FootPlacement:
    return row.stance.placement(foot)


@dataclass(frozen=True, slots=True)
class _Step:
    """One transition being scored: ``prev`` to ``curr`` on ``row``."""

    prev: FootRow
    curr: FootRow
    row: NoteRow
    speed: float  # See ``speed``.
    grace_remaining: Remaining

    @property
    def moved(self) -> FootMove:
        return self.curr.moved

    @property
    def single(self) -> bool:
        """Exactly one foot moved (not a jump)."""
        return self.moved != FootMove.BOTH

    @property
    def cue(self) -> Panel:
        """Panels with a mine since the last press, including this row."""
        return self.prev.mines_since_press | self.row.mines

    @property
    def same_foot(self) -> bool:
        """The foot that pressed last presses again (any panels)."""
        return self.single and self.prev.last_press_moved == self.moved

    @property
    def is_jack(self) -> bool:
        return self.curr.last_repeat is Repeat.JACK

    @property
    def is_switch(self) -> bool:
        return self.curr.last_repeat is Repeat.SWITCH


class _Features(dict[str, float]):
    """Feature values being accumulated for one transition."""

    def add(self, feature: Feature, value: float = 1.0) -> None:
        if value:
            self[feature] = self.get(feature, 0.0) + value


def _hold_release_features(step: _Step, feats: _Features) -> FootMove:
    """``hold_release`` and ``early_release``: a foot leaves its hold in the grace window.

    Returns the feet that released a hold on this row.
    """
    held = held_panels(step.row)
    still_owned = {panel for panel, _ in step.curr.hold_owners}
    released = FootMove.NONE
    for panel, foot in step.prev.hold_owners:
        # Released: the hold is still underway, but no foot owns it any more.
        if panel not in held or panel in still_owned:
            continue
        released |= foot.move
        feats.add(Feature.HOLD_RELEASE)
        remaining = step.grace_remaining[panel.column]
        if remaining:
            window = ROLL_GRACE_SEC if panel in step.row.rolls_active else HOLD_GRACE_SEC
            feats.add(Feature.EARLY_RELEASE, remaining / window)
    return released


def _repetition_features(step: _Step, feats: _Features, released_now: FootMove) -> None:
    """Same foot pressing twice (``same_foot*``) and same-panel repeats (``jack*``,
    ``switch*``, ``repeat_change``)."""
    if step.same_foot:
        # A double-step is natural when the other foot just let go of a hold (earlier
        # since the last press, or on this row), so it gets its own weight.
        released = step.prev.released_since_press | released_now
        other_foot_released = bool(released & ~step.moved)
        if other_foot_released:
            feats.add(Feature.SAME_FOOT_AFTER_RELEASE)
        else:
            feats.add(Feature.SAME_FOOT)
            feats.add(Feature.SAME_FOOT_SPEED, step.speed)

    if step.is_jack:
        feats.add(Feature.JACK)
        feats.add(Feature.JACK_SPEED, step.speed)
        feats.add(Feature.JACK_SPEED_SQ, step.speed * step.speed)
    elif step.is_switch:
        feats.add(Feature.SWITCH)
        feats.add(Feature.SWITCH_SPEED, step.speed)

    # A same-panel run changed technique (jack then switch, or the reverse).
    repeats = (step.prev.last_repeat, step.curr.last_repeat)
    if Repeat.NONE not in repeats and repeats[0] is not repeats[1]:
        feats.add(Feature.REPEAT_CHANGE)


def _mine_cue_features(step: _Step, feats: _Features) -> None:
    """Mines since the last press hint at which foot comes next (``mine_cued_*``,
    ``cued_foot_*``)."""
    cue = step.cue
    if not cue:
        return
    if step.same_foot:
        feats.add(Feature.MINE_CUED_SAME_FOOT)
    if step.is_switch:
        feats.add(Feature.MINE_CUED_SWITCH)

    for foot in Foot:
        if step.moved.includes(foot):
            if _placement(step.prev, foot).panels & cue:
                feats.add(Feature.CUED_FOOT_MOVES)
        elif _placement(step.curr, foot).panels & cue and not step.curr.is_displaced(foot):
            feats.add(Feature.CUED_FOOT_STAYS)


def _movement_features(step: _Step, feats: _Features) -> None:
    """How far and onto what the moving feet go (``travel*``, ``bracket*``,
    ``hold_bracket_tap``, ``jump*``)."""
    travel = 0.0
    brackets = 0
    hold_owners = {foot for _, foot in step.prev.hold_owners}
    for foot in step.moved.feet:
        before = _placement(step.prev, foot)
        after = _placement(step.curr, foot)
        travel += before.distance_to(after)
        if after.is_bracket:
            brackets += 1
            if foot in hold_owners:
                feats.add(Feature.HOLD_BRACKET_TAP)

    feats.add(Feature.TRAVEL, travel)
    feats.add(Feature.TRAVEL_SPEED, travel * step.speed)
    feats.add(Feature.BRACKET, brackets)
    feats.add(Feature.BRACKET_SPEED, brackets * step.speed)

    if not step.single:
        feats.add(Feature.JUMP)
        feats.add(Feature.JUMP_SPEED, step.speed)


def _stance_features(step: _Step, feats: _Features) -> None:
    """The shape of the stance the feet end up in (``overlap``, ``crossed``,
    ``cross_entry``, ``inverted``, ``facing_flip``, ``twisted``)."""
    stance = step.curr.stance
    before = step.prev.stance
    if step.single and stance.is_overlapping:
        feats.add(Feature.OVERLAP)
    if stance.is_crossed:
        feats.add(Feature.CROSSED)
        if not before.is_crossed:
            feats.add(Feature.CROSS_ENTRY)
    if stance.orientation == PlayerOrientation.INVERTED:
        feats.add(Feature.INVERTED)

    turned_to_other_side = (
        stance.orientation.is_facing
        and before.orientation.is_facing
        and stance.orientation != before.orientation
    )
    if turned_to_other_side:
        feats.add(Feature.FACING_FLIP)
    if stance.orientation.is_facing and not stance.is_crossed:
        feats.add(Feature.TWISTED)


def featurize(
    prev: FootRow,
    curr: FootRow,
    row: NoteRow,
    dt: float | None,
    grace_remaining: Remaining = (None, None, None, None),
) -> dict[str, float]:
    """Feature values for moving from ``prev`` to ``curr`` on ``row``."""
    if curr.moved == FootMove.NONE:
        return {}

    step = _Step(prev, curr, row, speed(dt), grace_remaining)
    feats = _Features()
    released_now = _hold_release_features(step, feats)
    _repetition_features(step, feats, released_now)
    _mine_cue_features(step, feats)
    _movement_features(step, feats)
    _stance_features(step, feats)
    return dict(feats)
