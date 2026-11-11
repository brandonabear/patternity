"""Exact search over legal foot states: trellis construction, Viterbi, and per-row confidence.

The trellis enumerates every reachable ``FootRow`` per chart row and stores each edge's
feature vector. Build once, decode many times (as training does).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from patternity.footing.features import FEATURE_INDEX, FEATURE_NAMES, featurize
from patternity.footing.grace import GraceWindow, hold_grace
from patternity.footing.rules import hits_mine
from patternity.footing.stance import FootMove, FootRow
from patternity.footing.transitions import iter_legal_transitions, stay_put
from patternity.simfile.notes import NoteRow

RELAXED_PENALTY = 1000.0


FeatureVector = tuple[tuple[int, float], ...]


@dataclass(slots=True)
class Layer:
    """States reachable at one chart row plus edges from the previous layer.

    Edges are stored as parallel lists, one entry per edge: edge ``k`` goes from
    state ``prev_idx[k]`` of the previous layer to state ``next_idx[k]`` of this
    one, and costs ``feature_table[feat_ids[k]]`` (weighted) plus ``penalty[k]``.
    ``add_edge`` adds each distinct ``FootRow`` to ``states`` only once.
    """

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


class _FeatureTable:
    """Distinct edge feature vectors, each stored once and referenced by index.

    Many edges share the same features, so a decode costs each vector once and
    looks edges up by index.
    """

    def __init__(self) -> None:
        self.vectors: list[FeatureVector] = []
        self._index: dict[FeatureVector, int] = {}

    def intern(self, feats: dict[str, float]) -> int:
        """Index of ``feats`` as a sparse vector, adding it if new.

        Values are rounded to 9 places so float noise doesn't create duplicates.
        """
        vec = tuple(sorted((FEATURE_INDEX[k], round(v, 9)) for k, v in feats.items()))
        idx = self._index.get(vec)
        if idx is None:
            idx = len(self.vectors)
            self.vectors.append(vec)
            self._index[vec] = idx
        return idx


# An edge held back because it steps on a mine: (prev state index, next state, feature id).
_Blocked = tuple[int, FootRow, int]


def _expand_layer(
    states: Sequence[FootRow],
    row: NoteRow,
    dt: float | None,
    grace: GraceWindow,
    features: _FeatureTable,
    allow_brackets: bool,
) -> tuple[Layer, list[_Blocked]]:
    """Every legal transition from each previous state to ``row``, as a layer of edges.

    Edges that step on a mine are returned separately rather than added: hitting a
    mine is avoidable, not impossible, so they're kept as a fallback.
    """
    layer = Layer()
    blocked: list[_Blocked] = []
    check_mines = bool(row.mines and row.pressed)
    for prev_i, prev in enumerate(states):
        for curr in iter_legal_transitions(
            prev, row, allow_brackets=allow_brackets, grace=grace.panels
        ):
            feat_id = features.intern(
                featurize(prev, curr, row, dt, grace_remaining=grace.remaining)
            )
            if check_mines and hits_mine(curr, row.mines):
                blocked.append((prev_i, curr, feat_id))
                continue
            layer.add_edge(prev_i, curr, feat_id, 0.0)
    return layer, blocked


def _add_relaxed_edges(
    layer: Layer,
    states: Sequence[FootRow],
    row: NoteRow,
    blocked: Sequence[_Blocked],
    grace: GraceWindow,
    features: _FeatureTable,
) -> None:
    """Give a row with no legal edge penalized edges so the path can continue.

    If the only moves stepped on a mine, allow them at ``RELAXED_PENALTY``.
    Otherwise nothing was physically possible (e.g. a malformed chart): every
    state stays put at the same penalty, carrying mines, hold owners and hold
    releases forward exactly as a no-press row would.
    """
    if blocked:
        for prev_i, curr, feat_id in blocked:
            layer.add_edge(prev_i, curr, feat_id, RELAXED_PENALTY)
        return

    empty = features.intern({})
    for prev_i, prev in enumerate(states):
        layer.add_edge(prev_i, stay_put(prev, row, grace.panels), empty, RELAXED_PENALTY)


def build_trellis(rows: Sequence[NoteRow], *, allow_brackets: bool = True) -> Trellis:
    """Enumerate every reachable state per row (no beam) with edge features."""
    features = _FeatureTable()
    grace_rows = hold_grace(rows)
    layers: list[Layer] = []
    relaxed: list[int] = []
    states = [FootRow.initial()]
    last_press_time: float | None = None

    for row_index, row in enumerate(rows):
        # Seconds since the previous press row (None on the first press or a no-press row).
        now = row.timestamp
        dt = now - last_press_time if row.pressed and last_press_time is not None else None

        layer, blocked = _expand_layer(
            states, row, dt, grace_rows[row_index], features, allow_brackets
        )
        if not layer.prev_idx:
            relaxed.append(row_index)
            _add_relaxed_edges(layer, states, row, blocked, grace_rows[row_index], features)

        layers.append(layer)
        states = layer.states
        if row.pressed:
            last_press_time = now

    return Trellis(
        rows=list(rows), layers=layers, feature_table=features.vectors, relaxed_rows=relaxed
    )


@dataclass(frozen=True, slots=True)
class Decoded:
    """One decoded path: chosen state and incoming edge per layer."""

    state_indices: tuple[int, ...]
    edge_indices: tuple[int, ...]
    cost: float
    relaxed_rows: tuple[int, ...] = ()

    def states(self, trellis: Trellis) -> list[FootRow]:
        return [trellis.layers[i].states[s] for i, s in enumerate(self.state_indices)]


def _table_costs(trellis: Trellis, weights: Sequence[float]) -> list[float]:
    return [sum(weights[i] * v for i, v in vec) for vec in trellis.feature_table]


@dataclass(frozen=True, slots=True)
class _Forward:
    """Result of a forward pass over the trellis.

    ``cost[i][s]`` is the cheapest cost from the start to state ``s`` of layer
    ``i`` (``inf`` if unreachable) and ``back[i][s]`` is the edge it arrived by.
    """

    cost: list[list[float]]
    back: list[list[int]]
    relaxed_rows: tuple[int, ...]


def _enter_layer(
    layer: Layer,
    prev_cost: Sequence[float],
    table_cost: Sequence[float],
    *,
    want: FootMove | None,
    gold: FootMove | None,
    margin: float,
) -> tuple[list[float], list[int]]:
    """Cheapest cost into each state of ``layer`` and the edge that achieves it.

    ``want`` keeps only states that moved that way. ``gold`` makes every other
    move ``margin`` cheaper (cost-augmented decoding), so the gold move has to
    win by at least ``margin``.
    """
    states = layer.states
    cost = [math.inf] * len(states)
    back = [-1] * len(states)
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
            back[s] = k
    return cost, back


def _forward(
    trellis: Trellis,
    table_cost: Sequence[float],
    *,
    allowed: Mapping[int, FootMove] | None = None,
    loss: Mapping[int, FootMove] | None = None,
    margin: float = 0.0,
) -> _Forward:
    """Cheapest cost to every state, layer by layer.

    A row whose ``allowed`` move is unreachable is redone unconstrained and
    reported in ``relaxed_rows``.
    """
    costs: list[list[float]] = []
    backs: list[list[int]] = []
    relaxed: list[int] = []
    prev_cost: list[float] = [0.0]

    for i, layer in enumerate(trellis.layers):
        want = allowed.get(i) if allowed else None
        gold = loss.get(i) if loss else None
        cost, back = _enter_layer(layer, prev_cost, table_cost, want=want, gold=gold, margin=margin)
        if want is not None and all(c == math.inf for c in cost):
            relaxed.append(i)
            cost, back = _enter_layer(
                layer, prev_cost, table_cost, want=None, gold=gold, margin=margin
            )
        costs.append(cost)
        backs.append(back)
        prev_cost = cost

    return _Forward(costs, backs, tuple(relaxed))


def _backtrace(trellis: Trellis, forward: _Forward) -> Decoded:
    """Follow back-pointers from the cheapest final state to the start."""
    if not trellis.layers:
        return Decoded((), (), 0.0)

    final_cost = forward.cost[-1]
    s = min(range(len(final_cost)), key=final_cost.__getitem__)
    total = final_cost[s]
    state_indices: list[int] = []
    edge_indices: list[int] = []
    for layer, back in zip(reversed(trellis.layers), reversed(forward.back), strict=True):
        k = back[s]
        state_indices.append(s)
        edge_indices.append(k)
        s = layer.prev_idx[k]
    state_indices.reverse()
    edge_indices.reverse()
    return Decoded(tuple(state_indices), tuple(edge_indices), total, forward.relaxed_rows)


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
    forward = _forward(trellis, table_cost, allowed=allowed, loss=loss, margin=margin)
    return _backtrace(trellis, forward)


def path_features(trellis: Trellis, decoded: Decoded) -> list[float]:
    """Dense summed feature vector of a decoded path."""
    total = [0.0] * len(FEATURE_NAMES)
    for layer, k in zip(trellis.layers, decoded.edge_indices, strict=True):
        for i, v in trellis.feature_table[layer.feat_ids[k]]:
            total[i] += v
    return total


def _backward(trellis: Trellis, table_cost: Sequence[float]) -> list[list[float]]:
    """``backward[i][s]``: cheapest cost from state ``s`` of layer ``i`` to the end."""
    layers = trellis.layers
    backward: list[list[float]] = [[] for _ in layers]
    if layers:
        backward[-1] = [0.0] * len(layers[-1].states)
    for i in range(len(layers) - 1, 0, -1):
        layer = layers[i]
        onward = backward[i]
        cost = [math.inf] * len(layers[i - 1].states)
        for k, p in enumerate(layer.prev_idx):
            c = table_cost[layer.feat_ids[k]] + layer.penalty[k] + onward[layer.next_idx[k]]
            cost[p] = min(cost[p], c)
        backward[i - 1] = cost
    return backward


def _foot_move_margin(layer: Layer, through: Sequence[float]) -> float:
    """Gap between the best path through ``layer`` and the best that moves other feet.

    ``through[s]`` is the cheapest full path via state ``s``. ``math.inf`` when
    only one ``FootMove`` is possible on the row.
    """
    best: dict[FootMove, float] = {}
    for state, total in zip(layer.states, through, strict=True):
        if total < best.get(state.moved, math.inf):
            best[state.moved] = total
    ranked = sorted(best.values())
    if len(ranked) < 2 or ranked[1] == math.inf:
        return math.inf
    return ranked[1] - ranked[0]


def row_confidence(trellis: Trellis, weights: Sequence[float]) -> list[float | None]:
    """Per-row margin between the best path and the best path using a different FootMove.

    Computed from forward/backward max-marginals. ``None`` for rows without a
    press, ``math.inf`` when only one ``FootMove`` is physically possible.
    """
    table_cost = _table_costs(trellis, weights)
    forward = _forward(trellis, table_cost).cost
    backward = _backward(trellis, table_cost)

    result: list[float | None] = []
    for row, layer, to_here, from_here in zip(
        trellis.rows, trellis.layers, forward, backward, strict=True
    ):
        if not row.pressed:
            result.append(None)
            continue
        through = [f + b for f, b in zip(to_here, from_here, strict=True)]
        result.append(_foot_move_margin(layer, through))
    return result
