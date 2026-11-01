from pathlib import Path

import pytest

from patternity import Analyzer, StepmaniaFileParser, read_simfile

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.mark.regression
def test_movement_turns_equals_tech_crossovers() -> None:
    path = FIXTURES / "patterns" / "sideswitches.sm"
    song = StepmaniaFileParser.parse(read_simfile(path))
    result = Analyzer(song.charts[0]).analyze()
    assert result["movement"]["turns"] == result["tech"]["crossovers"]
