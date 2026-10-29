from dataclasses import dataclass

from patternity.models.engine import NoteRow
from patternity.models.stance import FootMove, FootRow, PlayerOrientation
from patternity.models.transition import iter_legal_transitions


@dataclass(frozen=True, slots=True)
class CostWeights:
    """Tunable biomechanical penalty weights for Stage 5 transition scoring."""

    # Speed scaling reference: dt (seconds) at which repeat-foot penalties hit base value
    reference_dt: float = 0.15  # ~100 BPM 16ths / 200 BPM 8ths
    min_dt_clamp: float = 0.04  # Clamp to prevent division-by-zero on 0ms stops/warps

    # Same-foot repetition penalties (scaled by (reference_dt / dt) ** speed_exponent)
    jack_base: float = 6.0
    doublestep_base: float = 9.0
    speed_exponent: float = 1.5

    # Travel distance penalty per unit of Euclidean pad distance
    travel_distance: float = 0.5

    # Footswitch / overlap penalty (stepping onto the panel the other foot occupies)
    footswitch: float = 2.5

    # Bracket posture penalty (bridging two panels with one foot on a non-jump/non-chord)
    bracket_posture: float = 3.5

    # Body orientation & rotational momentum penalties
    crossover_entry: float = 2.5      # NEUTRAL -> FACING_LEFT / FACING_RIGHT
    crossover_sustain: float = 0.8    # Staying in FACING_LEFT / FACING_RIGHT
    hip_flip_180: float = 25.0        # FACING_LEFT <-> FACING_RIGHT without NEUTRAL
    inverted_stance: float = 35.0     # PlayerOrientation.INVERTED ("Dorito")

    # Engine coercion penalty
    mine_collision: float = 100.0


DEFAULT_WEIGHTS = CostWeights()


def _repeat_foot_penalty(
    dt: float, is_same_panel: bool, distance: float, weights: CostWeights
) -> float:
    """Calculate time-scaled penalty when the same foot actuates twice in a row."""
    clamped_dt = max(dt, weights.min_dt_clamp)
    speed_factor = (weights.reference_dt / clamped_dt) ** weights.speed_exponent
    base = weights.jack_base if is_same_panel else weights.doublestep_base
    return base * speed_factor + (distance * weights.travel_distance)


def _orientation_penalty(
    prev_ori: PlayerOrientation,
    curr_ori: PlayerOrientation,
    is_crossed: bool,
    weights: CostWeights,
) -> float:
    """Price hip rotation entry, sustain, 180-degree flips, and inverted twists."""
    if curr_ori == PlayerOrientation.NEUTRAL:
        return 0.0

    if curr_ori == PlayerOrientation.INVERTED:
        return weights.inverted_stance

    # curr_ori is FACING_LEFT or FACING_RIGHT
    # Scale down slightly if feet are aligned on U/D (not yet crossed over centerline)
    cross_multiplier = 1.0 if is_crossed else 0.5

    if prev_ori == PlayerOrientation.NEUTRAL:
        return weights.crossover_entry * cross_multiplier

    if prev_ori == curr_ori:
        # Smooth continuation of an existing crossover phrase
        return weights.crossover_sustain * cross_multiplier

    # prev_ori was the OPPOSITE side (FACING_LEFT <-> FACING_RIGHT) or INVERTED
    return weights.hip_flip_180


def score_transition(
    prev: FootRow,
    curr: FootRow,
    row: NoteRow,
    weights: CostWeights = DEFAULT_WEIGHTS,
) -> float:
    """Compute the biomechanical effort cost of transitioning from `prev` to `curr` at `row`."""
    cost = 0.0
    now = row.timestamp or 0.0

    # 1. Mine collision check: any foot covering a mine on this row takes a heavy penalty
    if row.mine_mask and (curr.stance.covered_mask & row.mine_mask):
        cost += weights.mine_collision

    # If no foot pressed a new note on this row (e.g., tail-only / mine-only row), we're done
    if curr.moved == FootMove.NONE:
        return cost

    # 2. Foot travel & same-foot repetition (Jacks vs. Double-Steps)
    # Only penalize single-foot consecutive moves when `prev` also moved (and wasn't a jump reset)
    if curr.moved & FootMove.LEFT:
        dist_l = prev.stance.left.distance_to(curr.stance.left)
        if prev.moved == FootMove.LEFT:
            dt_l = now - prev.left_time
            same_panel = prev.stance.left == curr.stance.left
            cost += _repeat_foot_penalty(dt_l, same_panel, dist_l, weights)
        else:
            cost += dist_l * weights.travel_distance

    if curr.moved & FootMove.RIGHT:
        dist_r = prev.stance.right.distance_to(curr.stance.right)
        if prev.moved == FootMove.RIGHT:
            dt_r = now - prev.right_time
            same_panel = prev.stance.right == curr.stance.right
            cost += _repeat_foot_penalty(dt_r, same_panel, dist_r, weights)
        else:
            cost += dist_r * weights.travel_distance

    # 3. Footswitch / Overlap cost (both feet end up sharing a panel)
    if curr.stance.is_overlapping:
        cost += weights.footswitch

    # 4. Bracket posture cost (using one foot to hit multiple panels)
    if curr.stance.left.is_bracket:
        cost += weights.bracket_posture
    if curr.stance.right.is_bracket:
        cost += weights.bracket_posture

    # 5. Body orientation / crossover momentum cost
    cost += _orientation_penalty(
        prev.stance.orientation,
        curr.stance.orientation,
        curr.stance.is_crossed,
        weights,
    )

    return cost

