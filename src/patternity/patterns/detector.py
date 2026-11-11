"""Tech pattern labels derived from a decoded foot path.

This is the only module that applies community / ITGMania timing cutoffs; the
footing decoder never sees them.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from patternity.footing.resolve import ResolvedStep
from patternity.footing.stance import Foot, FootMove, FootPlacement, PlayerOrientation
from patternity.patterns.metrics import TechMetrics
from patternity.patterns.spans import PatternKind, PatternSpan
from patternity.simfile.notes import PANELS, NoteType, Panel

ITG_JACK_CUTOFF_SEC = 0.176
# Inclusive of 90 BPM 8ths (exactly 1/3 s apart).
ITG_FOOTSWITCH_CUTOFF_SEC = (1.0 / 3.0) + 1e-6

_SIDE_PANELS = Panel.L | Panel.R
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
        start_beat=first.beat,
        end_beat=last.beat,
        start_measure=first.measure,
        end_measure=last.measure,
        steps=steps,
    )


def column_foot(step: ResolvedStep, panel: Panel) -> Foot | None:
    """Foot acting on ``panel``: the moving foot for a press, the hold owner for a tail."""
    note = step.note_row.notes[panel.column]
    fr = step.foot_row
    if panel in step.note_row.pressed:
        for foot in fr.moved.feet:
            if panel in fr.stance.placement(foot).panels:
                return foot
        return None
    if note == NoteType.TAIL:
        return fr.hold_owner_for(panel)
    return None


def _single_press(step: ResolvedStep) -> Panel:
    """The pressed panel if exactly one is pressed on this row, else ``Panel.NONE``."""
    pressed = step.note_row.pressed
    return pressed if len(pressed) == 1 else Panel.NONE


@dataclass(frozen=True, slots=True)
class _PanelEvent:
    """A press, or a hold/roll tail, on one panel.

    ``epoch`` is the number of press rows seen so far, including this event's row.
    """

    step: ResolvedStep
    foot: Foot
    time: float
    epoch: int
    is_tail: bool = False


@dataclass
class _ColumnHistory:
    """What last happened on one panel.

    Jacks and switches only pair a panel's event with the very next press row;
    a revisit after other steps (e.g. D-U-D in a stream) is neither. An earlier
    event is adjacent to the current press row exactly when its epoch equals the
    count of press rows *before* the current one (``epoch_before``).
    """

    last_event: _PanelEvent | None = None  # Press or tail.
    last_press: _PanelEvent | None = None  # Tails excluded.
    # Latest mine on this panel since its last press.
    mine_time: float | None = None

    def press_before(self, epoch_before: int) -> _PanelEvent | None:
        """The last press, if it was on the press row right before this one."""
        press = self.last_press
        return press if press is not None and press.epoch == epoch_before else None

    def event_before(self, epoch_before: int) -> _PanelEvent | None:
        """The last event, if it was no earlier than the press row right before this one."""
        event = self.last_event
        return event if event is not None and event.epoch == epoch_before else None

    def mine_after(self, time: float) -> float | None:
        """The panel's mine time if a mine fell after ``time``."""
        if self.mine_time is not None and self.mine_time > time:
            return self.mine_time
        return None

    def record(self, event: _PanelEvent) -> None:
        self.last_event = event
        if not event.is_tail:
            self.last_press = event
            self.mine_time = None


