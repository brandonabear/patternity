import pytest

from patternity.simfile import Difficulty, MissingTimingError
from patternity.simfile.parser import StepmaniaFileParser


def test_multiline_header_values_are_parsed() -> None:
    data = (
        "#TITLE:t;\n"
        "#BPMS:0.000=128.000\n,4.000=64.000\n;\n"
        "#NOTES:\n     dance-single:\n     t:\n     Challenge:\n     1:\n"
        "     0,0,0,0,0:\n1000\n0000\n0000\n0000\n,\n1000\n0000\n0000\n0000\n;\n"
    )
    song = StepmaniaFileParser.parse(data)
    assert song.header.bpms == {0.0: 128.0, 4.0: 64.0}
    second = song.charts[0].notes[1]
    assert second.timestamp is not None
    assert abs(second.timestamp - 4 * 60 / 128) < 1e-9


def _sm_chart(mode: str, difficulty: str, row: str) -> str:
    return (
        f"#NOTES:\n     {mode}:\n     t:\n     {difficulty}:\n     1:\n"
        f"     0,0,0,0,0:\n{row}\n,\n;\n"
    )


_HEADER = "#TITLE:t;\n#BPMS:0.000=120.000;\n"


def test_edit_difficulty_is_parsed() -> None:
    song = StepmaniaFileParser.parse(_HEADER + _sm_chart("dance-single", "Edit", "1000"))
    assert [chart.metadata.difficulty for chart in song.charts] == [Difficulty.EDIT]
    assert song.skipped_charts == []


@pytest.mark.parametrize(
    ("mode", "difficulty", "row", "reason"),
    [
        ("dance-double", "Hard", "10000000", "only dance-single"),
        ("dance-single", "Hard", "1K00", "unsupported note character"),
        ("dance-single", "Hard", "100", "expected 4 columns"),
        ("dance-single", "Impossible", "1000", "unknown difficulty"),
    ],
)
def test_unsupported_chart_is_skipped_without_losing_the_others(
    mode: str, difficulty: str, row: str, reason: str
) -> None:
    data = (
        _HEADER
        + _sm_chart(mode, difficulty, row)
        + _sm_chart("dance-single", "Challenge", "0100")
    )
    song = StepmaniaFileParser.parse(data)

    assert [chart.metadata.difficulty for chart in song.charts] == [Difficulty.CHALLENGE]
    (skipped,) = song.skipped_charts
    assert (skipped.mode, skipped.difficulty) == (mode, difficulty)
    assert reason in skipped.reason


def test_chart_without_bpms_raises() -> None:
    with pytest.raises(MissingTimingError):
        StepmaniaFileParser.parse("#TITLE:t;\n" + _sm_chart("dance-single", "Hard", "1000"))


def test_header_only_file_needs_no_bpms() -> None:
    assert StepmaniaFileParser.parse("#TITLE:t;\n").charts == []
