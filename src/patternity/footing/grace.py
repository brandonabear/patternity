"""Grace windows before hold/roll tails, during which the owning foot may leave.

These are anchoring physics (how long a hold survives without a foot on it),
not tech-pattern timing cutoffs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from patternity.footing.transitions import anchored_mask
from patternity.simfile.notes import ANCHORED_NOTES, NoteRow, NoteType

# StepMania / ITG hold and roll life windows.
HOLD_GRACE_SEC = 0.32
ROLL_GRACE_SEC = 0.35

Remaining = tuple[float | None, float | None, float | None, float | None]


@dataclass(frozen=True)
class GraceWindow:
    """Grace state of one row.

    ``mask``: anchored columns whose tail is within the grace window.
    ``remaining``: seconds left to each such column's tail (``None`` elsewhere).
    """

    mask: int = 0
    remaining: Remaining = (None, None, None, None)


def hold_grace(rows: Sequence[NoteRow]) -> list[GraceWindow]:
    """The grace window of each row."""
    next_tail: list[float | None] = [None] * 4
    out: list[GraceWindow] = []
    for row in reversed(rows):
        for col, note in enumerate(row.panels):
            if note == NoteType.TAIL:
                next_tail[col] = row.timestamp

        mask = 0
        remaining: list[float | None] = [None] * 4
        anchored = anchored_mask(row)
        for col in range(4):
            bit = 1 << col
            tail, now = next_tail[col], row.timestamp
            if not anchored & bit or tail is None or now is None:
                continue
            window = ROLL_GRACE_SEC if row.roll_active_mask & bit else HOLD_GRACE_SEC
            if 0.0 <= tail - now <= window:
                mask |= bit
                remaining[col] = tail - now
        out.append(GraceWindow(mask, (remaining[0], remaining[1], remaining[2], remaining[3])))

        for col, note in enumerate(row.panels):
            if note in ANCHORED_NOTES:
                next_tail[col] = None
    out.reverse()
    return out