class _TechDetector:
    """Walks a decoded path once, appending a span for each pattern it finds."""

    def __init__(self) -> None:
        self.spans: list[PatternSpan] = []
        self.columns = {panel: _ColumnHistory() for panel in PANELS}
        self.press_rows = 0
        self.any_mine_time = -math.inf
        self.prev_press: ResolvedStep | None = None
        # Each foot's previous press, for candles (the other foot's presses in
        # between don't matter).
        self.foot_press: dict[Foot, ResolvedStep] = {}
        # Orientation of the current crossed stance, or None while uncrossed.
        self.crossed_orientation: PlayerOrientation | None = None

    def feed(self, step: ResolvedStep) -> None:
        self._record_mines(step)

        epoch_before = self.press_rows
        if step.foot_row.moved != FootMove.NONE:
            self.press_rows += 1
            self._brackets(step)
            self._candles(step)
            self._doublestep(step)
            self._crossover(step)
            self.prev_press = step

        self._jacks_and_switches(step, epoch_before)

    def _record_mines(self, step: ResolvedStep) -> None:
        now = step.note_row.timestamp
        for panel in step.note_row.mines:
            self.columns[panel].mine_time = now
            self.any_mine_time = now

    def _brackets(self, step: ResolvedStep) -> None:
        """One foot presses two panels."""
        fr = step.foot_row
        for mover in fr.moved.feet:
            if len(fr.stance.placement(mover).panels & step.note_row.pressed) >= 2:
                self.spans.append(_span(PatternKind.BRACKET, (step,)))

    def _candles(self, step: ResolvedStep) -> None:
        """A foot's press lands opposite its own previous press."""
        fr = step.foot_row
        for mover in fr.moved.feet:
            before = self.foot_press.get(mover)
            if before is not None and _crosses_center(
                before.foot_row.stance.placement(mover), fr.stance.placement(mover)
            ):
                self.spans.append(_span(PatternKind.CANDLE, (before, step)))
            self.foot_press[mover] = step

    def _doublestep(self, step: ResolvedStep) -> None:
        """The same foot presses two different single panels in a row.

        A hold released by the other foot in between does not excuse it: that
        foot was free, but the same foot still took both steps. A holdswitch is
        therefore a doublestep as well.
        """
        prev = self.prev_press
        moved = step.foot_row.moved
        press = _single_press(step)
        if (
            prev is not None
            and len(moved.feet) == 1
            and prev.foot_row.moved == moved
            and press
            and _single_press(prev) not in (Panel.NONE, press)
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

    def _jacks_and_switches(self, step: ResolvedStep, epoch_before: int) -> None:
        """Compare each press with its panel's history, then record this row's events."""
        row = step.note_row
        for panel in PANELS:
            foot = column_foot(step, panel)
            if foot is None:
                continue
            is_press = panel in row.pressed
            if is_press:
                self._jack_or_switch(step, panel, foot, epoch_before)
            self.columns[panel].record(
                _PanelEvent(step, foot, row.timestamp, self.press_rows, is_tail=not is_press)
            )

    def _jack_or_switch(
        self, step: ResolvedStep, panel: Panel, foot: Foot, epoch_before: int
    ) -> None:
        """Pair this press with the panel's event on the previous press row."""
        history = self.columns[panel]
        prior_press = history.press_before(epoch_before)
        if prior_press is not None and prior_press.foot == foot:
            self._jack(step, panel, prior_press)
            return
        prior_event = history.event_before(epoch_before)
        if prior_event is not None and prior_event.foot != foot:
            self._switch(step, panel, prior_event)

    def _jack(self, step: ResolvedStep, panel: Panel, prior: _PanelEvent) -> None:
        """Same foot, same panel, fast enough. A mine in between resets the clock."""
        mine_time = self.columns[panel].mine_after(prior.time)
        since = prior.time if mine_time is None else mine_time
        if step.note_row.timestamp - since < ITG_JACK_CUTOFF_SEC:
            self.spans.append(_span(PatternKind.JACK, (prior.step, step)))

    def _switch(self, step: ResolvedStep, panel: Panel, prior: _PanelEvent) -> None:
        """The other foot takes over the panel fast enough. A mine in between resets the clock."""
        kind = PatternKind.SIDESWITCH if panel in _SIDE_PANELS else PatternKind.FOOTSWITCH
        mine_time = self.columns[panel].mine_after(prior.time)
        since = prior.time if mine_time is None else mine_time
        # A switch after a hold release (holdswitch) needs a mine cue, on any panel.
        cued = not prior.is_tail or self.any_mine_time > prior.time
        if cued and step.note_row.timestamp - since < ITG_FOOTSWITCH_CUTOFF_SEC:
            self.spans.append(_span(kind, (prior.step, step)))


def detect_tech_patterns(steps: Sequence[ResolvedStep]) -> TechMetrics:
    """Label jacks, foot/side switches, doublesteps, brackets, crossovers, and candles."""
    detector = _TechDetector()
    for step in steps:
        detector.feed(step)
    spans = sorted(detector.spans, key=lambda s: (s.start_beat, s.end_beat))
    return TechMetrics(spans=spans)
