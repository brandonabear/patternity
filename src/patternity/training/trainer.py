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
from patternity.footing.search import Trellis, build_trellis, path_features, viterbi
from patternity.footing.stance import FootMove
from patternity.simfile.reader import read_simfile
from patternity.training.annotations import AnnotatedChart, parse_annotated_sm

# Physically these can only add effort; with little data the perceptron could
# otherwise learn to reward them.
NONNEGATIVE: frozenset[str] = frozenset(
    {
        "travel",
        "travel_speed",
        "inverted",
        "facing_flip",
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
    annotated = parse_annotated_sm(read_simfile(path))
    return Example(
        name=name or path.name,
        annotated=annotated,
        trellis=build_trellis(annotated.chart.notes),
    )


def load_examples(relpaths: Sequence[str], root: Path) -> list[Example]:
    """Load fixtures named relative to ``root`` (usually ``tests/fixtures``)."""
    return [load_example(root / rel, rel) for rel in relpaths]


def _project(weights: list[float]) -> None:
    for name in NONNEGATIVE:
        i = FEATURE_INDEX[name]
        weights[i] = max(weights[i], 0.0)


def row_errors(example: Example, weights: Sequence[float]) -> int:
    decoded = viterbi(example.trellis, weights)
    states = decoded.states(example.trellis)
    return sum(1 for i, move in example.gold.items() if states[i].moved != move)


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
    n = len(FEATURE_NAMES)
    weights = [0.0] * n
    total = [0.0] * n
    steps = 0
    order = list(examples)
    rng = random.Random(seed)
    # Scale each chart's update by its size so one long chart cannot drown out
    # the short pattern fixtures.
    mean_rows = sum(len(e.gold) for e in examples) / max(len(examples), 1)
    scale = {id(e): mean_rows / max(len(e.gold), 1) for e in examples}

    for _ in range(epochs):
        rng.shuffle(order)
        mistakes = 0
        for example in order:
            gold = example.gold
            predicted = viterbi(example.trellis, weights, loss=gold, margin=margin)
            pred_states = predicted.states(example.trellis)
            if any(pred_states[i].moved != move for i, move in gold.items()):
                mistakes += 1
                target = viterbi(example.trellis, weights, allowed=gold)
                phi_gold = path_features(example.trellis, target)
                phi_pred = path_features(example.trellis, predicted)
                step = learning_rate * scale[id(example)]
                for i in range(n):
                    weights[i] -= step * (phi_gold[i] - phi_pred[i])
                _project(weights)
            for i in range(n):
                total[i] += weights[i]
            steps += 1
        if mistakes == 0:
            break
    converged = mistakes == 0

    averaged = [t / max(steps, 1) for t in total]
    return FootingModel.from_vector(
        weights if converged else averaged,
        metadata={
            "trainer": "structured-perceptron"
            if converged
            else "averaged-structured-perceptron",
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
