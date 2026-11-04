"""Grace windows before hold/roll tails, during which the owning foot may leave.

These are anchoring physics (how long a hold survives without a foot on it),
not tech-pattern timing cutoffs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from patternity.footing.transitions import held_panels
from patternity.simfile.notes import ANCHORED_NOTES, PANELS, NoteRow, NoteType, Panel

# StepMania / ITG hold and roll life windows.
HOLD_GRACE_SEC = 0.32
ROLL_GRACE_SEC = 0.35

Remaining = tuple[float | None, float | None, float | None, float | None]


@dataclass(frozen=True)
class GraceWindow:
    """Grace state of one row.

    ``panels``: held panels whose tail is within the grace window.
    ``remaining``: seconds left to each such panel's tail, by column (``None`` elsewhere).
    """

    panels: Panel = Panel.NONE
    remaining: Remaining = (None, None, None, None)


def hold_grace(rows: Sequence[NoteRow]) -> list[GraceWindow]:
    """The grace window of each row."""
    next_tail: list[float | None] = [None] * 4
    out: list[GraceWindow] = []
    for row in reversed(rows):
        for col, note in enumerate(row.notes):
            if note == NoteType.TAIL:
                next_tail[col] = row.timestamp

        releasable = Panel.NONE
        remaining: list[float | None] = [None] * 4
        held = held_panels(row)
        for col, panel in enumerate(PANELS):
            tail, now = next_tail[col], row.timestamp
            if panel not in held or tail is None or now is None:
                continue
            window = ROLL_GRACE_SEC if panel in row.rolls_active else HOLD_GRACE_SEC
            if 0.0 <= tail - now <= window:
                releasable |= panel
                remaining[col] = tail - now
        out.append(
            GraceWindow(releasable, (remaining[0], remaining[1], remaining[2], remaining[3]))
        )

        for col, note in enumerate(row.notes):
            if note in ANCHORED_NOTES:
                next_tail[col] = None
    out.reverse()
    return out
