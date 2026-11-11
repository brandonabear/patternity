"""Characterization snapshots: what the code outputs today for every fixture chart.

These catch unintended changes; they are not ground truth (that is
``fixtures/canonical/``, which is hand-counted). Two sets, so a retrain shows up
as one reviewable diff:

- ``snapshots/notation/``: parsing and basic metrics. Independent of the weights.
- ``snapshots/footing/``: decoded feet, tech and movement metrics. These change
  whenever the weights, features, rules or detector change.

After an intended change, rewrite them and review the diff:

    uv run pytest tests/integration/test_snapshots.py --update-snapshots
"""

import hashlib
import json
from collections.abc import Callable
from itertools import groupby
from pathlib import Path
from typing import Any

import pytest

from patternity import StepmaniaFileParser, read_simfile, resolve_chart
from patternity.analysis import count_basic
from patternity.footing import ResolvedStep
from patternity.footing.stance import FootMove
from patternity.movement import detect_movement
from patternity.patterns import detect_tech_patterns
from patternity.simfile import Chart

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SNAPSHOTS = FIXTURES / "snapshots"

# The annotation template has no steps worth pinning.
_EXCLUDED = {"patterns/template.sm"}
_FIXTURES = sorted(
    relpath
    for directory in ("charts", "patterns")
    for path in (FIXTURES / directory).iterdir()
    if path.suffix in {".sm", ".ssc"} and (relpath := f"{directory}/{path.name}") not in _EXCLUDED
)

_MOVE_CHARS = {FootMove.NONE: "-", FootMove.LEFT: "L", FootMove.RIGHT: "R", FootMove.BOTH: "B"}


def _moves_by_measure(steps: list[ResolvedStep]) -> list[str]:
    """The feet that moved on each row, one line per measure (``"12: LRLR-B"``).

    ``-`` is a row with no press (a mine or a tail). One line per measure keeps
    a changed row easy to find in a diff.
    """
    return [
        f"{measure}: " + "".join(_MOVE_CHARS[step.foot_row.moved] for step in rows)
        for measure, rows in groupby(steps, key=lambda step: step.note_row.measure)
    ]


def _label(chart: Chart) -> dict[str, Any]:
    return {"difficulty": chart.metadata.difficulty.value, "rating": chart.metadata.rating}


def _rows_digest(chart: Chart) -> str:
    """Fingerprint of every parsed row (notes, position, time, active holds).

    A digest can't say what changed, only that something did; the readable
    fields beside it narrow it down.
    """
    rows = [{**row.to_dict(), "timestamp": round(row.timestamp, 6)} for row in chart.notes]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]


def _notation(chart: Chart) -> dict[str, Any]:
    last = chart.notes[-1] if chart.notes else None
    return {
        **_label(chart),
        "rows": len(chart.notes),
        "last_beat": last.beat if last else None,
        "last_timestamp": round(last.timestamp, 6) if last else None,
        "rows_digest": _rows_digest(chart),
        "basic": count_basic(chart.notes).to_dict(),
    }


def _footing(chart: Chart) -> dict[str, Any]:
    resolved = resolve_chart(chart.notes, with_confidence=False)
    movement = detect_movement(resolved).to_dict()
    # Rounded so the snapshot doesn't depend on float summation noise.
    movement["total_cost"] = round(movement["total_cost"], 6)
    return {
        **_label(chart),
        "tech": detect_tech_patterns(resolved.steps).to_dict(),
        "movement": movement,
        "moved": _moves_by_measure(resolved.steps),
    }


def _check(
    kind: str, relpath: str, describe: Callable[[Chart], dict[str, Any]], update: bool
) -> None:
    song = StepmaniaFileParser.parse(read_simfile(FIXTURES / relpath))
    actual = {"fixture": relpath, "charts": [describe(chart) for chart in song.charts]}
    path = SNAPSHOTS / kind / (Path(relpath).stem + ".json")

    if update:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
        return

    assert path.is_file(), f"no snapshot for {relpath}; run with --update-snapshots"
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected, f"{relpath} changed; if intended, rerun with --update-snapshots"


@pytest.mark.regression
@pytest.mark.parametrize("relpath", _FIXTURES)
def test_notation_snapshot(relpath: str, update_snapshots: bool) -> None:
    _check("notation", relpath, _notation, update_snapshots)


@pytest.mark.regression
@pytest.mark.parametrize("relpath", _FIXTURES)
def test_footing_snapshot(relpath: str, update_snapshots: bool) -> None:
    _check("footing", relpath, _footing, update_snapshots)


def test_every_snapshot_belongs_to_a_fixture() -> None:
    stems = {Path(relpath).stem for relpath in _FIXTURES}
    stale = sorted(
        str(path.relative_to(SNAPSHOTS))
        for path in SNAPSHOTS.glob("*/*.json")
        if path.stem not in stems
    )
    assert not stale, f"snapshots without a fixture: {stale}"
