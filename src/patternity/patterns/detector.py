"""Tech pattern labels derived from a decoded foot path.

This is the only module that applies community / ITGMania timing cutoffs; the
footing decoder never sees them.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from patternity.analysis.metrics import TechMetrics
from patternity.footing.resolve import ResolvedStep
from patternity.footing.stance import FootMove, FootPlacement, PlayerOrientation
from patternity.patterns.spans import PatternKind, PatternSpan
from patternity.simfile.notes import PANELS, NoteType, Panel

ITG_JACK_CUTOFF_SEC = 0.176
# Inclusive of 90 BPM 8ths (exactly 1/3 s apart).
ITG_FOOTSWITCH_CUTOFF_SEC = (1.0 / 3.0) + 1e-6

_SIDE_PANELS = Panel.L | Panel.R
_PRESS = frozenset({NoteType.TAP, NoteType.HOLD, NoteType.ROLL, NoteType.LIFT})
_FEET = (FootMove.LEFT, FootMove.RIGHT)
_OPPOSITE_PANELS = ((Panel.U, Panel.D), (Panel.L, Panel.R))


def _crosses_center(before: FootPlacement, after: FootPlacement) -> bool:
    """The foot moved between opposite panels (U/D or L/R) without keeping one."""
    if before.shares_panel_with(after):
        return False
    return any(
        (a in before.panels and b in after.panels) or (b in before.panels and a in after.panels)
        for a, b in _OPPOSITE_PANELS
    )


def _span(kind: PatternKind, steps: tuple[ResolvedStep, ...]) -> PatternSpan:
    first, last = steps[0].note_row, steps[-1].note_row
    return PatternSpan(
        kind=kind,
        start_beat=first.beat or 0.0,
        end_beat=last.beat or 0.0,
        start_measure=first.measure or 0,
        end_measure=last.measure or 0,
        steps=steps,
    )


def column_foot(step: ResolvedStep, panel: Panel) -> FootMove | None:
    """Foot acting on ``panel``: the moving foot for a press, the hold owner for a tail."""
    note = step.note_row.notes[panel.column]
    fr = step.foot_row
    if note in _PRESS:
        for foot in _FEET:
            if fr.moved & foot and panel in fr.stance.placement(foot).panels:
                return foot
        return None
    if note == NoteType.TAIL:
        return fr.hold_owner_for(panel)
    return None


def _single_press(step: ResolvedStep) -> Panel:
    """The pressed panel if exactly one is pressed on this row, else ``Panel.NONE``."""
    pressed = step.note_row.pressed
    return pressed if len(pressed) == 1 else Panel.NONE


@dataclass
class _ColumnHistory:
    """What last happened on one panel.

    Jacks and switches only pair a panel's event with the very next press row;
    a revisit after other steps (e.g. D-U-D in a stream) is neither. To enforce
    this, events are stamped with an *epoch*: the number of press rows seen so
    far, including the row the event is on. An earlier event is adjacent to the
    current press row exactly when its epoch equals the count of press rows
    *before* the current one (``epoch_before``).
    """

    # Last event of any kind (press or hold/roll tail).
    last_event: ResolvedStep | None = None
    last_foot: FootMove | None = None
    last_time: float = -math.inf
    last_was_tail: bool = False
    event_epoch: int = -1
    # Last press (tails excluded).
    last_press: ResolvedStep | None = None
    press_foot: FootMove | None = None
    press_time: float = -math.inf
    press_epoch: int = -1
    # Latest mine on this panel since its last press.
    mine_time: float | None = None

    def press_before(self, epoch_before: int) -> ResolvedStep | None:
        """The last press, if it was on the press row right before this one."""
        return self.last_press if self.press_epoch == epoch_before else None

    def event_before(self, epoch_before: int) -> ResolvedStep | None:
        """The last event, if it was no earlier than the press row right before this one."""
        return self.last_event if self.event_epoch == epoch_before else None

    def mine_after(self, time: float) -> float | None:
        """The panel's mine time if a mine fell after ``time``."""
        if self.mine_time is not None and self.mine_time > time:
            return self.mine_time
        return None

    def record_press(self, step: ResolvedStep, foot: FootMove, now: float, epoch: int) -> None:
        self.last_press = step
        self.press_foot = foot
        self.press_time = now
        self.press_epoch = epoch
        self.mine_time = None

    def record_event(
        self, step: ResolvedStep, foot: FootMove, now: float, epoch: int, is_tail: bool
    ) -> None:
        self.last_event = step
        self.last_foot = foot
        self.last_time = now
        self.last_was_tail = is_tail
        self.event_epoch = epoch


