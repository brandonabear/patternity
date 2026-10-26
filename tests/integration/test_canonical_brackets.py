import json
from pathlib import Path
from typing import Any

import pytest

from patternity.analyzer import Analyzer
from patternity.parser import StepmaniaFileParser
from patternity.reader import read_simfile

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CANONICAL = FIXTURES / "canonical" / "brackets.json"


def _load_canonical(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _analyze_fixture(canonical: dict[str, Any], chart_entry: dict[str, Any]) -> dict[str, Any]:
    fixture_path = FIXTURES / canonical["fixture"]
    analyzer_opts = canonical.get("analyzer", {})
    song = StepmaniaFileParser.parse(read_simfile(fixture_path))
    chart_index = chart_entry["chart_index"]
    analyzer = Analyzer(
        song.header,
        song.charts[chart_index],
        min_jack_nps=float(analyzer_opts.get("min_jack_nps", 5.7)),
    )
    return analyzer.analyze()


def _assert_metrics_subset(
    actual: dict[str, Any],
    expected: dict[str, Any],
    *,
    label: str,
) -> None:
    for key, want in expected.items():
        got = actual[key]
        assert got == want, f"{label}.{key}: expected {want}, got {got}"


@pytest.mark.regression
def test_brackets_fixture_matches_canonical() -> None:
    canonical = _load_canonical(CANONICAL)
    for chart_entry in canonical["charts"]:
        result = _analyze_fixture(canonical, chart_entry)
        _assert_metrics_subset(result["basic"], chart_entry["basic"], label="basic")
        _assert_metrics_subset(result["tech"], chart_entry["tech"], label="tech")
