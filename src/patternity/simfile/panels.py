"""The four pad panels as a set-like flag.

``Panel`` is the one place the bit layout lives: each panel is one bit, in the
LDUR column order StepMania uses (Left = bit 0 ... Right = bit 3). Everywhere
else, treat a ``Panel`` value as a set of panels:

- ``Panel.U in pressed``: is Up pressed?
- ``Panel.L | Panel.U``: both panels.
- ``pressed in covered``: is every pressed panel covered? (subset)
- ``held & ~releasable``: held panels that are not releasable.
- ``len(pressed)``, ``for panel in pressed``: count and iterate.
"""

from __future__ import annotations

from enum import IntFlag


class Panel(IntFlag):
    """A set of pad panels (empty, one panel, or several)."""

    NONE = 0
    L = 1
    D = 2
    U = 4
    R = 8

    @classmethod
    def at(cls, col: int) -> Panel:
        """The single panel at column index ``col`` (0-3, LDUR order)."""
        return PANELS[col]

    @property
    def column(self) -> int:
        """Column index (0-3, LDUR order) of a single panel."""
        return PANELS.index(self)


# Single panels in column (LDUR) order; zip with per-column data such as
# ``NoteRow.notes``.
PANELS: tuple[Panel, ...] = (Panel.L, Panel.D, Panel.U, Panel.R)