class _TechDetector:
    """Walks a decoded path once, appending a span for each pattern it finds."""

    def __init__(self) -> None:
        self.spans: list[PatternSpan] = []
        self.columns = {panel: _ColumnHistory() for panel in PANELS}
        self.press_rows = 0
        self.any_mine_time = -math.inf
        self.prev_press: ResolvedStep | None = None
        self.prev_row: ResolvedStep | None = None
        # Each foot's previous press, for candles (the other foot's presses in
        # between don't matter).
        self.foot_press: dict[FootMove, ResolvedStep] = {}
        # Orientation of the current crossed stance, or None while uncrossed.
        self.crossed_orientation: PlayerOrientation | None = None

    def feed(self, step: ResolvedStep) -> None:
        row = step.note_row
        now = row.timestamp or 0.0
        self._record_mines(step, now)

        epoch_before = self.press_rows
        if step.foot_row.moved != FootMove.NONE:
            self.press_rows += 1
            self._brackets_and_candles(step)
            self._doublestep(step)
            self._crossover(step)
            self.prev_press = step

        for panel, note in zip(PANELS, row.notes, strict=True):
            foot = column_foot(step, panel)
            if foot is None:
                continue
            history = self.columns[panel]
            is_press = note in _PRESS
            if is_press:
                self._jack_or_switch(step, panel, foot, now, epoch_before)
                history.record_press(step, foot, now, self.press_rows)
            history.record_event(step, foot, now, self.press_rows, is_tail=not is_press)
        self.prev_row = step

    def _record_mines(self, step: ResolvedStep, now: float) -> None:
        for panel in step.note_row.mines:
            self.columns[panel].mine_time = now
            self.any_mine_time = now

    def _brackets_and_candles(self, step: ResolvedStep) -> None:
        """A bracket: one foot presses two panels. A candle: a foot's press lands
        opposite its own previous press."""
        fr = step.foot_row
        for mover in _FEET:
            if not fr.moved & mover:
                continue
            placement = fr.stance.placement(mover)
            if len(placement.panels & step.note_row.pressed) >= 2:
                self.spans.append(_span(PatternKind.BRACKET, (step,)))
            before = self.foot_press.get(mover)
            if before is not None and _crosses_center(
                before.foot_row.stance.placement(mover), placement
            ):
                self.spans.append(_span(PatternKind.CANDLE, (before, step)))
            self.foot_press[mover] = step

    def _doublestep(self, step: ResolvedStep) -> None:
        """The same foot presses two different single panels in a row, unless the
        other foot released a hold in between."""
        prev = self.prev_press
        moved = step.foot_row.moved
        press = _single_press(step)
        # Only a tail on a row of its own exempts the doublestep: the other foot
        # was free before this press. A tail on this press row does not, because
        # the other foot was still pinned when the step had to be taken (a
        # hold-cued doublestep).
        released = (
            self.prev_row.foot_row.released_since_press
            if self.prev_row is not None
            else FootMove.NONE
        )
        if (
            prev is not None
            and moved in _FEET
            and prev.foot_row.moved == moved
            and press
            and _single_press(prev) not in (Panel.NONE, press)
            and not released & ~moved
        ):
            self.spans.append(_span(PatternKind.DOUBLESTEP, (prev, step)))

    def _crossover(self, step: ResolvedStep) -> None:
        """A crossover starts when the legs cross, or turn while staying crossed."""
        stance = step.foot_row.stance
        orientation = stance.orientation if stance.is_crossed else None
        if orientation is not None and orientation != self.crossed_orientation:
            kind = (
                PatternKind.INVERTED_CROSSOVER
                if orientation == PlayerOrientation.INVERTED
                else PatternKind.CROSSOVER
            )
            entry = (step,) if self.prev_press is None else (self.prev_press, step)
            self.spans.append(_span(kind, entry))
        self.crossed_orientation = orientation

    def _jack_or_switch(
        self, step: ResolvedStep, panel: Panel, foot: FootMove, now: float, epoch_before: int
    ) -> None:
        """Pair this press with the panel's event on the previous press row."""
        history = self.columns[panel]
        prior_press = history.press_before(epoch_before)
        if prior_press is not None and history.press_foot == foot:
            self._jack(step, panel, prior_press, now)
            return
        prior_event = history.event_before(epoch_before)
        if prior_event is not None and history.last_foot not in (None, foot):
            self._switch(step, panel, prior_event, now)

    def _jack(self, step: ResolvedStep, panel: Panel, prior: ResolvedStep, now: float) -> None:
        """Same foot, same panel, fast enough. A mine in between resets the clock."""
        history = self.columns[panel]
        mine_ref = history.mine_after(history.press_time)
        ref_time = history.press_time if mine_ref is None else mine_ref
        mine_on_row = panel in step.note_row.mines
        if now - ref_time < ITG_JACK_CUTOFF_SEC and not mine_on_row:
            self.spans.append(_span(PatternKind.JACK, (prior, step)))

    def _switch(self, step: ResolvedStep, panel: Panel, prior: ResolvedStep, now: float) -> None:
        """The other foot takes over the panel fast enough."""
        history = self.columns[panel]
        mine_ref = history.mine_after(history.last_time)
        ref_time = history.last_time if mine_ref is None else mine_ref
        # A switch after a hold release (holdswitch) needs a mine cue.
        cued = not history.last_was_tail or self.any_mine_time > history.last_time
        if panel in _SIDE_PANELS:
            kind = PatternKind.SIDESWITCH
        else:
            kind = PatternKind.FOOTSWITCH
            if mine_ref is not None:
                return
        if cued and now - ref_time < ITG_FOOTSWITCH_CUTOFF_SEC:
            self.spans.append(_span(kind, (prior, step)))


def detect_tech_patterns(steps: Sequence[ResolvedStep]) -> TechMetrics:
    """Label jacks, foot/side switches, doublesteps, brackets, crossovers, and candles."""
    detector = _TechDetector()
    for step in steps:
        detector.feed(step)
    spans = sorted(detector.spans, key=lambda s: (s.start_beat, s.end_beat))
    return TechMetrics(spans=spans)
