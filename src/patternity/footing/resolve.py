"""Public footing API: decode the minimum-cost foot path for a chart."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from patternity.footing.model import FootingModel
from patternity.footing.search import Trellis, build_trellis, row_confidence, viterbi
from patternity.footing.stance import FootRow
from patternity.simfile.notes import NoteRow


@dataclass(frozen=True, slots=True)
class ResolvedStep:
    """One chart row paired with its decoded foot state."""

    index: int
    note_row: NoteRow
    foot_row: FootRow
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class FootingResult:
    steps: list[ResolvedStep]
    cost: float
    relaxed_rows: tuple[int, ...] = ()

    @property
    def feasible(self) -> bool:
        return not self.relaxed_rows


def resolve_chart(
    rows: Sequence[NoteRow],
    model: FootingModel | None = None,
    *,
    allow_brackets: bool = True,
    with_confidence: bool = True,
) -> FootingResult:
    """Decode the minimum-cost foot path for ``rows``."""
    trellis = build_trellis(rows, allow_brackets=allow_brackets)
    return resolve_trellis(trellis, model, with_confidence=with_confidence)


def resolve_trellis(
    trellis: Trellis,
    model: FootingModel | None = None,
    *,
    with_confidence: bool = True,
) -> FootingResult:
    """Decode the minimum-cost foot path through a trellis that is already built."""
    weights = (model or FootingModel.default()).vector()
    decoded = viterbi(trellis, weights)
    confidence: Sequence[float | None] = (
        row_confidence(trellis, weights) if with_confidence else [None] * len(trellis.rows)
    )
    steps = [
        ResolvedStep(index=i, note_row=row, foot_row=state, confidence=confidence[i])
        for i, (row, state) in enumerate(
            zip(trellis.rows, decoded.states(trellis), strict=True)
        )
    ]
    return FootingResult(
        steps=steps, cost=decoded.cost, relaxed_rows=tuple(trellis.relaxed_rows)
    )
