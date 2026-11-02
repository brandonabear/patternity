"""Tech pattern labels derived from a decoded foot path.

This is the only module that applies community / ITGMania timing cutoffs; the
footing decoder never sees them.
"""

import math
from collections.abc import Sequence

from patternity.analysis.metrics import TechMetrics
from patternity.footing.resolve import ResolvedStep
from patternity.footing.stance import FootMove, FootPlacement, PlayerOrientation
from patternity.patterns.spans import PatternKind, PatternSpan
from patternity.simfile.notes import NoteType

ITG_JACK_CUTOFF_SEC = 0.176
# Inclusive of 90 BPM 8ths (exactly 1/3 s apart).
ITG_FOOTSWITCH_CUTOFF_SEC = (1.0 / 3.0) + 1e-6

_LR_COLS = frozenset({0, 3})
_UD_COLS = frozenset({1, 2})
_PRESS = frozenset({NoteType.TAP, NoteType.HOLD, NoteType.ROLL, NoteType.LIFT})
_FEET = (FootMove.LEFT, FootMove.RIGHT)
_OPPOSITE_PANELS = (
    (FootPlacement.U.mask, FootPlacement.D.mask),
    (FootPlacement.L.mask, FootPlacement.R.mask),
)


def _crosses_center(before: FootPlacement, after: FootPlacement) -> bool:
    """The foot moved between opposite panels (U/D or L/R) without keeping one."""
    if before.shares_panel_with(after):
        return False
    return any(
        (before.mask & a and after.mask & b) or (before.mask & b and after.mask & a)
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


def column_foot(step: ResolvedStep, col: int) -> FootMove | None:
    """Foot acting on ``col``: the moving foot for a press, the hold owner for a tail."""
    note = (
        step.note_row.left,
        step.note_row.down,
        step.note_row.up,
        step.note_row.right,
    )[col]
    fr = step.foot_row
    bit = 1 << col
    if note in _PRESS:
        for foot in _FEET:
            if fr.moved & foot and fr.stance.placement(foot).mask & bit:
                return foot
        return None
    if note == NoteType.TAIL:
        return fr.hold_owner_for(col)
    return None


def _single_col(step: ResolvedStep) -> int | None:
    mask = step.note_row.press_mask
    return mask.bit_length() - 1 if mask.bit_count() == 1 else None


def detect_tech_patterns(steps: Sequence[ResolvedStep]) -> TechMetrics:
    """Label jacks, foot/side switches, doublesteps, brackets, crossovers, and candles."""
    spans: list[PatternSpan] = []

    last_foot: list[FootMove | None] = [None] * 4
    last_time = [-math.inf] * 4
    mine_time: list[float | None] = [None] * 4
    last_step: list[ResolvedStep | None] = [None] * 4
    from_tail = [False] * 4
    press_foot: list[FootMove | None] = [None] * 4
    press_time = [-math.inf] * 4
    press_step: list[ResolvedStep | None] = [None] * 4
    any_mine_time = -math.inf
    # Jacks and switches only pair a panel's event with the very next press
    # row; a revisit after other steps (e.g. D-U-D in a stream) is neither.
    press_rows = 0
    event_epoch = [-1] * 4
    press_epoch = [-1] * 4

    prev_press: ResolvedStep | None = None
    prev_row: ResolvedStep | None = None
    # Each foot's previous press, for candles (the other foot's presses in
    # between don't matter).
    foot_press: dict[FootMove, ResolvedStep] = {}
    # Orientation of the current crossed stance, or None while uncrossed. A new
    # crossover starts when the legs cross, or turn while staying crossed.
    crossed_orientation: PlayerOrientation | None = None

    for step in steps:
        row = step.note_row
        fr = step.foot_row
        now = row.timestamp or 0.0

        for col in range(4):
            if (1 << col) & row.mine_mask:
                mine_time[col] = now
                any_mine_time = now

        epoch_before = press_rows
        if fr.moved != FootMove.NONE:
            press_rows += 1
            for mover in _FEET:
                if not fr.moved & mover:
                    continue
                placement = fr.stance.placement(mover)
                if (placement.mask & row.press_mask).bit_count() >= 2:
                    spans.append(_span(PatternKind.BRACKET, (step,)))
                before = foot_press.get(mover)
                if before is not None and _crosses_center(
                    before.foot_row.stance.placement(mover), placement
                ):
                    spans.append(_span(PatternKind.CANDLE, (before, step)))
                foot_press[mover] = step

            press_col = _single_col(step)
            released = (
                prev_row.foot_row.released_since_press
                if prev_row is not None
                else FootMove.NONE
            )
            if (
                prev_press is not None
                and fr.moved in _FEET
                and prev_press.foot_row.moved == fr.moved
                and press_col is not None
                and _single_col(prev_press) not in (None, press_col)
                and not released & ~fr.moved
            ):
                spans.append(_span(PatternKind.DOUBLESTEP, (prev_press, step)))

            orientation = fr.stance.orientation if fr.stance.is_crossed else None
            if orientation is not None and orientation != crossed_orientation:
                kind = (
                    PatternKind.INVERTED_CROSSOVER
                    if orientation == PlayerOrientation.INVERTED
                    else PatternKind.CROSSOVER
                )
                entry = (step,) if prev_press is None else (prev_press, step)
                spans.append(_span(kind, entry))
            crossed_orientation = orientation
            prev_press = step

        for col in range(4):
            foot = column_foot(step, col)
            if foot is None:
                continue
            is_press = (
                row.left,
                row.down,
                row.up,
                row.right,
            )[col] in _PRESS
            col_mine = mine_time[col]

            if is_press:
                prior_press = press_step[col]
                prior_any = last_step[col]
                if press_epoch[col] != epoch_before:
                    prior_press = None
                if event_epoch[col] != epoch_before:
                    prior_any = None
                if prior_press is not None and press_foot[col] == foot:
                    ref_time = press_time[col]
                    if col_mine is not None and col_mine > ref_time:
                        ref_time = col_mine
                    if (
                        now - ref_time < ITG_JACK_CUTOFF_SEC
                        and not (1 << col) & row.mine_mask
                    ):
                        spans.append(_span(PatternKind.JACK, (prior_press, step)))
                elif prior_any is not None and last_foot[col] not in (None, foot):
                    ref_time = last_time[col]
                    used_mine_ref = col_mine is not None and col_mine > ref_time
                    if used_mine_ref:
                        ref_time = col_mine
                    # A switch after a hold release (holdswitch) needs a mine cue.
                    cued = not from_tail[col] or any_mine_time > last_time[col]
                    kind = (
                        PatternKind.SIDESWITCH
                        if col in _LR_COLS
                        else PatternKind.FOOTSWITCH
                    )
                    if (
                        cued
                        and now - ref_time < ITG_FOOTSWITCH_CUTOFF_SEC
                        and not (
                            kind == PatternKind.FOOTSWITCH
                            and used_mine_ref
                            and col in _UD_COLS
                        )
                    ):
                        spans.append(_span(kind, (prior_any, step)))
                press_foot[col] = foot
                press_time[col] = now
                press_step[col] = step
                press_epoch[col] = press_rows
                mine_time[col] = None

            event_epoch[col] = press_rows
            last_foot[col] = foot
            last_time[col] = now
            last_step[col] = step
            from_tail[col] = not is_press
        prev_row = step

    spans.sort(key=lambda s: (s.start_beat, s.end_beat))
    return TechMetrics(spans=spans)
