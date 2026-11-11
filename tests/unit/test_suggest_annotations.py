import importlib.util
from pathlib import Path

import pytest

from patternity.footing import FootingModel, resolve_chart
from patternity.training.annotations import parse_annotated_sm

_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "suggest_annotations", _ROOT / "scripts/suggest_annotations.py"
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
suggest_file = _mod.suggest_file

_HEADER = """\
#VERSION:0.83;
#TITLE:Mini;
#BPMS:0.000=120.000;
#NOTEDATA:;
#STEPSTYPE:dance-single;
#DIFFICULTY:Challenge;
#METER:1;
#NOTES:
"""

_MINI_CHART = (
    _HEADER
    + """\
0000
0000
0100
0000
,
1000
0000
0000
0000
;
"""
)

_PATTERN_CHART = (
    _HEADER
    + """\
1000 // @pattern=jump
0001 // @suggest=R @margin=1.0
0001 // @pattern=candle
0100
,
1000
0010
0000
0000
;
"""
)


@pytest.fixture
def mock_console(mocker):
    return mocker.Mock()


def test_suggest_adds_measure_markers_and_measure_on_tags(mock_console, tmp_path: Path) -> None:
    path = tmp_path / "mini.ssc"
    path.write_text(_MINI_CHART, encoding="utf-8")
    assert suggest_file(mock_console, path, FootingModel.default(), list_rows=10) == (
        2,
        0,
    )
    text = path.read_text(encoding="utf-8")
    assert "// measure 0\n" in text
    assert ",  // measure 1" in text
    assert "0100 // @suggest_foot=" in text
    assert "1000 // @suggest_foot=" in text
    assert "measure 0 @suggest" not in text


def test_suggest_patterns_where_decoder_disagrees(mock_console, tmp_path: Path) -> None:
    path = tmp_path / "patterns.ssc"
    path.write_text(_PATTERN_CHART, encoding="utf-8")
    _feet, patterns = suggest_file(mock_console, path, FootingModel.default(), list_rows=10)
    lines = path.read_text(encoding="utf-8").splitlines()

    assert patterns > 0
    assert lines[9].startswith("1000 // @pattern=jump @suggest_foot=L")
    assert "@suggest_pattern" not in lines[9]
    assert "@suggest=" not in "\n".join(lines)
    assert "@suggest_foot=R" in lines[10]
    assert lines[11].startswith("0001 // @pattern=candle ")
    assert "@suggest_pattern=none" in lines[11]


def test_suggest_rerun_is_stable(mock_console, tmp_path: Path) -> None:
    path = tmp_path / "patterns.ssc"
    path.write_text(_PATTERN_CHART, encoding="utf-8")
    suggest_file(mock_console, path, FootingModel.default(), list_rows=0)
    once = path.read_text(encoding="utf-8")
    suggest_file(mock_console, path, FootingModel.default(), list_rows=0)
    assert path.read_text(encoding="utf-8") == once


def test_accepting_all_suggestions_by_find_replace(mock_console, tmp_path: Path) -> None:
    path = tmp_path / "patterns.ssc"
    path.write_text(_PATTERN_CHART.replace(" // @pattern=candle", ""), encoding="utf-8")
    model = FootingModel.default()
    suggest_file(mock_console, path, model, list_rows=0)
    suggested = parse_annotated_sm(path.read_text(encoding="utf-8"))
    assert not suggested.tagged_assignments

    accepted = parse_annotated_sm(path.read_text(encoding="utf-8").replace("@suggest_", "@"))
    steps = resolve_chart(accepted.chart.notes, model).steps
    assert accepted.tagged_assignments == {
        step.index: step.foot_row.moved for step in steps if step.note_row.pressed
    }
    assert any(row.patterns - {"jump"} for row in accepted.rows)