@dataclass(frozen=True, slots=True)
class ResolvedStep:
    """A single resolved row pairing the engine NoteRow with the chosen FootRow."""

    note_row: NoteRow
    foot_row: FootRow
    step_cost: float
    cumulative_cost: float


@dataclass(frozen=True, slots=True)
class ResolveResult:
    """Foot-path resolution output for one chart."""

    steps: list[ResolvedStep]
    used_fallback: bool


def resolve_chart(
    rows: list[NoteRow],
    *,
    weights: CostWeights = DEFAULT_WEIGHTS,
    beam_width: int | None = 16,
    allow_brackets: bool = True,
    allow_mid_hold_switches: bool = False,
) -> ResolveResult:
    """Find the globally minimum-cost sequence of `FootRow` states across `rows`."""
    if not rows:
        return ResolveResult(steps=[], used_fallback=False)

    # Each entry in `trellis[t]` maps `state_key -> (FootRow, cumulative_cost, step_cost, prev_state_key)`
    StateKey = tuple  # (Stance, FootMove)
    TrellisEntry = tuple[FootRow, float, float, StateKey | None]

    trellis: list[dict[StateKey, TrellisEntry]] = []
    used_fallback = False

    # Seed before row 0 with the neutral initial state
    init_node = FootRow.initial()
    current_beam: dict[StateKey, TrellisEntry] = {
        init_node.state_key: (init_node, 0.0, 0.0, None)
    }

    for row in rows:
        next_layer: dict[StateKey, TrellisEntry] = {}

        for prev_key, (prev_node, prev_cum_cost, _, _) in current_beam.items():
            for cand_node in iter_legal_transitions(
                prev_node,
                row,
                allow_brackets=allow_brackets,
                allow_mid_hold_switches=allow_mid_hold_switches,
            ):
                edge_cost = score_transition(prev_node, cand_node, row, weights)
                total_cost = prev_cum_cost + edge_cost
                cand_key = cand_node.state_key

                existing = next_layer.get(cand_key)
                if existing is None or total_cost < existing[1]:
                    next_layer[cand_key] = (cand_node, total_cost, edge_cost, prev_key)

        if not next_layer:
            used_fallback = True
            for prev_key, (prev_node, prev_cum_cost, _, _) in current_beam.items():
                fallback = FootRow(
                    stance=prev_node.stance,
                    moved=FootMove.NONE,
                    left_time=prev_node.left_time,
                    right_time=prev_node.right_time,
                )
                next_layer[fallback.state_key] = (
                    fallback,
                    prev_cum_cost,
                    0.0,
                    prev_key,
                )

        # Prune to top `beam_width` lowest-cost states if beam_width is set
        if beam_width is not None and len(next_layer) > beam_width:
            sorted_items = sorted(next_layer.items(), key=lambda kv: kv[1][1])
            next_layer = dict(sorted_items[:beam_width])

        trellis.append(next_layer)
        current_beam = next_layer

    # Backtrack from the lowest-cost state at the final row
    best_final_key = min(current_beam, key=lambda k: current_beam[k][1])
    resolved: list[ResolvedStep] = []
    curr_key: StateKey | None = best_final_key

    for row_idx in range(len(rows) - 1, -1, -1):
        assert curr_key is not None
        foot_row, cum_cost, step_cost, prev_key = trellis[row_idx][curr_key]
        resolved.append(
            ResolvedStep(
                note_row=rows[row_idx],
                foot_row=foot_row,
                step_cost=step_cost,
                cumulative_cost=cum_cost,
            )
        )
        curr_key = prev_key

    resolved.reverse()
    return ResolveResult(steps=resolved, used_fallback=used_fallback)
