"""Exact search over legal foot states: trellis construction, Viterbi, and per-row confidence.

The trellis enumerates every reachable ``FootRow`` per chart row (no beam) and
stores each edge's feature vector, so it is independent of the weights and can
be decoded many times (as training does).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from patternity.footing.features import (
    FEATURE_INDEX,
    FEATURE_NAMES,
    featurize,
    hits_mine,
)
from patternity.footing.stance import FootMove, FootRow
from patternity.footing.transitions import iter_legal_transitions
from patternity.simfile.notes import NoteRow

RELAXED_PENALTY = 1000.0


FeatureVector = tuple[tuple[int, float], ...]


@dataclass(slots=True)
class Layer:
    """States reachable at one chart row plus edges from the previous layer."""

    states: list[FootRow] = field(default_factory=list)
    prev_idx: list[int] = field(default_factory=list)
    next_idx: list[int] = field(default_factory=list)
    feat_ids: list[int] = field(default_factory=list)
    penalty: list[float] = field(default_factory=list)
    _index: dict[FootRow, int] = field(default_factory=dict)

    def add_edge(self, prev_i: int, curr: FootRow, feat_id: int, penalty: float) -> None:
        state_i = self._index.get(curr)
        if state_i is None:
            state_i = len(self.states)
            self.states.append(curr)
            self._index[curr] = state_i
        self.prev_idx.append(prev_i)
        self.next_idx.append(state_i)
        self.feat_ids.append(feat_id)
        self.penalty.append(penalty)


@dataclass(slots=True)
class Trellis:
    """Weight-independent search graph; build once per chart, decode many times."""

    rows: list[NoteRow]
    layers: list[Layer]
    feature_table: list[FeatureVector]
    relaxed_rows: list[int]


def build_trellis(rows: Sequence[NoteRow], *, allow_brackets: bool = True) -> Trellis:
    """Enumerate every reachable state per row (no beam) with edge features."""
    table: list[FeatureVector] = []
    table_index: dict[FeatureVector, int] = {}

    def intern(feats: dict[str, float]) -> int:
        vec = tuple(sorted((FEATURE_INDEX[k], round(v, 9)) for k, v in feats.items()))
        idx = table_index.get(vec)
        if idx is None:
            idx = len(table)
            table.append(vec)
            table_index[vec] = idx
        return idx

    layers: list[Layer] = []
    relaxed: list[int] = []
    states = [FootRow.initial()]
    last_press_time: float | None = None

    for row_index, row in enumerate(rows):
        now = row.timestamp or 0.0
        dt = (
            now - last_press_time
            if row.press_mask and last_press_time is not None
            else None
        )
        layer = Layer()
        blocked: list[tuple[int, FootRow, int]] = []
        check_mines = bool(row.mine_mask and row.press_mask)
        for prev_i, prev in enumerate(states):
            for curr in iter_legal_transitions(
                prev, row, allow_brackets=allow_brackets
            ):
                feat_id = intern(featurize(prev, curr, row, dt))
                if check_mines and hits_mine(curr, row.mine_mask):
                    blocked.append((prev_i, curr, feat_id))
                    continue
                layer.add_edge(prev_i, curr, feat_id, 0.0)

        if not layer.prev_idx:
            relaxed.append(row_index)
            if blocked:
                for prev_i, curr, feat_id in blocked:
                    layer.add_edge(prev_i, curr, feat_id, RELAXED_PENALTY)
            else:
                empty = intern({})
                for prev_i, prev in enumerate(states):
                    stay = replace(
                        prev,
                        moved=FootMove.NONE,
                        mines_since_press=prev.mines_since_press | row.mine_mask,
                    )
                    layer.add_edge(prev_i, stay, empty, RELAXED_PENALTY)

        layers.append(layer)
        states = layer.states
        if row.press_mask:
            last_press_time = now

    return Trellis(rows=list(rows), layers=layers, feature_table=table, relaxed_rows=relaxed)


@dataclass(frozen=True, slots=True)
class Decoded:
    """One decoded path: chosen state and incoming edge per layer."""

    state_indices: tuple[int, ...]
    edge_indices: tuple[int, ...]
    cost: float
    relaxed_rows: tuple[int, ...] = ()

    def states(self, trellis: Trellis) -> list[FootRow]:
        return [
            trellis.layers[i].states[s] for i, s in enumerate(self.state_indices)
        ]


def _table_costs(trellis: Trellis, weights: Sequence[float]) -> list[float]:
    return [sum(weights[i] * v for i, v in vec) for vec in trellis.feature_table]


def viterbi(
    trellis: Trellis,
    weights: Sequence[float],
    *,
    allowed: Mapping[int, FootMove] | None = None,
    loss: Mapping[int, FootMove] | None = None,
    margin: float = 0.0,
) -> Decoded:
    """Minimum-cost path.

    ``allowed`` restricts rows to an annotated ``FootMove``; rows where that is
    impossible are left unconstrained and reported in ``relaxed_rows``.
    ``loss`` with ``margin`` lowers the cost of disagreeing with it (cost-augmented
    decoding for training).
    """
    table_cost = _table_costs(trellis, weights)
    prev_cost = [0.0]
    back: list[list[int]] = []
    relaxed: list[int] = []

    for i, layer in enumerate(trellis.layers):
        want = allowed.get(i) if allowed else None
        gold = loss.get(i) if loss else None
        states = layer.states
        while True:
            cost = [math.inf] * len(states)
            bp = [-1] * len(states)
            for k, p in enumerate(layer.prev_idx):
                base = prev_cost[p]
                if base == math.inf:
                    continue
                s = layer.next_idx[k]
                moved = states[s].moved
                if want is not None and moved != want:
                    continue
                c = base + table_cost[layer.feat_ids[k]] + layer.penalty[k]
                if gold is not None and moved != gold:
                    c -= margin
                if c < cost[s]:
                    cost[s] = c
                    bp[s] = k
            if want is None or any(c != math.inf for c in cost):
                break
            relaxed.append(i)
            want = None
        back.append(bp)
        prev_cost = cost

    if not trellis.layers:
        return Decoded((), (), 0.0)

    end = min(range(len(prev_cost)), key=prev_cost.__getitem__)
    total = prev_cost[end]
    state_indices: list[int] = []
    edge_indices: list[int] = []
    s = end
    for i in range(len(trellis.layers) - 1, -1, -1):
        k = back[i][s]
        state_indices.append(s)
        edge_indices.append(k)
        s = trellis.layers[i].prev_idx[k]
    state_indices.reverse()
    edge_indices.reverse()
    return Decoded(
        tuple(state_indices), tuple(edge_indices), total, tuple(relaxed)
    )


def path_features(trellis: Trellis, decoded: Decoded) -> list[float]:
    """Dense summed feature vector of a decoded path."""
    total = [0.0] * len(FEATURE_NAMES)
    for layer, k in zip(trellis.layers, decoded.edge_indices, strict=True):
        for i, v in trellis.feature_table[layer.feat_ids[k]]:
            total[i] += v
    return total


def row_confidence(trellis: Trellis, weights: Sequence[float]) -> list[float | None]:
    """Per-row margin between the best path and the best path using a different FootMove.

    Computed from forward/backward max-marginals. ``None`` for rows without a
    press, ``math.inf`` when only one ``FootMove`` is physically possible.
    """
    table_cost = _table_costs(trellis, weights)
    layers = trellis.layers
    forward: list[list[float]] = []
    prev_cost = [0.0]
    for layer in layers:
        cost = [math.inf] * len(layer.states)
        for k, p in enumerate(layer.prev_idx):
            c = prev_cost[p] + table_cost[layer.feat_ids[k]] + layer.penalty[k]
            s = layer.next_idx[k]
            cost[s] = min(cost[s], c)
        forward.append(cost)
        prev_cost = cost

    backward: list[list[float]] = [[] for _ in layers]
    if layers:
        backward[-1] = [0.0] * len(layers[-1].states)
    for i in range(len(layers) - 1, 0, -1):
        layer = layers[i]
        above = backward[i]
        cost = [math.inf] * len(layers[i - 1].states)
        for k, p in enumerate(layer.prev_idx):
            c = table_cost[layer.feat_ids[k]] + layer.penalty[k] + above[layer.next_idx[k]]
            cost[p] = min(cost[p], c)
        backward[i - 1] = cost

    result: list[float | None] = []
    for i, layer in enumerate(layers):
        if not trellis.rows[i].press_mask:
            result.append(None)
            continue
        best: dict[FootMove, float] = {}
        for s, state in enumerate(layer.states):
            total = forward[i][s] + backward[i][s]
            if total < best.get(state.moved, math.inf):
                best[state.moved] = total
        ranked = sorted(best.values())
        if len(ranked) < 2 or ranked[1] == math.inf:
            result.append(math.inf)
        else:
            result.append(ranked[1] - ranked[0])
    return result
