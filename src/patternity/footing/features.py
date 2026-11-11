"""Per-transition features: smooth, pattern-agnostic descriptions of what the feet do.

Several features are also scaled by speed (notes per second / 10). Nothing here
references tech-pattern timing cutoffs; those live in ``patternity.patterns.detector``.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    "repeat_change",  # A same-panel run changes technique midway (jack then switch, or
    # the reverse).
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
    "hold_release",  # A foot leaves a hold or roll it owns during the grace window (tail
    # row included).
    "early_release",  # Same, scaled by how early: seconds left to the tail / grace window (0 on
    # the tail row, up to 1).
)
FEATURE_INDEX: dict[str, int] = {name: i for i, name in enumerate(FEATURE_NAMES)}

_MAX_NPS = 20.0


def speed(dt: float | None) -> float:
    """Smooth speed scale in [0, 2]: notes per second / 10, capped at 20 NPS."""
    if dt is None or dt <= 0.0:
        return 0.0
    return min(1.0 / dt, _MAX_NPS) / 10.0


def _placement(row: FootRow, foot: Foot) -> FootPlacement:
    return row.stance.placement(foot)


def _displaced(curr: FootRow, foot: Foot) -> bool:
    """A stationary foot whose panel the moving foot just took over (it has lifted)."""
    return curr.moved.includes(foot.other) and _placement(curr, foot).shares_panel_with(
        _placement(curr, foot.other)
    )


def hits_mine(curr: FootRow, mines: Panel) -> bool:
    """True if a foot that is down on this row covers a mine on this row."""
    for foot in Foot:
        if not curr.moved.includes(foot) and _displaced(curr, foot):
            continue
        if _placement(curr, foot).panels & mines:
            return True
    return False


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

    def add(self, name: str, value: float = 1.0) -> None:
        if value:
            self[name] = self.get(name, 0.0) + value


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
        feats.add("hold_release")
        remaining = step.grace_remaining[panel.column]
        if remaining:
            window = ROLL_GRACE_SEC if panel in step.row.rolls_active else HOLD_GRACE_SEC
            feats.add("early_release", remaining / window)
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
            feats.add("same_foot_after_release")
        else:
            feats.add("same_foot")
            feats.add("same_foot_speed", step.speed)

    if step.is_jack:
        feats.add("jack")
        feats.add("jack_speed", step.speed)
        feats.add("jack_speed_sq", step.speed * step.speed)
    elif step.is_switch:
        feats.add("switch")
        feats.add("switch_speed", step.speed)

    # A same-panel run changed technique (jack then switch, or the reverse).
    repeats = (step.prev.last_repeat, step.curr.last_repeat)
    if Repeat.NONE not in repeats and repeats[0] is not repeats[1]:
        feats.add("repeat_change")


def _mine_cue_features(step: _Step, feats: _Features) -> None:
    """Mines since the last press hint at which foot comes next (``mine_cued_*``,
    ``cued_foot_*``)."""
    cue = step.cue
    if not cue:
        return
    if step.same_foot:
        feats.add("mine_cued_same_foot")
    if step.is_switch:
        feats.add("mine_cued_switch")

    for foot in Foot:
        if step.moved.includes(foot):
            if _placement(step.prev, foot).panels & cue:
                feats.add("cued_foot_moves")
        elif _placement(step.curr, foot).panels & cue and not _displaced(step.curr, foot):
            feats.add("cued_foot_stays")


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
                feats.add("hold_bracket_tap")

    feats.add("travel", travel)
    feats.add("travel_speed", travel * step.speed)
    feats.add("bracket", brackets)
    feats.add("bracket_speed", brackets * step.speed)

    if not step.single:
        feats.add("jump")
        feats.add("jump_speed", step.speed)


def _stance_features(step: _Step, feats: _Features) -> None:
    """The shape of the stance the feet end up in (``overlap``, ``crossed``,
    ``cross_entry``, ``inverted``, ``facing_flip``, ``twisted``)."""
    stance = step.curr.stance
    before = step.prev.stance
    if step.single and stance.is_overlapping:
        feats.add("overlap")
    if stance.is_crossed:
        feats.add("crossed")
        if not before.is_crossed:
            feats.add("cross_entry")
    if stance.orientation == PlayerOrientation.INVERTED:
        feats.add("inverted")

    turned_to_other_side = (
        stance.orientation.is_facing
        and before.orientation.is_facing
        and stance.orientation != before.orientation
    )
    if turned_to_other_side:
        feats.add("facing_flip")
    if stance.orientation.is_facing and not stance.is_crossed:
        feats.add("twisted")


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
