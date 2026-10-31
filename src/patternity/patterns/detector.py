from patternity.models.metric import TechMetrics
from patternity.models.pattern import PatternKind, PatternSpan
from patternity.models.stance import FootMove, FootPlacement, PlayerOrientation
from patternity.solver import ResolvedStep

# Column masks for distinguishing Up/Down footswitches from Left/Right sideswitches
_UD_MASK = FootPlacement.D.mask | FootPlacement.U.mask  # 0b0110
_LR_MASK = FootPlacement.L.mask | FootPlacement.R.mask  # 0b1001


def _moving_placement(step: ResolvedStep) -> FootPlacement | None:
    """Return the placement of the single foot that moved, or None if jump/none."""
    moved = step.foot_row.moved
    if moved == FootMove.LEFT:
        return step.foot_row.stance.left
    if moved == FootMove.RIGHT:
        return step.foot_row.stance.right
    return None


def _detect_point_patterns(
    active_steps: list[ResolvedStep],
    *,
    max_jack_dt: float = 0.25,
    max_doublestep_dt: float = 0.35,
) -> list[PatternSpan]:
    """Detect single-row and 2-row transition patterns (brackets, jacks, doublesteps, switches)."""
    spans: list[PatternSpan] = []

    for i, curr in enumerate(active_steps):
        curr_nr = curr.note_row
        curr_fr = curr.foot_row
        beat = curr_nr.beat or 0.0
        measure = curr_nr.measure or 0

        left_bracketed = (
            bool(curr_fr.moved & FootMove.LEFT) and curr_fr.stance.left.is_bracket
        )
        right_bracketed = (
            bool(curr_fr.moved & FootMove.RIGHT) and curr_fr.stance.right.is_bracket
        )
        if left_bracketed or right_bracketed:
            spans.append(
                PatternSpan(
                    kind=PatternKind.BRACKET,
                    start_beat=beat,
                    end_beat=beat,
                    start_measure=measure,
                    end_measure=measure,
                    steps=(curr,),
                )
            )

        if i == 0:
            continue

        prev = active_steps[i - 1]
        prev_nr = prev.note_row
        prev_fr = prev.foot_row

        prev_p = _moving_placement(prev)
        curr_p = _moving_placement(curr)
        if prev_p is None or curr_p is None:
            continue

        dt = (curr_nr.timestamp or 0.0) - (prev_nr.timestamp or 0.0)
        p_beat = prev_nr.beat or 0.0
        p_measure = prev_nr.measure or 0

        if prev_fr.moved == curr_fr.moved:
            if prev_p == curr_p and dt <= max_jack_dt:
                spans.append(
                    PatternSpan(
                        kind=PatternKind.JACK,
                        start_beat=p_beat,
                        end_beat=beat,
                        start_measure=p_measure,
                        end_measure=measure,
                        steps=(prev, curr),
                    )
                )
            elif prev_p != curr_p and dt <= max_doublestep_dt:
                spans.append(
                    PatternSpan(
                        kind=PatternKind.DOUBLESTEP,
                        start_beat=p_beat,
                        end_beat=beat,
                        start_measure=p_measure,
                        end_measure=measure,
                        steps=(prev, curr),
                    )
                )
        else:
            shared_mask = prev_p.mask & curr_p.mask
            if shared_mask and dt <= max_doublestep_dt:
                kind = (
                    PatternKind.SIDESWITCH
                    if (shared_mask & _LR_MASK)
                    else PatternKind.FOOTSWITCH
                )
                spans.append(
                    PatternSpan(
                        kind=kind,
                        start_beat=p_beat,
                        end_beat=beat,
                        start_measure=p_measure,
                        end_measure=measure,
                        steps=(prev, curr),
                    )
                )

    return spans


def _detect_crossover_spans(active_steps: list[ResolvedStep]) -> list[PatternSpan]:
    """Group contiguous non-neutral orientations with centerline cross into crossover spans."""
    spans: list[PatternSpan] = []
    n = len(active_steps)
    i = 0

    while i < n:
        ori = active_steps[i].foot_row.stance.orientation
        if ori == PlayerOrientation.NEUTRAL:
            i += 1
            continue

        run_start = i
        has_crossed = False
        while i < n and active_steps[i].foot_row.stance.orientation == ori:
            if active_steps[i].foot_row.stance.is_crossed:
                has_crossed = True
            i += 1

        if has_crossed:
            span_start = max(0, run_start - 1)
            span_end = min(n - 1, i)
            phrase_steps = tuple(active_steps[span_start : span_end + 1])

            kind = (
                PatternKind.INVERTED_CROSSOVER
                if ori == PlayerOrientation.INVERTED
                else PatternKind.CROSSOVER
            )
            spans.append(
                PatternSpan(
                    kind=kind,
                    start_beat=phrase_steps[0].note_row.beat or 0.0,
                    end_beat=phrase_steps[-1].note_row.beat or 0.0,
                    start_measure=phrase_steps[0].note_row.measure or 0,
                    end_measure=phrase_steps[-1].note_row.measure or 0,
                    steps=phrase_steps,
                )
            )

    return spans


def detect_tech_patterns(steps: list[ResolvedStep]) -> TechMetrics:
    """Run pattern detectors on a resolved foot path; returns spans inside TechMetrics."""
    active_steps = [s for s in steps if s.foot_row.moved != FootMove.NONE]
    if not active_steps:
        return TechMetrics()

    spans = _detect_point_patterns(active_steps)
    spans.extend(_detect_crossover_spans(active_steps))
    spans.sort(key=lambda s: (s.start_beat, s.end_beat))
    return TechMetrics(spans=spans)
