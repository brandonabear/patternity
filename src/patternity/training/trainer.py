"""Learn footing weights from annotated charts with a structured perceptron.

Annotations give which foot moved on each row (``FootMove``), not full stances,
so the "gold" path is the best path consistent with the annotations under the
current weights (latent-variable perceptron). Training decodes are
cost-augmented: disagreeing with an annotation is made ``margin`` cheaper, so the
learned weights must beat it by at least that much.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from patternity.footing.features import FEATURE_INDEX, FEATURE_NAMES
from patternity.footing.model import FootingModel
from patternity.footing.search import (
    Decoded,
    Trellis,
    build_trellis,
    path_features,
    viterbi,
)
from patternity.footing.stance import FootMove
from patternity.simfile.reader import read_simfile
from patternity.training.annotations import (
    AnnotatedChart,
    AnnotationError,
    parse_annotated_sm,
)

# Physically these can only add effort; with little data the perceptron could
# otherwise learn to reward them.
NONNEGATIVE: frozenset[str] = frozenset(
    {
        "travel",
        "travel_speed",
        "inverted",
        "cross_entry",
        "repeat_change",
        "jack_speed_sq",
        "bracket_speed",
        "hold_release",
        "early_release",
    }
)


@dataclass
class Example:
    name: str
    annotated: AnnotatedChart
    trellis: Trellis

    @property
    def gold(self) -> dict[int, FootMove]:
        return self.annotated.tagged_assignments


def load_example(path: Path, name: str | None = None) -> Example:
    name = name or path.name
    annotated = parse_annotated_sm(read_simfile(path))
    trellis = build_trellis(annotated.chart.notes)
    _require_possible_annotations(name, annotated, trellis)
    return Example(name=name, annotated=annotated, trellis=trellis)


def _require_possible_annotations(name: str, annotated: AnnotatedChart, trellis: Trellis) -> None:
    """Raise if any tag can't be satisfied by a legal path.

    Such a row is a mistake on every epoch, so training would never converge
    and would quietly return averaged weights fitted to a bad label.
    """
    # Reachability doesn't depend on the weights, so zeros will do.
    no_weights = [0.0] * len(FEATURE_NAMES)
    impossible = viterbi(trellis, no_weights, allowed=annotated.tagged_assignments).relaxed_rows
    if impossible:
        lines = ", ".join(str(annotated.rows[i].line_number) for i in impossible)
        raise AnnotationError(f"{name}: physically impossible annotation on line(s) {lines}")


def load_examples(relpaths: Sequence[str], root: Path) -> list[Example]:
    """Load fixtures named relative to ``root`` (usually ``tests/fixtures``)."""
    return [load_example(root / rel, rel) for rel in relpaths]


def row_errors(example: Example, weights: Sequence[float]) -> int:
    return _disagreements(example, viterbi(example.trellis, weights))


def train(
    examples: Sequence[Example],
    *,
    epochs: int = 100,
    margin: float = 5.0,
    learning_rate: float = 1.0,
    seed: int = 0,
) -> FootingModel:
    """Fit weights so annotated paths decode as the minimum-cost paths.

    If an epoch passes with every chart decoded correctly at the required
    margin, those weights are returned as-is; averaging (which mixes in the
    early, worse weights) is only the fallback when annotations conflict.
    """
    weights = [0.0] * len(FEATURE_NAMES)
    history = _RunningMean(len(FEATURE_NAMES))
    order = _scaled_steps(examples, learning_rate)
    rng = random.Random(seed)

    for _ in range(epochs):
        rng.shuffle(order)
        mistakes = 0
        for example, step in order:
            if _perceptron_update(weights, example, margin, step):
                mistakes += 1
            history.add(weights)
        if mistakes == 0:
            return _model(weights, "structured-perceptron", examples, epochs, margin)

    return _model(history.mean(), "averaged-structured-perceptron", examples, epochs, margin)


class _RunningMean:
    """Mean of the weight vectors seen after each update (averaged perceptron)."""

    def __init__(self, size: int) -> None:
        self._total = [0.0] * size
        self._count = 0

    def add(self, weights: Sequence[float]) -> None:
        for i, w in enumerate(weights):
            self._total[i] += w
        self._count += 1

    def mean(self) -> list[float]:
        return [t / max(self._count, 1) for t in self._total]


def _scaled_steps(examples: Sequence[Example], learning_rate: float) -> list[tuple[Example, float]]:
    """Pair each chart with its update size, scaled inversely to its row count.

    Scaling keeps one long chart from drowning out the short pattern fixtures.
    """
    mean_rows = sum(len(e.gold) for e in examples) / max(len(examples), 1)
    return [(e, learning_rate * mean_rows / max(len(e.gold), 1)) for e in examples]


def _perceptron_update(weights: list[float], example: Example, margin: float, step: float) -> bool:
    """Decode ``example``; on a mistake, move ``weights`` toward the gold path.

    Returns whether a mistake (and so an update) occurred.
    """
    predicted = viterbi(example.trellis, weights, loss=example.gold, margin=margin)
    if not _disagreements(example, predicted):
        return False
    target = viterbi(example.trellis, weights, allowed=example.gold)
    phi_gold = path_features(example.trellis, target)
    phi_pred = path_features(example.trellis, predicted)
    for i, (gold, pred) in enumerate(zip(phi_gold, phi_pred, strict=True)):
        weights[i] -= step * (gold - pred)
    _project(weights)
    return True


def _disagreements(example: Example, decoded: Decoded) -> int:
    """Annotated rows where ``decoded`` moves a different foot than tagged."""
    states = decoded.states(example.trellis)
    return sum(1 for i, move in example.gold.items() if states[i].moved != move)


def _project(weights: list[float]) -> None:
    """Clamp features that can only add effort to be nonnegative."""
    for name in NONNEGATIVE:
        i = FEATURE_INDEX[name]
        weights[i] = max(weights[i], 0.0)


def _model(
    weights: list[float],
    trainer: str,
    examples: Sequence[Example],
    epochs: int,
    margin: float,
) -> FootingModel:
    return FootingModel.from_vector(
        weights,
        metadata={
            "trainer": trainer,
            "epochs": epochs,
            "margin": margin,
            "examples": [example.name for example in examples],
        },
    )


@dataclass(frozen=True)
class FoldResult:
    held_out: str
    rows: int
    errors: int

    @property
    def accuracy(self) -> float:
        return 1.0 - self.errors / self.rows if self.rows else 1.0


def leave_one_out(
    examples: Sequence[Example], *, epochs: int = 100, margin: float = 5.0
) -> list[FoldResult]:
    """Train on all charts but one and score per-row accuracy on the held-out chart."""
    results: list[FoldResult] = []
    for held in examples:
        rest = [e for e in examples if e is not held]
        model = train(rest, epochs=epochs, margin=margin)
        results.append(
            FoldResult(
                held_out=held.name,
                rows=len(held.gold),
                errors=row_errors(held, model.vector()),
            )
        )
    return results
