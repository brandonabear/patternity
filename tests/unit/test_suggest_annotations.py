import importlib.util
from pathlib import Path

from patternity.footing import FootingModel

_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "suggest_annotations", _ROOT / "scripts/suggest_annotations.py"
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
suggest_file = _mod.suggest_file

_MINI_CHART = """\
#VERSION:0.83;
#TITLE:Mini;
#BPMS:0.000=120.000;
#NOTEDATA:;
#STEPSTYPE:dance-single;
#DIFFICULTY:Challenge;
#METER:1;
#NOTES:
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


def test_suggest_adds_measure_markers_and_measure_on_tags(tmp_path: Path) -> None:
    path = tmp_path / "mini.ssc"
    path.write_text(_MINI_CHART, encoding="utf-8")
    count = suggest_file(path, FootingModel.default(), list_rows=10)
    text = path.read_text(encoding="utf-8")
    assert count == 2
    assert "// measure 0\n" in text
    assert ",  // measure 1" in text
    assert "0100 // @suggest=" in text
    assert "1000 // @suggest=" in text
    assert "measure 0 @suggest=" not in text
