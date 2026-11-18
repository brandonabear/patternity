"""Grace windows before hold/roll tails, during which the owning foot may leave.

These are game mechanics (how long a hold survives without a foot on it),
not arbitrary tech-pattern timing cutoffs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from patternity.simfile.notes import ANCHORED_NOTES, PANELS, NoteRow, NoteType, Panel

# StepMania / ITG hold and roll life windows.
HOLD_GRACE_SEC = 0.32
ROLL_GRACE_SEC = 0.35

# Per column: the share of its grace window left before the tail (``None`` outside one).
GraceLeft = tuple[float | None, ...]
NO_GRACE: GraceLeft = (None, None, None, None)


@dataclass(frozen=True)
class GraceWindow:
    """Grace state of one row.

    ``panels``: held panels whose tail is within the grace window.
    ``left``: for each such panel, time to its tail as a share of its window, by column.
    """

    panels: Panel = Panel.NONE
    left: GraceLeft = NO_GRACE


def hold_grace(rows: Sequence[NoteRow]) -> list[GraceWindow]:
    """The grace window of each row."""
    next_tail: list[float | None] = [None] * 4
    out: list[GraceWindow] = []

    for row in reversed(rows):
        for col, note in enumerate(row.notes):
            if note == NoteType.TAIL:
                next_tail[col] = row.timestamp

        releasable = Panel.NONE
        left: list[float | None] = [None] * 4
        held = row.held

        for col, panel in enumerate(PANELS):
            tail, now = next_tail[col], row.timestamp

            # Skip non hold-related panel state
            if panel not in held or tail is None:
                continue

            window = ROLL_GRACE_SEC if panel in row.rolls_active else HOLD_GRACE_SEC
            if 0.0 <= tail - now <= window:
                releasable |= panel
                left[col] = (tail - now) / window

        out.append(GraceWindow(releasable, tuple(left)))

        for col, note in enumerate(row.notes):
            if note in ANCHORED_NOTES:
                next_tail[col] = None

    out.reverse()
    return out
