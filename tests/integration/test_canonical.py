import json
from pathlib import Path
from typing import Any

import pytest

from patternity import StepmaniaFileParser, analyze_chart, read_simfile

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CANONICAL_DIR = FIXTURES / "canonical"


def _load_canonical(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _analyze_fixture(
    canonical: dict[str, Any], chart_entry: dict[str, Any]
) -> dict[str, Any]:
    fixture_path = FIXTURES / canonical["fixture"]
    song = StepmaniaFileParser.parse(read_simfile(fixture_path))
    return analyze_chart(song.charts[chart_entry["chart_index"]]).to_dict()


def _metric_mismatches(
    actual: dict[str, Any],
    expected: dict[str, Any],
    *,
    label: str,
    tolerance: int = 0,
) -> list[str]:
    lines: list[str] = []
    for key, want in expected.items():
        if key not in actual:
            lines.append(f"{label}.{key}: expected {want}, got <missing>")
            continue
        got = actual[key]
        if abs(got - want) > tolerance:
            lines.append(f"{label}.{key}: expected {want} (±{tolerance}), got {got}")
    return lines


@pytest.mark.regression
@pytest.mark.parametrize(
    "canonical_path",
    sorted(CANONICAL_DIR.glob("*.json")),
    ids=lambda p: p.stem,
)
def test_canonical_fixture_analyzes(canonical_path: Path) -> None:
    """Every canonical file must point at a fixture that parses and analyzes."""
    canonical = _load_canonical(canonical_path)
    assert "fixture" in canonical
    for chart_entry in canonical["charts"]:
        result = _analyze_fixture(canonical, chart_entry)
        assert "basic" in result
        assert "tech" in result


@pytest.mark.regression
@pytest.mark.parametrize(
    "canonical_path",
    sorted(CANONICAL_DIR.glob("*.json")),
    ids=lambda p: p.stem,
)
def test_canonical_hand_counted_metrics(canonical_path: Path) -> None:
    """Assert basic/tech only when the file is marked validated (hand-counted)."""
    canonical = _load_canonical(canonical_path)
    if not canonical.get("validated"):
        pytest.skip(
            f"{canonical_path.name}: set validated=true after hand-counting "
            "(see tests/fixtures/canonical/README.md)"
        )
    for chart_entry in canonical["charts"]:
        result = _analyze_fixture(canonical, chart_entry)
        basic = chart_entry.get("basic")
        tech = chart_entry.get("tech")
        if basic is None or tech is None:
            pytest.fail(
                f"{canonical_path.name}: validated fixtures must include "
                "charts[].basic and charts[].tech"
            )
        mismatches: list[str] = []
        mismatches.extend(_metric_mismatches(result["basic"], basic, label="basic"))
        mismatches.extend(
            _metric_mismatches(
                result["tech"],
                tech,
                label="tech",
                tolerance=int(canonical.get("tech_tolerance", 0)),
            )
        )
        if mismatches:
            header = f"{canonical_path.name} chart_index={chart_entry['chart_index']}:"
            pytest.fail(header + "\n" + "\n".join(mismatches))
